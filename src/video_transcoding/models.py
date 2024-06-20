import os
from typing import Any, cast
from uuid import UUID

from django.core.validators import URLValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from video_transcoding import defaults


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

    status = models.SmallIntegerField(default=CREATED, choices=STATUS_CHOICES,
                                      verbose_name=_('Status'))
    error = models.TextField(blank=True, null=True, verbose_name=_('Error'))
    task_id = models.UUIDField(blank=True, null=True,
                               verbose_name=_('Task ID'))
    source = models.URLField(verbose_name=_('Source'),
                             validators=[
                                 URLValidator(schemes=('http', 'https'))])
    basename = models.UUIDField(blank=True, null=True,
                                verbose_name=_('Basename'))

    class Meta:
        app_label = 'video_transcoding'
        verbose_name = _('Video')
        verbose_name_plural = _('Video')

    def __str__(self) -> str:
        basename = os.path.basename(self.source)
        return f'{basename} ({self.get_status_display()})'

    def format_video_url(self, edge: str) -> str:
        """
        Returns a link to m3u8 playlist on one of randomly chosen edges.
        """
        if self.basename is None:
            raise RuntimeError("Video has no files")
        basename = cast(UUID, self.basename)
        return defaults.VIDEO_URL.format(
            edge=edge.rstrip('/'),
            filename=basename.hex)

    def change_status(self, status: int, **fields: Any) -> None:
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
        # suppress mypy [no-untyped-calls]
        self.save(update_fields=tuple(update_fields))  # type: ignore
