from django.conf import settings


def notification_settings(request):
    return {
        'NOTIFICATION_METHOD': getattr(settings, 'NOTIFICATION_METHOD', 'none'),
    }
