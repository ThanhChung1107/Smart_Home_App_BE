from django.urls import path, re_path
from . import views

urlpatterns = [
    path('api/devices/', views.DeviceListView.as_view(), name='devices'),
    re_path(r'^api/devices/(?P<device_id>[\w-]+)/control/$', views.DeviceControlView.as_view(), name='device_control'),
    re_path(r'^api/devices/(?P<device_id>[\w-]+)/logs/$', views.DeviceLogsView.as_view(), name='device_logs'),
    path('api/devices/<uuid:device_id>/statistics/', views.DeviceStatisticsView.as_view(), name='device-statistics'),
    path('api/statistics/overall/', views.OverallStatisticsView.as_view(), name='overall-statistics'),
    path('api/statistics/realtime/', views.RealTimeUsageView.as_view(), name='realtime-usage'),
    path('api/statistics/', views.RealStatisticsView.as_view(), name='real_statistics'),
    path('api/debug/stats/', views.DebugStatsView.as_view(), name='debug_stats'),
    path('api/cleanup-sessions/', views.CleanupSessionsView.as_view(), name='cleanup_sessions'),
    path('api/schedules/', views.ScheduleListView.as_view(), name='schedule_list_create'),
    path('api/schedules/<uuid:schedule_id>/', views.ScheduleDetailView.as_view(), name='schedule_detail_update_delete'),
    path('api/sensor-data/', views.SensorDataView.as_view(), name='sensor_data'), 
    path('api/devices/sync/', views.DeviceSyncView.as_view(), name='device_sync'),
]