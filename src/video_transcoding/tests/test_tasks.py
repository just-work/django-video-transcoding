from dataclasses import asdict
from datetime import timedelta
from unittest import mock
from uuid import UUID, uuid4

from billiard.exceptions import SoftTimeLimitExceeded
from celery.exceptions import Retry

from video_transcoding import models, tasks
from video_transcoding.tests import base
from video_transcoding.transcoding import profiles


class TranscodeTaskVideoStateTestCase(base.BaseTestCase):
    """ Tests Video status handling in transcode task."""

    def setUp(self):
        super().setUp()
        self.video = models.Video.objects.create(
            status=models.Video.QUEUED,
            task_id=uuid4(),
            source='ftp://ya.ru/1.mp4')
        cls = "video_transcoding.tasks.TranscodeVideo"
        self.handle_patcher = mock.patch(
            f'{cls}.process_video',
            return_value={"duration": 42.0})
        self.handle_mock: mock.MagicMock = self.handle_patcher.start()
        self.retry_patcher = mock.patch(f'{cls}.retry',
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
        error = RuntimeError("my error " * 100)
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

    def test_init_preset_default(self):
        preset = tasks.transcode_video.init_preset(None)
        self.assertEqual(preset, profiles.DEFAULT_PRESET)

    def test_init_preset_from_video(self):
        p = models.Preset.objects.create()
        vt = models.VideoTrack.objects.create(
            name='v',
            preset=p,
            params={
                'codec': 'libx264',
                'constant_rate_factor': 23,
                'preset': 'slow',
                'max_rate': 1_500_000,
                'buf_size': 3_000_000,
                'profile': 'main',
                'pix_fmt': 'yuv420p',
                'width': 1920,
                'height': 1080,
                'frame_rate': 30.0,
                'gop_size': 30,
                'force_key_frames': 'formula'
            })
        at = models.AudioTrack.objects.create(
            name='a',
            preset=p,
            params={
                'codec': 'libfdk_aac',
                'bitrate': 128_000,
                'channels': 2,
                'sample_rate': 44100,
            }
        )
        vp = models.VideoProfile.objects.create(
            preset=p,
            segment_duration=timedelta(seconds=1.0),
            condition={
                'min_width': 1,
                'min_height': 2,
                'min_bitrate': 3,
                'min_frame_rate': 4.0,
                'min_dar': 5.0,
                'max_dar': 6.0,
            }
        )
        ap = models.AudioProfile.objects.create(
            preset=p,
            condition={
                'min_sample_rate': 1,
                'min_bitrate': 2,
            }
        )
        vp.videoprofiletracks_set.create(track=vt)
        ap.audioprofiletracks_set.create(track=at)

        preset = tasks.transcode_video.init_preset(p)

        self.assertIsInstance(preset, profiles.Preset)
        self.assertEqual(len(preset.video_profiles), 1)
        vp = preset.video_profiles[0]
        self.assertEqual(vp, profiles.VideoProfile(
            condition=profiles.VideoCondition(
                min_width=1,
                min_height=2,
                min_bitrate=3,
                min_frame_rate=4.0,
                min_dar=5.0,
                max_dar=6.0,

            ),
            segment_duration=1.0,
            video=['v']
        ))
        self.assertEqual(len(preset.video), 1)
        v = preset.video[0]
        self.assertEqual(v, profiles.VideoTrack(
            id='v',
            codec='libx264',
            constant_rate_factor=23,
            preset='slow',
            max_rate=1_500_000,
            buf_size=3_000_000,
            profile='main',
            pix_fmt='yuv420p',
            width=1920,
            height=1080,
            frame_rate=30.0,
            gop_size=30,
            force_key_frames='formula'
        ))

        self.assertEqual(len(preset.audio_profiles), 1)
        ap = preset.audio_profiles[0]
        self.assertEqual(ap, profiles.AudioProfile(
            condition=profiles.AudioCondition(
                min_sample_rate=1,
                min_bitrate=2,
            ),
            audio=['a'],
        ))
        self.assertEqual(len(preset.audio), 1)
        a = preset.audio[0]
        self.assertEqual(a, profiles.AudioTrack(
            id='a',
            codec='libfdk_aac',
            bitrate=128_000,
            channels=2,
            sample_rate=44100,
        ))


class ProcessVideoTestCase(base.MetadataMixin, base.BaseTestCase):
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
        self.video.basename = UUID(self.basename)

        self.strategy_patcher = mock.patch(
            'video_transcoding.strategy.ResumableStrategy')
        self.strategy_mock = self.strategy_patcher.start()
        self.meta = self.make_meta(30.0)
        # noinspection PyTypeChecker
        self.strategy_mock.return_value.return_value = self.meta

    def tearDown(self):
        super().tearDown()
        self.strategy_patcher.stop()

    def run_task(self):
        return tasks.transcode_video.process_video(self.video)

    def test_process_video(self):
        result = self.run_task()

        self.strategy_mock.assert_called_once_with(
            source_uri=self.video.source,
            basename=self.video.basename.hex,
            preset=tasks.transcode_video.init_preset(self.video.preset),
        )
        self.strategy_mock.return_value.assert_called_once_with()

        # noinspection PyTypeChecker
        expected = asdict(self.meta)
        streams = expected['audios'] + expected['videos']
        for s in streams:
            for f in ('scenes', 'streams', 'start', 'device'):
                s.pop(f, None)
        duration = min(s['duration'] for s in streams)
        expected['duration'] = duration
        self.assertEqual(result, expected)
