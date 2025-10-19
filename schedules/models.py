from django.db import models
import uuid
from django.conf import settings
from devices.models import Device

class Schedule(models.Model):
    DAYS_OF_WEEK = (
        ('mon', 'Thứ 2'),
        ('tue', 'Thứ 3'),
        ('wed', 'Thứ 4'),
        ('thu', 'Thứ 5'),
        ('fri', 'Thứ 6'),
        ('sat', 'Thứ 7'),
        ('sun', 'Chủ nhật'),
    )

    ACTIONS = (
        ('on', 'Bật'),
        ('off', 'Tắt'),
        ('toggle', 'Chuyển trạng thái'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=True)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='schedules')
    action = models.CharField(max_length=10, choices=ACTIONS)
    scheduled_time = models.TimeField()
    repeat_days = models.JSONField(default=list)  # ['mon', 'tue', ...]
    is_active = models.BooleanField(default=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='schedules')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'schedules'
        ordering = ['scheduled_time']

    def save(self, *args, **kwargs):
        # Tự động tạo name nếu để trống
        if not self.name:
            device_name = self.device.name
            action_name = dict(self.ACTIONS).get(self.action)
            self.name = f"{action_name} {device_name} lúc {self.scheduled_time}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {'Active' if self.is_active else 'Inactive'}"