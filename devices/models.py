from django.db import models
import uuid
from users.models import User   # để liên kết với User

class Device(models.Model):
    DEVICE_TYPES = (
        ('light', 'Đèn'),
        ('fan', 'Quạt'),
        ('ac', 'Điều hòa'),
        ('socket', 'Ổ cắm'),
        ('door', 'Cửa'),
    )

    ROOM_CHOICES = (
        ('living_room', 'Phòng khách'),
        ('bedroom', 'Phòng ngủ'),
        ('kitchen', 'Nhà bếp'),
        ('bathroom', 'Phòng tắm'),
        ('outside', 'Bên ngoài'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES)
    room = models.CharField(max_length=20, choices=ROOM_CHOICES)
    is_on = models.BooleanField(default=False)
    status = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'devices'


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
    date = models.DateField()  # Ngày thống kê
    turn_on_count = models.IntegerField(default=0)
    total_usage_minutes = models.IntegerField(default=0)  # Tổng thời gian sử dụng (phút)
    power_consumption = models.FloatField(default=0.0)  # kWh
    cost = models.FloatField(default=0.0)  # Chi phí
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'device_statistics'
        unique_together = ['device', 'date']

class DeviceUsageSession(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='usage_sessions')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=0)  # Thời gian sử dụng (phút)
    
    class Meta:
        db_table = 'device_usage_sessions'
