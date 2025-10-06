from django.urls import path
from . import views

urlpatterns = [
    path('api/devices/', views.DeviceListView.as_view(), name='devices'),
    path('api/devices/<uuid:device_id>/control/', views.DeviceControlView.as_view(), name='device_control'),
    path('api/devices/<uuid:device_id>/logs/', views.DeviceLogsView.as_view(), name='device_logs'),
]