from django.urls import path
from . import api_filter_views

urlpatterns = [
    path('', api_filter_views.groups_filter_api, name='api_groups_filter'),
]
