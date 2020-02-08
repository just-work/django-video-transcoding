import os

from django.core.validators import URLValidator
from django.db import models
from django.utils.translation import ugettext_lazy as _
from model_utils.models import TimeStampedModel

nullable = dict(blank=True, null=True)


class Video(TimeStampedModel):
    """ Video model."""
    CREATED, QUEUED, PROCESS, DONE, ERROR = range(5)
    STATUS_CHOICES = (
        (CREATED, _('created')),  # And editor created video in db
        (QUEUED, _('queued')),  # Transcoding task is sent to broker
        (PROCESS, _('process')),  # Celery worker started video processing
        (DONE, _('done')),  # Video processing is done successfully
        (ERROR, _('error')),  # Video processing error
    )

    status = models.SmallIntegerField(default=CREATED, choices=STATUS_CHOICES)
    error = models.TextField(**nullable)
    task_id = models.UUIDField(**nullable)
    source = models.URLField(validators=[URLValidator(schemes=('ftp', 'http'))])
    basename = models.UUIDField(**nullable)

    class Meta:
        app_label = 'video_transcoding'
        verbose_name = _('Video')
        verbose_name_plural = _('Video')

    def __str__(self):
        basename = os.path.basename(self.source)
        return f'{basename} ({self.get_status_display()})'

    def change_status(self, status: int, **fields):
        """
        Changes video status.

        Also saves another model fields and always updates `modified` value.

        :param status: one of statuses for Video.status (see STATUS_CHOICES)
        :param fields: dict with model field values.
        """
        self.status = status
        update_fields = {'status', 'modified'}
        for k, v in fields.items():
            setattr(self, k, v)
            update_fields.add(k)
        self.save(update_fields=update_fields)
