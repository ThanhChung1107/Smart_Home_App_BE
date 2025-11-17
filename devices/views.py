from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
import json
from django.db.models import Sum, Avg, Count
from django.utils import timezone
from datetime import timedelta, datetime
from .models import Device, DeviceLog, DeviceStatistics, DeviceUsageSession 

# Helper functions
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

def _update_device_statistics(device, action, old_is_on):
    """Cập nhật thống kê khi thay đổi trạng thái thiếtết bị"""
    print(f"🔧 Updating stats: device={device.name}, action={action}, old_is_on={old_is_on}, new_is_on={not old_is_on if action == 'toggle' else action == 'on'}")
    
    # Tính trạng thái mới thực tế
    if action == 'toggle':
        new_is_on = not old_is_on
    elif action == 'on':
        new_is_on = True
    elif action == 'off':
        new_is_on = False
    else:
        new_is_on = old_is_on

    # Bật thiết bị - TẠO SESSION MỚI
    if new_is_on and not old_is_on:
        print(f"🚀 Starting NEW session for {device.name}")
        # Đảm bảo kết thúc session cũ nếu có (phòng trường hợp)
        old_sessions = DeviceUsageSession.objects.filter(
            device=device, 
            end_time__isnull=True
        )
        if old_sessions.exists():
            print(f"⚠️  Found {old_sessions.count()} old active sessions, ending them")
            for old_session in old_sessions:
                old_session.end_time = timezone.now()
                old_session.duration_minutes = round((session.end_time - session.start_time).total_seconds() / 60)
                old_session.save()
        
        # Tạo session mới
        DeviceUsageSession.objects.create(device=device, start_time=timezone.now())
        
        # Cập nhật số lần bật
        today = timezone.localtime(timezone.now()).date()
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
        print(f"✅ Session started. Turn on count: {stats.turn_on_count}")
    
    # Tắt thiết bị - KẾT THÚC SESSION
    elif not new_is_on and old_is_on:
        print(f"🛑 Ending session for {device.name}")
        # Tìm session đang chạy
        session = DeviceUsageSession.objects.filter(
            device=device, 
            end_time__isnull=True
        ).order_by('-start_time').first()
        
        if session:
            session.end_time = timezone.now()
            duration = session.end_time - session.start_time
            duration_minutes = int(duration.total_seconds() / 60)
            duration_seconds = int(duration.total_seconds())
            session.duration_minutes = duration_minutes
            session.save()

            print(f"⏱️ Session duration: {duration_seconds} seconds ({duration_minutes} minutes)")
            
            # Cập nhật thống kê
            if duration_minutes > 0:
                power_rate = _get_power_rate(device.device_type)
                hours_used = duration_minutes / 60.0
                power_consumed = power_rate * hours_used
                cost = power_consumed * 2500  # 2500 VND/kWh

                today = timezone.localtime(timezone.now()).date()
                stats, created = DeviceStatistics.objects.get_or_create(
                    device=device,
                    date=today,
                    defaults={
                        'turn_on_count': 0,
                        'total_usage_minutes': duration_minutes,
                        'power_consumption': power_consumed,
                        'cost': cost
                    }
                )
                if not created:
                    stats.total_usage_minutes += duration_minutes
                    stats.power_consumption += power_consumed
                    stats.cost += cost
                    stats.save()
                
                print(f"✅ Stats updated: +{duration_minutes}min, total: {stats.total_usage_minutes}min, cost: {cost} VND")
            else:
                print("⏩ Session too short (< 1 min), skipping stats update")
        else:
            print("❌ No active session found to end")
    
    else:
        print(f"ℹ️  No state change needed: {device.name}")

# Views
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
            
            # Cập nhật thống kê TRƯỚC KHI thay đổi trạng thái
            _update_device_statistics(device, action, old_is_on)
            
            # Cập nhật trạng thái thiết bị
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

# XÓA các view trùng lặp: DeviceUsageStartView, DeviceUsageEndView, và function toggle_device
# Vì logic đã được tích hợp vào DeviceControlView thông qua _update_device_statistics

