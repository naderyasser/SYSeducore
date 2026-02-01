from django.apps import AppConfig


class TeachersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.teachers'
    verbose_name = 'المدرسين'
    
    def ready(self):
        """Import signals when app is ready"""
        import apps.teachers.signals

