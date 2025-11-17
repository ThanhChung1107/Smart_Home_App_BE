from django.core.management.base import BaseCommand
from django.utils import timezone
from devices.models import DeviceSchedule, DeviceLog
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run custom device scheduler without Celery'
    
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
            self.style.SUCCESS(f'🚀 Starting Device Scheduler (checking every {interval}s)...')
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
        
        # ✅ LẤY THỜI GIAN HIỆN TẠI (aware datetime)
        now = timezone.now()
        
        # ✅ Convert sang local timezone để hiển thị
        now_local = timezone.localtime(now)
        
        self.stdout.write(
            f'🕐 Current time: {now_local.strftime("%Y-%m-%d %H:%M:%S %z")}'
        )
        
        # Tìm schedules chưa executed, active
        pending_schedules = DeviceSchedule.objects.filter(
            is_active=True,
            is_executed=False
        ).select_related('device', 'user')
        
        if not pending_schedules.exists():
            self.stdout.write('⏰ No pending schedules found')
            return
        
        schedules_to_execute = []
        
        for schedule in pending_schedules:
            # ✅ TẠO SCHEDULED_DATETIME (naive)
            if schedule.scheduled_date:
                # Có ngày cụ thể
                scheduled_naive = datetime.combine(
                    schedule.scheduled_date, 
                    schedule.scheduled_time
                )
            else:
                # Không có ngày - dùng ngày hôm nay (local date)
                scheduled_naive = datetime.combine(
                    now_local.date(), 
                    schedule.scheduled_time
                )
            
            # ✅ QUAN TRỌNG: Chuyển naive datetime thành aware datetime
            # Assume naive datetime là theo timezone của project (settings.TIME_ZONE)
            scheduled_aware = timezone.make_aware(scheduled_naive)
            
            # Convert sang local để hiển thị
            scheduled_local = timezone.localtime(scheduled_aware)
            
            # DEBUG: In thông tin
            self.stdout.write(
                f'📅 {schedule.device.name} ({schedule.device.device_type.upper()})'
            )
            self.stdout.write(
                f'   ⏰ Scheduled: {scheduled_local.strftime("%Y-%m-%d %H:%M:%S %z")}'
            )
            self.stdout.write(
                f'   🕐 Current:   {now_local.strftime("%Y-%m-%d %H:%M:%S %z")}'
            )
            
            # ✅ So sánh (cả 2 đều là aware datetime)
            time_diff = (now - scheduled_aware).total_seconds()
            
            if time_diff >= 0:  # Đã đến hoặc qua giờ
                if time_diff > 300:  # Quá 5 phút
                    self.stdout.write(
                        self.style.WARNING(
                            f'   ⚠️  Too late (delayed {time_diff/60:.1f} minutes) - Skipping'
                        )
                    )
                    # Đánh dấu executed nhưng không thực thi
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
        """Thực thi một schedule"""
        try:
            device = schedule.device
            old_state = device.is_on
            
            self.stdout.write(f'⚡ Executing: {device.name} -> {schedule.action}')
            
            # Thực hiện hành động
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
            
            # ✅ QUAN TRỌNG: Đánh dấu đã executed
            schedule.is_executed = True
            schedule.executed_at = timezone.now()
            schedule.save()
            
            # Ghi log
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
                    f'Trạng thái: {old_state} → {device.is_on}'
                )
            )
            
            # Gửi realtime update
            self.send_realtime_update(device)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Lỗi thực thi schedule {schedule.id}: {e}')
            )
            logger.error(f'Schedule execution error: {e}', exc_info=True)
            
            # Đánh dấu executed để không retry liên tục
            try:
                schedule.is_executed = True
                schedule.save()
            except:
                pass
    
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
                self.stdout.write('📡 Đã gửi realtime update')
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'⚠️ Không gửi được realtime update: {e}')
            )