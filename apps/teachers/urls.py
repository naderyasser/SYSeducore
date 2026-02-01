from django.urls import path
from . import views

app_name = 'teachers'

urlpatterns = [
    # Teachers
    path('', views.teacher_list, name='list'),
    path('create/', views.teacher_create, name='create'),
    path('<int:teacher_id>/', views.teacher_detail, name='detail'),
    path('<int:teacher_id>/edit/', views.teacher_update, name='update'),
    path('<int:teacher_id>/delete/', views.teacher_delete, name='delete'),

    # Rooms
    path('rooms/', views.room_list, name='room_list'),
    path('rooms/create/', views.room_create, name='room_create'),
    path('rooms/<int:room_id>/edit/', views.room_update, name='room_update'),
    path('rooms/<int:room_id>/delete/', views.room_delete, name='room_delete'),
    path('rooms/schedule/', views.room_schedule_dashboard, name='room_schedule_dashboard'),
    path('rooms/<int:room_id>/schedule/', views.room_detail_schedule, name='room_detail_schedule'),
    path('rooms/find-available/', views.find_available_room, name='find_available_room'),
    path('rooms/utilization/', views.room_utilization_report, name='room_utilization_report'),

    # Groups
    path('groups/', views.group_list, name='group_list'),
    path('groups/create/', views.group_create, name='group_create'),
    path('groups/<int:group_id>/edit/', views.group_update, name='group_update'),
    path('groups/<int:group_id>/delete/', views.group_delete, name='group_delete'),
]
