import os
import signal
from typing import cast
from unittest import mock
from uuid import UUID, uuid4

import requests
from billiard.exceptions import SoftTimeLimitExceeded
from celery.exceptions import Retry
from celery.platforms import EX_OK
from celery.signals import worker_shutting_down
from django.test import TestCase

from video_transcoding import models, tasks, transcoding, defaults
from video_transcoding.tests.base import BaseTestCase


class TranscodeTaskVideoStateTestCase(BaseTestCase):
    """ Tests Video status handling in transcode task."""

    def setUp(self):
        super().setUp()
        self.video = models.Video.objects.create(
            status=models.Video.QUEUED,
            task_id=uuid4(),
            source='ftp://ya.ru/1.mp4')
        self.handle_patcher = mock.patch(
            'video_transcoding.tasks.TranscodeVideo.process_video')
        self.handle_mock: mock.MagicMock = self.handle_patcher.start()
        self.retry_patcher = mock.patch('celery.Task.retry',
                                        side_effect=Retry)
        self.retry_mock = self.retry_patcher.start()

    def tearDown(self):
        super().tearDown()
        self.handle_patcher.stop()
        self.retry_patcher.stop()

    def run_task(self):
        result = tasks.transcode_video.apply(
            task_id=str(self.video.task_id),
            args=(self.video.id,),
            throw=True)
        return result

    def test_lock_video(self):
        """
        Video transcoding starts with status PROCESS and finished with DONE.
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
        Video transcoding failed with ERROR status and error message saved.
        """
        error = transcoding.TranscodeError("my error " * 100)
        self.handle_mock.side_effect = error

        self.run_task()

        self.video.refresh_from_db()
        self.assertEqual(self.video.status, models.Video.ERROR)
        self.assertEqual(self.video.error, repr(error))

    def test_skip_incorrect_status(self):
        """
        Unexpected video statuses lead to task retry.
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
        Locked video leads to task retry.
        """
        # We can't simulate database lock, so just simulate this with
        # DoesNotExist in select_related(skip_locked=True)
        self.video.pk += 1

        with self.assertRaises(Retry):
            self.run_task()

        self.handle_mock.assert_not_called()

    def test_skip_unlock_incorrect_status(self):
        """
        Video status is not changed in db if video was modified somewhere else.
        """

        # noinspection PyUnusedLocal
        def change_status(video, *args, **kwargs):
            video.change_status(models.Video.QUEUED)

        self.handle_mock.side_effect = change_status

        with self.assertRaises(RuntimeError):
            self.run_task()

        self.video.refresh_from_db()
        self.assertEqual(self.video.status, models.Video.QUEUED)

    def test_skip_unlock_foreign_task_id(self):
        """
        Video status is not changed in db if it was locked by another task.
        """
        task_id = uuid4()

        # noinspection PyUnusedLocal
        def change_status(video, *args, **kwargs):
            video.task_id = task_id
            video.save()

        self.handle_mock.side_effect = change_status

        with self.assertRaises(RuntimeError):
            self.run_task()

        self.video.refresh_from_db()
        self.assertEqual(self.video.task_id, task_id)
        self.assertEqual(self.video.status, models.Video.PROCESS)

    def test_retry_task_on_worker_shutdown(self):
        """
        For graceful restart Video status should be reverted to queued on task
        retry.
        """
        exc = SoftTimeLimitExceeded()
        self.handle_mock.side_effect = exc

        with self.assertRaises(Retry):
            self.run_task()

        self.video.refresh_from_db()
        self.assertEqual(self.video.status, models.Video.QUEUED)
        self.assertEqual(self.video.error, repr(exc))
        self.retry_mock.assert_called_once_with(countdown=10)


