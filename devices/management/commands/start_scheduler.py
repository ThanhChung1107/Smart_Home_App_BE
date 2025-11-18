from django.core.management.base import BaseCommand
from django.utils import timezone
from devices.models import DeviceSchedule, DeviceLog, Device
import time
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run custom device scheduler with real ESP8266 control'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=30,
            help='Check interval in seconds (default: 30)',
        )
    
    def handle(self, *args, **options):
        interval = options['interval']
        self.stdout.write(
            self.style.SUCCESS(f'🚀 Starting Device Scheduler with ESP8266 Control (checking every {interval}s)...')
        )
        
        try:
            while True:
                self.check_and_execute_schedules()
                self.stdout.write(f'⏰ Next check in {interval} seconds...\n')
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING('\n🛑 Scheduler stopped by user')
            )
    
    def check_and_execute_schedules(self):
        """Kiểm tra và thực thi schedules"""
        now = timezone.now()
        now_local = timezone.localtime(now)
        
        self.stdout.write(
            f'🕐 Current time: {now_local.strftime("%Y-%m-%d %H:%M:%S %z")}'
        )
        
        # Tìm schedules active, chưa executed
        pending_schedules = DeviceSchedule.objects.filter(
            is_active=True,
            is_executed=False
        ).select_related('device', 'user')
        
        if not pending_schedules.exists():
            self.stdout.write('⏰ No pending schedules found')
            return
        
        schedules_to_execute = []
        
        for schedule in pending_schedules:
            if schedule.scheduled_date:
                scheduled_naive = datetime.combine(
                    schedule.scheduled_date, 
                    schedule.scheduled_time
                )
            else:
                scheduled_naive = datetime.combine(
                    now_local.date(), 
                    schedule.scheduled_time
                )
            
            scheduled_aware = timezone.make_aware(scheduled_naive)
            scheduled_local = timezone.localtime(scheduled_aware)
            
            self.stdout.write(
                f'📅 {schedule.device.name} ({schedule.device.device_type.upper()})'
            )
            self.stdout.write(
                f'   ⏰ Scheduled: {scheduled_local.strftime("%Y-%m-%d %H:%M:%S %z")}'
            )
            self.stdout.write(
                f'   🕐 Current:   {now_local.strftime("%Y-%m-%d %H:%M:%S %z")}'
            )
            
            time_diff = (now - scheduled_aware).total_seconds()
            
            if time_diff >= 0:
                if time_diff > 300:  # Quá 5 phút
                    self.stdout.write(
                        self.style.WARNING(
                            f'   ⚠️  Too late (delayed {time_diff/60:.1f} minutes) - Skipping'
                        )
                    )
                    schedule.is_executed = True
                    schedule.save()
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f'   ✅ Ready to execute (delay: {time_diff:.0f}s)')
                    )
                    schedules_to_execute.append(schedule)
            else:
                minutes_left = abs(time_diff) / 60
                self.stdout.write(
                    f'   ⏳ Not yet (in {minutes_left:.1f} minutes)'
                )
        
        if schedules_to_execute:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n📋 Executing {len(schedules_to_execute)} schedule(s)...\n'
                )
            )
            
            for schedule in schedules_to_execute:
                self.execute_schedule(schedule)
        else:
            self.stdout.write('⏰ No schedules ready for execution')
    
    def execute_schedule(self, schedule):
        """Thực thi schedule - GỬI LỆNH ĐẾN ESP8266"""
        try:
            device = schedule.device
            old_state = device.is_on
            
            self.stdout.write(f'⚡ Executing: {device.name} -> {schedule.action}')
            
            # ✅ BƯỚC 1: GỬI LỆNH ĐẾN ESP8266 TRƯỚC
            esp_success = self._send_to_esp8266(device, schedule.action)
            
            if not esp_success:
                self.stdout.write(
                    self.style.ERROR(f'❌ Failed to send command to ESP8266')
                )
                # Có thể chọn: return để không cập nhật DB, hoặc vẫn cập nhật
                # return  # Uncomment nếu muốn bỏ qua khi ESP8266 lỗi
            
            # ✅ BƯỚC 2: Cập nhật database
            if schedule.action == 'on':
                device.is_on = True
                action_text = "BẬT"
            elif schedule.action == 'off':
                device.is_on = False
                action_text = "TẮT"
            else:
                self.stdout.write(
                    self.style.ERROR(f'❌ Unknown action: {schedule.action}')
                )
                return
            
            # Cập nhật device status
            if not device.status:
                device.status = {}
            
            device.status['last_scheduled_action'] = schedule.action
            device.status['last_scheduled_time'] = timezone.now().isoformat()
            device.save()
            
            # ✅ BƯỚC 3: Đánh dấu schedule đã executed
            schedule.is_executed = True
            schedule.executed_at = timezone.now()
            schedule.save()
            
            # ✅ BƯỚC 4: Ghi log
            try:
                DeviceLog.objects.create(
                    device=device,
                    action=f'scheduled_{schedule.action}',
                    old_status={'is_on': old_state},
                    new_status={'is_on': device.is_on},
                    user=schedule.user if schedule.user else None
                )
            except Exception as log_error:
                self.stdout.write(
                    self.style.WARNING(f'⚠️ Log error: {log_error}')
                )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ {action_text} {device.name} ({device.device_type.upper()}) | '
                    f'ESP8266: {"✅" if esp_success else "❌"} | '
                    f'DB: {old_state} → {device.is_on}'
                )
            )
            
            # ✅ BƯỚC 5: Gửi realtime update
            self.send_realtime_update(device)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Lỗi thực thi schedule {schedule.id}: {e}')
            )
            logger.error(f'Schedule execution error: {e}', exc_info=True)
            
            try:
                schedule.is_executed = True
                schedule.save()
            except:
                pass
    
    def _send_to_esp8266(self, device, action):
        """
        🔥 QUAN TRỌNG: Gửi lệnh điều khiển đến ESP8266
        """
        try:
            if not device.ip_address:
                self.stdout.write(
                    self.style.WARNING(f'⚠️ Device {device.name} không có IP address')
                )
                return False
            
            self.stdout.write(f'📡 Sending to ESP8266: {device.ip_address}')
            
            # Mapping device types
            device_type = device.device_type.lower()
            
            if device_type in ['light', 'led']:
                return self._control_light(device, action)
            elif device_type == 'fan':
                return self._control_fan(device, action)
            elif device_type == 'door':
                return self._control_door(device, action)
            elif device_type == 'dryer':
                return self._control_dryer(device, action)
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠️ Device type {device_type} chưa hỗ trợ')
                )
                return True  # Vẫn cho phép cập nhật DB
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ ESP8266 error: {e}')
            )
            return False
    
    def _control_light(self, device, action):
        """Điều khiển đèn LED"""
        try:
            # Xác định LED number
            led_number = self._get_led_number(device)
            
            # Xác định state
            state = '1' if action == 'on' else '0'
            
            url = f"http://{device.ip_address}/led{led_number}?state={state}"
            self.stdout.write(f'   🔗 LED URL: {url}')
            
            response = requests.get(url, timeout=5)
            success = response.status_code == 200
            
            self.stdout.write(
                self.style.SUCCESS(f'   ✅ LED response: {response.status_code}')
                if success else
                self.style.ERROR(f'   ❌ LED failed: {response.status_code}')
            )
            
            return success
            
        except requests.exceptions.Timeout:
            self.stdout.write(self.style.ERROR('   ❌ LED timeout'))
            return False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ LED error: {e}'))
            return False
    
    def _control_fan(self, device, action):
        """Điều khiển quạt"""
        try:
            speed = '3' if action == 'on' else '0'
            
            url = f"http://{device.ip_address}/fan?speed={speed}"
            self.stdout.write(f'   🔗 FAN URL: {url}')
            
            response = requests.get(url, timeout=5)
            success = response.status_code == 200
            
            self.stdout.write(
                self.style.SUCCESS(f'   ✅ FAN response: {response.status_code}')
                if success else
                self.style.ERROR(f'   ❌ FAN failed: {response.status_code}')
            )
            
            return success
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ FAN error: {e}'))
            return False
    
    def _control_door(self, device, action):
        """Điều khiển cửa"""
        try:
            door_action = 'open' if action == 'on' else 'close'
            
            url = f"http://{device.ip_address}/door?action={door_action}"
            self.stdout.write(f'   🔗 DOOR URL: {url}')
            
            response = requests.get(url, timeout=5)
            success = response.status_code == 200
            
            self.stdout.write(
                self.style.SUCCESS(f'   ✅ DOOR response: {response.status_code}')
                if success else
                self.style.ERROR(f'   ❌ DOOR failed: {response.status_code}')
            )
            
            return success
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ DOOR error: {e}'))
            return False
    
    def _control_dryer(self, device, action):
        """Điều khiển máy sấy"""
        try:
            dryer_action = 'out' if action == 'on' else 'in'
            
            url = f"http://{device.ip_address}/dry?action={dryer_action}"
            self.stdout.write(f'   🔗 DRYER URL: {url}')
            
            response = requests.get(url, timeout=5)
            success = response.status_code == 200
            
            self.stdout.write(
                self.style.SUCCESS(f'   ✅ DRYER response: {response.status_code}')
                if success else
                self.style.ERROR(f'   ❌ DRYER failed: {response.status_code}')
            )
            
            return success
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ DRYER error: {e}'))
            return False
    
    def _get_led_number(self, device):
        """Xác định LED number từ device name"""
        name = device.name.lower()
        if '2' in name or 'ngủ' in name or 'ngu' in name:
            return '2'
        return '1'
    
    def send_realtime_update(self, device):
        """Gửi realtime update qua WebSocket"""
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    'device_updates',
                    {
                        'type': 'device_update',
                        'device': {
                            'id': str(device.id),
                            'name': device.name,
                            'is_on': device.is_on,
                            'device_type': device.device_type,
                            'status': device.status,
                            'updated_at': device.updated_at.isoformat() if device.updated_at else None,
                        }
                    }
                )
                self.stdout.write('   📡 Đã gửi realtime update')
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'   ⚠️ Không gửi được realtime update: {e}')
            )