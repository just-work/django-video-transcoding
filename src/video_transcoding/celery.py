import os
import signal
from typing import Any

from celery import Celery
from celery import signals
from celery.utils.log import get_logger
from django.conf import settings

from video_transcoding import defaults

app = Celery(defaults.CELERY_APP_NAME)
app.config_from_object(defaults.VIDEO_TRANSCODING_CELERY_CONF)
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


# noinspection PyUnusedLocal
@signals.worker_init.connect
def set_same_process_group(**kwargs: Any) -> None:
    logger = get_logger(app.__module__)
    os.setpgrp()
    logger.info("Set process group to %s for %s",
                os.getpgid(os.getpid()), os.getpid())


# noinspection PyUnusedLocal
@signals.worker_shutting_down.connect
def send_term_to_children(**kwargs: Any) -> None:
    logger = get_logger(app.__module__)
    logger.warning(
        "Received shutdown signal, sending SIGUSR1 to worker process group")
    # raises SoftTimeLimitExceeded in worker processes
    try:
        os.killpg(os.getpid(), signal.SIGUSR1)
    except ProcessLookupError:
        logger.error("failed to send SIGUSR1 to %s", os.getpid())
