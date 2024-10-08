from typing import TYPE_CHECKING, Dict, Any, Tuple
from unittest import mock, skip

import pymediainfo
from fffw.graph import VideoMeta, AudioMeta
from fffw.wrapper.helpers import ensure_text

from video_transcoding.tests.base import BaseTestCase
from video_transcoding.transcoding import transcoder
from video_transcoding.transcoding.metadata import Analyzer
from video_transcoding.transcoding.profiles import DEFAULT_PRESET

if TYPE_CHECKING:
    MediaInfoMixinTarget = BaseTestCase
else:
    MediaInfoMixinTarget = object


class MediaInfoMixin(MediaInfoMixinTarget):
    """ Mixin to manipulate MediaInfo output."""

    # Minimal mediainfo output template to mock MediaInfo.parse result
    media_info_xml = """<?xml version="1.0" encoding="UTF-8"?>
<File>
<track type="General">
<VideoCount>1</VideoCount>
<AudioCount>1</AudioCount>
</track>

<track type="Video">
<Duration>{video_duration:.3f}</Duration>
<Bit_Rate>{video_bitrate}</Bit_Rate>
<Width>{width}</Width>
<Height>{height}</Height>
<Pixel_Aspect_Ratio>{par:.3f}</Pixel_Aspect_Ratio>
<Display_Aspect_Ratio>{aspect:.3f}</Display_Aspect_Ratio>
<Frame_Rate>{video_frame_rate:.3f}</Frame_Rate>
<Frame_count>{video_frames}</Frame_count>
</track>

<track type="Audio">
<Duration>{audio_duration:.3f}</Duration>
<Bit_Rate>{audio_bitrate}</Bit_Rate>
<Sampling_Rate>{audio_sampling_rate}</Sampling_Rate>
<Samples_count>{audio_samples}</Samples_count>
</track>

</File>
"""

    # Default video file metadata
    metadata = {
        'width': 1920,
        'height': 1080,
        'aspect': 1.778,
        'par': 1.0,

        'video_bitrate': 5000000,

        'video_duration': 3600.22,
        'video_frame_rate': 24.97,
        'frames_count': round(3600.22 * 24.97),

        'audio_bitrate': 192000,

        'audio_duration': 3600.22,
        'audio_sampling_rate': 48000,
        'samples_count': round(3600.22 * 48000),
    }

    def setUp(self):
        super().setUp()
        self.media_info_patcher = mock.patch.object(
            pymediainfo.MediaInfo, 'parse', side_effect=self.get_media_info)
        self.media_info_mock = self.media_info_patcher.start()
        self.media_info: Dict[str, Dict[str, Any]] = {}

    def tearDown(self):
        self.media_info_patcher.stop()

    def get_media_info(self, filename: str) -> pymediainfo.MediaInfo:
        """ Prepares mediainfo result for file."""
        metadata = self.media_info[filename].copy()
        rate = metadata['audio_sampling_rate']
        audio_duration = metadata.pop('audio_duration')
        fps = metadata['video_frame_rate']
        video_duration = metadata.pop('video_duration')
        xml = self.media_info_xml.format(
            filename=filename,
            audio_samples=metadata.get('samples_count',
                                       int(rate * audio_duration)),
            video_frames=metadata.get('frames_count',
                                      int(fps * video_duration)),
            audio_duration=audio_duration * 1000,  # ms
            video_duration=video_duration * 1000,  # ms
            **metadata)
        return pymediainfo.MediaInfo(xml)

    def prepare_metadata(self, **kwargs):
        """
        Modifies metadata template with new values.
        """
        media_info = self.metadata.copy()
        media_info.update(kwargs)
        return media_info


