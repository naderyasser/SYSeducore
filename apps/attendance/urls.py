from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('scanner/', views.scanner_page, name='scanner'),
    path('session/<int:session_id>/', views.session_detail, name='session_detail'),
]
