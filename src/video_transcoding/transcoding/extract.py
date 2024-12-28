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
    def get_meta_data(self, uri: str) -> Metadata:  # pragma: no cover
        raise NotImplementedError()

    def ffprobe(self, uri: str, timeout: float = 60.0, **kwargs: Any) -> ffprobe.ProbeInfo:
        self.logger.debug("Probing %s", uri)
        ff = FFProbe(uri, show_format=True, show_streams=True, output_format='json', **kwargs)
        ret, output, errors = ff.run(timeout=timeout)
        if ret != 0:  # pragma: no cover
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
            else:  # pragma: no cover
                raise RuntimeError("unexpected stream kind")
        return Metadata(
            uri=uri,
            videos=video_streams,
            audios=audio_streams,
        )


class MKVExtractor(Extractor, abc.ABC):
    """
    Supports analyzing media from playlists with .mkv segments.
    """
    def ffprobe(self, uri: str, timeout: float = 60.0, **kwargs: Any) -> ffprobe.ProbeInfo:
        kwargs.setdefault('allowed_extensions', 'mkv')
        return super().ffprobe(uri, timeout=timeout, **kwargs)


class SplitExtractor(MKVExtractor):
    """
    Extracts source metadata from video and audio HLS playlists.
    """

    def get_meta_data(self, uri: str) -> Metadata:
        video_uri = uri.replace('/split.json', '/source-video.m3u8')
        video_streams = analysis.MKVPlaylistAnalyzer(self.ffprobe(video_uri)).analyze()
        audio_uri = uri.replace('/split.json', '/source-audio.m3u8')
        audio_streams = analysis.MKVPlaylistAnalyzer(self.ffprobe(audio_uri)).analyze()
        return Metadata(
            uri=uri,
            videos=cast(List[meta.VideoMeta], video_streams),
            audios=cast(List[meta.AudioMeta], audio_streams),
        )


class VideoSegmentExtractor(MKVExtractor):
    """
    Extracts metadata from video segments
    """

    def get_meta_data(self, uri: str) -> Metadata:
        streams = analysis.MKVSegmentAnalyzer(self.ffprobe(uri)).analyze()
        return Metadata(
            uri=uri,
            videos=cast(List[meta.VideoMeta], streams),
            audios=[],
        )


class VideoResultExtractor(MKVExtractor):
    """
    Extracts metadata from video segment transcoding results.
    """

    def get_meta_data(self, uri: str) -> Metadata:
        streams = analysis.VideoResultAnalyzer(self.ffprobe(uri)).analyze()
        # Missing bitrate is OK because it varies among segments.
        return Metadata(
            uri=uri,
            videos=cast(List[meta.VideoMeta], streams),
            audios=[],
        )


class HLSExtractor(Extractor):
    """
    Extracts metadata from HLS results.
    """

    def get_meta_data(self, uri: str) -> Metadata:
        info = self.ffprobe(uri)
        video_streams: List[meta.VideoMeta] = []
        audio_streams: List[meta.AudioMeta] = []
        for s in analysis.FFProbeHLSAnalyzer(info).analyze():
            if isinstance(s, meta.VideoMeta):
                video_streams.append(s)
            elif isinstance(s, meta.AudioMeta):
                audio_streams.append(s)
            else:  # pragma: no cover
                raise RuntimeError("invalid stream kind")
        return Metadata(
            uri=uri,
            videos=video_streams,
            audios=audio_streams,
        )
