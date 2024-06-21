from dataclasses import dataclass
from typing import List


@dataclass
class VideoTrack:
    codec: str
    constant_rate_factor: int
    preset: str
    max_rate: int
    buf_size: int
    profile: str
    pix_fmt: str
    width: int
    height: int
    frame_rate: int
    gop_size: int
    force_key_frames: str


@dataclass
class AudioTrack:
    codec: str
    bitrate: int
    channels: int
    sample_rate: int


@dataclass
class Condition:
    min_width: int
    min_height: int
    min_bitrate: int
    min_frame_rate: int
    sample_rate: int


@dataclass
class Profile:
    condition: Condition
    video: List[VideoTrack]
    audio: List[AudioTrack]


# HLS Segment duration step, seconds
SEGMENT_SIZE = 4
# H.264 Group of pixels duration, seconds
GOP_DURATION = 2
# Force key frame every N seconds
KEY_FRAMES = 'expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+{sec}))'

DEFAULT_PROFILE = Profile(
    condition=Condition(
        min_width=0,
        min_height=0,
        min_bitrate=0,
        min_frame_rate=0,
        sample_rate=0,
    ),
    video=[
        VideoTrack(
            codec='libx264',
            profile='high',
            preset='slow',
            constant_rate_factor=23,
            max_rate=5_000_000,
            buf_size=10_000_000,
            pix_fmt='yuv420p',
            width=1920,
            height=1080,
            force_key_frames=KEY_FRAMES.format(sec=SEGMENT_SIZE),
            gop_size=GOP_DURATION,
            frame_rate=30,
        )
    ],
    audio=[
        AudioTrack(
            codec='aac',
            bitrate=192000,
            channels=2,
            sample_rate=48000,
        )
    ]
)
