from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'schedules', views.ScheduleViewSet, basename='schedule')

urlpatterns = [
    path('', include(router.urls)),
    # path('api/schedules/', ScheduleListView.as_view(), name='schedule-list'),
# path('api/schedules/<str:schedule_id>/', ScheduleDetailView.as_view(), name='schedule-detail'),
# path('api/schedules/<str:schedule_id>/toggle/', ScheduleToggleView.as_view(), name='schedule-toggle'),
# path('api/schedules/devices/', ScheduleDevicesView.as_view(), name='schedule-devices'),
]