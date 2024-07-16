from dataclasses import dataclass
from typing import Optional

from fffw.encoding.outputs import Output
from fffw.wrapper import param


@dataclass
class HLSOutput(Output):
    hls_time: Optional[float] = param(default=2)
    hls_playlist_type: Optional[str] = None
    var_stream_map: Optional[str] = None
    hls_segment_filename: Optional[str] = None
    master_pl_name: Optional[str] = None
    muxdelay: Optional[str] = None
    copyts: bool = param(default=False)


@dataclass
class FileOutput(Output):
    method: Optional[str] = param(default=None)
    copyts: bool = param(default=False)
    muxdelay: Optional[str] = None
