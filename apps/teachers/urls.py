from django.urls import path
from . import views, api_views

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
    path('rooms/<int:room_id>/', views.room_detail, name='room_detail'),
    path('rooms/<int:room_id>/edit/', views.room_update, name='room_update'),
    path('rooms/<int:room_id>/delete/', views.room_delete, name='room_delete'),

    # Groups
    path('groups/', views.group_list, name='group_list'),
    path('groups/create/', views.group_create, name='group_create'),
    path('groups/<int:group_id>/edit/', views.group_update, name='group_update'),
    path('groups/<int:group_id>/delete/', views.group_delete, name='group_delete'),

    # API: Rooms
    path('api/rooms/', api_views.room_list_api, name='api_room_list'),
    path('api/rooms/<int:room_id>/', api_views.room_detail_api, name='api_room_detail'),
    path('api/rooms/<int:room_id>/schedule/', api_views.room_schedule_api, name='api_room_schedule'),
    path('api/rooms/check-availability/', api_views.room_availability_check, name='api_room_availability'),
    path('api/rooms/statistics/', api_views.room_statistics_api, name='api_room_statistics'),
]
