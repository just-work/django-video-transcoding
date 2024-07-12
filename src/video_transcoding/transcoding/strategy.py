import abc

from video_transcoding import defaults
from video_transcoding.transcoding.metadata import Metadata, Analyzer
from video_transcoding.utils import LoggerMixin


class Processor(LoggerMixin, abc.ABC):
    """
    A single processing step abstract class.
    """
    def __init__(self, src: str, dst: str) -> None:
        super().__init__()
        self.src = src
        self.dst = dst

    def __call__(self) -> Metadata:
        return self.process()

    @abc.abstractmethod
    def process(self) -> Metadata:
        raise NotImplementedError

    def get_media_info(self, uri: str) -> Metadata:
        """
        Transforms video and audio metadata to a dict

        :param uri: analyzed media
        :returns: metadata object with video and audio stream
        """
        self.logger.debug("Analyzing %s", uri)
        mi = Analyzer().get_meta_data(uri)
        if not mi.videos:
            raise ValueError("missing video stream")
        if not mi.audios:
            raise ValueError("missing audio stream")
        return mi
