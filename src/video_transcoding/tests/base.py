from unittest import mock
from uuid import uuid4

from celery.result import AsyncResult
from django.test import TestCase
from fffw.graph import VideoMeta, TS, Scene, AudioMeta

from video_transcoding.transcoding import profiles, metadata


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


class ProfileMixin:
    def default_profile(self) -> profiles.Profile:
        return profiles.Profile(
            video=[profiles.VideoTrack(
                frame_rate=30,
                width=1920,
                height=1080,
                profile='main',
                pix_fmt='yuv420p',
                buf_size=3_000_000,
                gop_size=30,
                max_rate=1_500_000,
                id='v',
                force_key_frames='1.0',
                codec='libx264',
                preset='slow',
                constant_rate_factor=23,
            )],
            audio=[profiles.AudioTrack(
                codec='libfdk_aac',
                id='a',
                bitrate=128_000,
                channels=2,
                sample_rate=48000,
            )],
            container=profiles.Container(segment_duration=1.0)
        )


class MetadataMixin:

    @staticmethod
    def make_meta(*scenes: float, uri='uri') -> metadata.Metadata:
        duration = sum(scenes)
        # technically, merged scenes are incorrect because start value is
        # always zero, but we don't care as we don't use them.
        return metadata.Metadata(
            uri=uri,
            videos=[
                VideoMeta(
                    bitrate=100500,
                    frame_rate=30.0,
                    dar=1.778,
                    par=1.0,
                    width=1920,
                    height=1080,
                    frames=int(duration * 30.0),
                    streams=['v'],
                    start=TS(0),
                    duration=TS(duration),
                    device=None,
                    scenes=[Scene(stream='v',
                                  duration=TS(s),
                                  start=TS(0),
                                  position=TS(0))
                            for s in scenes]
                ),
            ],
            audios=[
                AudioMeta(
                    bitrate=100500,
                    sampling_rate=48000,
                    channels=2,
                    samples=int(duration * 48000),
                    streams=['a'],
                    start=TS(0),
                    duration=TS(duration),
                    scenes=[Scene(stream='a',
                                  duration=TS(s),
                                  start=TS(0),
                                  position=TS(0))
                            for s in scenes]
                ),
            ]
        )
