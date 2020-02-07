import os

from django.core.validators import URLValidator
from django.db import models
from model_utils.models import TimeStampedModel


nullable = dict(blank=True, null=True)


class Video(TimeStampedModel):
    """ Модель видео."""
    CREATED, QUEUED, PROCESS, DONE, ERROR = range(5)
    STATUS_CHOICES = (
        (CREATED, 'создано'),  # редактор создал объект в БД
        (QUEUED, 'в очереди'),  # задача на конвертацию поставлена в RabbitMQ
        (PROCESS, 'в обработке'),  # Celery worker взял задачу в обработку
        (DONE, 'готово'),  # видео успешно обработано
        (ERROR, 'ошибка'),  # ошибка обработки видео
    )

    status = models.SmallIntegerField(default=CREATED, choices=STATUS_CHOICES)
    error = models.TextField(**nullable)
    task_id = models.UUIDField(**nullable)
    source = models.URLField(validators=[URLValidator(schemes=('ftp', 'http'))])
    basename = models.UUIDField(**nullable)

    class Meta:
        app_label = 'video_transcoding'
        verbose_name = 'Видео'
        verbose_name_plural = 'Видео'

    def __str__(self):
        basename = os.path.basename(self.source)
        return f'{basename} ({self.get_status_display()})'

    def change_status(self, status: int, **fields):
        """
        Меняет статус объекта видео.

        Параллельно обновляет другие поля модели. При сохранении также
        обновляет поле modified.

        :param status: один из статусов (см. STATUS_CHOICES)
        :param fields: словарь из значений полей модели.
        """
        self.status = status
        update_fields = {'status', 'modified'}
        for k, v in fields.items():
            setattr(self, k, v)
            update_fields.add(k)
        self.save(update_fields=update_fields)
