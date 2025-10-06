from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views import View
import json
from .models import User
import base64
from django.core.files.base import ContentFile

@method_decorator(csrf_exempt, name='dispatch')
class RegisterView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            email = data.get('email')
            phone = data.get('phone')
            role = data.get('role', 'guest')
            
            if User.objects.filter(username=username).exists():
                return JsonResponse({
                    'success': False,
                    'message': 'Tên đăng nhập đã tồn tại'
                }, status=400)
            
            user = User.objects.create_user(
                username=username,
                password=password,
                email=email,
                phone=phone,
                role=role
            )
            
            # Xử lý avatar nếu có
            avatar_data = data.get('avatar')
            if avatar_data:
                format, imgstr = avatar_data.split(';base64,')
                ext = format.split('/')[-1]
                avatar_file = ContentFile(
                    base64.b64decode(imgstr),
                    name=f"{user.id}_avatar.{ext}"
                )
                user.avatar = avatar_file
                user.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Đăng ký thành công',
                'user': {
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'phone': user.phone,
                    'role': user.role,
                    'avatar': user.avatar.url if user.avatar else None
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Lỗi đăng ký: {str(e)}'
            }, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class LoginView(View):
    def post(self, request):
        try:
            # Parse JSON data
            data = json.loads(request.body.decode('utf-8'))
            username = data.get('username')
            password = data.get('password')
            
            print(f"Login attempt: {username}")  # Debug log
            
            # Authenticate user
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                return JsonResponse({
                    'success': True,
                    'message': 'Đăng nhập thành công',
                    'user': {
                        'id': str(user.id),
                        'username': user.username,
                        'email': user.email,
                        'phone': user.phone,
                        'role': user.role,
                        'avatar': user.avatar.url if user.avatar else None
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Tên đăng nhập hoặc mật khẩu không đúng'
                }, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            print(f"Login error: {str(e)}")  # Debug log
            return JsonResponse({
                'success': False,
                'message': f'Lỗi server: {str(e)}'
            }, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class LogoutView(View):
    def post(self, request):
        logout(request)
        return JsonResponse({
            'success': True,
            'message': 'Đăng xuất thành công'
        })

@method_decorator(csrf_exempt, name='dispatch')
class ProfileView(View):
    def get(self, request):
        if request.user.is_authenticated:
            user = request.user
            return JsonResponse({
                'success': True,
                'user': {
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'phone': user.phone,
                    'role': user.role,
                    'avatar': user.avatar.url if user.avatar else None
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Chưa đăng nhập'
            }, status=401)