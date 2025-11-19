# devices/management/commands/sync_device_status.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from devices.models import Device, DeviceLog
import requests
import json
import time
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sync device status from ESP8266 hardware'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Polling interval in seconds (default: 5)',
        )
    
    def handle(self, *args, **options):
        interval = options['interval']
        self.stdout.write(
            self.style.SUCCESS(f'🔄 Starting Device Status Sync (polling every {interval}s)...')
        )
        
        try:
            while True:
                self.sync_all_devices()
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING('\n🛑 Status sync stopped by user')
            )
    
    def sync_all_devices(self):
        """Đồng bộ trạng thái - DÙNG SQL TRỰC TIẾP HOÀN TOÀN"""
        
        from django.db import connection
        
        self.stdout.write("🔄 Starting sync with SQL direct query...")
        
        # Lấy devices có IP bằng SQL trực tiếp
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, name, device_type, ip_address, is_on, status 
                FROM devices 
                WHERE ip_address IS NOT NULL AND ip_address != ''
            """)
            devices_data = cursor.fetchall()
        
        self.stdout.write(f"🔍 SQL found {len(devices_data)} devices with IP")
        
        if not devices_data:
            self.stdout.write('⚠️ No devices with IP found')
            return
        
        # Tạo device objects từ SQL data
        devices = []
        for device_data in devices_data:
            device_id, name, device_type, ip, is_on, status = device_data
            
            # Tạo device instance
            device = Device(
                id=device_id,
                name=name,
                device_type=device_type,
                ip_address=ip,
                is_on=is_on,
                status=status
            )
            devices.append(device)
            self.stdout.write(f"📋 {name} -> {ip}")
        
        # Group by IP
        devices_by_ip = {}
        for device in devices:
            clean_ip = str(device.ip_address).strip()
            if clean_ip not in devices_by_ip:
                devices_by_ip[clean_ip] = []
            devices_by_ip[clean_ip].append(device)
        
        # Sync từng IP
        for ip, device_list in devices_by_ip.items():
            self.stdout.write(f'🔄 Syncing {len(device_list)} devices from {ip}')
            self.sync_esp8266(ip, device_list)

    def sync_esp8266(self, ip, devices):
        """Đồng bộ trạng thái từ ESP8266 qua endpoint /api/status"""
        try:
            # Gọi API status của ESP8266
            url = f"http://{ip}/api/status"
            response = requests.get(url, timeout=3)
            
            if response.status_code != 200:
                self.stdout.write(
                    self.style.WARNING(f'⚠️ ESP8266 {ip}: HTTP {response.status_code}')
                )
                return
            
            # Parse JSON response
            esp_status = response.json()
            self.stdout.write(f'📡 ESP8266 {ip}: {esp_status}')
            
            # Cập nhật từng device
            changes_count = 0
            for device in devices:
                if self.update_device_status(device, esp_status):
                    changes_count += 1
            
            if changes_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Updated {changes_count} device(s) from {ip}')
                )
            else:
                self.stdout.write(f'ℹ️ No changes from {ip}')
                
        except requests.exceptions.Timeout:
            self.stdout.write(
                self.style.WARNING(f'⏱️ ESP8266 {ip}: Timeout')
            )
        except requests.exceptions.ConnectionError:
            self.stdout.write(
                self.style.WARNING(f'❌ ESP8266 {ip}: Connection failed')
            )
        except json.JSONDecodeError:
            self.stdout.write(
                self.style.ERROR(f'❌ ESP8266 {ip}: Invalid JSON response')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ ESP8266 {ip}: {e}')
            )

    def update_device_status(self, device, esp_status):
        """
        Cập nhật trạng thái 1 device dựa trên ESP status
        Returns: True nếu có thay đổi, False nếu không
        """
        # Lấy device thực từ database
        real_device = Device.objects.get(id=device.id)
        
        # Xử lý status field (có thể là string hoặc dict)
        old_status = self._parse_status_field(real_device.status)
        old_is_on = real_device.is_on
        
        new_is_on = None
        
        # Map device type với key trong ESP status
        device_type = real_device.device_type.lower()
        
        if device_type in ['light', 'led']:
            led_num = self._get_led_number(real_device)
            key = f"LED{led_num}"
            if key in esp_status:
                new_is_on = bool(esp_status[key])
        
        elif device_type == 'fan':
            if 'FAN' in esp_status:
                new_is_on = esp_status['FAN'] > 0
        
        elif device_type == 'door':
            if 'DOOR' in esp_status:
                new_is_on = bool(esp_status['DOOR'])
        
        elif device_type in ['dryer', 'dry', 'ac']:
            if 'DRY' in esp_status:
                new_is_on = esp_status['DRY'] > 40
        
        # Nếu không xác định được hoặc không thay đổi
        if new_is_on is None or new_is_on == old_is_on:
            return False
        
        # CÓ THAY ĐỔI - Cập nhật database
        self.stdout.write(
            self.style.WARNING(
                f'🔄 {real_device.name}: {old_is_on} → {new_is_on}'
            )
        )
        
        real_device.is_on = new_is_on
        
        # Cập nhật status chi tiết
        device_status = old_status.copy()  # Đã được parse thành dict
        
        if device_type in ['light', 'led']:
            led_num = self._get_led_number(real_device)
            key = f"LED{led_num}"
            device_status['state'] = 'on' if new_is_on else 'off'
            device_status['value'] = esp_status.get(key, 0)
        
        elif device_type == 'fan':
            device_status['speed'] = esp_status.get('FAN', 0)
            device_status['state'] = 'on' if new_is_on else 'off'
        
        elif device_type == 'door':
            device_status['state'] = 'open' if new_is_on else 'closed'
            device_status['value'] = esp_status.get('DOOR', False)
        
        elif device_type in ['dryer', 'dry', 'ac']:
            device_status['position'] = esp_status.get('DRY', 0)
            device_status['state'] = 'out' if new_is_on else 'in'
        
        # Cập nhật sensor data nếu có
        if 'TEMP' in esp_status or 'HUM' in esp_status:
            device_status['temperature'] = esp_status.get('TEMP')
            device_status['humidity'] = esp_status.get('HUM')
            device_status['last_updated'] = timezone.now().isoformat()
        
        real_device.status = device_status
        real_device.save()
        
        # 🔥 ĐÃ BỎ GHI LOG Ở ĐÂY
        
        # Gửi realtime update
        self.send_realtime_update(real_device)
        
        return True

    def _parse_status_field(self, status_field):
        """Parse status field từ string JSON thành dictionary"""
        if status_field is None:
            return {}
        
        if isinstance(status_field, dict):
            return status_field
        
        if isinstance(status_field, str):
            try:
                # Thử parse JSON string
                return json.loads(status_field)
            except (json.JSONDecodeError, TypeError):
                # Nếu không phải JSON, trả về dict rỗng
                return {}
        
        return {}

    
    def _get_led_number(self, device):
        """Xác định LED number từ device name"""
        name = device.name.lower()
        if '2' in name or 'ngủ' in name or 'ngu' in name:
            return '2'
        return '1'
    
    def _update_statistics(self, device, new_is_on, old_is_on):
        """Cập nhật thống kê khi có thay đổi trạng thái"""
        from devices.models import DeviceStatistics, DeviceUsageSession
        
        today = timezone.localtime(timezone.now()).date()
        
        # Bật thiết bị
        if new_is_on and not old_is_on:
            # Tạo session mới
            DeviceUsageSession.objects.create(
                device=device,
                start_time=timezone.now()
            )
            
            # Cập nhật số lần bật
            stats, created = DeviceStatistics.objects.get_or_create(
                device=device,
                date=today,
                defaults={
                    'turn_on_count': 1,
                    'total_usage_minutes': 0,
                    'power_consumption': 0.0,
                    'cost': 0.0
                }
            )
            if not created:
                stats.turn_on_count += 1
                stats.save()
        
        # Tắt thiết bị
        elif not new_is_on and old_is_on:
            # Kết thúc session
            active_session = DeviceUsageSession.objects.filter(
                device=device,
                end_time__isnull=True
            ).order_by('-start_time').first()
            
            if active_session:
                active_session.end_time = timezone.now()
                duration = (active_session.end_time - active_session.start_time).total_seconds() / 60
                active_session.duration_minutes = int(duration)
                active_session.save()
                
                # Cập nhật thống kê
                if active_session.duration_minutes > 0:
                    power_rates = {
                        'light': 0.01, 'led': 0.01, 'fan': 0.05,
                        'ac': 0.8, 'dryer': 0.1, 'door': 0.005
                    }
                    
                    stats, _ = DeviceStatistics.objects.get_or_create(
                        device=device,
                        date=today,
                        defaults={
                            'turn_on_count': 0,
                            'total_usage_minutes': 0,
                            'power_consumption': 0.0,
                            'cost': 0.0
                        }
                    )
                    
                    power_rate = power_rates.get(device.device_type.lower(), 0.01)
                    hours_used = active_session.duration_minutes / 60
                    stats.total_usage_minutes += active_session.duration_minutes
                    stats.power_consumption += power_rate * hours_used
                    stats.cost += stats.power_consumption * 3000
                    stats.save()
    
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
                            'updated_at': timezone.now().isoformat(),
                        }
                    }
                )
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'⚠️ WebSocket update failed: {e}')
            )