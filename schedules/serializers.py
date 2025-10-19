from rest_framework import serializers
from .models import Schedule
from devices.models import Device

class ScheduleSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)
    device_type = serializers.CharField(source='device.device_type', read_only=True)
    room = serializers.CharField(source='device.room', read_only=True)
    
    class Meta:
        model = Schedule
        fields = [
            'id', 'name', 'device', 'device_name', 'device_type', 'room',
            'action', 'scheduled_time', 'repeat_days', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'device_name', 'device_type', 'room']

class CreateScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Schedule
        fields = ['name', 'device', 'action', 'scheduled_time', 'repeat_days', 'is_active']

    def validate(self, data):
        # Validate repeat_days
        valid_days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        repeat_days = data.get('repeat_days', [])
        
        for day in repeat_days:
            if day not in valid_days:
                raise serializers.ValidationError(f"Ngày '{day}' không hợp lệ")
        
        return data