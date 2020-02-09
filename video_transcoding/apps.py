from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class VideoTranscodingConfig(AppConfig):
    name = 'video_transcoding'
    verbose_name = _('Video Transcoding')

    def ready(self) -> None:
        __import__('video_transcoding.signals')
