import os
from typing import Any, cast, Type
from uuid import UUID

from django.apps import apps
from django.core.validators import URLValidator
from django.db import models
from django.db.models.fields import related_descriptors
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from video_transcoding import defaults


class PresetBase(TimeStampedModel):
    """ Transcoding preset."""
    video_tracks: related_descriptors.ReverseManyToOneDescriptor
    audio_tracks: related_descriptors.ReverseManyToOneDescriptor
    video_profiles: related_descriptors.ReverseManyToOneDescriptor
    audio_profiles: related_descriptors.ReverseManyToOneDescriptor
    name = models.SlugField(verbose_name=_('name'), max_length=255, unique=True)

    class Meta:
        abstract = True
        verbose_name = _('Preset')
        verbose_name_plural = _('Presets')

    def __str__(self) -> str:
        return self.name


class Preset(PresetBase):
    pass


class VideoTrackBase(TimeStampedModel):
    """ Video stream transcoding parameters."""
    name = models.SlugField(verbose_name=_('name'), max_length=255, unique=False)
    params = models.JSONField(verbose_name=_('params'), default=dict)
    preset = models.ForeignKey(Preset, models.CASCADE,
                               related_name='video_tracks',
                               verbose_name=_('preset'))

    class Meta:
        abstract = True
        unique_together = (('name', 'preset'),)
        verbose_name = _('Video track')
        verbose_name_plural = _('Video tracks')

    def __str__(self) -> str:
        return f'{self.name}@{self.preset}'


class VideoTrack(VideoTrackBase):
    pass


class AudioTrackBase(TimeStampedModel):
    """ Audio stream transcoding parameters."""
    name = models.SlugField(verbose_name=_('name'), max_length=255, unique=False)
    params = models.JSONField(verbose_name=_('params'), default=dict)
    preset = models.ForeignKey(Preset, models.CASCADE,
                               related_name='audio_tracks',
                               verbose_name=_('preset'))

    class Meta:
        abstract = True
        unique_together = (('name', 'preset'),)
        verbose_name = _('Audio track')
        verbose_name_plural = _('Audio tracks')

    def __str__(self) -> str:
        return f'{self.name}@{self.preset}'


class AudioTrack(AudioTrackBase):
    pass


class VideoProfileBase(TimeStampedModel):
    """ Video transcoding profile."""
    name = models.SlugField(verbose_name=_('name'), max_length=255, unique=False)
    order_number = models.SmallIntegerField(verbose_name=_('order number'), default=0)
    condition = models.JSONField(verbose_name=_('condition'), default=dict)
    preset = models.ForeignKey(Preset, models.CASCADE,
                               related_name='video_profiles',
                               verbose_name=_('preset'))
    segment_duration = models.DurationField(verbose_name=_('segment duration'))

    video = cast(
        related_descriptors.ManyToManyDescriptor,
        models.ManyToManyField(VideoTrack,
                               verbose_name=_('Video tracks'),
                               through='VideoProfileTracks'))

    class Meta:
        abstract = True
        unique_together = (('name', 'preset'),)
        ordering = ['order_number']
        verbose_name = _('Video profile')
        verbose_name_plural = _('Video profiles')

    def __str__(self) -> str:
        return f'{self.name}@{self.preset}'


class VideoProfile(VideoProfileBase):
    pass


class VideoProfileTracksBase(models.Model):
    profile = models.ForeignKey(VideoProfile, models.CASCADE, verbose_name=_('profile'))
    track = models.ForeignKey(VideoTrack, models.CASCADE, verbose_name=_('track'))
    order_number = models.SmallIntegerField(default=0, verbose_name=_('order number'))

    class Meta:
        abstract = True
        unique_together = (('profile', 'track'),)
        ordering = ['order_number']
        verbose_name = _('Video profile track')
        verbose_name_plural = _('Video profile tracks')

    def __str__(self) -> str:
        return f'{self.track.name}/{self.profile.name}@{self.profile.preset}'


class VideoProfileTracks(VideoProfileTracksBase):
    pass


class AudioProfileBase(TimeStampedModel):
    """ Audio transcoding profile."""
    name = models.SlugField(verbose_name=_('name'), max_length=255, unique=False)
    order_number = models.SmallIntegerField(verbose_name=_('order number'), default=0)
    condition = models.JSONField(verbose_name=_('condition'), default=dict)
    preset = models.ForeignKey(Preset, models.CASCADE,
                               related_name='audio_profiles',
                               verbose_name=_('preset'))

    audio = cast(
        related_descriptors.ManyToManyDescriptor,
        models.ManyToManyField(AudioTrack,
                               verbose_name=_('Audio tracks'),
                               through='AudioProfileTracks'))

    class Meta:
        abstract = True
        unique_together = (('name', 'preset'),)
        ordering = ['order_number']
        verbose_name = _('Audio profile')
        verbose_name_plural = _('Audio profiles')

    def __str__(self) -> str:
        return f'{self.name}@{self.preset}'


class AudioProfile(AudioProfileBase):
    pass


class AudioProfileTracksBase(models.Model):
    profile = models.ForeignKey(AudioProfile, models.CASCADE, verbose_name=_('profile'))
    track = models.ForeignKey(AudioTrack, models.CASCADE, verbose_name=_('track'))
    order_number = models.SmallIntegerField(default=0, verbose_name=_('order number'))

    class Meta:
        abstract = True
        unique_together = (('profile', 'track'),)
        ordering = ['order_number']
        verbose_name = _('Audio profile track')
        verbose_name_plural = _('Audio profile tracks')

    def __str__(self) -> str:
        return f'{self.track.name}/{self.profile.name}@{self.profile.preset}'


class AudioProfileTracks(AudioProfileTracksBase):
    pass


class Video(TimeStampedModel):
    """ Video model."""
    CREATED, QUEUED, PROCESS, DONE, ERROR = range(5)
    STATUS_CHOICES = (
        (CREATED, _('new')),  # And editor created video in db
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
    source = models.URLField(
        verbose_name=_('Source'),
        validators=[URLValidator(schemes=('ftp', 'http', 'https'))])
    basename = models.UUIDField(blank=True, null=True, verbose_name=_('Basename'))
    preset = models.ForeignKey(Preset,
                               models.SET_NULL,
                               verbose_name=_('preset'),
                               blank=True,
                               null=True)
    metadata = models.JSONField(verbose_name=_('metadata'), blank=True, null=True)
    duration = models.DurationField(verbose_name=_('duration'), blank=True, null=True)

    class Meta:
        abstract = defaults.VIDEO_MODEL != 'video_transcoding.Video'
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


def get_video_model() -> Type[Video]:
    app_label, model_name = defaults.VIDEO_MODEL.split('.')
    return cast(Type[Video], apps.get_registered_model(app_label, model_name))
