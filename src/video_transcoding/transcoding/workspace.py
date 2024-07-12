import abc
import http
import os
import shutil
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, ParseResult

import requests

from video_transcoding import defaults
from video_transcoding.utils import LoggerMixin


class Resource(abc.ABC):
    """
    Directory or file in a workspace.
    """

    def __init__(self, *parts: str):
        self.parts = parts

    @property
    def basename(self) -> str:
        return self.parts[-1] if self.parts else ''

    @property
    @abc.abstractmethod
    def trailing_slash(self) -> str:
        raise NotImplementedError

    @property
    def path(self) -> str:
        return '/'.join(('', *self.parts))

    @property
    def parent(self) -> Optional["Collection"]:
        if not self.parts:
            return None
        return Collection(*self.parts[:-1])


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

    @property
    def trailing_slash(self) -> str:
        return '/'

    def collection(self, *parts: str) -> "Collection":
        return Collection(*self.parts, *parts)

    def file(self, *parts: str) -> "File":
        return File(*self.parts, *parts)


class File(Resource):
    """
    File in a workspace.
    """

    @property
    def trailing_slash(self) -> str:
        return ''


class Workspace(LoggerMixin, abc.ABC):

    def __init__(self, uri: ParseResult) -> None:
        super().__init__()
        self.uri = uri._replace(path=uri.path.rstrip('/'))
        self.root = Collection()

    def ensure_collection(self, path: str) -> Collection:
        """
        Ensures that a directory with relative path exists.

        :returns: complete uri for a directory.
        """
        c = self.root.collection(*Path(path).parts)
        self.create_collection(c)
        return c

    @abc.abstractmethod
    def create_collection(self, c: Collection) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_collection(self, c: Collection) -> None:
        raise NotImplementedError

    def get_absolute_uri(self, r: Resource) -> ParseResult:
        path = '/'.join((*Path(self.uri.path.lstrip('/')).parts, *r.parts))
        return self.uri._replace(path='/' + path + r.trailing_slash)


class FileSystemWorkspace(Workspace):

    def __init__(self, base: str) -> None:
        uri = urlparse(base, scheme='file')
        super().__init__(uri)

    def create_collection(self, c: Collection) -> None:
        uri = self.get_absolute_uri(c)
        self.logger.debug("mkdir %s", uri.path)
        os.makedirs(uri.path, exist_ok=True)

    def delete_collection(self, c: Collection) -> None:
        uri = self.get_absolute_uri(c)
        self.logger.debug("rmtree %s", uri.path)
        shutil.rmtree(uri.path)


class WebDAVWorkspace(Workspace):
    def __init__(self, base: str) -> None:
        super().__init__(urlparse(base))
        self.session = requests.Session()

    def create_collection(self, c: Collection) -> None:
        self._mkcol(self.root)
        tmp = self.root
        for p in c.parts:
            tmp = tmp.collection(p)
            self._mkcol(tmp)

    def delete_collection(self, c: Collection) -> None:
        self._delete(c)

    def _mkcol(self, c: Collection) -> None:
        uri = self.get_absolute_uri(c)
        if not uri.path.endswith('/'):
            uri = uri._replace(path=uri.path + '/')
        self.logger.debug("mkcol %s", uri.geturl())
        timeout = (defaults.VIDEO_CONNECT_TIMEOUT,
                   defaults.VIDEO_REQUEST_TIMEOUT,)
        r = self.session.request("MKCOL", uri.geturl(), timeout=timeout)
        if r.status_code != http.HTTPStatus.METHOD_NOT_ALLOWED:
            # MKCOL returns 405 if collection already exists and
            # 409 if existing resource is not a collection
            r.raise_for_status()

    def _delete(self, c: Collection) -> None:
        uri = self.get_absolute_uri(c)
        self.logger.debug("delete %s", uri)
        timeout = (defaults.VIDEO_CONNECT_TIMEOUT,
                   defaults.VIDEO_REQUEST_TIMEOUT,)
        r = self.session.request("DELETE", uri.geturl(), timeout=timeout)
        r.raise_for_status()