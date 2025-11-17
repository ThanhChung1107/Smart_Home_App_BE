# devices/tasks.py
from celery import shared_task
from django.utils import timezone
from .models import DeviceSchedule, DeviceLog
import logging

logger = logging.getLogger(__name__)

# SỬA: Thêm ignore_result=True
@shared_task(bind=True, ignore_result=True)
def check_pending_schedules(self):
    """Kiểm tra các lịch hẹn sắp tới - không return result"""
    logger.info("=== CHECKING PENDING SCHEDULES ===")
    
    now = timezone.now()
    pending_schedules = DeviceSchedule.objects.filter(
        is_active=True,
        is_executed=False,
        scheduled_time__lte=now
    )
    
    logger.info(f"Found {pending_schedules.count()} pending schedules")
    
    for schedule in pending_schedules:
        logger.info(f"Executing: {schedule.device.name} -> {schedule.action}")
        execute_scheduled_task.delay(str(schedule.id))
    
    # Không return gì cả

@shared_task(bind=True, ignore_result=True)
def execute_scheduled_task(self, schedule_id):
    """Thực thi một lịch hẹn cụ thể - không return result"""
    try:
        logger.info(f"=== EXECUTING SCHEDULE: {schedule_id} ===")
        
        schedule = DeviceSchedule.objects.get(
            id=schedule_id, 
            is_active=True, 
            is_executed=False
        )
        
        device = schedule.device
        logger.info(f"Device before: {device.name} - is_on: {device.is_on}")
        
        # Thực hiện hành động
        if schedule.action == 'on':
            device.is_on = True
        elif schedule.action == 'off':
            device.is_on = False
        
        device.save()
        schedule.is_executed = True
        schedule.save()
        
        logger.info(f"Device after: {device.name} - is_on: {device.is_on}")
        
        # Ghi log
        DeviceLog.objects.create(
            device=device,
            action=f'scheduled_{schedule.action}',
            old_status={},
            new_status={'is_on': device.is_on},
            user=schedule.user
        )
        
        logger.info(f"Schedule {schedule_id} executed successfully")
        
        # Không return gì cả
        
    except Exception as e:
        logger.error(f"Error executing schedule {schedule_id}: {str(e)}")