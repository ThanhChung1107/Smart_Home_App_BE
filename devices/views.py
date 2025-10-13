from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
import json
from django.db.models import Sum
from .models import Device, DeviceLog, DeviceStatistics, DeviceUsageSession 

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


from django.utils import timezone
from datetime import timedelta, datetime
import json

@method_decorator(csrf_exempt, name='dispatch')
class RealStatisticsView(View):
    def get(self, request):
        """API lấy thống kê thực tế"""
        try:
            period = request.GET.get('period', 'today')
            
            # Xác định khoảng thời gian
            if period == 'today':
                start_date = timezone.now().date()
                end_date = start_date
            elif period == 'week':
                start_date = timezone.now().date() - timedelta(days=7)
                end_date = timezone.now().date()
            elif period == 'month':
                start_date = timezone.now().date() - timedelta(days=30)
                end_date = timezone.now().date()
            else:
                start_date = timezone.now().date()
                end_date = start_date

            devices = Device.objects.all()
            statistics = []

            for device in devices:
                # Lấy thống kê từ database
                device_stats = DeviceStatistics.objects.filter(
                    device=device,
                    date__range=[start_date, end_date]
                ).aggregate(
                    total_turn_on=Sum('turn_on_count'),
                    total_minutes=Sum('total_usage_minutes'),
                    total_power=Sum('power_consumption'),
                    total_cost=Sum('cost')
                )

                # Lấy sessions sử dụng gần đây
                recent_sessions = DeviceUsageSession.objects.filter(
                    device=device,
                    start_time__date=timezone.now().date()
                ).order_by('-start_time')[:5]

                usage_data = []
                for session in recent_sessions:
                    if session.end_time:
                        duration_hours = session.duration_minutes / 60.0
                        usage_data.append({
                            'time': session.start_time.strftime('%H:%M'),
                            'duration': round(duration_hours, 1)
                        })

                # Tính toán dữ liệu
                total_hours = (device_stats['total_minutes'] or 0) / 60.0
                power_consumption = device_stats['total_power'] or 0.0
                cost = device_stats['total_cost'] or 0.0
                turn_on_count = device_stats['total_turn_on'] or 0

                statistics.append({
                    'device_id': str(device.id),
                    'device_name': device.name,
                    'device_type': device.device_type,
                    'turn_on_count': turn_on_count,
                    'total_usage_hours': round(total_hours, 1),
                    'power_consumption': round(power_consumption, 2),
                    'cost': round(cost),
                    'usage_data': usage_data,
                })

            return JsonResponse({
                'success': True,
                'statistics': statistics,
                'period': period,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            })

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
# Thêm vào views.py
from django.db.models import Sum, Avg, Count
from datetime import datetime, timedelta

@method_decorator(csrf_exempt, name='dispatch')
class DeviceStatisticsView(View):
    """API lấy thống kê chi tiết theo thiết bị"""
    def get(self, request, device_id):
        try:
            period = request.GET.get('period', 'today')  # today, week, month, year
            device = Device.objects.get(id=device_id)
            
            # Xác định khoảng thời gian
            end_date = timezone.now().date()
            if period == 'today':
                start_date = end_date
            elif period == 'week':
                start_date = end_date - timedelta(days=7)
            elif period == 'month':
                start_date = end_date - timedelta(days=30)
            elif period == 'year':
                start_date = end_date - timedelta(days=365)
            else:
                start_date = end_date

            # Lấy thống kê tổng hợp
            stats = DeviceStatistics.objects.filter(
                device=device,
                date__range=[start_date, end_date]
            ).aggregate(
                total_turn_on=Sum('turn_on_count'),
                total_usage_minutes=Sum('total_usage_minutes'),
                total_power=Sum('power_consumption'),
                total_cost=Sum('cost'),
                avg_daily_usage=Avg('total_usage_minutes'),
                avg_daily_cost=Avg('cost')
            )

            # Lấy thống kê theo ngày (cho biểu đồ)
            daily_stats = DeviceStatistics.objects.filter(
                device=device,
                date__range=[start_date, end_date]
            ).order_by('date')

            daily_data = []
            for day_stat in daily_stats:
                daily_data.append({
                    'date': day_stat.date.isoformat(),
                    'usage_hours': round(day_stat.total_usage_minutes / 60, 1),
                    'cost': round(day_stat.cost),
                    'turn_on_count': day_stat.turn_on_count,
                })

            # Thống kê sessions gần đây
            recent_sessions = DeviceUsageSession.objects.filter(
                device=device,
                start_time__date__range=[start_date, end_date]
            ).order_by('-start_time')[:10]

            sessions_data = []
            for session in recent_sessions:
                sessions_data.append({
                    'start_time': session.start_time.isoformat(),
                    'end_time': session.end_time.isoformat() if session.end_time else None,
                    'duration_minutes': session.duration_minutes,
                    'duration_hours': round(session.duration_minutes / 60, 1),
                })

            return JsonResponse({
                'success': True,
                'device': {
                    'id': str(device.id),
                    'name': device.name,
                    'type': device.device_type,
                    'room': device.room,
                },
                'period': period,
                'summary': {
                    'total_turn_on': stats['total_turn_on'] or 0,
                    'total_usage_hours': round((stats['total_usage_minutes'] or 0) / 60, 1),
                    'total_power_consumption': round(stats['total_power'] or 0, 2),
                    'total_cost': round(stats['total_cost'] or 0),
                    'avg_daily_usage_hours': round((stats['avg_daily_usage'] or 0) / 60, 1),
                    'avg_daily_cost': round(stats['avg_daily_cost'] or 0),
                },
                'daily_data': daily_data,
                'recent_sessions': sessions_data,
                'power_rate': _get_power_rate(device.device_type),  # kW
                'electricity_price': 2500,  # VND/kWh
            })

        except Device.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Thiết bị không tồn tại'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

