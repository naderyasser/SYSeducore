from django.db import models
from django.conf import settings
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that filters out soft-deleted objects by default."""

    def delete(self):
        """Soft delete all objects in queryset."""
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        """Permanently delete all objects in queryset."""
        return super().delete()

    def alive(self):
        """Return only non-deleted objects."""
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        """Return only soft-deleted objects."""
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
    """Manager that excludes soft-deleted objects by default."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class AllObjectsManager(models.Manager):
    """Manager that includes all objects, including soft-deleted ones."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    """
    Abstract model that provides soft delete functionality.
    Objects are marked as deleted instead of being permanently removed.
    """
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="تاريخ الحذف"
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_deleted",
        verbose_name="حُذف بواسطة"
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self, user=None):
        """Soft delete this object."""
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=['deleted_at', 'deleted_by'])

    def restore(self):
        """Restore a soft-deleted object."""
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['deleted_at', 'deleted_by'])
