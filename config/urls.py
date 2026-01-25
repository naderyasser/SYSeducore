"""
URL configuration for attendance_system project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Redirect root to dashboard
    path('', RedirectView.as_view(url='/reports/', permanent=False)),
    path('dashboard/', RedirectView.as_view(url='/reports/', permanent=False)),
    
    # App URLs
    path('accounts/', include('apps.accounts.urls')),
    path('students/', include('apps.students.urls')),
    path('teachers/', include('apps.teachers.urls')),
    path('attendance/', include('apps.attendance.urls')),
    path('payments/', include('apps.payments.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('reports/', include('apps.reports.urls')),
    
    # API endpoints
    path('api/', include([
        path('attendance/', include('apps.attendance.api_urls')),
        path('payments/', include('apps.payments.api_urls')),
    ])),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