# noinspection PyUnresolvedReferences,PyArgumentList
@skip("refactor needed")
class TranscodingTestCase(MediaInfoMixin, BaseTestCase):
    """ Video file transcoding tests."""

    def setUp(self):
        self.source = 'http://ya.ru/source.mp4'
        self.dest = '/tmp/result.mp4'
        super().setUp()
        self.media_info = {
            self.source: self.prepare_metadata(),
            self.dest: self.prepare_metadata()
        }

        self.transcoder = transcoder.Transcoder(self.source, self.dest,
                                                DEFAULT_PRESET)

        self.runner_mock = mock.MagicMock(
            return_value=(0, '', '')
        )

        self.runner_patcher = mock.patch(
            'fffw.encoding.ffmpeg.FFMPEG.runner_class',
            return_value=self.runner_mock)
        self.ffmpeg_mock = self.runner_patcher.start()

    def tearDown(self):
        super().tearDown()
        self.runner_patcher.stop()

    def test_smoke(self):
        """
        ffmpeg arguments test.
        """
        self.transcoder.transcode()

        filter_complex = ';'.join([
            '[0:v:0]split=4[v:split0][v:split1][v:split2][v:split3]',
            '[v:split0]scale=w=1920:h=1080[vout0]',
            '[v:split1]scale=w=1280:h=720[vout1]',
            '[v:split2]scale=w=854:h=480[vout2]',
            '[v:split3]scale=w=640:h=360[vout3]',
        ])

        ffmpeg_args = [
            'ffmpeg',
            '-loglevel', 'repeat+level+info',
            '-y',
            '-i', self.source,

            '-filter_complex', filter_complex,

            '-map', '[vout0]',
            '-c:v:0', 'libx264',
            '-force_key_frames:0',
            'expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+4))',
            '-crf:0', '23',
            '-preset:0', 'slow',
            '-maxrate:0', '5000000',
            '-bufsize:0', '10000000',
            '-profile:v:0', 'high',
            '-g:0', '60',
            '-r:0', '30',
            '-pix_fmt:0', 'yuv420p',

            '-map', '[vout1]',
            '-c:v:1', 'libx264',
            '-force_key_frames:1',
            'expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+4))',
            '-crf:1', '23',
            '-preset:1', 'slow',
            '-maxrate:1', '3000000',
            '-bufsize:1', '6000000',
            '-profile:v:1', 'high',
            '-g:1', '60',
            '-r:1', '30',
            '-pix_fmt:1', 'yuv420p',

            '-map', '[vout2]',
            '-c:v:2', 'libx264',
            '-force_key_frames:2',
            'expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+4))',
            '-crf:2', '23',
            '-preset:2', 'slow',
            '-maxrate:2', '1500000',
            '-bufsize:2', '3000000',
            '-profile:v:2', 'main',
            '-g:2', '60',
            '-r:2', '30',
            '-pix_fmt:2', 'yuv420p',

            '-map', '[vout3]',
            '-c:v:3', 'libx264',
            '-force_key_frames:3',
            'expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+4))',
            '-crf:3', '23',
            '-preset:3', 'slow',
            '-maxrate:3', '800000',
            '-bufsize:3', '1600000',
            '-profile:v:3', 'main',
            '-g:3', '60',
            '-r:3', '30',
            '-pix_fmt:3', 'yuv420p',

            '-map', '0:a:0',
            '-c:a:0', 'aac',
            '-b:a:0', '192000',
            '-ar:0', '48000',
            '-ac:0', '2',

            '-f', 'mp4', self.dest,
        ]
        args, kwargs = self.ffmpeg_mock.call_args
        self.assertEqual(ensure_text(args), tuple(ffmpeg_args))

    def test_select_profile(self):
        """
        select another set of video and audio tracks to transcode.
        """
        src = self.transcoder.get_media_info(self.source)
        p = self.transcoder.select_profile(src)
        self.assertEqual(len(p.video), 4)
        self.assertEqual(len(p.audio), 1)

        mi = self.media_info[self.source]
        vb = DEFAULT_PRESET.video_profiles[0].condition.min_bitrate
        mi['video_bitrate'] = vb - 1

        src = self.transcoder.get_media_info(self.source)
        p = self.transcoder.select_profile(src)
        self.assertEqual(len(p.video), 3)
        self.assertEqual(len(p.audio), 1)

    def test_handle_stderr_errors(self):
        self.runner_mock.return_value = (
            0, 'stdout', '[error] a warning captured',
        )
        try:
            self.transcoder.transcode()
        except transcoder.TranscodeError:  # pragma: no cover
            self.fail("False positive error")

    def test_handle_return_code_from_stderr(self):
        error = '[error] a warning captured'
        self.runner_mock.return_value = (1, 'stdout', error)

        with self.assertRaises(transcoder.TranscodeError) as ctx:
            self.transcoder.transcode()

        self.assertEqual(ctx.exception.message, error)

    def test_handle_return_code(self):
        self.runner_mock.return_value = (-9, '', '')

        with self.assertRaises(transcoder.TranscodeError) as ctx:
            self.transcoder.transcode()

        self.assertEqual(ctx.exception.message, "invalid ffmpeg return code -9")


