import os

from celery.result import AsyncResult

from video_transcoding import tasks, defaults
from video_transcoding import models


def send_transcode_task(video: models.Video) -> AsyncResult:
    """
    Send a video transcoding task.

    If task is successfully sent to broker, Video status is changed to QUEUED
    and Celery task identifier is saved.

    :param video: video object
    :type video: video.models.Video
    :returns: Celery task result
    :rtype: celery.result.AsyncResult
    """
    result = tasks.transcode_video.apply_async(
        args=(video.pk,),
        kwargs={'download': defaults.VIDEO_DOWNLOAD_SOURCE},
        countdown=10)
    video.change_status(video.QUEUED, task_id=result.task_id)
    return result
