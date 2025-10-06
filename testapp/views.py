# api/views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import ButtonClick
from .serializers import ButtonClickSerializer
import uuid

@permission_classes([AllowAny]) 
@api_view(['GET'])
def get_click_count(request):
    """Lấy số lần click hiện tại"""
    click, created = ButtonClick.objects.get_or_create(id='00000000-0000-0000-0000-000000000000')
    serializer = ButtonClickSerializer(click)
    return Response({
        'success': True,
        'data': serializer.data
    })

@permission_classes([AllowAny]) 
@api_view(['POST'])
def increment_click(request):
    """Tăng số lần click lên 1"""
    click, created = ButtonClick.objects.get_or_create(id='00000000-0000-0000-0000-000000000000')
    click.click_count += 1
    click.save()
    
    serializer = ButtonClickSerializer(click)
    return Response({
        'success': True,
        'message': 'Click counted!',
        'data': serializer.data
    })

@permission_classes([AllowAny]) 
@api_view(['POST'])
def reset_clicks(request):
    """Reset số lần click về 0"""
    click, created = ButtonClick.objects.get_or_create(id='00000000-0000-0000-0000-000000000000')
    click.click_count = 0
    click.save()
    
    serializer = ButtonClickSerializer(click)
    return Response({
        'success': True,
        'message': 'Reset successful!',
        'data': serializer.data
    })