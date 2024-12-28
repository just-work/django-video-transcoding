from typing import Dict, Any, List

from fffw.analysis import ffprobe, mediainfo
from fffw.graph import meta


class SourceAnalyzer(mediainfo.Analyzer):
    """
    Universal source media analyzer.
    """


class MKVPlaylistAnalyzer(ffprobe.Analyzer):
    """
    Analyzer for HLS playlist with .mkv fragments.
    """

    def get_duration(self, track: Dict[str, Any]) -> meta.TS:
        """
        Augment track duration with a value from container.

        This is legit if media contains only a single stream.
        """
        duration = super().get_duration(track)
        if not duration and len(self.info.streams) == 1:
            duration = self.maybe_parse_duration(self.info.format.get('duration'))
        return duration


class MKVSegmentAnalyzer(MKVPlaylistAnalyzer):
    """
    Analyzer for audio/video segments in .NUT container.
    """

    def get_bitrate(self, track: Dict[str, Any]) -> int:
        bitrate = super().get_bitrate(track)
        if bitrate == 0 and len(self.info.streams) == 1:
            bitrate = int(self.info.format.get('bit_rate', 0))
        return bitrate


class VideoResultAnalyzer(ffprobe.Analyzer):
    """
    Analyzer for multi-stream video segments in MPEGTS container.
    """


class FFProbeHLSAnalyzer(ffprobe.Analyzer):
    """
    Analyzer for multi-variant HLS results.
    """

    def analyze(self) -> List[meta.Meta]:
        streams: List[meta.Meta] = []
        for stream in self.info.streams:
            if stream.get('tags', {}).get('comment'):
                # Skip HLS alternative groups
                continue
            if stream["codec_type"] == "video":
                streams.append(self.video_meta_data(**stream))
            elif stream["codec_type"] == "audio":
                streams.append(self.audio_meta_data(**stream))
            else:
                # Skip side data
                continue
        return streams

    def get_duration(self, track: Dict[str, Any]) -> meta.TS:
        duration = super().get_duration(track)
        if duration:
            return duration
        return self.maybe_parse_duration(self.info.format.get('duration'))

    def get_bitrate(self, track: Dict[str, Any]) -> int:
        bitrate = super().get_bitrate(track)
        if bitrate:
            return bitrate
        variant_bitrate = int(track.get('tags', {}).get('variant_bitrate', 0))
        # Revert multiplying real bitrate on 1.1
        # https://github.com/FFmpeg/FFmpeg/blob/n7.0.1/libavformat/hlsenc.c#L1493
        return round(variant_bitrate / 1.1)
