from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('test/', views.test_whatsapp, name='test'),
]
