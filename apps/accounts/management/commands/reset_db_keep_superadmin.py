from django.core.management.base import BaseCommand
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection

User = get_user_model()

class Command(BaseCommand):
    help = 'Delete all data except superadmin account'

    def handle(self, *args, **options):
        superadmins = User.objects.filter(is_superuser=True)
        
        if not superadmins.exists():
            self.stdout.write(self.style.ERROR('No superadmin found!'))
            return
        
        superadmin_ids = list(superadmins.values_list('user_id', 'username'))
        self.stdout.write(f'Preserving superadmin(s): {superadmin_ids}')
        
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF;")
            
            for model in apps.get_models():
                if model._meta.app_label in ['contenttypes', 'auth', 'admin', 'sessions']:
                    continue
                
                # ``db_table`` comes from Django's own model metadata, never
                # from user input, so this cannot be an injection vector — but
                # it is still interpolated, so it goes through the backend's
                # identifier quoting rather than being pasted in bare. That
                # also makes the command correct for a table whose name needs
                # quoting in the first place.
                table = connection.ops.quote_name(model._meta.db_table)

                if model == User:
                    sql = f"DELETE FROM {table} WHERE is_superuser = 0;"  # nosec B608
                    cursor.execute(sql)
                    count = cursor.rowcount
                    self.stdout.write(f'Deleted non-superadmin users: {count}')
                else:
                    sql = f"DELETE FROM {table};"  # nosec B608
                    cursor.execute(sql)
                    count = cursor.rowcount
                    if count > 0:
                        self.stdout.write(f'Deleted {model._meta.app_label}.{model._meta.model_name}: {count}')
            
            cursor.execute("PRAGMA foreign_keys = ON;")
        
        self.stdout.write(self.style.SUCCESS('Database reset complete!'))
