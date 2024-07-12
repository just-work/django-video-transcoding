import abc
import os
from pathlib import Path
from urllib.parse import urlparse, ParseResult

import requests

from video_transcoding import defaults
from video_transcoding.utils import LoggerMixin


class Resource:
    """
    Directory or file in a workspace.
    """

    def __init__(self, *parts: str):
        self.parts = parts

    @property
    def basename(self) -> str:
        return self.parts[-1] if self.parts else ''

    @property
    def path(self) -> str:
        return '/'.join(('', *self.parts))


class Collection(Resource):
    """
    Directory in a workspace
    """

    def __repr__(self):
        return '/'.join((self.path, ''))

    def __truediv__(self, other: str) -> "Collection":
        return self.collection(other)

    def __floordiv__(self, other: str) -> "File":
        return self.file(other)

    def collection(self, *parts: str) -> "Collection":
        return Collection(*self.parts, *parts)

    def file(self, *parts: str) -> "File":
        return File(*self.parts, *parts)


class File(Resource):
    """
    File in a workspace.
    """


class Workspace(LoggerMixin, abc.ABC):

    def __init__(self, uri: ParseResult) -> None:
        super().__init__()
        self.uri = uri
        self.root = Collection()

    def ensure_collection(self, path: str) -> str:
        """
        Ensures that a directory with relative path exists.

        :returns: complete uri for a directory.
        """
        c = self.root.collection(*Path(path).parts)
        uri = self.absolute_uri(c)
        self.create_collection(c)
        return uri.geturl()

    @abc.abstractmethod
    def create_collection(self, c: Collection) -> None:
        raise NotImplementedError

    def absolute_uri(self, c: Resource) -> ParseResult:
        path = '/'.join((*Path(self.uri.path).parts, *c.parts))
        return self.uri._replace(path=path)


class FileSystemWorkspace(Workspace):

    def __init__(self, base: str) -> None:
        base = os.path.join(defaults.VIDEO_TEMP_DIR, base)
        uri = urlparse(base, scheme='file')
        super().__init__(uri)

    def create_collection(self, c: Collection) -> None:
        uri = self.absolute_uri(c)
        os.makedirs(uri.path, exist_ok=True)


class WebDAVWorkspace(Workspace):
    def __init__(self, base: str) -> None:
        uri: ParseResult = urlparse(defaults.VIDEO_TEMP_URI)
        uri = uri._replace(path=str(Path(uri.path) / base))
        super().__init__(uri)
        self.session = requests.Session()

    def create_collection(self, c: Collection) -> None:
        self._mkcol(self.root)
        tmp = self.root
        for p in c.parts:
            tmp = tmp.collection(p)
            self._mkcol(tmp)

    def _mkcol(self, c: Collection) -> None:
        uri = self.absolute_uri(c)
        self.logger.debug("mkcol %s", uri)
        timeout = (defaults.VIDEO_CONNECT_TIMEOUT,
                   defaults.VIDEO_REQUEST_TIMEOUT,)
        r = self.session.request("MKCOL", uri.geturl(), timeout=timeout)
        r.raise_for_status()
