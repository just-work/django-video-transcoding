from django.test import TestCase
from fffw.analysis.ffprobe import ProbeInfo
from fffw.graph import VideoMeta, AudioMeta

from video_transcoding.tests import base
from video_transcoding.transcoding import analysis


class MKVPlaylistAnalyzerTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.info = ProbeInfo(
            streams=[
                {'duration': 30.0},
                {'duration': 45.0},
            ],
            format={
                'duration': 60.0,
            }
        )
        self.analyzer = analysis.MKVPlaylistAnalyzer(self.info)

    def test_multiple_streams_duration_normalize(self):
        d = self.analyzer.get_duration(self.info.streams[0])

        self.assertEqual(d, 30.0)

        self.info.streams[0]['duration'] = 0.0

        d = self.analyzer.get_duration(self.info.streams[0])

        self.assertEqual(d, 0.0)

        del self.info.streams[1:]

        d = self.analyzer.get_duration(self.info.streams[0])

        self.assertEqual(d, 60.0)


class MKVSegmentAnalyzerTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.info = ProbeInfo(
            streams=[
                {'duration': 30.0, 'bit_rate': 3_000_000},
                {'duration': 45.0, 'bit_rate': 128_000},
            ],
            format={
                'duration': 60.0, 'bit_rate': 3_500_000,
            }
        )
        self.analyzer = analysis.MKVSegmentAnalyzer(self.info)

    def test_multiple_streams_duration_normalize(self):
        d = self.analyzer.get_duration(self.info.streams[0])

        self.assertEqual(d, 30.0)

        self.info.streams[0]['duration'] = 0.0

        d = self.analyzer.get_duration(self.info.streams[0])

        self.assertEqual(d, 0.0)

        del self.info.streams[1:]

        d = self.analyzer.get_duration(self.info.streams[0])

        self.assertEqual(d, 60.0)

    def test_multiple_streams_bitrate_normalize(self):
        b = self.analyzer.get_bitrate(self.info.streams[0])

        self.assertEqual(b, 3_000_000)

        self.info.streams[0]['bit_rate'] = 0

        b = self.analyzer.get_bitrate(self.info.streams[0])

        self.assertEqual(b, 0)

        del self.info.streams[1:]

        d = self.analyzer.get_bitrate(self.info.streams[0])

        self.assertEqual(d, 3_500_000)


class FFprobeHLSAnalyzerTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.info = ProbeInfo(
            streams=[
                {
                    'duration': 30.0,
                    'bit_rate': 3_000_000,
                    'codec_type': 'video',
                    'tags': {'variant_bitrate': 2_200_000}
                },
                {
                    'duration': 45.0,
                    'bit_rate': 128_000,
                    'codec_type': 'audio',
                },
            ],
            format={
                'duration': 60.0, 'bit_rate': 3_500_000,
            }
        )
        self.analyzer = analysis.FFProbeHLSAnalyzer(self.info)

    def test_container_duration_normalize(self):
        d = self.analyzer.get_duration(self.info.streams[0])

        self.assertEqual(d, 30.0)

        self.info.streams[0]['duration'] = 0.0

        d = self.analyzer.get_duration(self.info.streams[0])
        self.assertEqual(d, 60.0)

    def test_variant_bitrate_normalize(self):
        b = self.analyzer.get_bitrate(self.info.streams[0])

        self.assertEqual(b, 3_000_000)

        self.info.streams[0]['bit_rate'] = 0

        b = self.analyzer.get_bitrate(self.info.streams[0])

        self.assertEqual(b, 2_000_000)

        del self.info.streams[0]['tags']['variant_bitrate']

        b = self.analyzer.get_bitrate(self.info.streams[0])

        self.assertEqual(b, 0)

        del self.info.streams[0]['tags']

        b = self.analyzer.get_bitrate(self.info.streams[0])

        self.assertEqual(b, 0)

    def test_skip_unrelated_streams(self):
        streams = self.analyzer.analyze()

        self.assertEqual(len(streams), 2)
        self.assertIsInstance(streams[0], VideoMeta)
        self.assertIsInstance(streams[1], AudioMeta)

        self.info.streams[1]['tags'] = {'comment': 'a:group0'}

        streams = self.analyzer.analyze()

        self.assertEqual(len(streams), 1)
        self.assertIsInstance(streams[0], VideoMeta)

        self.info.streams[0]['codec_type'] = 'side_data'

        streams = self.analyzer.analyze()

        self.assertEqual(len(streams), 0)
