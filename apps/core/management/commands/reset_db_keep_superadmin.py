from django.core.management.base import BaseCommand
from django.apps import apps
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Delete all data except superadmin account'

    def handle(self, *args, **options):
        superadmins = User.objects.filter(is_superuser=True)
        
        if not superadmins.exists():
            self.stdout.write(self.style.ERROR('No superadmin found!'))
            return
        
        superadmin_ids = list(superadmins.values_list('id', 'username'))
        self.stdout.write(f'Preserving superadmin(s): {superadmin_ids}')
        
        for model in apps.get_models():
            if model._meta.app_label in ['contenttypes', 'auth', 'admin', 'sessions']:
                continue
            
            model_name = f"{model._meta.app_label}.{model._meta.model_name}"
            
            if model == User:
                deleted = User.objects.exclude(is_superuser=True).delete()
                self.stdout.write(f'Deleted non-superadmin users: {deleted[0]}')
            else:
                deleted = model.objects.all().delete()
                if deleted[0] > 0:
                    self.stdout.write(f'Deleted {model_name}: {deleted[0]}')
        
        self.stdout.write(self.style.SUCCESS('Database reset complete!'))
