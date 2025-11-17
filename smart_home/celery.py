# smart_home/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# đặt mặc định settings module của Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_home.settings')

app = Celery('smart_home')

# đọc cấu hình từ Django settings, namespace='CELERY' nghĩa là các setting của Celery bắt đầu bằng CELERY_*
app.config_from_object('django.conf:settings', namespace='CELERY')

# tự động phát hiện task từ tất cả app trong Django
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
