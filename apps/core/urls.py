from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('quick-search/', views.quick_search, name='quick_search'),
]
