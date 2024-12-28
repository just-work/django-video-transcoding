from typing import TYPE_CHECKING, Dict, Any
from unittest import mock, skip

import pymediainfo
from fffw.wrapper.helpers import ensure_text

from video_transcoding.tests.base import BaseTestCase
from video_transcoding.transcoding import transcoder
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
