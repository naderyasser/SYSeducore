from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('', views.payment_list, name='list'),
    path('create/', views.payment_create, name='create'),
    path('settlements/', views.settlement_list, name='settlement_list'),
    path('<int:teacher_id>/settlement/', views.teacher_settlement, name='settlement'),
]
