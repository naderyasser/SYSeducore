from django.core.management.base import BaseCommand
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()

class Command(BaseCommand):
    help = 'Delete all data except superadmin account'

    def handle(self, *args, **options):
        superadmins = User.objects.filter(is_superuser=True)

        if not superadmins.exists():
            self.stdout.write(self.style.ERROR('No superadmin found!'))
            return

        superadmin_ids = list(superadmins.values_list('pk', 'username'))
        self.stdout.write(f'Preserving superadmin(s): {superadmin_ids}')

        with transaction.atomic():
            for model in apps.get_models():
                if model._meta.app_label in ['contenttypes', 'auth', 'admin', 'sessions']:
                    continue

                model_name = f"{model._meta.app_label}.{model._meta.model_name}"

                if model == User:
                    deleted = User.objects.exclude(is_superuser=True).delete()
                    self.stdout.write(f'Deleted non-superadmin users: {deleted[0]}')
                else:
                    # Soft-deletable models expose all_objects (includes
                    # already-soft-deleted rows) and hard_delete() (a real
                    # DELETE, not a deleted_at update) — use them when
                    # available so a reset actually clears the table.
                    manager = getattr(model, 'all_objects', model.objects)
                    queryset = manager.all()
                    if hasattr(queryset, 'hard_delete'):
                        deleted = queryset.hard_delete()
                    else:
                        deleted = queryset.delete()
                    if deleted[0] > 0:
                        self.stdout.write(f'Deleted {model_name}: {deleted[0]}')

        self.stdout.write(self.style.SUCCESS('Database reset complete!'))
