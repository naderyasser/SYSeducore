from django.db import models
from django.utils import timezone


class Session(models.Model):
    """
    Session model for managing class sessions.
    """
    session_id = models.AutoField(primary_key=True)
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    session_date = models.DateField(default=timezone.now)
    
    teacher_attended = models.BooleanField(default=False)
    teacher_checkin_time = models.DateTimeField(null=True, blank=True)
    
    is_cancelled = models.BooleanField(default=False)
    cancellation_reason = models.TextField(blank=True)
    
    notification_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'sessions'
        unique_together = ['group', 'session_date']
        ordering = ['-session_date']
    
    def __str__(self):
        return f"{self.group.group_name} - {self.session_date}"


class Attendance(models.Model):
    """
    Attendance model for managing student attendance records.
    """
    STATUS_CHOICES = [
        ('present', 'حاضر'),
        ('late', 'متأخر'),
        ('absent', 'غائب'),
    ]
    
    attendance_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    
    scan_time = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    rejection_reason = models.CharField(max_length=255, blank=True)
    
    supervisor = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='supervised_attendances'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'attendances'
        unique_together = ['student', 'session']
        ordering = ['-scan_time']
    
    def __str__(self):
        return f"{self.student.full_name} - {self.status}"
