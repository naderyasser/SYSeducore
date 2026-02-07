from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('test/', views.test_whatsapp, name='test'),
    path('api/bulk-attendance-report/', views.send_bulk_attendance_report, name='bulk_attendance_report'),
    path('api/bulk-message/', views.send_bulk_custom_message, name='bulk_custom_message'),
]