@method_decorator(csrf_exempt, name='dispatch')
class RealStatisticsView(View):
    def get(self, request):
        """API lấy thống kê thực tế"""
        try:
            period = request.GET.get('period', 'today')
            
            # Xác định khoảng thời gian
            if period == 'today':
                start_date = timezone.localtime(timezone.now()).date()
                end_date = start_date
            elif period == 'week':
                start_date = timezone.localtime(timezone.now()).date() - timedelta(days=7)
                end_date = timezone.localtime(timezone.now()).date()
            elif period == 'month':
                start_date = timezone.localtime(timezone.now()).date() - timedelta(days=30)
                end_date = timezone.localtime(timezone.now()).date()
            else:
                start_date = timezone.localtime(timezone.now()).date()
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

@method_decorator(csrf_exempt, name='dispatch')
class DeviceStatisticsView(View):
    """API lấy thống kê chi tiết theo thiết bị"""
    def get(self, request, device_id):
        try:
            period = request.GET.get('period', 'today')
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
                'power_rate': _get_power_rate(device.device_type),
                'electricity_price': 2500,
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
                    now = timezone.now()  # Giữ consistent
                    usage_duration = now - active_session.start_time
                    usage_minutes = round(usage_duration.total_seconds() / 60)
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
class DebugStatsView(View):
    def get(self, request):
        """API debug để kiểm tra chi tiết sessions và statistics"""
        try:
            from django.utils import timezone
            from datetime import datetime, timedelta
            
            debug_data = {}
            
            # 1. Kiểm tra sessions hôm nay
            today = timezone.localtime(timezone.now()).date()
            sessions_today = DeviceUsageSession.objects.filter(
                start_time__date=today
            ).order_by('-start_time')
            
            debug_data['sessions_today'] = []
            for session in sessions_today:
                duration = None
                if session.end_time:
                    duration = int((session.end_time - session.start_time).total_seconds() / 60)  # phút
                
                debug_data['sessions_today'].append({
                    'device': session.device.name,
                    'start_time': session.start_time.strftime('%H:%M:%S'),
                    'end_time': session.end_time.strftime('%H:%M:%S') if session.end_time else 'Đang chạy',
                    'duration_minutes': duration,
                    'duration_minutes_field': session.duration_minutes,
                })
            
            # 2. Kiểm tra statistics hôm nay
            stats_today = DeviceStatistics.objects.filter(date=today)
            
            debug_data['statistics_today'] = []
            for stat in stats_today:
                debug_data['statistics_today'].append({
                    'device': stat.device.name,
                    'turn_on_count': stat.turn_on_count,
                    'total_usage_minutes': stat.total_usage_minutes,
                    'total_usage_hours': round(stat.total_usage_minutes / 60, 2),
                    'power_consumption': stat.power_consumption,
                    'cost': stat.cost,
                })
            
            # 3. Kiểm tra sessions đang chạy
            active_sessions = DeviceUsageSession.objects.filter(end_time__isnull=True)
            
            debug_data['active_sessions'] = []
            for session in active_sessions:
                current_duration = int((timezone.now() - session.start_time).total_seconds() / 60)
                debug_data['active_sessions'].append({
                    'device': session.device.name,
                    'start_time': session.start_time.strftime('%H:%M:%S'),
                    'current_duration_minutes': current_duration,
                })
            
            return JsonResponse({
                'success': True,
                'debug_data': debug_data,
                'timestamp': timezone.now().strftime('%H:%M:%S')
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
        
@method_decorator(csrf_exempt, name='dispatch')
class CleanupSessionsView(View):
    def post(self, request):
        """Dọn dẹp các sessions đang chạy"""
        try:
            active_sessions = DeviceUsageSession.objects.filter(end_time__isnull=True)
            count = active_sessions.count()
            
            for session in active_sessions:
                session.end_time = timezone.now()
                duration = session.end_time - session.start_time
                session.duration_minutes = int(duration.total_seconds() / 60)
                session.save()
                
                print(f"🧹 Cleaned session: {session.device.name}, duration: {session.duration_minutes}min")
            
            return JsonResponse({
                'success': True,
                'message': f'Đã dọn dẹp {count} sessions đang chạy',
                'cleaned_sessions': count
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
        
# devices/views.py
# ... (imports đã có)
from .models import Device, DeviceLog, DeviceStatistics, DeviceUsageSession, DeviceSchedule # Thêm DeviceSchedule
from django.utils import timezone

# ... (Các views DeviceListView, DeviceControlView, v.v. giữ nguyên)

@method_decorator(csrf_exempt, name='dispatch')
class ScheduleListView(View):
    """
    API để LẤY DANH SÁCH và TẠO MỚI lịch hẹn.
    """
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        # Lấy các lịch hẹn chưa thực thi của user
        schedules = DeviceSchedule.objects.filter(
            user=request.user, 
            is_active=True
        ).order_by('scheduled_time')
        
        data = []
        for schedule in schedules:
            data.append({
                'id': str(schedule.id),
                'device_id': str(schedule.device.id),
                'device_name': schedule.device.name,
                'action': schedule.action,
                'scheduled_time': schedule.scheduled_time.isoformat(),
                'is_executed': schedule.is_executed,
            })
        return JsonResponse({'success': True, 'schedules': data})

    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False, 
                'message': 'Chưa đăng nhập'
            }, status=401)
        
        try:
            data = json.loads(request.body)
            print(f"📝 Received schedule data: {data}")  # DEBUG
            
            # Validate required fields
            required_fields = ['device_id', 'action', 'scheduled_time']
            for field in required_fields:
                if field not in data:
                    return JsonResponse({
                        'success': False,
                        'message': f'Thiếu trường {field}'
                    }, status=400)
            
            # Get device
            try:
                device = Device.objects.get(id=data['device_id'])
            except Device.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Thiết bị không tồn tại'
                }, status=404)
            
            # Parse scheduled_time - DEBUG CHI TIẾT
            scheduled_time_str = data['scheduled_time']
            print(f"🕒 Parsing time string: '{scheduled_time_str}'")  # DEBUG
            
            from datetime import datetime
            try:
                scheduled_time = datetime.strptime(scheduled_time_str, '%H:%M').time()
                print(f"✅ Successfully parsed time: {scheduled_time}")  # DEBUG
            except ValueError as e:
                print(f"❌ Time parsing error: {e}")  # DEBUG
                return JsonResponse({
                    'success': False,
                    'message': f'Định dạng thời gian không hợp lệ: {scheduled_time_str}. Lỗi: {str(e)}'
                }, status=400)
            
            # Parse scheduled_date if provided
            scheduled_date = None
            if data.get('scheduled_date'):
                date_str = data['scheduled_date']
                print(f"📅 Parsing date string: '{date_str}'")  # DEBUG
                try:
                    scheduled_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    print(f"✅ Successfully parsed date: {scheduled_date}")  # DEBUG
                except ValueError as e:
                    print(f"❌ Date parsing error: {e}")  # DEBUG
                    return JsonResponse({
                        'success': False,
                        'message': f'Định dạng ngày không hợp lệ: {date_str}'
                    }, status=400)
            
            # Create schedule
            schedule = DeviceSchedule.objects.create(
                user=request.user,
                device=device,
                action=data['action'],
                scheduled_time=scheduled_time,
                scheduled_date=scheduled_date,
                repeat_type=data.get('repeat_type', 'once'),
                repeat_days=data.get('repeat_days', []),
                is_active=data.get('is_active', True)
            )
            
            print(f"✅ Schedule created: {schedule.id}")  # DEBUG
            
            return JsonResponse({
                'success': True,
                'message': 'Đã tạo lịch trình thành công',
                'schedule_id': str(schedule.id)
            }, status=201)
            
        except Exception as e:
            print(f"❌ General error: {e}")  # DEBUG
            import traceback
            print(f"❌ Traceback: {traceback.format_exc()}")  # DEBUG
            return JsonResponse({
                'success': False,
                'message': f'Lỗi: {str(e)}'
            }, status=400)
    
@method_decorator(csrf_exempt, name='dispatch')
class ScheduleDetailView(View):
    """
    API để XÓA hoặc SỬA (bật/tắt) một lịch hẹn.
    """
    def delete(self, request, schedule_id):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'}, status=401)
        
        try:
            schedule = DeviceSchedule.objects.get(id=schedule_id, user=request.user)
            schedule.delete()
            return JsonResponse({'success': True, 'message': 'Đã xóa lịch hẹn'})
            
        except DeviceSchedule.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Lịch hẹn không tồn tại'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Lỗi: {str(e)}'}, status=400)
            
    # Bạn có thể thêm hàm `put` để cập nhật (ví dụ: thay đổi thời gian, hoặc bật/tắt is_active)
    def put(self, request, schedule_id):
        # ... Tương tự, lấy data và cập nhật schedule.save() ...
        pass