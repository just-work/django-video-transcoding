from dataclasses import dataclass

from fffw.encoding import ffmpeg, vector
from fffw.wrapper import param


@dataclass
class FFMPEG(ffmpeg.FFMPEG):
    threads: int = param(default=0)


class SIMD(vector.SIMD):
    ffmpeg_wrapper = FFMPEG
