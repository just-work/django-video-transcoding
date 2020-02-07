from video_transcoding import tasks


def send_transcode_task(video):
    """
    Ставит задачу на транскодирование видео.

    При успешной постановки задачи в очередь меняет статус видео на QUEUED и
    сохраняет идентификатор celery-задачи.

    :param video: объект видеофайла
    :type video: video.models.Video
    :returns: объект результата Celery-задачи
    :rtype: celery.result.AsyncResult
    """
    result = tasks.transcode_video.apply_async(args=(video.pk,), countdown=10)
    video.change_status(video.QUEUED, task_id=result.task_id)
    return result
