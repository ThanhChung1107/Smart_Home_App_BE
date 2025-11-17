# models.py
from django.db import models
import uuid
from users.models import User

class Device(models.Model):
    DEVICE_TYPES = (
        ('light', 'Đèn'),
        ('fan', 'Quạt'),
        ('ac', 'Điều hòa'),
        ('socket', 'Ổ cắm'),
        ('door', 'Cửa'),
        ('sensor', 'Cảm biến'),
        ('dryer', 'Máy sấy'),
    )

    ROOM_CHOICES = (
        ('living_room', 'Phòng khách'),
        ('bedroom', 'Phòng ngủ'),
        ('kitchen', 'Nhà bếp'),
        ('bathroom', 'Phòng tắm'),
        ('outside', 'Bên ngoài'),
        ('corridor', 'Hành lang'),
    )

    id = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=100)
    device_code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES)
    room = models.CharField(max_length=20, choices=ROOM_CHOICES)
    is_on = models.BooleanField(default=False)
    status = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    is_online = models.BooleanField(default=False)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'devices'
        
    def __str__(self):
        return f"{self.name} ({self.device_code})"

class DeviceLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=50)
    old_status = models.JSONField(default=dict)
    new_status = models.JSONField(default=dict)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_logs')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'device_logs'
        ordering = ['-created_at']

class DeviceStatistics(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='statistics')
    date = models.DateField()
    turn_on_count = models.IntegerField(default=0)
    total_usage_minutes = models.IntegerField(default=0)
    power_consumption = models.FloatField(default=0.0)
    cost = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'device_statistics'
        unique_together = ['device', 'date']

class DeviceUsageSession(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='usage_sessions')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'device_usage_sessions'

# devices/models.py - Cập nhật DeviceSchedule model
class DeviceSchedule(models.Model):
    ACTION_CHOICES = (
        ('on', 'Bật thiết bị'),
        ('off', 'Tắt thiết bị'),
    )
    
    REPEAT_CHOICES = (
        ('once', 'Một lần'),
        ('daily', 'Hàng ngày'),
        ('weekly', 'Hàng tuần'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='schedules')
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='schedules')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    scheduled_time = models.TimeField()  # Thời gian trong ngày
    scheduled_date = models.DateField(null=True, blank=True)  # Ngày cụ thể (cho lịch một lần)
    repeat_type = models.CharField(max_length=10, choices=REPEAT_CHOICES, default='once')
    repeat_days = models.JSONField(default=list, blank=True)  # ['mon', 'tue', ...]
    is_active = models.BooleanField(default=True)
    is_executed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'device_schedules'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.device.name} -> {self.action} lúc {self.scheduled_time}"

    def get_next_scheduled_datetime(self):
        """Tính toán thời gian thực thi tiếp theo"""
        from django.utils import timezone
        import datetime
        
        now = timezone.now()
        today = now.date()
        current_time = now.time()
        
        # Tạo datetime từ scheduled_time
        scheduled_datetime = datetime.datetime.combine(today, self.scheduled_time)
        scheduled_datetime = timezone.make_aware(scheduled_datetime)
        
        if self.repeat_type == 'once':
            if self.scheduled_date:
                once_datetime = datetime.datetime.combine(self.scheduled_date, self.scheduled_time)
                once_datetime = timezone.make_aware(once_datetime)
                return once_datetime if once_datetime > now else None
            return scheduled_datetime if scheduled_datetime > now else None
        
        elif self.repeat_type == 'daily':
            if scheduled_datetime > now:
                return scheduled_datetime
            else:
                return scheduled_datetime + datetime.timedelta(days=1)
        
        elif self.repeat_type == 'weekly' and self.repeat_days:
            # Tìm ngày trong tuần tiếp theo
            current_weekday = now.strftime('%a').lower()[:3]  # 'mon', 'tue', etc.
            days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
            
            # Tìm ngày gần nhất trong tuần
            current_idx = days.index(current_weekday)
            for i in range(7):
                check_day = days[(current_idx + i) % 7]
                if check_day in self.repeat_days:
                    days_to_add = i
                    next_date = today + datetime.timedelta(days=days_to_add)
                    next_datetime = datetime.datetime.combine(next_date, self.scheduled_time)
                    next_datetime = timezone.make_aware(next_datetime)
                    if next_datetime > now:
                        return next_datetime
        
        return None