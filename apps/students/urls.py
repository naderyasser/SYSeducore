from django.urls import path
from . import views

app_name = 'students'

urlpatterns = [
    path('', views.student_list, name='list'),
    path('create/', views.student_create, name='create'),
    path('<int:student_id>/', views.student_detail, name='detail'),
    path('<int:student_id>/update/', views.student_update, name='update'),
    path('qr/print/', views.print_qr_codes, name='print_qr_codes'),
    path('<int:student_id>/qr/card/', views.qr_card_single, name='qr_card_single'),
]
