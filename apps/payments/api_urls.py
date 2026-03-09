from django.urls import path
from . import api_views

urlpatterns = [
    path('<int:payment_id>/record/', api_views.record_payment, name='api_record_payment'),
    path('<int:payment_id>/mark-paid/', api_views.mark_as_paid, name='api_mark_paid'),
]
