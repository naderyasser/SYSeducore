from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # WhatsApp Management
    path('whatsapp/', views.whatsapp_dashboard, name='whatsapp_dashboard'),
    path('whatsapp/send/', views.send_message, name='send_message'),
    path('whatsapp/bulk/', views.send_bulk_message, name='send_bulk_message'),
    path('whatsapp/history/', views.message_history, name='message_history'),
    path('whatsapp/contacts/', views.contact_list, name='contact_list'),
    path('whatsapp/templates/', views.manage_templates, name='manage_templates'),

    # Testing
    path('test/', views.test_whatsapp, name='test'),

    # API Endpoints
    path('api/bulk-attendance-report/', views.send_bulk_attendance_report, name='bulk_attendance_report'),
    path('api/bulk-message/', views.send_bulk_custom_message, name='bulk_custom_message'),
]
