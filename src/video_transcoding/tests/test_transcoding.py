from unittest import mock

import pymediainfo
from fffw.wrapper.helpers import ensure_text

from video_transcoding import transcoding
from video_transcoding.tests.base import BaseTestCase


class TranscodingTestCase(BaseTestCase):
    """ Video file transcoding tests."""

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
        transcoding.WIDTH: 1920,
        transcoding.HEIGHT: 1080,
        transcoding.DAR: 1.778,
        transcoding.PAR: 1.0,

        'video_bitrate': 5000000,

        transcoding.VIDEO_DURATION: 3600.22,
        transcoding.VIDEO_FRAME_RATE: 24.97,
        transcoding.FRAMES_COUNT: round(3600.22 * 24.97),

        'audio_bitrate': 192000,

        transcoding.AUDIO_DURATION: 3600.22,
        transcoding.AUDIO_SAMPLING_RATE: 48000,
        transcoding.SAMPLES_COUNT: round(3600.22 * 48000),
    }

    def setUp(self):
        self.source = 'http://ya.ru/source.mp4'
        self.dest = '/tmp/result.mp4'
        self.media_info = {
            self.source: self.prepare_metadata(),
            self.dest: self.prepare_metadata()
        }

        self.transcoder = transcoding.Transcoder(self.source, self.dest)

        self.media_info_patcher = mock.patch.object(
            pymediainfo.MediaInfo, 'parse', side_effect=self.get_media_info)
        self.media_info_mock = self.media_info_patcher.start()

        self.runner_mock = mock.MagicMock(
            return_value=(0, '', '')
        )

        self.runner_patcher = mock.patch(
            'fffw.encoding.ffmpeg.FFMPEG.runner_class',
            return_value=self.runner_mock)
        self.ffmpeg_mock = self.runner_patcher.start()

    def tearDown(self):
        self.media_info_patcher.stop()
        self.runner_patcher.stop()

    def prepare_metadata(self, **kwargs):
        """
        Modifies metadata template with new values.
        """
        media_info = self.metadata.copy()
        media_info.update(kwargs)
        return media_info

    def get_media_info(self, filename) -> pymediainfo.MediaInfo:
        """ Prepares mediainfo result for file."""
        metadata = self.media_info[filename].copy()
        rate = metadata[transcoding.AUDIO_SAMPLING_RATE]
        audio_duration = metadata.pop(transcoding.AUDIO_DURATION)
        fps = metadata[transcoding.VIDEO_FRAME_RATE]
        video_duration = metadata.pop(transcoding.VIDEO_DURATION)
        xml = self.media_info_xml.format(
            filename=filename,
            audio_samples=metadata.get(transcoding.SAMPLES_COUNT, int(rate * audio_duration)),
            video_frames=metadata.get(transcoding.FRAMES_COUNT, int(fps * video_duration)),
            audio_duration=audio_duration * 1000,  # ms
            video_duration=video_duration * 1000,  # ms
            **metadata)
        return pymediainfo.MediaInfo(xml)

    def test_smoke(self):
        """
        ffmpeg arguments test.
        """
        self.transcoder.transcode()
        ffmpeg_args = [
            'ffmpeg',
            '-loglevel', 'repeat+level+info',
            '-y',
            '-i', self.source,
            '-filter_complex', '[0:v:0]scale=w=1920:h=1080[vout0]',
            '-map', '[vout0]',
            '-c:v:0', 'libx264',
            '-force_key_frames:0',
            'expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+4))',
            '-crf:0', '23',
            '-preset:0', 'slow',
            '-maxrate:0', '5000000',
            '-bufsize:0', '10000000',
            '-profile:v:0', 'high',
            '-g:0', '49',
            '-r:0', '24.97',
            '-pix_fmt:0', 'yuv420p',
            '-map', '0:a:0',
            '-c:a:0', 'aac',
            '-b:a:0', '192000',
            '-ar:0', '48000',
            '-ac:0', '2',
            '-f', 'mp4', self.dest,
        ]
        args, kwargs = self.ffmpeg_mock.call_args
        self.assertEqual(ensure_text(args), tuple(ffmpeg_args))

    def test_handle_stderr_errors(self):
        self.runner_mock.return_value = (0, 'stdout', '[error] a warning captured')
        try:
            self.transcoder.transcode()
        except transcoding.TranscodeError:  # pragma: no cover
            self.fail("False positive error")

    def test_handle_return_code_from_stderr(self):
        error = '[error] a warning captured'
        self.runner_mock.return_value = (1, 'stdout', error)

        with self.assertRaises(transcoding.TranscodeError) as ctx:
            self.transcoder.transcode()

        self.assertEqual(ctx.exception.message, error)

    def test_handle_return_code(self):
        self.runner_mock.return_value = (-9, '', '')

        with self.assertRaises(transcoding.TranscodeError) as ctx:
            self.transcoder.transcode()

        self.assertEqual(ctx.exception.message, "invalid ffmpeg return code -9")

    def test_restore_video_aspect(self):
        """
        Metadata must satisfy following equations:

        * DAR = Width / Height * PAR
        """
        dar = round(21/9, 3)
        width = 1600
        height = 1200
        par = round(dar / (width / height), 3)

        m = self.media_info[self.source]
        m[transcoding.DAR] = dar
        m[transcoding.WIDTH] = width
        m[transcoding.HEIGHT] = height
        m[transcoding.PAR] = par

        # Check that by default metadata parsed correctly
        try:
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertEqual(v.dar, dar)
            self.assertEqual(v.par, par)
            self.assertEqual(v.width, width)
            self.assertEqual(v.height, height)
        except Exception as exc:
            self.fail(exc)

        with self.subTest("fix par"):
            # wrong PAR in source metadata
            m[transcoding.PAR] *= 1.1
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertAlmostEqual(v.par, par, 3)
        m[transcoding.PAR] = par

        with self.subTest("restore par from dar"):
            m[transcoding.PAR] = 0
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertAlmostEqual(v.par, par, 3)
        m[transcoding.PAR] = par

        with self.subTest("restore dar from par"):
            m[transcoding.DAR] = 0
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertAlmostEqual(v.dar, dar, 3)
        m[transcoding.DAR] = dar

        with self.subTest("default dar and par"):
            m[transcoding.DAR] = m[transcoding.PAR] = 0
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertAlmostEqual(v.dar, width / height, 3)
            self.assertAlmostEqual(v.par, 1.0, 3)
        m[transcoding.PAR] = par
        m[transcoding.DAR] = dar

        with self.subTest("missing width or height"):
            m[transcoding.WIDTH] = 0
            m[transcoding.HEIGHT] = 0
            with self.assertRaises(AssertionError):
                # without W and H we can't restore initial metadata
                self.transcoder.get_meta_data(self.source)

    def test_restore_frames(self):
        """
        Metadata must satisfy following equation:

        FPS = duration / frames_count
        """
        frames = 123456
        fps = 29.97
        duration = frames / fps

        m = self.media_info[self.source]
        m[transcoding.VIDEO_DURATION] = duration
        m[transcoding.VIDEO_FRAME_RATE] = fps
        m[transcoding.FRAMES_COUNT] = frames

        # Check that by default metadata parsed correctly
        try:
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertEqual(v.frames, frames)
            self.assertAlmostEqual(v.frame_rate, fps, 3)
            self.assertAlmostEqual(float(v.duration), duration, 3)
        except Exception as exc:
            self.fail(exc)

        with self.subTest("restore frames"):
            m[transcoding.FRAMES_COUNT] = 0
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertEqual(v.frames, frames)
        m[transcoding.FRAMES_COUNT] = frames

        with self.subTest("restore frame rate"):
            m[transcoding.VIDEO_FRAME_RATE] = 0
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertAlmostEqual(v.frame_rate, fps, 3)
        m[transcoding.VIDEO_FRAME_RATE] = fps

        with self.subTest("restore duration"):
            m[transcoding.VIDEO_DURATION] = 0
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertAlmostEqual(v.duration, duration, 3)
        m[transcoding.VIDEO_DURATION] = duration

        with self.subTest("only frames"):
            m[transcoding.VIDEO_DURATION] = m[transcoding.VIDEO_FRAME_RATE] = 0
            with self.assertRaises(AssertionError):
                self.transcoder.get_meta_data(self.source)
        m[transcoding.VIDEO_DURATION] = duration
        m[transcoding.VIDEO_FRAME_RATE] = fps

        with self.subTest("only frame rate"):
            m[transcoding.VIDEO_DURATION] = m[transcoding.FRAMES_COUNT] = 0
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertEqual(v.duration, 0)
            self.assertEqual(v.frames, 0)
        m[transcoding.VIDEO_DURATION] = duration
        m[transcoding.FRAMES_COUNT] = frames

        with self.subTest("only duration"):
            m[transcoding.VIDEO_FRAME_RATE] = m[transcoding.FRAMES_COUNT] = 0
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertEqual(v.frames, 0)
            self.assertEqual(v.frame_rate, 0)
            self.assertAlmostEqual(float(v.duration), duration, 3)
        m[transcoding.FRAMES_COUNT] = frames
        m[transcoding.VIDEO_FRAME_RATE] = fps

        with self.subTest("fix fps"):
            m[transcoding.VIDEO_FRAME_RATE] *= 1.1
            _, v = self.transcoder.get_meta_data(self.source)
            self.assertAlmostEqual(v.frame_rate, fps, 3)

    def test_restore_samples(self):
        """
        Metadata must satisfy following equation:

        Sampling rate = duration / samples
        """
        sampling_rate = 12025
        duration = 10.123
        samples = round(sampling_rate * duration)

        m = self.media_info[self.source]
        m[transcoding.AUDIO_DURATION] = duration
        m[transcoding.AUDIO_SAMPLING_RATE] = sampling_rate
        m[transcoding.SAMPLES_COUNT] = samples

        # Check that by default metadata parsed correctly
        try:
            a, _ = self.transcoder.get_meta_data(self.source)
            self.assertEqual(a.samples, samples)
            self.assertEqual(a.sampling_rate, sampling_rate)
            self.assertAlmostEqual(float(a.duration), duration, 3)
        except Exception as exc:
            self.fail(exc)

        with self.subTest("restore samples"):
            m[transcoding.SAMPLES_COUNT] = 0
            a, _ = self.transcoder.get_meta_data(self.source)
            self.assertEqual(a.samples, samples)
        m[transcoding.SAMPLES_COUNT] = samples

        with self.subTest("restore sampling rate"):
            m[transcoding.AUDIO_SAMPLING_RATE] = 0
            a, _ = self.transcoder.get_meta_data(self.source)
            self.assertAlmostEqual(a.sampling_rate, sampling_rate, 3)
        m[transcoding.AUDIO_SAMPLING_RATE] = sampling_rate

        with self.subTest("restore duration"):
            m[transcoding.AUDIO_DURATION] = 0
            a, _ = self.transcoder.get_meta_data(self.source)
            self.assertAlmostEqual(a.duration, duration, 3)
        m[transcoding.AUDIO_DURATION] = duration

        with self.subTest("only samples"):
            m[transcoding.AUDIO_DURATION] = m[transcoding.AUDIO_SAMPLING_RATE] = 0
            with self.assertRaises(AssertionError):
                self.transcoder.get_meta_data(self.source)
        m[transcoding.AUDIO_DURATION] = duration
        m[transcoding.AUDIO_SAMPLING_RATE] = sampling_rate

        with self.subTest("only sampling rate"):
            m[transcoding.AUDIO_DURATION] = m[transcoding.SAMPLES_COUNT] = 0
            a, _ = self.transcoder.get_meta_data(self.source)
            self.assertEqual(a.duration, 0)
            self.assertEqual(a.samples, 0)
        m[transcoding.AUDIO_DURATION] = duration
        m[transcoding.SAMPLES_COUNT] = samples

        with self.subTest("only duration"):
            m[transcoding.AUDIO_SAMPLING_RATE] = m[transcoding.SAMPLES_COUNT] = 0
            a, _ = self.transcoder.get_meta_data(self.source)
            self.assertEqual(a.samples, 0)
            self.assertEqual(a.sampling_rate, 0)
            self.assertEqual(a.duration, duration)
        m[transcoding.SAMPLES_COUNT] = samples
        m[transcoding.AUDIO_SAMPLING_RATE] = sampling_rate

        with self.subTest("fix sampling rate"):
            # Samples count is adjusted to sampling rate
            m[transcoding.AUDIO_SAMPLING_RATE] *= 2
            a, _ = self.transcoder.get_meta_data(self.source)
            self.assertAlmostEqual(a.samples, samples * 2)
