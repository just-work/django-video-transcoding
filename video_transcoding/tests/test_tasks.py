import os
from unittest import mock
from uuid import UUID, uuid4

from celery.exceptions import Retry

from video_transcoding import models, tasks, transcoding, defaults
from video_transcoding.tests.base import BaseTestCase


class TranscodeTaskVideoStateTestCase(BaseTestCase):
    """ Тестирует работу со статусами видео в задаче конвертации."""

    def setUp(self):
        super().setUp()
        self.video = models.Video.objects.create(
            status=models.Video.QUEUED,
            source='ftp://ya.ru/1.mp4')
        self.handle_patcher = mock.patch(
            'video_transcoding.tasks.TranscodeVideo.process_video')
        self.handle_mock: mock.MagicMock = self.handle_patcher.start()
        self.retry_patcher = mock.patch('celery.Task.retry',
                                        side_effect=Retry)
        self.retry_patcher.start()

    def tearDown(self):
        super().tearDown()
        self.handle_patcher.stop()
        self.retry_patcher.stop()

    def run_task(self):
        result = tasks.transcode_video.apply(
            args=(self.video.id,),
            throw=True)
        return result

    def test_lock_video(self):
        """
        Видео в обработку попадает в статусе PROCESS и заканчивается в DONE.
        """
        self.video.error = "my error"
        self.video.save()

        result = self.run_task()

        video = self.handle_mock.call_args[0][0]
        self.assertEqual(video.status, models.Video.PROCESS)

        self.video.refresh_from_db()
        self.assertEqual(self.video.status, models.Video.DONE)
        self.assertIsNone(self.video.error)
        self.assertEqual(self.video.task_id, UUID(result.task_id))
        self.assertIsNotNone(self.video.basename)

    def test_mark_error(self):
        """
        При ошибке обработки видео падает в статус ERROR с сообщением об ошибке.
        """
        error = transcoding.TranscodeError("my error " * 100)
        self.handle_mock.side_effect = error

        self.run_task()

        self.video.refresh_from_db()
        self.assertEqual(self.video.status, models.Video.ERROR)
        self.assertEqual(self.video.error, error.message)

    def test_skip_incorrect_status(self):
        """
        Видео в неожиданных статусах не берутся в обработку.
        """
        self.video.status = models.Video.ERROR
        self.video.save()

        with self.assertRaises(Retry):
            self.run_task()

        self.video.refresh_from_db()
        self.assertEqual(self.video.status, models.Video.ERROR)
        self.handle_mock.assert_not_called()

    def test_skip_locked(self):
        """
        Видео, заблокированное в БД, не берется в обработку
        """
        self.video.pk += 1

        with self.assertRaises(Retry):
            self.run_task()

        self.handle_mock.assert_not_called()

    def test_skip_unlock_incorrect_status(self):
        """
        После завершения обработки видео не изменяется в БД, если оно было
        изменено в другом процессе.
        """

        # noinspection PyUnusedLocal
        def change_status(video, basename):
            video.change_status(models.Video.QUEUED)

        self.handle_mock.side_effect = change_status

        with self.assertRaises(RuntimeError):
            self.run_task()

        self.video.refresh_from_db()
        self.assertEqual(self.video.status, models.Video.QUEUED)

    def test_skip_unlock_foreign_task_id(self):
        """
        После завершения обработки видео не изменяется в БД, если оно было
        залочено другой задачей
        """
        task_id = uuid4()

        # noinspection PyUnusedLocal
        def change_status(video, basename):
            video.task_id = task_id
            video.save()

        self.handle_mock.side_effect = change_status

        with self.assertRaises(RuntimeError):
            self.run_task()

        self.video.refresh_from_db()
        self.assertEqual(self.video.task_id, task_id)
        self.assertEqual(self.video.status, models.Video.PROCESS)


class ProcessVideoTestCase(BaseTestCase):
    """
    Проверяет обработку видеофайла в рамках задачи транскодирования видео.
    """

    def setUp(self):
        super().setUp()
        self.video = models.Video.objects.create(
            status=models.Video.PROCESS,
            source='ftp://ya.ru/1.mp4')
        self.basename = uuid4().hex

        self.transcoder_patcher = mock.patch(
            'video_transcoding.transcoding.Transcoder')
        self.transcoder_mock = self.transcoder_patcher.start()
        self.open_patcher = mock.patch('builtins.open', mock.mock_open(
            read_data=b'video_result'))
        self.open_mock = self.open_patcher.start()
        self.requests_patcher = mock.patch('requests.api.request')
        self.requests_mock = self.requests_patcher.start()

    def tearDown(self):
        super().tearDown()
        self.transcoder_patcher.stop()
        self.open_patcher.stop()
        self.requests_patcher.stop()

    def run_task(self):
        return tasks.transcode_video.process_video(self.video, self.basename)

    def test_pass_args_to_transcoder(self):
        """
        Проверяет корректность передачи путей до файлов в методы
        транскодирования и загрузки результата обработки на ориджины.
        """
        tmp_dir = os.path.join(defaults.VIDEO_TEMP_DIR, 'tmp')
        with mock.patch('tempfile.TemporaryDirectory.__enter__',
                        return_value=tmp_dir) as tmp:
            self.run_task()
        tmp.assert_called_once_with()

        filename = f'{self.basename}1080p.mp4'
        destination = os.path.join(tmp_dir, filename)
        self.transcoder_mock.assert_called_once_with(
            self.video.source, destination)

        self.open_mock.assert_called_once_with(destination, 'rb')

        self.requests_mock.assert_called_once_with(
            'put', os.path.join(defaults.VIDEO_ORIGINS[0], filename),
            data=self.open_mock.return_value, timeout=(1, None))
