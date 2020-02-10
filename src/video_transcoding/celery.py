from celery import Celery
from django.conf import settings

from video_transcoding import defaults

app = Celery(defaults.CELERY_APP_NAME)
app.config_from_object(defaults.VIDEO_TRANSCODING_CELERY_CONF)
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
