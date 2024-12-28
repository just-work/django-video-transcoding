import abc
import json
from dataclasses import replace, asdict
from types import TracebackType
from typing import Type, List, Optional

from video_transcoding import defaults
from video_transcoding.transcoding import (
    workspace,
    profiles,
    metadata,
    transcoder,
    extract,
)
from video_transcoding.utils import LoggerMixin


class Strategy(LoggerMixin, abc.ABC):
    """
    Transcoding strategy.
    """

    def __init__(self,
                 source_uri: str,
                 basename: str,
                 preset: profiles.Preset,
                 ) -> None:
        """

        :param source_uri: URI of source file at remote storage.
        :param basename: common prefix for temporary and resulting paths.
        :param preset: preset to choose profile from.

        >>> from uuid import uuid4
        >>> s = Strategy(source_uri='http://storage.localhost:8080/source.mp4',
        ...              basename=uuid4().hex,
        ...              preset=profiles.DEFAULT_PRESET)
        >>> result_metadata = s()
        """
        super().__init__()
        self.source_uri = source_uri
        self.basename = basename
        self.preset = preset

    def __call__(self) -> metadata.Metadata:
        """
        Entrypoint.
        :return: result media metadata.
        """
        with self:
            return self.process()

    def __enter__(self) -> None:
        """
        Initializes working and result directories on open context.
        """
        self.initialize()

    def __exit__(self,
                 exc_type: Type[Exception],
                 exc_val: Exception,
                 exc_tb: TracebackType) -> None:
        """
        Cleanups working and result directories on context exit.
        """
        self.cleanup(is_error=exc_type is not None)

    @abc.abstractmethod
    def process(self) -> metadata.Metadata:  # pragma: no cover
        """
        Run processing logic.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def initialize(self) -> None:  # pragma: no cover
        """
        Initialize workspace.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def cleanup(self, is_error: bool) -> None:  # pragma: no cover
        """
        Cleanup workspace.

        :param is_error: True if processing finished with an error
        """
        raise NotImplementedError


