import math
from pprint import pformat
from typing import Optional, Dict, Any

import pymediainfo
from fffw.encoding import FFMPEG, VideoCodec, AudioCodec, Muxer
from fffw.graph import SourceFile
from fffw.graph.filters import Scale

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
        'vcodec': 'libx264',
        'force_key_frames': KEY_FRAMES.format(sec=SEGMENT_SIZE),
        'crf': 23,
        'preset': 'slow',
        'maxrate': 5_000_000,
        'bufsize': 10_000_000,
        'vprofile': 'high',
    },
    SCALE: {
        'width': 1920,
        'height': 1080,
    },
    AUDIO_CODEC: {
        'acodec': 'aac',
        'abitrate': 192000,
        'achannels': 2,
    },
}

Metadata = Dict[str, Any]
""" File metadata type."""


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

    def get_media_info(self, filename: str) -> Metadata:
        """
        Gets file metadata, returns it in a dict form.

        :param filename: file path or link
        :returns: metadata single level dictionary
        """
        result: pymediainfo.MediaInfo = pymediainfo.MediaInfo.parse(filename)
        video: Optional[pymediainfo.Track] = None
        audio: Optional[pymediainfo.Track] = None
        for track in result.tracks:
            if track.track_type == 'Video':
                video = track
            if track.track_type == 'Audio':
                audio = track

        self.logger.info(MEDIA_INFO_MSG_FORMAT,
                         filename,
                         pformat(getattr(video, '__dict__', None)),
                         pformat(getattr(audio, '__dict__', None)))

        if video is None:
            raise TranscodeError("missing video stream")
        if audio is None:
            raise TranscodeError("missing audio stream")

        media_info = {
            'width': int(video.width),
            'height': int(video.height),
            'aspect': float(video.display_aspect_ratio),
            'par': float(video.pixel_aspect_ratio),
            VIDEO_DURATION: float(video.duration),
            'video_bitrate': float(video.bit_rate),
            VIDEO_FRAME_RATE: float(video.frame_rate),
            'audio_bitrate': float(audio.bit_rate),
            AUDIO_SAMPLING_RATE: float(audio.sampling_rate),
            AUDIO_DURATION: float(audio.duration),
        }
        self.logger.info("Parsed media info:\n%s", pformat(media_info))
        return media_info

    def transcode(self) -> None:
        """ Transcodes video

        * checks source mediainfo
        * runs `ffmpeg`
        * validates result
        """
        # Get source mediainfo to use in validation
        source_media_info = self.get_media_info(self.source)

        # Common ffmpeg flags
        ff = FFMPEG(overwrite=True, loglevel='repeat+level+info')
        # Init source file
        ff < SourceFile(self.source)
        # Scaling
        fc = ff.init_filter_complex()
        fc.video | Scale(**TRANSCODING_OPTIONS[SCALE]) | fc.get_video_dest(0)

        # set group of pixels length to segment size
        gop = math.floor(source_media_info[VIDEO_FRAME_RATE] * GOP_DURATION)
        # preserve source audio sampling rate
        arate = source_media_info[AUDIO_SAMPLING_RATE]
        # preserve original video FPS
        vrate = source_media_info[VIDEO_FRAME_RATE]
        # codecs, muxer and output path

        cv0 = VideoCodec(
            gop=gop,
            vrate=vrate,
            **TRANSCODING_OPTIONS[VIDEO_CODEC])
        ca0 = AudioCodec(
            arate=arate,
            **TRANSCODING_OPTIONS[AUDIO_CODEC])
        out0 = Muxer(self.destination, format='mp4')

        # Add output file to ffmpeg
        ff.add_output(out0, cv0, ca0)

        # Run ffmpeg
        self.run(ff)

        # Get result mediainfo
        dest_media_info = self.get_media_info(self.destination)

        # Validate ffmpeg result
        self.validate(source_media_info, dest_media_info)

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

    def run(self, ff: FFMPEG) -> None:
        """ Starts ffmpeg process and captures errors from it's logs"""
        return_code, error = ff.run()
        if error or return_code != 0:
            # Check return code and error messages
            error = error or f"invalid ffmpeg return code {return_code}"
            raise TranscodeError(error)
