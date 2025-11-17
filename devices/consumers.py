# devices/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Device

class DeviceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'device_updates'
        
        # Tham gia room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()

    async def disconnect(self, close_code):
        # Rời khỏi room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Nhận message từ WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        
        # Gửi message đến room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'device_message',
                'message': message
            }
        )

    # Nhận message từ room group
    async def device_message(self, event):
        message = event['message']
        
        # Gửi message đến WebSocket
        await self.send(text_data=json.dumps({
            'message': message
        }))

    async def device_update(self, event):
        # Gửi device update đến client
        await self.send(text_data=json.dumps({
            'type': 'device_update',
            'device': event['device']
        }))