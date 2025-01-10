from dataclasses import dataclass
from typing import Optional

from fffw.encoding import outputs
from fffw.wrapper import param


@dataclass
class Output(outputs.Output):
    copyts: bool = param(default=False)
    avoid_negative_ts: str = param()


@dataclass
class HLSOutput(Output):
    hls_time: Optional[float] = param(default=2)
    hls_playlist_type: Optional[str] = None
    var_stream_map: Optional[str] = None
    hls_segment_filename: Optional[str] = None
    master_pl_name: Optional[str] = None
    muxdelay: Optional[str] = None
    reset_timestamps: Optional[int] = 0


@dataclass
class SegmentOutput(Output):
    """
    Segment muxer
    """
    segment_format: Optional[str] = None
    segment_list: Optional[str] = None
    segment_list_type: Optional[str] = None
    segment_time: Optional[float] = None


@dataclass
class FileOutput(Output):
    method: Optional[str] = param(default=None)
    muxdelay: Optional[str] = None
