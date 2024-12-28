import abc
import http
import os
import shutil
from pathlib import Path
from typing import Optional, Any
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
    def trailing_slash(self) -> str:  # pragma: no cover
        raise NotImplementedError

    @property
    def path(self) -> str:
        return '/'.join(('', *self.parts))

    @property
    def parent(self) -> Optional["Collection"]:
        if not self.parts:
            return None
        return Collection(*self.parts[:-1])

    def __repr__(self) -> str:
        return self.path

    def __eq__(self, other: Any) -> bool:  # pragma: no cover
        if not isinstance(other, Resource):
            return False
        return self.parts == other.parts


class Collection(Resource):
    """
    Directory in a workspace
    """

    def __repr__(self) -> str:
        return '/'.join((self.path, ''))

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

    @abc.abstractmethod
    def create_collection(self, c: Collection) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_absolute_uri(self, r: Resource) -> ParseResult:
        path = '/'.join((*Path(self.uri.path.lstrip('/')).parts, *r.parts))
        if not path:
            return self.uri
        return self.uri._replace(path='/' + path + r.trailing_slash)

    @abc.abstractmethod
    def delete_collection(self, c: Collection) -> None:  # pragma: no cover
        raise NotImplementedError

    @abc.abstractmethod
    def read(self, f: File) -> str:  # pragma: no cover
        raise NotImplementedError

    @abc.abstractmethod
    def write(self, f: File, content: str) -> None:  # pragma: no cover
        raise NotImplementedError

    @abc.abstractmethod
    def exists(self, r: Resource) -> bool:  # pragma: no cover
        raise NotImplementedError

    def __init__(self, uri: ParseResult) -> None:
        super().__init__()
        self.uri = uri._replace(path=uri.path.rstrip('/'))
        self.root = Collection()

    def ensure_collection(self, path: str) -> Collection:
        """
        Ensures that a directory with relative path exists.

        :returns: complete uri for a directory.
        """
        c = self.root.collection(*Path(path.lstrip('/')).parts)
        self.create_collection(c)
        return c


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
        try:
            shutil.rmtree(uri.path)
        except FileNotFoundError:
            self.logger.warning("dir not found: %s", uri.path)

    def exists(self, r: Resource) -> bool:
        uri = self.get_absolute_uri(r)
        self.logger.debug("exists %s", uri.path)
        return os.path.exists(uri.path)

    def read(self, r: File) -> str:
        uri = self.get_absolute_uri(r)
        self.logger.debug("read %s", uri.path)
        with open(uri.path, 'r') as f:
            return f.read()

    def write(self, r: File, content: str) -> None:
        uri = self.get_absolute_uri(r)
        self.logger.debug("write %s", uri.path)
        with open(uri.path, 'w') as f:
            f.write(content)


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
        uri = self.get_absolute_uri(c)
        self.logger.debug("delete %s", uri)
        timeout = (defaults.VIDEO_CONNECT_TIMEOUT,
                   defaults.VIDEO_REQUEST_TIMEOUT,)
        resp = self.session.request("DELETE", uri.geturl(), timeout=timeout)
        if resp.status_code == http.HTTPStatus.NOT_FOUND:
            self.logger.warning("collection not found: %s", uri.geturl())
            return
        resp.raise_for_status()

    def exists(self, r: Resource) -> bool:
        uri = self.get_absolute_uri(r)
        self.logger.debug("exists %s", uri.geturl())
        timeout = (defaults.VIDEO_CONNECT_TIMEOUT,
                   defaults.VIDEO_REQUEST_TIMEOUT,)
        resp = self.session.request("HEAD", uri.geturl(), timeout=timeout)
        if resp.status_code == http.HTTPStatus.NOT_FOUND:
            return False
        resp.raise_for_status()
        return True

    def read(self, r: File) -> str:
        uri = self.get_absolute_uri(r)
        self.logger.debug("get %s", uri.geturl())
        timeout = (defaults.VIDEO_CONNECT_TIMEOUT,
                   defaults.VIDEO_REQUEST_TIMEOUT,)
        resp = self.session.request("GET", uri.geturl(), timeout=timeout)
        resp.raise_for_status()
        return resp.text

    def write(self, r: File, content: str) -> None:
        uri = self.get_absolute_uri(r)
        self.logger.debug("put %s", uri.geturl())
        resp = self.session.request("PUT", uri.geturl(), data=content)
        resp.raise_for_status()

    def _mkcol(self, c: Collection) -> None:
        uri = self.get_absolute_uri(c)
        if not uri.path.endswith('/'):
            uri = uri._replace(path=uri.path + '/')
        self.logger.debug("mkcol %s", uri.geturl())
        timeout = (defaults.VIDEO_CONNECT_TIMEOUT,
                   defaults.VIDEO_REQUEST_TIMEOUT,)
        resp = self.session.request("MKCOL", uri.geturl(), timeout=timeout)
        if resp.status_code != http.HTTPStatus.METHOD_NOT_ALLOWED:
            # MKCOL returns 405 if collection already exists and
            # 409 if existing resource is not a collection
            resp.raise_for_status()


def init(base: str) -> Workspace:
    uri = urlparse(base)
    if uri.scheme == 'file':
        return FileSystemWorkspace(base)
    elif uri.scheme == 'dav':
        uri = uri._replace(scheme='http')
        return WebDAVWorkspace(uri.geturl())
    elif uri.scheme == 'davs':
        uri = uri._replace(scheme='https')
        return WebDAVWorkspace(uri.geturl())
    else:
        raise ValueError(base)
