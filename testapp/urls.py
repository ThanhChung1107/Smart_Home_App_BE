from django.urls import path
from . import views

urlpatterns = [
    path('click/', views.get_click_count, name='get_click_count'),
    path('click/increment/', views.increment_click, name='increment_click'),
    path('click/reset/', views.reset_clicks, name='reset_clicks'),
]