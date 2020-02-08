from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class VideoTranscodingConfig(AppConfig):
    name = 'video_transcoding'
    label = _('Video Transcoding')

    def ready(self):
        __import__('video_transcoding.signals')
