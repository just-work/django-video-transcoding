from dataclasses import dataclass
from typing import Optional, Dict, Any

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


def render_opts(value: Dict[str, Any]) -> str:
    """
    Formatter for segment_format_options option for segment muxer.

    > -segment_format_options <dictionary> ... set list of options for the container format used for the segments
    """
    return ':'.join(f'{k}={v}' for k, v in value.items())


@dataclass
class SegmentOutput(Output):
    """
    Segment muxer
    """
    segment_format: Optional[str] = None
    segment_format_options: Optional[dict] = param(render=render_opts)
    segment_list: Optional[str] = None
    segment_list_type: Optional[str] = None
    segment_time: Optional[float] = None
    min_seg_duration: Optional[float] = None


@dataclass
class FileOutput(Output):
    method: Optional[str] = param(default=None)
    copyts: bool = param(default=False)
    muxdelay: Optional[str] = None
