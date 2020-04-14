import os
import signal
from typing import Any

from celery import Celery
from celery.signals import worker_shutting_down
from celery.utils.log import get_logger
from django.conf import settings

from video_transcoding import defaults

app = Celery(defaults.CELERY_APP_NAME)
app.config_from_object(defaults.VIDEO_TRANSCODING_CELERY_CONF)
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


# noinspection PyUnusedLocal
@worker_shutting_down.connect
def send_term_to_children(**kwargs: Any) -> None:
    get_logger(app.__module__).warning(
        "Received shutdown signal, sending SIGUSR1 to worker process group")
    # raises SoftTimeLimitExceeded in worker processes
    os.killpg(os.getpid(), signal.SIGUSR1)
