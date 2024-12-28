from unittest import TestCase

from fffw.encoding import Stream
from fffw.graph import Scene, TS, VideoMeta, AudioMeta, VIDEO, AUDIO

from video_transcoding.transcoding import metadata


class MetadataTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.video_data = {
            'bitrate': 100500,
            'width': 1920,
            'height': 1080,
            'par': 1.0,
            'dar': 1.7778,
            'frame_rate': 30.0,
            'frames': int(30 * 1.23),
            'device': None,
            'start': 1.23,
            'duration': '1.23',
            'scenes': [{
                'duration': '1.23',
                'start': 1.23,
                'stream': 's',
                'position': 2460,
            }],
            'streams': ['stream'],
        }
        self.audio_data = {
            'bitrate': 100500,
            'sampling_rate': 44100,
            'samples': int(44100 * 1.23),
            'channels': 2,
            'start': 1.23,
            'duration': '1.23',
            'scenes': [{
                'duration': '1.23',
                'start': 1.23,
                'stream': 's',
                'position': 2460,
            }],
            'streams': ['stream'],
        }
        self.meta_data = {
            'videos': [self.video_data],
            'audios': [self.audio_data],
            'uri': 'file:///tmp/source.mp4',
        }

    def test_scenes_from_native(self):
        data = {
            'duration': '1.23',
            'start': 1.23,
            'stream': 's',
            'position': 2460,
        }
        scene = metadata.scene_from_native(data)
        self.assertIsInstance(scene, Scene)
        self.assertIsInstance(scene.duration, TS)
        self.assertEqual(scene.duration, TS(1.23))
        self.assertIsInstance(scene.start, TS)
        self.assertEqual(scene.start, TS(1.23))
        self.assertIsInstance(scene.position, TS)
        self.assertEqual(scene.position, TS(2.46))
        self.assertIsInstance(scene.stream, str)
        self.assertEqual(scene.stream, 's')

    def test_get_meta_kwargs(self):
        data = {
            'sentinel': {'deep': 'copy'},
            'start': 1.23,
            'duration': '1.23',
            'scenes': [{
                'duration': '1.23',
                'start': 1.23,
                'stream': 's',
                'position': 2460,
            }]
        }

        kwargs = metadata.get_meta_kwargs(data)

        data['sentinel']['deep'] = 'copied'
        self.assertEqual(kwargs['sentinel']['deep'], 'copy')
        self.assertIsInstance(kwargs['start'], TS)
        self.assertEqual(kwargs['start'], TS(1.23))
        self.assertIsInstance(kwargs['duration'], TS)
        self.assertEqual(kwargs['duration'], TS(1.23))
        self.assertIsInstance(kwargs['scenes'], list)
        self.assertEqual(len(kwargs['scenes']), len(data['scenes']))
        self.assertIsInstance(kwargs['scenes'][0], Scene)

    def test_video_meta_from_native(self):
        m = metadata.video_meta_from_native(self.video_data)

        self.assertIsInstance(m, VideoMeta)
        expected = VideoMeta(
            streams=['stream'],
            scenes=[Scene(
                duration=TS(1.23),
                start=TS(1.23),
                stream='s',
                position=TS(2.46),
            )],
            device=None,
            start=TS(1.23),
            duration=TS(1.23),
            bitrate=100500,
            width=1920,
            height=1080,
            par=1.0,
            dar=1.7778,
            frame_rate=30.0,
            frames=int(30 * 1.23),
        )
        self.assertEqual(m, expected)

    def test_audio_meta_from_native(self):
        m = metadata.audio_meta_from_native(self.audio_data)

        self.assertIsInstance(m, AudioMeta)
        expected = AudioMeta(
            streams=['stream'],
            scenes=[Scene(
                duration=TS(1.23),
                start=TS(1.23),
                stream='s',
                position=TS(2.46),
            )],
            start=TS(1.23),
            duration=TS(1.23),
            bitrate=100500,
            sampling_rate=44100,
            samples=int(44100 * 1.23),
            channels=2,
        )
        self.assertEqual(m, expected)

    def test_metadata_from_native(self):
        m = metadata.Metadata.from_native(self.meta_data)
        self.assertIsInstance(m, metadata.Metadata)
        self.assertIsInstance(m.uri, str)
        self.assertEqual(m.uri, 'file:///tmp/source.mp4')
        self.assertIsInstance(m.videos, list)
        self.assertEqual(len(m.videos), 1)
        self.assertIsInstance(m.videos[0], VideoMeta)
        self.assertIsInstance(m.audios, list)
        self.assertEqual(len(m.audios), 1)
        self.assertIsInstance(m.audios[0], AudioMeta)

    def test_metadata_properties(self):
        m = metadata.Metadata.from_native(self.meta_data)
        self.assertIsInstance(m.video, VideoMeta)
        self.assertEqual(m.video, m.videos[0])
        self.assertIsInstance(m.audio, AudioMeta)
        self.assertEqual(m.audio, m.audios[0])
        self.assertIsInstance(m.streams, list)
        self.assertEqual(len(m.streams), 1 + 1)
        for s in m.streams:
            self.assertIsInstance(s, Stream)
        self.assertEqual(m.streams[0].kind, VIDEO)
        self.assertEqual(m.streams[0].meta, m.videos[0])
        self.assertEqual(m.streams[1].kind, AUDIO)
        self.assertEqual(m.streams[1].meta, m.audios[0])

    def test_metadata_repr_smoke(self):
        m = metadata.Metadata.from_native(self.meta_data)
        self.assertIsInstance(repr(m), str)
