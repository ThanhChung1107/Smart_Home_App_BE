from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
import json
from .models import Device, DeviceLog

@method_decorator(csrf_exempt, name='dispatch')
class DeviceListView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        devices = Device.objects.all()
        devices_data = []
        
        for device in devices:
            devices_data.append({
                'id': str(device.id),
                'name': device.name,
                'device_type': device.device_type,
                'room': device.room,
                'is_on': device.is_on,
                'status': device.status,
                'ip_address': device.ip_address,
                'created_at': device.created_at.isoformat(),
            })
        
        return JsonResponse({
            'success': True,
            'devices': devices_data
        })

@method_decorator(csrf_exempt, name='dispatch')
class DeviceControlView(View):
    def post(self, request, device_id):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        try:
            data = json.loads(request.body)
            action = data.get('action')  # 'toggle', 'on', 'off'
            
            device = Device.objects.get(id=device_id)
            old_status = device.status.copy()
            old_is_on = device.is_on
            
            if action == 'toggle':
                device.is_on = not device.is_on
            elif action == 'on':
                device.is_on = True
            elif action == 'off':
                device.is_on = False
            
            # Cập nhật status dựa trên device type
            if device.device_type == 'light':
                device.status = {
                    'brightness': data.get('brightness', device.status.get('brightness', 100)),
                    'color': data.get('color', device.status.get('color', '#ffffff'))
                }
            elif device.device_type == 'fan':
                device.status = {
                    'speed': data.get('speed', device.status.get('speed', 3)),
                    'mode': data.get('mode', device.status.get('mode', 'normal'))
                }
            elif device.device_type == 'ac':
                device.status = {
                    'temperature': data.get('temperature', device.status.get('temperature', 25)),
                    'mode': data.get('mode', device.status.get('mode', 'cool'))
                }
            
            device.save()
            
            # Ghi log
            DeviceLog.objects.create(
                device=device,
                action=action,
                old_status={'is_on': old_is_on, **old_status},
                new_status={'is_on': device.is_on, **device.status},
                user=request.user
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Đã { "bật" if device.is_on else "tắt" } {device.name}',
                'device': {
                    'id': str(device.id),
                    'name': device.name,
                    'is_on': device.is_on,
                    'status': device.status
                }
            })
            
        except Device.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Thiết bị không tồn tại'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Lỗi: {str(e)}'}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class DeviceLogsView(View):
    def get(self, request, device_id):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        try:
            device = Device.objects.get(id=device_id)
            logs = device.logs.all()[:50]  # Lấy 50 log gần nhất
            
            logs_data = []
            for log in logs:
                logs_data.append({
                    'id': str(log.id),
                    'action': log.action,
                    'old_status': log.old_status,
                    'new_status': log.new_status,
                    'user': log.user.username,
                    'created_at': log.created_at.isoformat(),
                })
            
            return JsonResponse({
                'success': True,
                'logs': logs_data
            })
            
        except Device.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Thiết bị không tồn tại'}, status=404)