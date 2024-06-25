from dataclasses import dataclass

from fffw.encoding import codecs
from fffw.wrapper import param


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
