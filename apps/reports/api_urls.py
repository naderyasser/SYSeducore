from django.urls import path
from . import api_views

urlpatterns = [
    path('stats/', api_views.stats_api, name='reports_api_stats'),
    path('activity/recent/', api_views.recent_activity_api, name='reports_api_recent_activity'),
]
