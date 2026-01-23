from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('', views.payment_list, name='list'),
    path('<int:teacher_id>/settlement/', views.teacher_settlement, name='settlement'),
]
