from django.urls import path
from . import views, api_views

app_name = 'students'

urlpatterns = [
    # Main Views
    path('', views.student_list, name='list'),
    path('create/', views.student_create, name='create'),
    path('<int:student_id>/', views.student_detail, name='detail'),
    path('<int:student_id>/update/', views.student_update, name='update'),
    path('<int:student_id>/delete/', views.student_delete, name='delete'),
    path('<int:student_id>/id-card/', views.student_id_card, name='id_card'),
    path('<int:student_id>/id-card/print/', views.student_id_card_print, name='id_card_print'),
    path('<int:student_id>/qr-ticket/', views.student_qr_ticket, name='qr_ticket'),
    path('<int:student_id>/qr-ticket/pdf/', views.qr_ticket_pdf, name='qr_ticket_pdf'),
    path('<int:student_id>/toggle-status/', views.student_toggle_status, name='toggle_status'),

    # Helper Views
    path('api/next-code/', views.get_next_code, name='next_code'),

    # API Endpoints
    path('api/list/', api_views.students_list_api, name='api_list'),
    path('api/statistics/', api_views.student_statistics, name='api_statistics'),
    path('api/bulk-action/', api_views.bulk_action, name='api_bulk_action'),
    path('api/<int:student_id>/barcode/', api_views.student_barcode, name='api_barcode'),
    path('api/<int:student_id>/barcode/send/', api_views.send_barcode_whatsapp, name='api_send_barcode'),
    path('api/<int:student_id>/whatsapp/', api_views.whatsapp_barcode, name='api_whatsapp'),
    path('api/<int:student_id>/id-card/', api_views.student_id_card_data, name='api_id_card'),
    path('api/<int:student_id>/groups/', api_views.student_groups, name='api_groups'),
    path('api/<int:student_id>/available-groups/', api_views.available_groups, name='api_available_groups'),
    path('api/add-to-group/', api_views.add_to_group, name='api_add_to_group'),
    path('api/remove-from-group/', api_views.remove_from_group, name='api_remove_from_group'),
    
    # Entitlement (session-based, per group) — replaces the old global subscription APIs.
    path('api/<int:student_id>/entitlement/', api_views.entitlement_status, name='api_entitlement_status'),
]
