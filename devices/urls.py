from django.urls import path
from . import views

urlpatterns = [
    path('api/devices/', views.DeviceListView.as_view(), name='devices'),
    path('api/devices/<uuid:device_id>/control/', views.DeviceControlView.as_view(), name='device_control'),
    path('api/devices/<uuid:device_id>/logs/', views.DeviceLogsView.as_view(), name='device_logs'),
    path('api/devices/<uuid:device_id>/statistics/', views.DeviceStatisticsView.as_view(), name='device-statistics'),
    path('api/statistics/overall/', views.OverallStatisticsView.as_view(), name='overall-statistics'),
    path('api/statistics/realtime/', views.RealTimeUsageView.as_view(), name='realtime-usage'),
    path('api/statistics/', views.RealStatisticsView.as_view(), name='real_statistics'),
    path('api/debug/stats/', views.DebugStatsView.as_view(), name='debug_stats'),
    path('api/cleanup-sessions/', views.CleanupSessionsView.as_view(), name='cleanup_sessions'),
]