@method_decorator(csrf_exempt, name='dispatch')
class OverallStatisticsView(View):
    """API thống kê tổng quan toàn hệ thống"""
    def get(self, request):
        try:
            period = request.GET.get('period', 'today')
            
            # Xác định khoảng thời gian
            end_date = timezone.now().date()
            if period == 'today':
                start_date = end_date
            elif period == 'week':
                start_date = end_date - timedelta(days=7)
            elif period == 'month':
                start_date = end_date - timedelta(days=30)
            else:
                start_date = end_date

            # Thống kê tổng hợp
            overall_stats = DeviceStatistics.objects.filter(
                date__range=[start_date, end_date]
            ).aggregate(
                total_turn_on=Sum('turn_on_count'),
                total_usage_minutes=Sum('total_usage_minutes'),
                total_power=Sum('power_consumption'),
                total_cost=Sum('cost'),
                device_count=Count('device', distinct=True)
            )

            # Thống kê theo loại thiết bị
            stats_by_type = DeviceStatistics.objects.filter(
                date__range=[start_date, end_date]
            ).values('device__device_type').annotate(
                total_usage=Sum('total_usage_minutes'),
                total_cost=Sum('cost'),
                total_turn_on=Sum('turn_on_count'),
                device_count=Count('device', distinct=True)
            )

            device_type_stats = []
            for stat in stats_by_type:
                device_type_stats.append({
                    'type': stat['device__device_type'],
                    'type_name': dict(Device.DEVICE_TYPES).get(stat['device__device_type'], 'Khác'),
                    'total_usage_hours': round(stat['total_usage'] / 60, 1),
                    'total_cost': round(stat['total_cost']),
                    'total_turn_on': stat['total_turn_on'],
                    'device_count': stat['device_count'],
                })

            # Thống kê theo phòng
            stats_by_room = DeviceStatistics.objects.filter(
                date__range=[start_date, end_date]
            ).values('device__room').annotate(
                total_usage=Sum('total_usage_minutes'),
                total_cost=Sum('cost'),
                device_count=Count('device', distinct=True)
            )

            room_stats = []
            for stat in stats_by_room:
                room_stats.append({
                    'room': stat['device__room'],
                    'room_name': dict(Device.ROOM_CHOICES).get(stat['device__room'], 'Khác'),
                    'total_usage_hours': round(stat['total_usage'] / 60, 1),
                    'total_cost': round(stat['total_cost']),
                    'device_count': stat['device_count'],
                })

            # Thiết bị sử dụng nhiều nhất
            top_devices = DeviceStatistics.objects.filter(
                date__range=[start_date, end_date]
            ).values('device__id', 'device__name', 'device__device_type').annotate(
                total_usage=Sum('total_usage_minutes'),
                total_cost=Sum('cost')
            ).order_by('-total_usage')[:5]

            top_usage_devices = []
            for device in top_devices:
                top_usage_devices.append({
                    'id': device['device__id'],
                    'name': device['device__name'],
                    'type': device['device__device_type'],
                    'usage_hours': round(device['total_usage'] / 60, 1),
                    'cost': round(device['total_cost']),
                })

            return JsonResponse({
                'success': True,
                'period': period,
                'overall_summary': {
                    'total_devices': overall_stats['device_count'] or 0,
                    'total_turn_on': overall_stats['total_turn_on'] or 0,
                    'total_usage_hours': round((overall_stats['total_usage_minutes'] or 0) / 60, 1),
                    'total_power_consumption': round(overall_stats['total_power'] or 0, 2),
                    'total_cost': round(overall_stats['total_cost'] or 0),
                    'avg_daily_cost': round((overall_stats['total_cost'] or 0) / max((end_date - start_date).days, 1)),
                },
                'by_device_type': device_type_stats,
                'by_room': room_stats,
                'top_usage_devices': top_usage_devices,
            })

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

