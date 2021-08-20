import math
from dataclasses import dataclass
from pprint import pformat
from typing import Optional, Dict, Any, Tuple, cast

import pymediainfo
from fffw.encoding import codecs
from fffw.graph.meta import VideoMeta, AudioMeta, AUDIO, VIDEO, from_media_info, TS
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
SAMPLES_COUNT = 'samples'
VIDEO_DURATION = 'video_duration'
VIDEO_FRAME_RATE = 'video_frame_rate'
FRAMES_COUNT = 'frames'
DAR = 'aspect'
PAR = 'par'
WIDTH = 'width'
HEIGHT = 'height'

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

    def fix_par(self, t: pymediainfo.Track) -> None:
        """
        Fix PAR to satisfy equation DAR = width / height * PAR.
        """
        dar = float(t.__dict__.get('display_aspect_ratio', 0))
        par = float(t.__dict__.get('pixel_aspect_ratio', 0))
        width = int(t.__dict__.get('width', 0))
        height = int(t.__dict__.get('height', 0))

        if not (width and height):
            # not enough info to fix PAR
            self.logger.debug("width or height unknown, can't restore PAR metadata")
            return
        ratio = width / height

        if not par and dar:
            self.logger.debug("restoring par from dar")
            par = dar / ratio
        elif not dar and par:
            self.logger.debug("restoring dar from par")
            dar = par * ratio
        elif not dar and not par:
            self.logger.debug("setting aspects to defaults")
            par = 1.0
            dar = ratio

        # at this moment we know all 4 variables, checking equation
        if abs(dar - ratio * par) >= 0.001:  # see fffw.meta.VideoMeta.validate
            # par is least reliable value, using it to fix equation
            par = dar / ratio
        t.__dict__['display_aspect_ratio'] = f'{dar:.3f}'
        t.__dict__['pixel_aspect_ratio'] = f'{par:.3f}'

    def fix_frames(self, t: pymediainfo.Track) -> None:
        """
        Fix frames count to satisfy equation:

        Duration = FPS * frames
        """
        duration = float(t.__dict__.get('duration', 0)) / 1000  # duration in seconds
        frame_rate = float(t.__dict__.get('frame_rate', 0))
        frames = int(t.__dict__.get('frame_count', 0))

        if not duration and frames and frame_rate:
            self.logger.debug("restoring video duration")
            duration = frames / frame_rate
        elif not frames and duration and frame_rate:
            self.logger.debug("restoring frames")
            frames = round(duration * frame_rate)
        elif not frame_rate and duration and frames:
            self.logger.debug("restoging frame_rate")
            frame_rate = frames / duration
        elif not all([frames, frame_rate, duration]):
            # 2 of 3 variables are unknown, or even all of them.
            # can't restore metadata
            return

        # checking equation
        if abs(frames - duration * frame_rate) > 1:
            # frames is least reliable value
            frame_rate = frames / duration

        t.__dict__['frame_rate'] = f'{frame_rate:.3f}'
        t.__dict__['duration'] = f'{duration * 1000.0:.3f}'  # milliseconds again
        t.__dict__['frame_count'] = f'{frames}'

    def fix_samples(self, t: pymediainfo.Track) -> None:
        """
        Fix sample count to satisfy equation:

        Duration = Sampling rate * samples
        """
        duration = float(t.__dict__.get('duration', 0)) / 1000  # duration in seconds
        sampling_rate = float(t.__dict__.get('sampling_rate', 0))
        samples = int(t.__dict__.get('samples_count', 0))

        if not duration and samples and sampling_rate:
            self.logger.debug("restoring audio duration")
            duration = samples / sampling_rate
        elif not samples and duration and sampling_rate:
            self.logger.debug("restoring samples")
            samples = round(duration * sampling_rate)
        elif not sampling_rate and duration and samples:
            self.logger.debug("restoging sampling_rate")
            sampling_rate = samples / duration
        elif not all([samples, sampling_rate, duration]):
            # 2 of 3 variables are unknown, or even all of them.
            # can't restore metadata
            return

        # fix sampling rate type
        sampling_rate = round(sampling_rate)
        # handle duration rounding
        duration = round(duration, 3)

        # checking equation
        if abs(samples - duration * sampling_rate) > 1:
            # samples is least reliable data, because sampling rate has common values like 48000,
            # and duration is more reliable.
            samples = round(duration * sampling_rate)

        t.__dict__['sampling_rate'] = f'{sampling_rate}'
        t.__dict__['duration'] = f'{duration * 1000.0:.3f}'  # milliseconds again
        t.__dict__['samples_count'] = f'{samples}'

    def get_meta_data(self, filename: str
                      ) -> Tuple[Optional[AudioMeta], Optional[VideoMeta]]:
        result: pymediainfo.MediaInfo = pymediainfo.MediaInfo.parse(filename)
        for t in result.tracks:
            if t.track_type in ('Video', 'Image'):
                self.fix_par(t)
                self.fix_frames(t)
            elif t.track_type == 'Audio':
                self.fix_samples(t)
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
        if return_code != 0:
            # Check return code and error messages
            error = error or f"invalid ffmpeg return code {return_code}"
            raise TranscodeError(error)
