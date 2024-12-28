import json
from dataclasses import asdict
from typing import Type, TYPE_CHECKING
from unittest import mock

from django.test import TestCase
from fffw.analysis import ffprobe
from fffw.graph import VIDEO, AUDIO

from video_transcoding.tests import base
from video_transcoding.transcoding import extract


class ExtractorBaseTestCase(base.MetadataMixin, TestCase):
    analyzer: str
    extractor_class: Type[extract.Extractor]

    def setUp(self):
        super().setUp()
        self.meta = self.make_meta(30.0)
        self.analyzer_instance = mock.MagicMock()
        meta = [s.meta for s in self.meta.streams]
        self.analyze_mock = self.analyzer_instance.analyze
        self.analyze_mock.return_value = meta
        self.analyzer_patcher = mock.patch(
            f'video_transcoding.transcoding.analysis.{self.analyzer}',
            return_value=self.analyzer_instance
        )
        self.analyzer_mock = self.analyzer_patcher.start()
        self.mediainfo_pacher = mock.patch(
            'video_transcoding.transcoding.extract.Extractor.mediainfo',
            return_value=mock.sentinel.mediainfo)
        self.mediainfo_mock = self.mediainfo_pacher.start()
        self.ffprobe_patcher = mock.patch(
            'video_transcoding.transcoding.extract.Extractor.ffprobe',
            return_value=mock.sentinel.ffprobe
        )
        self.ffprobe_mock = self.ffprobe_patcher.start()
        self.extractor = self.extractor_class()

    def tearDown(self):
        super().tearDown()
        self.analyzer_patcher.stop()
        self.mediainfo_pacher.stop()
        self.ffprobe_patcher.stop()


class SourceExtractorTestCase(ExtractorBaseTestCase):
    analyzer = 'SourceAnalyzer'
    extractor_class = extract.SourceExtractor

    def test_extract(self):
        meta = self.extractor.get_meta_data('uri')

        self.analyzer_mock.assert_called_once_with(mock.sentinel.mediainfo)
        self.analyze_mock.assert_called_once_with()
        self.assertEqual(meta, self.meta)

    def test_mediainfo(self):
        try:
            self.mediainfo_pacher.stop()
            with mock.patch('pymediainfo.MediaInfo.parse',
                            return_value=mock.sentinel.mi) as m:
                result = self.extractor.mediainfo('uri')

            self.assertEqual(result, mock.sentinel.mi)
            m.assert_called_once_with('uri')
        finally:
            self.mediainfo_pacher.start()


if TYPE_CHECKING:  # pragma: no cover
    MKVVideoSegmentTestsMixinTarget = ExtractorBaseTestCase
else:
    MKVVideoSegmentTestsMixinTarget = object


class MKVVideoSegmentTestsMixin(MKVVideoSegmentTestsMixinTarget):

    def test_extract(self):
        # video segments don't contain audio streams
        self.meta.audios.clear()
        self.analyze_mock.return_value = [s.meta for s in self.meta.streams]

        meta = self.extractor.get_meta_data('uri')

        self.analyzer_mock.assert_called_once_with(mock.sentinel.ffprobe)
        self.analyze_mock.assert_called_once_with()
        self.assertEqual(meta, self.meta)

    def test_ffprobe(self):
        try:
            self.ffprobe_patcher.stop()
            pi = ffprobe.ProbeInfo(
                streams=[{}],
                format={}
            )
            # noinspection PyTypeChecker
            content = json.dumps(asdict(pi))
            with mock.patch('video_transcoding.transcoding.extract.FFProbe',
                            ) as m:
                m.return_value.run.return_value = (0, content, '')
                result = self.extractor.ffprobe('uri')
            m.assert_called_once_with(
                'uri',
                show_format=True,
                show_streams=True,
                output_format='json',
                allowed_extensions='mkv',
            )
            self.assertEqual(result, pi)
        finally:
            self.ffprobe_patcher.start()


class VideoSegmentExtractorTestCase(MKVVideoSegmentTestsMixin,
                                    ExtractorBaseTestCase):
    analyzer = 'MKVSegmentAnalyzer'
    extractor_class = extract.VideoSegmentExtractor


class VideoResultExtractorTestCase(MKVVideoSegmentTestsMixin,
                                   ExtractorBaseTestCase):
    analyzer = 'VideoResultAnalyzer'
    extractor_class = extract.VideoResultExtractor


class SplitExtractorTestCase(ExtractorBaseTestCase):
    analyzer = 'MKVPlaylistAnalyzer'
    extractor_class = extract.SplitExtractor

    def test_extract(self):
        self.video_meta = [s.meta for s in self.meta.streams if s.kind == VIDEO]
        self.audio_meta = [s.meta for s in self.meta.streams if s.kind == AUDIO]
        self.streams = None
        self.ffprobe_mock.side_effect = self.ffprobe
        self.analyze_mock.side_effect = self.analyze

        meta = self.extractor.get_meta_data('/dir/split.json')
        kw = dict(timeout=60.0, allowed_extensions='mkv')
        self.ffprobe_mock.assert_has_calls([
            mock.call('/dir/source-video.m3u8', **kw),
            mock.call('/dir/source-audio.m3u8', **kw),
        ])
        self.analyze_mock.assert_has_calls([mock.call(), mock.call()])
        self.meta.uri = '/dir/split.json'
        self.assertEqual(meta, self.meta)

    def test_ffprobe(self):
        try:
            self.ffprobe_patcher.stop()
            pi = ffprobe.ProbeInfo(
                streams=[{}],
                format={}
            )
            # noinspection PyTypeChecker
            content = json.dumps(asdict(pi))
            with mock.patch('video_transcoding.transcoding.extract.FFProbe',
                            ) as m:
                m.return_value.run.return_value = (0, content, '')
                result = self.extractor.ffprobe('uri')
            m.assert_called_once_with(
                'uri',
                show_format=True,
                show_streams=True,
                output_format='json',
                allowed_extensions='mkv',
            )
            self.assertEqual(result, pi)
        finally:
            self.ffprobe_patcher.start()

    def ffprobe(self, uri: str, *_, **__):
        if 'video' in uri:
            self.streams = self.video_meta
        elif 'audio' in uri:
            self.streams = self.audio_meta
        else:  # pragma: no cover
            raise ValueError('uri')
        return self.ffprobe_mock.return_value

    def analyze(self):
        return self.streams


class HLSExtractorTestCase(ExtractorBaseTestCase):
    analyzer = 'FFProbeHLSAnalyzer'
    extractor_class = extract.HLSExtractor

    def test_extract(self):
        meta = self.extractor.get_meta_data('uri')

        self.analyzer_mock.assert_called_once_with(mock.sentinel.ffprobe)
        self.analyze_mock.assert_called_once_with()
        self.assertEqual(meta, self.meta)

    def test_ffprobe(self):
        try:
            self.ffprobe_patcher.stop()
            pi = ffprobe.ProbeInfo(
                streams=[{}],
                format={}
            )
            # noinspection PyTypeChecker
            content = json.dumps(asdict(pi))
            with mock.patch('video_transcoding.transcoding.extract.FFProbe',
                            ) as m:
                m.return_value.run.return_value = (0, content, '')
                result = self.extractor.ffprobe('uri')
            m.assert_called_once_with(
                'uri',
                show_format=True,
                show_streams=True,
                output_format='json',
            )
            self.assertEqual(result, pi)
        finally:
            self.ffprobe_patcher.start()
