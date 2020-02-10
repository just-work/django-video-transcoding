from unittest import mock
from uuid import uuid4

from celery.result import AsyncResult
from django.test import TestCase


class BaseTestCase(TestCase):

    def setUp(self):
        super().setUp()
        self.apply_async_patcher = mock.patch(
            'video_transcoding.tasks.transcode_video.apply_async',
            return_value=AsyncResult(str(uuid4())))
        self.apply_async_mock = self.apply_async_patcher.start()

    def tearDown(self):
        super().tearDown()
        self.apply_async_patcher.stop()
