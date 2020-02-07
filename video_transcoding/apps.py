from django.apps import AppConfig


class VideoTranscodingConfig(AppConfig):
    name = 'video_transcoding'

    def ready(self):
        __import__('video_transcoding.signals')
