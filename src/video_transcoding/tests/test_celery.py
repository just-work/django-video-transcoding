import os
import signal
from unittest import mock

from celery import signals
from django.test import TestCase


class CelerySignalsTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        __import__('video_transcoding.celery')

    @mock.patch('os.setpgrp')
    def test_worker_init_signal(self, m: mock.Mock):
        """
        Celery master process creates a process group to send signals to all
        children via killpg.
        """
        signals.worker_init.send(None)
        m.assert_called_once_with()

    @mock.patch('os.killpg')
    def test_worker_shutting_down_signal(self, m: mock.Mock):
        """
        After receiving TERM signal celery master process propagates it to
        all worker processes via process group.
        """
        signals.worker_shutting_down.send(None)
        m.assert_called_once_with(os.getpid(), signal.SIGUSR1)

        m.side_effect = ProcessLookupError()

        try:
            signals.worker_shutting_down.send(None)
        except ProcessLookupError:  # pragma: no cover
            self.fail("exception not handled")
