from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('', views.payment_list, name='list'),
    path('<int:teacher_id>/settlement/', views.teacher_settlement, name='settlement'),
    path('receipt/<int:payment_id>/', views.payment_receipt, name='receipt'),

    path('settlements/', views.settlement_index, name='settlement_index'),
    path('settlements/<int:settlement_id>/', views.settlement_detail, name='settlement_detail'),
    path('settlements/<int:settlement_id>/print/', views.settlement_print, name='settlement_print'),
]