class ResumableStrategy(Strategy):
    """
    Transcoding strategy implementation with resume support.

    Source file is downloaded to temporary shared webdav directory,
    split to chunks. Chunks are transcoded on by one and merged to a
    single file at the end. Resulting file is segmented to HLS on
    a result storage.
    """
    sources: workspace.Collection
    """
    A collection to store split source file downloaded to shared webdav."""
    results: workspace.Collection
    """
    A collection to store split resulting chunks after transcoding.
    """
    profile: profiles.Profile
    """
    Profile selected for current source.
    """

    def __init__(self,
                 source_uri: str,
                 basename: str,
                 preset: profiles.Preset,
                 ) -> None:
        super().__init__(source_uri, basename, preset)

        root = defaults.VIDEO_TEMP_URI.rstrip('/')
        base = f'{root}/{basename}/'
        self.ws = workspace.init(base)

        root = defaults.VIDEO_RESULTS_URI.rstrip('/')
        base = f'{root}/{basename}/'
        self.store = workspace.init(base)

    @property
    def source_metadata(self) -> workspace.File:
        """
        :return: A json file with source metadata.
        """
        return self.sources.file('source.json')

    @property
    def split_metadata(self) -> workspace.File:
        """
        :return: A json file with metadata for split file.
        """
        return self.sources.file('split.json')

    @property
    def video_playlist_file(self) -> workspace.File:
        """
        :return: An m3u8 playlist file for split video source.
        """
        return self.sources.file('source-video.m3u8')

    @property
    def audio_playlist_file(self) -> workspace.File:
        """
        :return: An m3u8 playlist file for transcoded audio.
        """
        return self.sources.file('source-audio.m3u8')

    @property
    def manifest_uri(self) -> str:
        """
        :return: A m3u8 master manifest uri for results at storage.
        """
        f = self.store.root.file('index.m3u8')
        return self.store.get_absolute_uri(f).geturl()

    @property
    def profile_file(self) -> workspace.File:
        """
        :return: a json file containing selected profile.
        """
        return self.sources.file('profile.json')

    @staticmethod
    def metadata_file(file: workspace.File) -> workspace.File:
        """
        :param file: chunk filename
        :return: a json file containing resulting file metadata.
        """
        parts = list(file.parts)
        parts[-1] = f'{file.basename}.json'
        return workspace.File(*parts)

    def initialize(self) -> None:
        self.ws.create_collection(self.ws.root)
        self.sources = self.ws.ensure_collection('sources')
        self.results = self.ws.ensure_collection('results')
        self.store.create_collection(self.store.root)

    def cleanup(self, is_error: bool) -> None:
        if is_error:
            self.store.delete_collection(self.store.root)
        else:
            self.ws.delete_collection(self.ws.root)

    def process(self) -> metadata.Metadata:
        src = self.analyze_source()
        self.profile = self.select_profile(src)

        self.split(src)

        segments = self.get_segment_list()

        result_meta: Optional[metadata.Metadata] = None
        for fn in segments:
            segment_meta = self.process_segment(fn)
            result_meta = self.merge_metadata(result_meta, segment_meta)
        if result_meta is None:  # pragma: no cover
            raise RuntimeError("no segments")

        return self.merge(segments, meta=result_meta)

    @staticmethod
    def merge_metadata(result_meta: Optional[metadata.Metadata],
                       segment_meta: metadata.Metadata,
                       ) -> metadata.Metadata:
        """
        Appends next chunk metadata to resulting file metadata.

        Combines duration, scenes and samples/frames count.

        :param result_meta: resulting file metadata.
        :param segment_meta: chunk metadata.
        :return: updated resulting file metadata.
        """
        if result_meta is None:
            return segment_meta
        pairs = zip(result_meta.audios, segment_meta.audios)
        for i, (r, s) in enumerate(pairs):
            r = replace(r,
                        duration=r.duration + s.duration,
                        samples=r.samples + s.samples,
                        scenes=r.scenes + s.scenes,
                        )
            result_meta.audios[i] = r
        pairs = zip(result_meta.videos, segment_meta.videos)
        for i, (r, s) in enumerate(pairs):
            r = replace(r,
                        duration=r.duration + s.duration,
                        frames=r.frames + s.frames,
                        scenes=r.scenes + s.scenes,
                        )
            result_meta.videos[i] = r
        return result_meta

    def analyze_source(self) -> metadata.Metadata:
        """
        Analyzes source file

        :return: source file metadata
        """
        if self.ws.exists(self.source_metadata):
            self.logger.debug("Using previous metadata %s",
                              self.source_metadata)
            content = self.ws.read(self.source_metadata)
            data = json.loads(content)
            return metadata.Metadata.from_native(data)

        meta = self._analyze_source()

        # noinspection PyTypeChecker
        content = json.dumps(asdict(meta))
        self.ws.write(self.source_metadata, content)

        return meta

    def _analyze_source(self) -> metadata.Metadata:
        """
        Runs source file analysis
        :return: source file metadata.
        """
        src = extract.SourceExtractor().get_meta_data(self.source_uri)
        return src

    def select_profile(self, src: metadata.Metadata) -> profiles.Profile:
        """
        Selects profile for input if it has not already been selected.

        Selected profile is stored in sources collection.
        :return: selected or cached profile.
        """
        if self.ws.exists(self.profile_file):
            self.logger.debug("Using previous profile %s", self.profile_file)
            content = self.ws.read(self.profile_file)
            data = json.loads(content)
            return profiles.Profile.from_native(data)

        profile = self._select_profile(src)

        # noinspection PyTypeChecker
        content = json.dumps(asdict(profile))
        self.ws.write(self.profile_file, content)

        return profile

    def _select_profile(self, src: metadata.Metadata) -> profiles.Profile:
        """
        Analyzes source file and selects profile for it from preset.

        :return: selected profile.
        """
        profile = self.preset.select_profile(src.video, src.audio)
        return profile

    def split(self, src: metadata.Metadata) -> metadata.Metadata:
        """
        Splits source file to chunks at shared webdav

        :param src: remote source metadata.
        :return: a list of chunk filenames.
        """
        f = self.split_metadata
        if self.ws.exists(f):
            # split metadata is already written after playlists finished, reuse it
            self.logger.debug("Source already split to %s", self.split_metadata)
            content = self.ws.read(f)
            data = json.loads(content)
            meta = metadata.Metadata.from_native(data)
            return meta

        meta = self._split(src)
        # noinspection PyTypeChecker
        content = json.dumps(asdict(meta))
        self.ws.write(f, content)
        return meta

    def _split(self, src: metadata.Metadata) -> metadata.Metadata:
        """
        Downloads source file and split it to chunks at shared webdav.
        """
        destination = self.ws.get_absolute_uri(self.split_metadata)
        split = transcoder.Splitter(
            self.source_uri,
            destination.geturl(),
            profile=self.profile,
            meta=src,
        )
        return split()

    def get_segment_list(self) -> List[str]:
        """
        Parses a list of segment names from a M3U8 playlist.
        :return: a list of chunk filenames.
        """
        segments = []
        content = self.ws.read(self.video_playlist_file)
        for line in content.splitlines(keepends=False):
            if line.startswith('#'):
                continue
            segments.append(line)
        return segments

    def process_segment(self, filename: str) -> metadata.Metadata:
        """
        Transcodes source chunk to a resulting chunk if not yed transcoded.

        Skips transcoding if resulting chunk metadata exists on shared webdav.
        :param filename: chunk filename
        :return: resulting chunk metadata.
        """
        f = self.metadata_file(self.results.file(filename))
        if self.ws.exists(f):
            self.logger.debug("Skip %s, using metadata from %s", filename, f)
            content = self.ws.read(f)
            data = json.loads(content)
            meta = metadata.Metadata.from_native(data)
            return meta

        meta = self._process_segment(filename)

        # noinspection PyTypeChecker
        content = json.dumps(asdict(meta))
        self.ws.write(f, content)
        return meta

    def _process_segment(self, filename: str) -> metadata.Metadata:
        """
        Runs transcoding process on a source chunk.
        :param filename: chunk filename
        :return: resulting file metadata.
        """
        self.logger.debug("Processing %s", filename)
        src = self.sources.file(filename)
        meta = self.get_segment_meta(src)
        dst = self.results.file(filename)
        transcode = transcoder.Transcoder(
            self.ws.get_absolute_uri(src).geturl(),
            self.ws.get_absolute_uri(dst).geturl(),
            profile=self.profile,
            meta=meta,
        )
        meta = transcode()
        self.logger.debug("Transcoded: %s", meta)
        return meta

    def merge(self,
              segments: List[str],
              meta: metadata.Metadata,
              ) -> metadata.Metadata:
        """
        Combines resulting chunks to a single output and segments it to HLS.
        :param segments: list of chunk filenames.
        :param meta: resulting file metadata.
        :return: resulting file metadata.
        """
        src = self.write_concat_file(segments)
        dst = self.manifest_uri
        self.logger.debug("Segmenting %s to %s", src, dst)
        audio = self.ws.get_absolute_uri(self.audio_playlist_file).geturl()
        segment = transcoder.Segmentor(
            video_source=src,
            audio_source=audio,
            dst=dst,
            profile=self.profile,
            meta=meta,
        )
        result = segment()
        return result

    def write_concat_file(self, segments: List[str]) -> str:
        """
        Writes ffconcat file to a shared collection
        :param segments: segments list
        :return: uri for ffconcat file
        """
        concat = ['ffconcat version 1.0']
        for fn in segments:
            concat.append(f"file '{fn}'")
        f = self.results.file('concat.ffconcat')
        self.ws.write(f, '\n'.join(concat))
        return self.ws.get_absolute_uri(f).geturl()

    def get_segment_meta(self, src: workspace.File) -> metadata.Metadata:
        segment_uri = self.ws.get_absolute_uri(src).geturl()
        segment = extract.VideoSegmentExtractor().get_meta_data(segment_uri)
        return segment
