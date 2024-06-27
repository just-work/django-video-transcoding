from dataclasses import dataclass
from typing import List

from fffw.graph import VideoMeta, AudioMeta


@dataclass
class VideoTrack:
    """
    Settings for a single video stream in resulting media file
    """
    id: str
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
    """
    Settings for a single audio stream in resulting media file
    """
    id: str
    codec: str
    bitrate: int
    channels: int
    sample_rate: int


@dataclass
class VideoCondition:
    """
    Condition for source video stream for video profile selection
    """
    min_width: int
    min_height: int
    min_bitrate: int
    min_frame_rate: float

    def is_valid(self, meta: VideoMeta) -> bool:
        """
        :param meta: source video stream metadata
        :return: True if source stream satisfies condition.
        """
        return (
            meta.width >= self.min_width and
            meta.height >= self.min_height and
            meta.bitrate >= self.min_bitrate and
            meta.frame_rate >= self.min_frame_rate
        )


@dataclass
class AudioCondition:
    """
    Condition for source audio stream for video profile selection
    """

    min_sample_rate: int
    min_bitrate: int

    def is_valid(self, meta: AudioMeta) -> bool:
        """
        :param meta: source video stream metadata
        :return: True if source stream satisfies condition.
        """
        return (
            meta.bitrate >= self.min_bitrate and
            meta.sampling_rate >= self.min_sample_rate
        )


@dataclass
class VideoProfile:
    """
    Video transcoding profile.
    """
    condition: VideoCondition
    video: List[str]  # List of VideoTrack ids defined in a preset


@dataclass
class AudioProfile:
    """
    Audio transcoding profile.
    """
    condition: AudioCondition
    audio: List[str]  # List of AudioTrack ids defined in a preset


@dataclass
class Profile:
    """
    Selected transcoding profile containing a number of audio and video streams.
    """
    video: List[VideoTrack]
    audio: List[AudioTrack]


@dataclass
class Preset:
    """
    A set of video and audio profiles to select from.
    """
    video_profiles: List[VideoProfile]
    audio_profiles: List[AudioProfile]
    video: List[VideoTrack]
    audio: List[AudioTrack]

    def select_profile(self, video: VideoMeta, audio: AudioMeta) -> Profile:
        video_profile = None
        for vp in self.video_profiles:
            if vp.condition.is_valid(video):
                video_profile = vp
                break
        if video_profile is None:
            raise RuntimeError("No compatible video profiles")

        audio_profile = None
        for ap in self.audio_profiles:
            if ap.condition.is_valid(audio):
                audio_profile = ap
                break
        if audio_profile is None:
            raise RuntimeError("No compatible audio profiles")

        return Profile(
            video=[v for v in self.video if v.id in video_profile.video],
            audio=[a for a in self.audio if a.id in audio_profile.audio],
        )


# Default frame rate
FRAME_RATE = 30
# HLS Segment duration step, seconds
SEGMENT_SIZE = 4
# H.264 Group of pixels duration, seconds
GOP_DURATION = 2
# Force key frame every N seconds
KEY_FRAMES = 'expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+{sec}))'

DEFAULT_PRESET = Preset(
    video_profiles=[
        VideoProfile(
            condition=VideoCondition(
                min_width=1920,
                min_height=1080,
                min_bitrate=4_000_000,
                min_frame_rate=0,
            ),
            video=['1080p', '720p', '480p', '360p']
        ),
        VideoProfile(
            condition=VideoCondition(
                min_width=1280,
                min_height=720,
                min_bitrate=2_500_000,
                min_frame_rate=0,
            ),
            video=['720p', '480p', '360p']
        ),
        VideoProfile(
            condition=VideoCondition(
                min_width=854,
                min_height=480,
                min_bitrate=1_200_000,
                min_frame_rate=0,
            ),
            video=['480p', '360p']
        ),
        VideoProfile(
            condition=VideoCondition(
                min_width=0,
                min_height=0,
                min_bitrate=0,
                min_frame_rate=0,
            ),
            video=['360p']
        ),
    ],
    audio_profiles=[
        AudioProfile(
            condition=AudioCondition(
                min_bitrate=160,
                min_sample_rate=0
            ),
            audio=['192k', '96k']
        ),
        AudioProfile(
            condition=AudioCondition(
                min_bitrate=0,
                min_sample_rate=0
            ),
            audio=['96k']
        ),
    ],

    video=[
        VideoTrack(
            id='1080p',
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
            gop_size=GOP_DURATION * FRAME_RATE,
            frame_rate=FRAME_RATE,
        ),
        VideoTrack(
            id='720p',
            codec='libx264',
            profile='high',
            preset='slow',
            constant_rate_factor=23,
            max_rate=3_000_000,
            buf_size=6_000_000,
            pix_fmt='yuv420p',
            width=1280,
            height=720,
            force_key_frames=KEY_FRAMES.format(sec=SEGMENT_SIZE),
            gop_size=GOP_DURATION * FRAME_RATE,
            frame_rate=FRAME_RATE,
        ),
        VideoTrack(
            id='480p',
            codec='libx264',
            profile='main',
            preset='slow',
            constant_rate_factor=23,
            max_rate=1_500_000,
            buf_size=3_000_000,
            pix_fmt='yuv420p',
            width=854,
            height=480,
            force_key_frames=KEY_FRAMES.format(sec=SEGMENT_SIZE),
            gop_size=GOP_DURATION * FRAME_RATE,
            frame_rate=FRAME_RATE,
        ),
        VideoTrack(
            id='360p',
            codec='libx264',
            profile='main',
            preset='slow',
            constant_rate_factor=23,
            max_rate=800_000,
            buf_size=1_600_000,
            pix_fmt='yuv420p',
            width=640,
            height=360,
            force_key_frames=KEY_FRAMES.format(sec=SEGMENT_SIZE),
            gop_size=GOP_DURATION * FRAME_RATE,
            frame_rate=FRAME_RATE,
        ),
    ],
    audio=[
        AudioTrack(
            id='192k',
            codec='aac',
            bitrate=192000,
            channels=2,
            sample_rate=48000,
        ),
    ]
)