@method_decorator(csrf_exempt, name='dispatch')
class RealTimeUsageView(View):
    """API theo dõi sử dụng real-time"""
    def get(self, request):
        try:
            # Thiết bị đang bật
            active_devices = Device.objects.filter(is_on=True)
            
            active_devices_data = []
            total_active_power = 0.0
            
            for device in active_devices:
                # Tìm session đang chạy
                active_session = DeviceUsageSession.objects.filter(
                    device=device,
                    end_time__isnull=True
                ).first()
                
                if active_session:
                    usage_duration = timezone.now() - active_session.start_time
                    usage_minutes = int(usage_duration.total_seconds() / 60)
                    power_rate = _get_power_rate(device.device_type)
                    estimated_cost = (power_rate * (usage_minutes / 60)) * 2500
                    
                    active_devices_data.append({
                        'device_id': str(device.id),
                        'device_name': device.name,
                        'device_type': device.device_type,
                        'start_time': active_session.start_time.isoformat(),
                        'usage_minutes': usage_minutes,
                        'usage_hours': round(usage_minutes / 60, 2),
                        'power_consumption': round(power_rate * (usage_minutes / 60), 3),
                        'estimated_cost': round(estimated_cost),
                    })
                    
                    total_active_power += power_rate

            # Thống kê hôm nay
            today = timezone.now().date()
            today_stats = DeviceStatistics.objects.filter(
                date=today
            ).aggregate(
                total_usage=Sum('total_usage_minutes'),
                total_cost=Sum('cost'),
                total_turn_on=Sum('turn_on_count')
            )

            return JsonResponse({
                'success': True,
                'active_devices': active_devices_data,
                'active_devices_count': len(active_devices_data),
                'total_active_power': round(total_active_power, 2),
                'today_summary': {
                    'usage_hours': round((today_stats['total_usage'] or 0) / 60, 1),
                    'cost': today_stats['total_cost'] or 0,
                    'turn_on_count': today_stats['total_turn_on'] or 0,
                },
                'timestamp': timezone.now().isoformat(),
            })

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
@method_decorator(csrf_exempt, name='dispatch')
class DeviceUsageStartView(View):
    """Bắt đầu session sử dụng device"""
    def post(self, request, device_id):
        try:
            data = json.loads(request.body)
            device = Device.objects.get(id=device_id)
            
            # Tạo session mới
            session = DeviceUsageSession.objects.create(
                device=device,
                start_time=timezone.now()
            )
            
            # Cập nhật thống kê ngày hiện tại
            today = timezone.now().date()
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
            
            return JsonResponse({
                'success': True,
                'session_id': session.id,
                'message': 'Bắt đầu theo dõi sử dụng'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

@method_decorator(csrf_exempt, name='dispatch')
class DeviceUsageEndView(View):
    """Kết thúc session sử dụng device"""
    def post(self, request, session_id):
        try:
            session = DeviceUsageSession.objects.get(id=session_id)
            session.end_time = timezone.now()
            
            # Tính thời gian sử dụng
            duration = session.end_time - session.start_time
            duration_minutes = int(duration.total_seconds() / 60)
            session.duration_minutes = duration_minutes
            session.save()
            
            # Cập nhật thống kê
            today = timezone.now().date()
            stats, created = DeviceStatistics.objects.get_or_create(
                device=session.device,
                date=today,
                defaults={
                    'turn_on_count': 0,
                    'total_usage_minutes': duration_minutes,
                    'power_consumption': 0.0,
                    'cost': 0.0
                }
            )
            
            if not created:
                stats.total_usage_minutes += duration_minutes
                
                # Tính điện năng tiêu thụ và chi phí
                power_rate = _get_power_rate(session.device.device_type)
                hours_used = duration_minutes / 60.0
                power_consumed = power_rate * hours_used
                cost = power_consumed * 2500  # 2500 VND/kWh
                
                stats.power_consumption += power_consumed
                stats.cost += cost
                stats.save()
            
            return JsonResponse({
                'success': True,
                'duration_minutes': duration_minutes,
                'message': 'Kết thúc session sử dụng'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

def _get_power_rate(device_type):
    """Lấy công suất thiết bị (kW)"""
    power_rates = {
        'light': 0.015,    # 15W = 0.015kW
        'fan': 0.05,       # 50W = 0.05kW
        'ac': 1.2,         # 1200W = 1.2kW
        'socket': 0.1,     # 100W = 0.1kW
        'door': 0.005,     # 5W = 0.005kW
    }
    return power_rates.get(device_type, 0.1)
