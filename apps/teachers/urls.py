from django.urls import path
from . import views

app_name = 'teachers'

urlpatterns = [
    path('', views.teacher_list, name='list'),
    path('<int:teacher_id>/', views.teacher_detail, name='detail'),
]
