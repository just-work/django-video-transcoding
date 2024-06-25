import os
from typing import Any, cast
from uuid import UUID

from django.core.validators import URLValidator
from django.db import models
from django.db.models.fields import related_descriptors
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from video_transcoding import defaults


class Preset(TimeStampedModel):
    """ Transcoding preset."""
    video_tracks: related_descriptors.ReverseManyToOneDescriptor
    audio_tracks: related_descriptors.ReverseManyToOneDescriptor
    video_profiles: related_descriptors.ReverseManyToOneDescriptor
    audio_profiles: related_descriptors.ReverseManyToOneDescriptor
    name = models.SlugField(max_length=255, unique=True)

    def __str__(self) -> str:
        return self.name


class VideoTrack(TimeStampedModel):
    """ Video stream transcoding parameters."""
    name = models.SlugField(max_length=255, unique=False)
    params = models.JSONField(default=dict)
    preset = models.ForeignKey(Preset, models.CASCADE,
                               related_name='video_tracks')

    class Meta:
        unique_together = (('name', 'preset'),)

    def __str__(self) -> str:
        return f'{self.name}@{self.preset}'


class AudioTrack(TimeStampedModel):
    """ Audio stream transcoding parameters."""
    name = models.SlugField(max_length=255, unique=False)
    params = models.JSONField(default=dict)
    preset = models.ForeignKey(Preset, models.CASCADE,
                               related_name='audio_tracks')

    class Meta:
        unique_together = (('name', 'preset'),)

    def __str__(self) -> str:
        return f'{self.name}@{self.preset}'


class VideoProfile(TimeStampedModel):
    """ Video transcoding profile."""
    name = models.SlugField(max_length=255, unique=False)
    order_number = models.SmallIntegerField(default=0)
    condition = models.JSONField(default=dict)
    preset = models.ForeignKey(Preset, models.CASCADE,
                               related_name='video_profiles')

    video = cast(
        related_descriptors.ManyToManyDescriptor,
        models.ManyToManyField(VideoTrack, through='VideoProfileTracks'))

    class Meta:
        unique_together = (('name', 'preset'),)
        ordering = ['order_number']

    def __str__(self) -> str:
        return f'{self.name}@{self.preset}'


class VideoProfileTracks(models.Model):
    profile = models.ForeignKey(VideoProfile, models.CASCADE)
    track = models.ForeignKey(VideoTrack, models.CASCADE)
    order_number = models.SmallIntegerField(default=0)

    class Meta:
        unique_together = (('profile', 'track'),)
        ordering = ['order_number']


class AudioProfile(TimeStampedModel):
    """ Audio transcoding profile."""
    name = models.SlugField(max_length=255, unique=False)
    order_number = models.SmallIntegerField(default=0)
    condition = models.JSONField(default=dict)
    preset = models.ForeignKey(Preset, models.CASCADE,
                               related_name='audio_profiles')

    audio = cast(
        related_descriptors.ManyToManyDescriptor,
        models.ManyToManyField(AudioTrack, through='AudioProfileTracks'))

    class Meta:
        unique_together = (('name', 'preset'),)
        ordering = ['order_number']

    def __str__(self) -> str:
        return f'{self.name}@{self.preset}'


class AudioProfileTracks(models.Model):
    profile = models.ForeignKey(AudioProfile, models.CASCADE)
    track = models.ForeignKey(AudioTrack, models.CASCADE)
    order_number = models.SmallIntegerField(default=0)

    class Meta:
        unique_together = (('profile', 'track'),)
        ordering = ['order_number']


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
    preset = models.ForeignKey(Preset, models.SET_NULL, blank=True, null=True)

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
