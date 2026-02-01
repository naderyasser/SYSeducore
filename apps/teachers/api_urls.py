"""
API URLs for Room Scheduling
مسارات واجهات برمجة التطبيقات لنظام جدولة القاعات
"""

from django.urls import path
from . import api_views

app_name = 'teachers_api'

urlpatterns = [
    # Room availability endpoints
    path('rooms/available/', api_views.api_available_rooms, name='available_rooms'),
    path('rooms/list/', api_views.api_rooms_list, name='rooms_list'),
    path('rooms/days/', api_views.api_days_list, name='days_list'),
    
    # Room schedule endpoints
    path('rooms/<int:room_id>/schedule/', api_views.api_room_schedule, name='room_schedule'),
    path('rooms/schedule/all/', api_views.api_all_rooms_schedule, name='all_rooms_schedule'),
    
    # Room utilization endpoints
    path('rooms/<int:room_id>/utilization/', api_views.api_room_utilization, name='room_utilization'),
    path('rooms/utilization/all/', api_views.api_all_utilization, name='all_utilization'),
    
    # Weekly grid endpoint
    path('schedule/grid/', api_views.api_weekly_grid, name='weekly_grid'),
    
    # Conflict detection endpoint
    path('check-conflict/', api_views.api_check_conflict, name='check_conflict'),
]