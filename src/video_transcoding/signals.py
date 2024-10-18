from typing import Any

import celery
from django.core.signals import request_started, request_finished
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from video_transcoding import helpers, models
from celery.signals import task_prerun, task_postrun


# noinspection PyUnusedLocal
@receiver(post_save, sender=models.get_video_model())
def send_transcode_task(sender: Any, *, instance: models.Video, created: bool,
                        **kw: Any) -> None:
    if not created:
        return
    transaction.on_commit(lambda: helpers.send_transcode_task(instance))


# noinspection PyUnusedLocal
@task_prerun.connect
def send_request_started(task: celery.Task, **kwargs: Any) -> None:
    """
    Send request_started signal to launch django life cycle handlers.
    """
    request_started.send(sender=task.__class__, request=task.request)


# noinspection PyUnusedLocal
@task_postrun.connect
def send_request_finished(task: celery.Task, **kwargs: Any) -> None:
    """
    Send request_finished signal to launch django life cycle handlers.
    """
    request_finished.send(sender=task.__class__, request=task.request)
