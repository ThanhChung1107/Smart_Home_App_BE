# schedules/views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.db.models import Q
import json
from datetime import datetime, time
from devices.models import Device
from .models import Schedule

@method_decorator(csrf_exempt, name='dispatch')
class ScheduleListView(View):
    """Lấy danh sách lịch trình hoặc tạo lịch trình mới"""
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        try:
            # Lấy tất cả schedules của user
            schedules = Schedule.objects.filter(user=request.user)
            
            schedules_data = []
            for schedule in schedules:
                schedules_data.append({
                    'id': str(schedule.id),
                    'name': schedule.name,
                    'device_id': str(schedule.device.id),
                    'device_name': schedule.device.name,
                    'action': schedule.action,
                    'scheduled_time': schedule.scheduled_time.strftime('%H:%M'),
                    'repeat_days': schedule.repeat_days,
                    'is_active': schedule.is_active,
                    'created_at': schedule.created_at.isoformat(),
                })
            
            return JsonResponse({
                'success': True,
                'schedules': schedules_data,
                'count': len(schedules_data)
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    def post(self, request):
        """Tạo lịch trình mới"""
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        try:
            data = json.loads(request.body)
            
            # Validate dữ liệu
            device_id = data.get('device_id')
            action = data.get('action')
            scheduled_time_str = data.get('scheduled_time')  # "HH:MM"
            repeat_days = data.get('repeat_days', [])
            
            if not all([device_id, action, scheduled_time_str]):
                return JsonResponse({
                    'success': False,
                    'message': 'Thiếu thông tin bắt buộc'
                }, status=400)
            
            # Kiểm tra device tồn tại
            try:
                device = Device.objects.get(id=device_id)
            except Device.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Thiết bị không tồn tại'
                }, status=404)
            
            # Parse time
            try:
                hour, minute = map(int, scheduled_time_str.split(':'))
                scheduled_time = time(hour, minute)
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'message': 'Định dạng thời gian không hợp lệ (HH:MM)'
                }, status=400)
            
            # Kiểm tra action hợp lệ
            valid_actions = ['on', 'off', 'toggle']
            if action not in valid_actions:
                return JsonResponse({
                    'success': False,
                    'message': f'Hành động không hợp lệ. Phải là: {valid_actions}'
                }, status=400)
            
            # Tạo schedule
            schedule = Schedule.objects.create(
                device=device,
                action=action,
                scheduled_time=scheduled_time,
                repeat_days=repeat_days if repeat_days else [],
                user=request.user
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Đã tạo lịch trình mới',
                'schedule': {
                    'id': str(schedule.id),
                    'name': schedule.name,
                    'device_id': str(schedule.device.id),
                    'device_name': schedule.device.name,
                    'action': schedule.action,
                    'scheduled_time': schedule.scheduled_time.strftime('%H:%M'),
                    'repeat_days': schedule.repeat_days,
                    'is_active': schedule.is_active,
                }
            }, status=201)
        
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'JSON không hợp lệ'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class ScheduleDetailView(View):
    """Cập nhật, xóa lịch trình"""
    def put(self, request, schedule_id):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        try:
            schedule = Schedule.objects.get(id=schedule_id, user=request.user)
            data = json.loads(request.body)
            
            # Cập nhật các field
            if 'action' in data:
                if data['action'] not in ['on', 'off', 'toggle']:
                    return JsonResponse({'success': False, 'message': 'Hành động không hợp lệ'})
                schedule.action = data['action']
            
            if 'scheduled_time' in data:
                try:
                    hour, minute = map(int, data['scheduled_time'].split(':'))
                    schedule.scheduled_time = time(hour, minute)
                except ValueError:
                    return JsonResponse({
                        'success': False,
                        'message': 'Định dạng thời gian không hợp lệ'
                    })
            
            if 'repeat_days' in data:
                schedule.repeat_days = data['repeat_days']
            
            if 'device_id' in data:
                try:
                    device = Device.objects.get(id=data['device_id'])
                    schedule.device = device
                except Device.DoesNotExist:
                    return JsonResponse({'success': False, 'message': 'Thiết bị không tồn tại'})
            
            schedule.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Đã cập nhật lịch trình',
                'schedule': {
                    'id': str(schedule.id),
                    'name': schedule.name,
                    'device_id': str(schedule.device.id),
                    'device_name': schedule.device.name,
                    'action': schedule.action,
                    'scheduled_time': schedule.scheduled_time.strftime('%H:%M'),
                    'repeat_days': schedule.repeat_days,
                    'is_active': schedule.is_active,
                }
            })
        
        except Schedule.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Lịch trình không tồn tại'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    def delete(self, request, schedule_id):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        try:
            schedule = Schedule.objects.get(id=schedule_id, user=request.user)
            device_name = schedule.device.name
            schedule.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Đã xóa lịch trình {device_name}'
            })
        
        except Schedule.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Lịch trình không tồn tại'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

@method_decorator(csrf_exempt, name='dispatch')
class ScheduleToggleView(View):
    """Bật/tắt lịch trình"""
    def post(self, request, schedule_id):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        try:
            schedule = Schedule.objects.get(id=schedule_id, user=request.user)
            data = json.loads(request.body) if request.body else {}
            
            # Toggle hoặc set trạng thái cụ thể
            if 'is_active' in data:
                schedule.is_active = data['is_active']
            else:
                schedule.is_active = not schedule.is_active
            
            schedule.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Lịch trình {"được bật" if schedule.is_active else "bị tắt"}',
                'is_active': schedule.is_active
            })
        
        except Schedule.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Lịch trình không tồn tại'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

@method_decorator(csrf_exempt, name='dispatch')
class ScheduleDevicesView(View):
    """Lấy danh sách devices để tạo schedule"""
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        try:
            devices = Device.objects.all()
            
            devices_data = []
            for device in devices:
                devices_data.append({
                    'id': str(device.id),
                    'name': device.name,
                    'device_type': device.device_type,
                    'room': device.room,
                })
            
            return JsonResponse({
                'success': True,
                'devices': devices_data
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})