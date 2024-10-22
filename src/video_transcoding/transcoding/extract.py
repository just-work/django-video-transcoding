import abc
import json
from typing import List, cast, Any

from pymediainfo import MediaInfo

from fffw.analysis import ffprobe
from fffw.graph import meta
from video_transcoding.transcoding import analysis
from video_transcoding.transcoding.ffprobe import FFProbe
from video_transcoding.transcoding.metadata import Metadata
from video_transcoding.utils import LoggerMixin


class Extractor(LoggerMixin, abc.ABC):
    @abc.abstractmethod
    def get_meta_data(self, uri: str) -> Metadata:
        raise NotImplementedError()

    def ffprobe(self, uri: str, timeout: float = 60.0, **kwargs: Any) -> ffprobe.ProbeInfo:
        self.logger.debug("Probing %s", uri)
        ff = FFProbe(uri, show_format=True, show_streams=True, output_format='json', **kwargs)
        self.logger.debug('[%s] %s', timeout, ff.get_cmd())
        ret, output, errors = ff.run(timeout=timeout)
        if ret != 0:
            raise RuntimeError(f"ffprobe returned {ret}")
        return ffprobe.ProbeInfo(**json.loads(output))

    def mediainfo(self, uri: str) -> MediaInfo:
        self.logger.debug("Mediainfo %s", uri)
        return MediaInfo.parse(uri)


class SourceExtractor(Extractor):

    def get_meta_data(self, uri: str) -> Metadata:
        info = self.mediainfo(uri)
        video_streams: List[meta.VideoMeta] = []
        audio_streams: List[meta.AudioMeta] = []
        for s in analysis.SourceAnalyzer(info).analyze():
            if isinstance(s, meta.VideoMeta):
                video_streams.append(s)
            elif isinstance(s, meta.AudioMeta):
                audio_streams.append(s)
        return Metadata(
            uri=uri,
            videos=video_streams,
            audios=audio_streams,
        )


class NutExtractor(Extractor, abc.ABC):
    """
    Supports analyzing media with .nut extension.
    """
    def ffprobe(self, uri: str, timeout: float = 60.0, **kwargs: Any) -> ffprobe.ProbeInfo:
        kwargs.setdefault('allowed_extensions', 'nut')
        return super().ffprobe(uri, timeout, **kwargs)



class SplitExtractor(NutExtractor):
    """
    Extracts source metadata from video and audio HLS playlists.
    """

    def get_meta_data(self, uri: str) -> Metadata:
        video_uri = uri.replace('/split.json', '/source-video.m3u8')
        video_streams = analysis.NutPlaylistAnalyzer(self.ffprobe(video_uri)).analyze()
        audio_uri = uri.replace('/split.json', '/source-audio.m3u8')
        audio_streams = analysis.NutPlaylistAnalyzer(self.ffprobe(audio_uri)).analyze()
        return Metadata(
            uri=uri,
            videos=cast(List[meta.VideoMeta], video_streams),
            audios=cast(List[meta.AudioMeta], audio_streams),
        )


class VideoSegmentExtractor(NutExtractor):
    """
    Extracts metadata from video segments
    """

    def get_meta_data(self, uri: str) -> Metadata:
        streams = analysis.NutSegmentAnalyzer(self.ffprobe(uri)).analyze()
        return Metadata(
            uri=uri,
            videos=cast(List[meta.VideoMeta], streams),
            audios=[],
        )
