import os
import tempfile
from typing import Optional
from uuid import UUID, uuid4

import celery
import requests
from django.db.transaction import atomic

from video_transcoding import models, transcoding, defaults
from video_transcoding.celery import app
from video_transcoding.utils import LoggerMixin

DESTINATION_FILENAME = '{basename}1080p.mp4'


class TranscodeVideo(LoggerMixin, celery.Task):
    """ Задача на обработку видео."""
    name = 'video.transcode'
    routing_key = 'video'

    def run(self, video_id: int):
        """
        Выполняет транскодирование видео.

        1. Блокирует видео, меняя статус с QUEUED на PROCESS и запоминая task_id
        2. Выполняет обработку
        3. В случае успеха проставляет статус DONE и basename результата
        4. В случае неудачи проставляет статус ERROR и сообщение об ошибке.

        :param video_id: первичный ключ видео.
        """
        status = models.Video.DONE
        error = basename = None
        video = self.lock_video(video_id)
        try:
            basename = uuid4().hex
            self.process_video(video, basename)
        except transcoding.TranscodeError as e:
            basename = None
            status = models.Video.ERROR
            error = e.message
        finally:
            self.unlock_video(video_id, status, error, basename)
        return error

    def select_for_update(self, video_id: int, status: int) -> models.Video:
        """ Блокирует видео для обновлений в БД.

        :param video_id: первичный ключ видео
        :param status: ожидаемый статус видео
        :returns: объект видео, полученный из БД

        :raises models.Video.DoesNotExist: в случае, если не удалось найти
        видео с указанным первичным ключом и заблокировать его для обновлений
        :raises ValueError: вслучае если статус видео отличается от ожидаемого
        """
        try:
            video = models.Video.objects.select_for_update(
                skip_locked=True, of=('self',)).get(pk=video_id)
        except models.Video.DoesNotExist:
            self.logger.error("Can't lock video %s", video_id)
            raise
        if video.status != status:
            self.logger.error("Unexpected video %s status %s",
                              video.id, video.get_status_display())
            raise ValueError(video.status)
        return video

    @atomic
    def lock_video(self, video_id: int) -> models.Video:
        """
        Получает из БД видео в ожидаемых статусах и переставляет статус на
        "в обработке".

        :param video_id: первичный ключ объекта видео
        :returns: объект видео, полученный из БД
        :raises Retry: в случае ошибки блокирования видео или если статус
            видео отличается от "в очереди".
        """
        try:
            video = self.select_for_update(video_id, models.Video.QUEUED)
        except (models.Video.DoesNotExist, ValueError) as e:
            # в случае ошибки блокировки повторяем попытку
            raise self.retry(exc=e)

        video.change_status(models.Video.PROCESS,
                            task_id=self.request.id)
        return video

    @atomic
    def unlock_video(self, video_id: int, status: int, error: Optional[str],
                     basename: Optional[str]):
        """
        Помечает видео одним из финальных статусов.

        :param video_id: первичный ключ объекта видео
        :param status: финальный статус видео
            (models.Video.DONE, models.Video.ERROR)
        :param error: текстовое сообщение об ошибке
        :param basename: UUID-подобный идентификатор результата обработки
        :raises RuntimeError:
        """
        try:
            video = self.select_for_update(video_id, models.Video.PROCESS)
            if video.task_id != UUID(self.request.id):
                raise ValueError(video.task_id)
        except (models.Video.DoesNotExist, ValueError) as e:
            # в случае ошибки блокировки ничего не меняем, т.к. кто-то другой
            # изменил видео пока мы над ним работали
            raise RuntimeError("Can't unlock locked video %s: %s",
                               video_id, repr(e))

        video.change_status(status, error=error, basename=basename)

    def process_video(self, video: models.Video, basename: str):
        """ Собственно, транскодирование видео."""
        with tempfile.TemporaryDirectory(dir=defaults.VIDEO_TEMP_DIR,
                                         prefix=f'video-{video.pk}-') as d:
            destination = os.path.join(d, f'{basename}1080p.mp4')
            self.transcode(video.source, destination)
            self.store(destination)
        self.logger.info("Processing done")

    def transcode(self, source: str, destination: str):
        """
        Стартует процесс транскодирования.

        :param source: ссылка на исходник
        :param destination: путь для результата
        """
        self.logger.info("Start transcoding %s to %s",
                         source, destination)
        transcoder = transcoding.Transcoder(source, destination)
        transcoder.transcode()
        self.logger.info("Transcoding %s finished", source)

    def store(self, destination: str):
        """
        Загружает результат транскодирования на ориджины.

        :param destination: путь до результата транскодирования.
        """
        self.logger.info("Start saving %s to origins", destination)
        filename = os.path.basename(destination)
        for origin in defaults.VIDEO_ORIGINS:
            url = os.path.join(origin, filename)
            self.logger.debug("Uploading %s to %s", destination, url)
            with open(destination, 'rb') as f:
                response = requests.put(url, data=f, timeout=(1, None))
                response.raise_for_status()
            self.logger.info("Uploaded to %s", url)
        self.logger.info("%s save finished", destination)


transcode_video = app.register_task(TranscodeVideo())
