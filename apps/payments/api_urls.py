from django.urls import path
from . import api_views

urlpatterns = [
    path('<int:payment_id>/record/', api_views.record_payment, name='api_record_payment'),
    path('<int:payment_id>/mark-paid/', api_views.mark_as_paid, name='api_mark_paid'),
    path('collect/', api_views.collect_payment, name='api_collect'),

    path('settlements/build/', api_views.settlement_build, name='api_settlement_build'),
    path('settlements/<int:settlement_id>/refresh/', api_views.settlement_refresh, name='api_settlement_refresh'),
    path('settlements/lines/<int:line_id>/', api_views.settlement_line_update, name='api_settlement_line'),
    path('settlements/<int:settlement_id>/approve/', api_views.settlement_approve, name='api_settlement_approve'),
    path('settlements/<int:settlement_id>/reopen/', api_views.settlement_reopen, name='api_settlement_reopen'),
]
