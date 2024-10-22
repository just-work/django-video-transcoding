from typing import Dict, Any

from fffw.analysis import ffprobe, mediainfo
from fffw.graph import meta


class SourceAnalyzer(mediainfo.Analyzer):
    """
    Universal source media analyzer.
    """


class NutPlaylistAnalyzer(ffprobe.Analyzer):
    """
    Analyzer for HLS playlist with .NUT fragments.
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
