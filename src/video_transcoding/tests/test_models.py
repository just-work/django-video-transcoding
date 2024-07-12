from unittest import mock
from uuid import uuid4, UUID

from celery.result import AsyncResult

from video_transcoding import models
from video_transcoding.tests.base import BaseTestCase


class VideoModelTestCase(BaseTestCase):
    """ Video django model tests."""
    def setUp(self):
        self.on_commit_patcher = mock.patch('django.db.transaction.on_commit',
                                            side_effect=self.on_commit)
        self.on_commit_mock = self.on_commit_patcher.start()
        self.apply_async_patcher = mock.patch(
            'video_transcoding.tasks.transcode_video.apply_async',
            return_value=AsyncResult(str(uuid4())))
        self.apply_async_mock = self.apply_async_patcher.start()

    def tearDown(self):
        self.on_commit_patcher.stop()
        self.apply_async_patcher.stop()

    @staticmethod
    def on_commit(func):
        func()

    def test_send_transcode_task(self):
        """ When new video is created, a transcode task is sent."""
        v = models.Video.objects.create(source='http://ya.ru/1.mp4')
        self.on_commit_mock.assert_called()
        self.apply_async_mock.assert_called_once_with(
            args=(v.id,),
            countdown=10)
        v.refresh_from_db()
        self.assertEqual(v.status, models.Video.QUEUED)
        result = self.apply_async_mock.return_value
        self.assertEqual(v.task_id, UUID(result.task_id))
