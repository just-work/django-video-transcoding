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
    def process(self) -> metadata.Metadata:
        """
        Run processing logic.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def initialize(self) -> None:
        """
        Initialize workspace.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def cleanup(self, is_error: bool) -> None:
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
        self.ws = workspace.WebDAVWorkspace(base)

        if len(defaults.VIDEO_ORIGINS) > 1:
            raise RuntimeError("More that origin not supported yet")
        root = defaults.VIDEO_ORIGINS[0].rstrip('/')
        base = f'{root}/{basename}/'
        self.store = workspace.WebDAVWorkspace(base)

    @property
    def playlist_file(self) -> workspace.File:
        """
        :return: An m3u8 playlist file for split source in sources colleciton.
        """
        return self.sources.file('source.m3u8')

    @property
    def manifest_uri(self) -> str:
        """
        :return: A m3u8 master manifest uri for results at storage.
        """
        f = self.store.root.file('master.m3u8')
        return self.store.get_absolute_uri(f).geturl()

    @property
    def profile_file(self) -> workspace.File:
        """
        :return: a json file containing selected profile.
        """
        return self.sources.file('profile.json')

    def metadata_file(self, fn: str) -> workspace.File:
        """
        :param fn: chunk filename
        :return: a json file containing resulting file metadata.
        """
        return self.results.file(f'{fn}.json')

    def initialize(self) -> None:
        self.sources = self.ws.ensure_collection('sources')
        self.results = self.ws.ensure_collection('results')

    def cleanup(self, is_error: bool) -> None:
        if is_error:
            self.store.delete_collection(self.store.root)
        else:
            self.ws.delete_collection(self.ws.root)

    def process(self) -> metadata.Metadata:
        self.profile = self.select_profile()

        segments = self.split()

        result_meta: Optional[metadata.Metadata] = None
        for fn in segments:
            segment_meta = self.process_segment(fn)
            result_meta = self.merge_metadata(result_meta, segment_meta)
        if result_meta is None:
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

    def select_profile(self) -> profiles.Profile:
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

        profile = self._select_profile()

        content = json.dumps(asdict(profile))
        self.ws.write(self.profile_file, content)

        return profile

    def _select_profile(self) -> profiles.Profile:
        """
        Analyzes source file and selects profile for it from preset.

        :return: selected profile.
        """
        src = metadata.Analyzer().get_meta_data(self.source_uri)
        profile = self.preset.select_profile(
            src.video, src.audio,
            container=profiles.Container(format='m3u8'),
        )
        return profile

    def split(self) -> List[str]:
        """
        Downloads source file and split it to chunks at shared webdav.

        :return: a list of chunk filenames.
        """
        destination = self.ws.get_absolute_uri(self.playlist_file)
        container = replace(self.profile.container,
                            segment_duration=defaults.VIDEO_CHUNK_DURATION)
        profile = replace(self.profile, container=container)
        split = transcoder.Splitter(
            self.source_uri,
            destination.geturl(),
            profile=profile,
        )
        split()

        segments = self.get_segment_list()

        return segments

    def get_segment_list(self) -> List[str]:
        """
        Parses a list of segment names from a M3U8 playlist.
        :return: a list of chunk filenames.
        """
        segments = []
        content = self.ws.read(self.playlist_file)
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
        f = self.metadata_file(filename)
        if self.ws.exists(f):
            self.logger.debug("Skip %s, using metadata from %s", filename, f)
            content = self.ws.read(f)
            data = json.loads(content)
            meta = metadata.Metadata.from_native(data)
            return meta

        meta = self._process_segment(filename)

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
        profile = replace(self.profile,
                          container=profiles.Container(
                              format='mpegts',
                              copyts=True,
                          ))

        src = self.sources.file(filename)
        dst = self.results.file(filename)
        transcode = transcoder.Transcoder(
            self.ws.get_absolute_uri(src).geturl(),
            self.ws.get_absolute_uri(dst).geturl(),
            profile=profile,
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
        profile = replace(self.profile,
                          container=profiles.Container(
                              format='m3u8',
                              segment_duration=defaults.VIDEO_SEGMENT_DURATION,
                              copyts=False,
                          ))
        src = self.write_concat_file(segments)
        dst = self.manifest_uri
        self.logger.debug("Segmenting %s to %s", src, dst)
        profile.container = profiles.Container(
            format='m3u8',
            segment_duration=defaults.VIDEO_SEGMENT_DURATION,
            copyts=False,
        )
        segment = transcoder.HLSSegmentor(
            src,
            dst,
            profile=profile,
            meta=meta,
        )
        result = segment()
        return replace(meta, uri=result.uri)

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