class ProcessVideoTestCase(BaseTestCase):
    """
    Tests video processing in terms of transcoding and uploading in
    transcode_video task.
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
        self.response = requests.Response()
        self.response.status_code = 200
        self.response.raw = mock.MagicMock()
        self.requests_patcher = mock.patch('requests.api.request',
                                           return_value=self.response)
        self.requests_mock = self.requests_patcher.start()
        self.copy_patcher = mock.patch('shutil.copyfileobj')
        self.copy_mock = self.copy_patcher.start()

    def tearDown(self):
        super().tearDown()
        self.transcoder_patcher.stop()
        self.open_patcher.stop()
        self.requests_patcher.stop()
        self.copy_patcher.stop()

    def run_task(self, download: bool = False):
        return tasks.transcode_video.process_video(
            self.video, self.basename, download=download)

    @staticmethod
    def temp_dir_mock() -> mock.MagicMock:
        tmp_dir = os.path.join(defaults.VIDEO_TEMP_DIR, 'video-1')
        return cast(mock.MagicMock,
                    mock.patch('tempfile.TemporaryDirectory.__enter__',
                               return_value=tmp_dir))

    def test_pass_args_to_transcoder(self):
        """
        Source file link and destination path are passed correctly to
        transcoding and uploading methods. Temporary dir is created and removed.
        """
        with self.temp_dir_mock() as tmp:
            self.run_task()
        tmp.assert_called_once_with()

        filename = f'{self.basename}1080p.mp4'
        destination = os.path.join(tmp.return_value, filename)
        self.transcoder_mock.assert_called_once_with(
            self.video.source, destination)

        self.open_mock.assert_called_once_with(destination, 'rb')

        timeout = (tasks.CONNECT_TIMEOUT, tasks.UPLOAD_TIMEOUT)
        self.requests_mock.assert_called_once_with(
            'put', os.path.join(defaults.VIDEO_ORIGINS[0], filename),
            data=self.open_mock.return_value, timeout=timeout)

    def test_pass_downloaded_file_to_transcoder(self):
        """
        Downloaded source file in temporary directory is passed as input to
        transcoder.

        """
        with self.temp_dir_mock() as tmp:
            self.run_task(download=True)
        tmp.assert_called_once_with()
        tmp_dir = tmp.return_value

        filename = f'{self.basename}1080p.mp4'
        temp_file = os.path.join(tmp_dir, f'{self.basename}.src.bin')
        destination = os.path.join(tmp_dir, filename)
        self.transcoder_mock.assert_called_once_with(temp_file, destination)

    def test_download_source(self):
        """
        Source file is downloaded to temporary directory.
        """
        with self.temp_dir_mock() as tmp:
            dest = os.path.join(tmp.return_value, 'dest')
            tasks.transcode_video.download(self.video.source, dest)

        # Requested source file from web server
        timeout = (tasks.CONNECT_TIMEOUT, tasks.DOWNLOAD_TIMEOUT)
        self.requests_mock.assert_called_once_with(
            'get', self.video.source, params=None, stream=True, timeout=timeout,
            allow_redirects=True)

        # Opened temp file in write mode
        self.open_mock.assert_called_once_with(dest, 'wb')

        # Copied response body to file
        self.copy_mock.assert_called_once_with(
            self.response.raw, self.open_mock.return_value)

    def test_download_chunked(self):
        """
        Downloading gzipped source file supported.
        """
        self.response.headers['Transfer-encoding'] = 'gzip'
        self.response.raw.stream.return_value = (
            'first_chunk',
            'second_chunk'
        )
        with self.temp_dir_mock() as tmp:
            dest = os.path.join(tmp.return_value, 'dest')
            tasks.transcode_video.download(self.video.source, dest)

        self.open_mock.return_value.write.assert_has_calls(
            [mock.call('first_chunk'), mock.call('second_chunk')])

    def test_download_handle_server_status(self):
        """
        Non-20x server status is an error.
        """
        self.response.status_code = 404
        with self.temp_dir_mock() as tmp:
            dest = os.path.join(tmp.return_value, 'dest')
            with self.assertRaises(requests.HTTPError) as e:
                tasks.transcode_video.download(self.video.source, dest)
            self.assertEqual(e.exception.response.status_code, 404)

    def test_store_result(self):
        """
        Transcoded file is correctly stored to origin server.
        """
        with self.temp_dir_mock() as tmp:
            dest = os.path.join(tmp.return_value, 'dest')
            tasks.transcode_video.store(dest)

        # Opened temp file for reading
        self.open_mock.assert_called_once_with(dest, 'rb')

        # Put file to origin server
        timeout = (tasks.CONNECT_TIMEOUT, tasks.DOWNLOAD_TIMEOUT)
        store_url = os.path.join(
            defaults.VIDEO_ORIGINS[0], os.path.basename(dest))
        self.requests_mock.assert_called_once_with(
            'put', store_url, data=self.open_mock.return_value,
            timeout=timeout)

    def test_store_handle_response_status(self):
        """
        Failed store request is and error.
        """
        self.response.status_code = 403

        with self.temp_dir_mock() as tmp:
            dest = os.path.join(tmp.return_value, 'dest')
            with self.assertRaises(requests.HTTPError) as e:
                tasks.transcode_video.store(dest)
            self.assertEqual(e.exception.response.status_code, 403)


class CelerySignalsTestCase(TestCase):
    """ Celery signals handling tests."""

    def setUp(self) -> None:
        super().setUp()
        self.kill_patcher = mock.patch('os.killpg')
        self.kill_mock = self.kill_patcher.start()

    def tearDown(self) -> None:
        super().tearDown()
        self.kill_patcher.stop()

    def test_handle_worker_shutting_down(self):
        """
        On worker_shutting_down signal send SIGUSR1 to child process group.
        """
        worker_shutting_down.send(sender=None, sig="TERM", how="Warm",
                                  exitcode=EX_OK)

        self.kill_mock.assert_called_once_with(os.getpid(), signal.SIGUSR1)
