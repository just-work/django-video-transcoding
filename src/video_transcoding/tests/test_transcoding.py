import subprocess
from unittest import mock

import pymediainfo
from fffw.wrapper import ensure_binary

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

        self.popen = mock.MagicMock()  # Popen()
        self.process = mock.MagicMock()  # with Popen() as process
        self.stderr = mock.MagicMock()  # process.stderr
        self.popen.__enter__.return_value = self.process
        self.process.stderr = self.stderr
        self.process.returncode = 0
        self.stderr.readline.side_effect = ('', None)
        self.popen_patcher = mock.patch('subprocess.Popen',
                                        return_value=self.popen)
        self.popen_mock = self.popen_patcher.start()

    def tearDown(self):
        self.media_info_patcher.stop()
        self.popen_patcher.stop()

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
        xml = self.media_info_xml.format(filename=filename, **metadata)
        return pymediainfo.MediaInfo(xml)

    def test_smoke(self):
        """
        ffmpeg arguments test.
        """
        self.transcoder.transcode()
        ffmpeg_args = list(map(ensure_binary, [
            'ffmpeg',
            '-loglevel', 'repeat+level+info',
            '-i', self.source,
            '-filter_complex', '[0:v]scale=1920x1080[vout0]',
            '-y',
            '-map', '[vout0]',
            '-c:v', 'libx264',
            '-force_key_frames',
            'expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+4))',
            '-g', '24',
            '-r', '24.97',
            '-b:v', '5000000',
            '-map', '0:a',
            '-c:a', 'aac',
            '-b:a', '192000',
            '-ar', '48000.0',
            '-ac', '2',
            '-f', 'mp4', self.dest
        ]))
        self.popen_mock.assert_called_once_with(
            ffmpeg_args, stderr=subprocess.PIPE)
