from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # Preferences (Opt-out mechanism)
    path('preferences/<int:student_id>/', views.notification_preferences, name='preferences'),
    
    # History and Stats
    path('history/', views.notification_history, name='history'),
    path('history/<int:student_id>/', views.notification_history, name='history_student'),
    path('stats/', views.notification_stats, name='stats'),
    
    # Templates
    path('templates/', views.template_list, name='templates'),
    path('templates/<int:template_id>/preview/', views.template_preview, name='template_preview'),
    
    # Cost Report
    path('costs/', views.cost_report, name='cost_report'),
    
    # API Endpoints
    path('api/update-preference/', views.api_update_preference, name='api_update_preference'),
    path('api/stats/', views.api_notification_stats, name='api_stats'),
    
    # Test (Development Only)
    path('test/', views.test_whatsapp, name='test'),
]