class AnalyzerTestCase(MediaInfoMixin, BaseTestCase):
    """ Media analyzer tests."""

    def setUp(self):
        super().setUp()
        self.source = 'http://ya.ru/source.mp4'
        self.analyzer = Analyzer()
        self.media_info[self.source] = self.prepare_metadata()

    def test_restore_video_aspect(self):
        """
        Metadata must satisfy following equations:

        * DAR = Width / Height * PAR
        """
        dar = round(21 / 9, 3)
        width = 1600
        height = 1200
        par = round(dar / (width / height), 3)

        m = self.media_info[self.source]
        m['aspect'] = dar
        m['width'] = width
        m['height'] = height
        m['par'] = par

        # Check that by default metadata parsed correctly
        try:
            _, v = self.get_meta_data()
            self.assertEqual(v.dar, dar)
            self.assertEqual(v.par, par)
            self.assertEqual(v.width, width)
            self.assertEqual(v.height, height)
        except Exception as exc:
            self.fail(exc)

        with self.subTest("fix par"):
            # wrong PAR in source metadata
            m['par'] *= 1.1
            _, v = self.get_meta_data()
            self.assertAlmostEqual(v.par, par, 3)
        m['par'] = par

        with self.subTest("restore par from dar"):
            m['par'] = 0
            _, v = self.get_meta_data()
            self.assertAlmostEqual(v.par, par, 3)
        m['par'] = par

        with self.subTest("restore dar from par"):
            m['aspect'] = 0
            _, v = self.get_meta_data()
            self.assertAlmostEqual(v.dar, dar, 3)
        m['aspect'] = dar

        with self.subTest("default dar and par"):
            m['aspect'] = m['par'] = 0
            _, v = self.get_meta_data()
            self.assertAlmostEqual(v.dar, width / height, 3)
            self.assertAlmostEqual(v.par, 1.0, 3)
        m['par'] = par
        m['aspect'] = dar

        with self.subTest("missing width or height"):
            m['width'] = 0
            m['height'] = 0
            with self.assertRaises(AssertionError):
                # without W and H we can't restore initial metadata
                self.get_meta_data()

    def test_restore_frames(self):
        """
        Metadata must satisfy following equation:

        FPS = duration / frames_count
        """
        frames = 123456
        fps = 29.97
        duration = frames / fps

        m = self.media_info[self.source]
        m['video_duration'] = duration
        m['video_frame_rate'] = fps
        m['frames_count'] = frames

        # Check that by default metadata parsed correctly
        try:
            _, v = self.get_meta_data()
            self.assertEqual(v.frames, frames)
            self.assertAlmostEqual(v.frame_rate, fps, 3)
            self.assertAlmostEqual(float(v.duration), duration, 3)
        except Exception as exc:
            self.fail(exc)

        with self.subTest("restore frames"):
            m['frames_count'] = 0
            _, v = self.get_meta_data()
            self.assertEqual(v.frames, frames)
        m['frames_count'] = frames

        with self.subTest("restore frame rate"):
            m['video_frame_rate'] = 0
            _, v = self.get_meta_data()
            self.assertAlmostEqual(v.frame_rate, fps, 3)
        m['video_frame_rate'] = fps

        with self.subTest("restore duration"):
            m['video_duration'] = 0
            _, v = self.get_meta_data()
            self.assertAlmostEqual(v.duration, duration, 3)
        m['video_duration'] = duration

        with self.subTest("only frames"):
            m['video_duration'] = m['video_frame_rate'] = 0
            with self.assertRaises(AssertionError):
                self.get_meta_data()
        m['video_duration'] = duration
        m['video_frame_rate'] = fps

        with self.subTest("only frame rate"):
            m['video_duration'] = m['frames_count'] = 0
            _, v = self.get_meta_data()
            self.assertEqual(v.duration, 0)
            self.assertEqual(v.frames, 0)
        m['video_duration'] = duration
        m['frames_count'] = frames

        with self.subTest("only duration"):
            m['video_frame_rate'] = m['frames_count'] = 0
            _, v = self.get_meta_data()
            self.assertEqual(v.frames, 0)
            self.assertEqual(v.frame_rate, 0)
            self.assertAlmostEqual(float(v.duration), duration, 3)
        m['frames_count'] = frames
        m['video_frame_rate'] = fps

        with self.subTest("fix fps"):
            m['video_frame_rate'] *= 1.1
            _, v = self.get_meta_data()
            self.assertAlmostEqual(v.frame_rate, fps, 3)

    def get_meta_data(self) -> Tuple[AudioMeta, VideoMeta]:
        mi = self.analyzer.get_meta_data(self.source)
        return mi.audio, mi.video

    def test_restore_samples(self):
        """
        Metadata must satisfy following equation:

        Sampling rate = duration / samples
        """
        sampling_rate = 12025
        duration = 10.123
        samples = round(sampling_rate * duration)

        m = self.media_info[self.source]
        m['audio_duration'] = duration
        m['audio_sampling_rate'] = sampling_rate
        m['samples_count'] = samples

        # Check that by default metadata parsed correctly
        try:
            a, _ = self.get_meta_data()
            self.assertEqual(a.samples, samples)
            self.assertEqual(a.sampling_rate, sampling_rate)
            self.assertAlmostEqual(float(a.duration), duration, 3)
        except Exception as exc:
            self.fail(exc)

        with self.subTest("restore samples"):
            m['samples_count'] = 0
            a, _ = self.get_meta_data()
            self.assertEqual(a.samples, samples)
        m['samples_count'] = samples

        with self.subTest("restore sampling rate"):
            m['audio_sampling_rate'] = 0
            a, _ = self.get_meta_data()
            self.assertAlmostEqual(a.sampling_rate, sampling_rate, 3)
        m['audio_sampling_rate'] = sampling_rate

        with self.subTest("restore duration"):
            m['audio_duration'] = 0
            a, _ = self.get_meta_data()
            self.assertAlmostEqual(a.duration, duration, 3)
        m['audio_duration'] = duration

        with self.subTest("only samples"):
            m['audio_duration'] = m['audio_sampling_rate'] = 0
            with self.assertRaises(AssertionError):
                self.get_meta_data()
        m['audio_duration'] = duration
        m['audio_sampling_rate'] = sampling_rate

        with self.subTest("only sampling rate"):
            m['audio_duration'] = m['samples_count'] = 0
            a, _ = self.get_meta_data()
            self.assertEqual(a.duration, 0)
            self.assertEqual(a.samples, 0)
        m['audio_duration'] = duration
        m['samples_count'] = samples

        with self.subTest("only duration"):
            m['audio_sampling_rate'] = m['samples_count'] = 0
            a, _ = self.get_meta_data()
            self.assertEqual(a.samples, 0)
            self.assertEqual(a.sampling_rate, 0)
            self.assertEqual(a.duration, duration)
        m['samples_count'] = samples
        m['audio_sampling_rate'] = sampling_rate

        with self.subTest("fix sampling rate"):
            # Samples count is adjusted to sampling rate
            m['audio_sampling_rate'] *= 2
            a, _ = self.get_meta_data()
            self.assertAlmostEqual(a.samples, samples * 2)
