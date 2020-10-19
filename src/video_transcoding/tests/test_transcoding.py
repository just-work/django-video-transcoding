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
        transcoding.VIDEO_DURATION: 3600.22,
        'video_bitrate': 5000000,
        'video_frame_rate': 24.97,
        'audio_bitrate': 192000,
        'audio_sampling_rate': 48000,
        transcoding.AUDIO_DURATION: 3600.22,
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
        metadata = self.media_info[filename]
        rate = metadata['audio_sampling_rate']
        duration = metadata['audio_duration']
        xml = self.media_info_xml.format(
            filename=filename,
            audio_samples=int(rate * duration),
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
            '-filter_complex', '[0:v]scale=w=1920:h=1080[vout0]',
            '-map', '[vout0]',
            '-c:v', 'libx264',
            '-force_key_frames',
            'expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+4))',
            '-crf', '23',
            '-preset', 'slow',
            '-maxrate', '5000000',
            '-bufsize', '10000000',
            '-profile:v', 'high',
            '-g', '49',
            '-r', '24.97',
            '-map', '0:a',
            '-c:a', 'aac',
            '-b:a', '192000',
            '-ar', '48000',
            '-ac', '2',
            '-f', 'mp4', self.dest
        ]
        args, kwargs = self.ffmpeg_mock.call_args
        self.assertEqual(ensure_text(args), tuple(ffmpeg_args))
