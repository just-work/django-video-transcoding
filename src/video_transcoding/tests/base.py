from unittest import mock
from urllib.parse import ParseResult, urlparse, urlunparse
from uuid import uuid4

from celery.result import AsyncResult
from django.test import TestCase
from fffw.graph import VideoMeta, TS, Scene, AudioMeta

from video_transcoding.transcoding import profiles, metadata, workspace


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
    @staticmethod
    def default_profile() -> profiles.Profile:
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


class MemoryWorkspace:
    def __init__(self, basename: str):
        self.tree = {}
        self.root = workspace.Collection(basename)

    def ensure_collection(self, path: str) -> workspace.Collection:
        parts = self.root.parts + tuple(path.strip('/').split('/'))
        t = self.tree
        for p in parts:
            t = t.setdefault(p, {})
        return workspace.Collection(*parts)

    def create_collection(self, c: workspace.Collection) -> None:
        t = self.tree
        for p in c.parts:
            t = t.setdefault(p, {})

    def delete_collection(self, c: workspace.Collection) -> None:
        t = self.tree
        parent = p = None
        for p in c.parts:
            parent = t
            try:
                t = t[p]
            except KeyError:  # pragma: no cover
                break
        else:
            del parent[p]

    def exists(self, r: workspace.Resource) -> bool:
        t = self.tree
        for p in r.parts:
            try:
                t = t[p]
            except KeyError:
                return False
        else:
            return True

    def read(self, f: workspace.File) -> str:
        t = self.tree
        for p in f.parts:
            t = t[p]
        return t

    def write(self, f: workspace.File, content: str) -> None:
        t = self.tree
        for p in f.parts[:-1]:
            t = t[p]
        t[f.parts[-1]] = content

    @staticmethod
    def get_absolute_uri(r: workspace.Resource) -> ParseResult:
        path = '/'.join(r.parts)
        # noinspection PyArgumentList
        return urlparse(urlunparse(('memory', '', path, '', '', '')))
