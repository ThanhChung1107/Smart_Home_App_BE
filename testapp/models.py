from django.db import models
import uuid

class ButtonClick(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    click_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Click {self.click_count} at {self.created_at}"

    class Meta:
        db_table = 'button_clicks'