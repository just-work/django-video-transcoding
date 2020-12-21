import math
from dataclasses import dataclass
from pprint import pformat
from typing import Optional, Dict, Any, Tuple, cast

import pymediainfo
from fffw.encoding import codecs
from fffw.graph.meta import VideoMeta, AudioMeta, AUDIO, VIDEO, from_media_info
from fffw.encoding.inputs import input_file, Stream
from fffw.encoding.filters import Scale
from fffw.encoding.outputs import output_file
from fffw.encoding.ffmpeg import FFMPEG
from fffw.wrapper import param

from video_transcoding.utils import LoggerMixin

AUDIO_CODEC = 'audio_codec'
VIDEO_CODEC = 'video_codec'
SCALE = 'scale'

# Used metadata keys
AUDIO_DURATION = 'audio_duration'
AUDIO_SAMPLING_RATE = 'audio_sampling_rate'
VIDEO_DURATION = 'video_duration'
VIDEO_FRAME_RATE = 'video_frame_rate'

# Handy media info log format
MEDIA_INFO_MSG_FORMAT = """%s media info:
VIDEO:
%s
AUDIO: 
%s
"""

# HLS Segment duration step, seconds
SEGMENT_SIZE = 4
# H.264 Group of pixels duration, seconds
GOP_DURATION = 2

# Force key frame every N seconds
KEY_FRAMES = 'expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+{sec}))'

# Allowed duration difference between source and result
DURATION_DELTA = 0.95

# Video transcoding params
TRANSCODING_OPTIONS = {
    VIDEO_CODEC: {
        'codec': 'libx264',
        'force_key_frames': KEY_FRAMES.format(sec=SEGMENT_SIZE),
        'constant_rate_factor': 23,
        'preset': 'slow',
        'max_rate': 5_000_000,
        'buf_size': 10_000_000,
        'profile': 'high',
        'pix_fmt': 'yuv420p',
    },
    SCALE: {
        'width': 1920,
        'height': 1080,
    },
    AUDIO_CODEC: {
        'codec': 'aac',
        'bitrate': 192000,
        'channels': 2,
    },
}

Metadata = Dict[str, Any]
""" File metadata type."""


@dataclass
class AudioCodec(codecs.AudioCodec):
    rate: float = param(name='ar')
    channels: int = param(name='ac')


@dataclass
class VideoCodec(codecs.VideoCodec):
    force_key_frames: str = param()
    constant_rate_factor: int = param(name='crf')
    preset: str = param()
    max_rate: int = param(name='maxrate')
    buf_size: int = param(name='bufsize')
    profile: str = param(stream_suffix=True)
    gop: int = param(name='g')
    rate: float = param(name='r')
    pix_fmt: str = param()


class TranscodeError(Exception):
    """ Video transcoding error."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class Transcoder(LoggerMixin):
    """ Video transcoder.

    >>> t = Transcoder('http://source.localhost/source.mp4', '/tmp/result.mp4')
    >>> t.transcode()
    """

    def __init__(self, source: str, destination: str):
        """
        :param source: source file link (http/ftp or file path)
        :param destination: result file path
        """
        super().__init__()
        self.source = source
        self.destination = destination

    def get_media_info(self, video: Optional[VideoMeta],
                       audio: Optional[AudioMeta]) -> Metadata:
        """
        Transforms video and audio metadata to a dict

        :param video: video stream metadata
        :param audio: audio stream metadata
        :returns: metadata single level dictionary
        """
        if video is None:
            raise TranscodeError("missing video stream")
        if audio is None:
            raise TranscodeError("missing audio stream")

        media_info = {
            'width': video.width,
            'height': video.height,
            'aspect': video.dar,
            'par': video.par,
            VIDEO_DURATION: video.duration.total_seconds(),
            'video_bitrate': video.bitrate,
            VIDEO_FRAME_RATE: video.frame_rate,
            'audio_bitrate': audio.bitrate,
            AUDIO_SAMPLING_RATE: audio.sampling_rate,
            AUDIO_DURATION: audio.duration.total_seconds(),
        }
        self.logger.info("Parsed media info:\n%s", pformat(media_info))
        return media_info

    def transcode(self) -> None:
        """ Transcodes video

        * checks source mediainfo
        * runs `ffmpeg`
        * validates result
        """
        audio_meta, video_meta = self.get_meta_data(self.source)

        # Get source mediainfo to use in validation
        source_media_info = self.get_media_info(video_meta, audio_meta)

        # set group of pixels length to segment size
        gop = math.floor(source_media_info[VIDEO_FRAME_RATE] * GOP_DURATION)
        # preserve original video FPS
        vrate = source_media_info[VIDEO_FRAME_RATE]
        # preserve source audio sampling rate
        arate = source_media_info[AUDIO_SAMPLING_RATE]

        # Common ffmpeg flags
        ff = FFMPEG(overwrite=True, loglevel='repeat+level+info')
        # Init source file
        ff < input_file(self.source,
                        Stream(VIDEO, video_meta),
                        Stream(AUDIO, audio_meta))

        # Output codecs
        video_opts = cast(Dict[str, Any], TRANSCODING_OPTIONS[VIDEO_CODEC])
        cv0 = VideoCodec(
            gop=gop,
            rate=vrate,
            **video_opts)
        audio_opts = cast(Dict[str, Any], TRANSCODING_OPTIONS[AUDIO_CODEC])
        ca0 = AudioCodec(
            rate=arate,
            **audio_opts)

        # Scaling
        ff.video | Scale(**TRANSCODING_OPTIONS[SCALE]) > cv0

        # codecs, muxer and output path
        ff > output_file(self.destination, cv0, ca0, format='mp4')

        # Run ffmpeg
        self.run(ff)

        # Get result mediainfo
        audio_meta, video_meta = self.get_meta_data(self.destination)
        dest_media_info = self.get_media_info(video_meta, audio_meta)

        # Validate ffmpeg result
        self.validate(source_media_info, dest_media_info)

    @staticmethod
    def get_meta_data(filename: str) -> Tuple[Optional[AudioMeta],
                                              Optional[VideoMeta]]:
        result: pymediainfo.MediaInfo = pymediainfo.MediaInfo.parse(filename)
        metadata = from_media_info(result)
        video_meta = None
        audio_meta = None
        for m in metadata:
            if m.kind == VIDEO and video_meta is None:
                video_meta = m
            if m.kind == AUDIO and audio_meta is None:
                audio_meta = m
        return audio_meta, video_meta

    @staticmethod
    def validate(source_media_info: Metadata,
                 dest_media_info: Metadata) -> None:
        """
        Validate video transcoding result.

        :param source_media_info: source metadata
        :param dest_media_info: result metadata
        """
        src_duration = max(source_media_info[VIDEO_DURATION],
                           source_media_info[AUDIO_DURATION])
        dst_duration = min(dest_media_info[VIDEO_DURATION],
                           dest_media_info[AUDIO_DURATION])
        if dst_duration < DURATION_DELTA * src_duration:
            # Check whether result duration corresponds to source duration
            # (damaged source files may be processed successfully but result
            # is shorter)
            raise TranscodeError(f"incomplete file: {dst_duration}")

    @staticmethod
    def run(ff: FFMPEG) -> None:
        """ Starts ffmpeg process and captures errors from it's logs"""
        return_code, output, error = ff.run()
        if error or return_code != 0:
            # Check return code and error messages
            error = error or f"invalid ffmpeg return code {return_code}"
            raise TranscodeError(error)
