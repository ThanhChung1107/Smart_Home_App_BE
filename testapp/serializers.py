from rest_framework import serializers
from .models import ButtonClick

class ButtonClickSerializer(serializers.ModelSerializer):
    class Meta:
        model = ButtonClick
        fields = ['id', 'click_count', 'created_at', 'updated_at']