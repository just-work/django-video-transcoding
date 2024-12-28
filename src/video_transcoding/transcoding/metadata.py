from copy import deepcopy
from dataclasses import dataclass, asdict
from pprint import pformat
from typing import List, TYPE_CHECKING

from fffw.encoding import Stream
from fffw.graph import meta

if TYPE_CHECKING:  # pragma: no cover
    from _typeshed import DataclassInstance
else:
    DataclassInstance = object


def scene_from_native(data: dict) -> meta.Scene:
    return meta.Scene(
        duration=meta.TS(data['duration']),
        start=meta.TS(data['start']),
        position=meta.TS(data['position']),
        stream=data['stream']
    )


def get_meta_kwargs(data: dict) -> dict:
    kwargs = deepcopy(data)
    kwargs['start'] = meta.TS(data['start'])
    kwargs['duration'] = meta.TS(data['duration'])
    kwargs['scenes'] = [scene_from_native(s) for s in data['scenes']]
    return kwargs


def video_meta_from_native(data: dict) -> meta.VideoMeta:
    return meta.VideoMeta(**get_meta_kwargs(data))


def audio_meta_from_native(data: dict) -> meta.AudioMeta:
    return meta.AudioMeta(**get_meta_kwargs(data))


@dataclass(repr=False)
class Metadata(DataclassInstance):
    uri: str
    videos: List[meta.VideoMeta]
    audios: List[meta.AudioMeta]

    @classmethod
    def from_native(cls, data: dict) -> 'Metadata':
        return cls(
            videos=list(map(video_meta_from_native, data['videos'])),
            audios=list(map(audio_meta_from_native, data['audios'])),
            uri=data['uri'],
        )

    @property
    def video(self) -> meta.VideoMeta:
        return self.videos[0]

    @property
    def audio(self) -> meta.AudioMeta:
        return self.audios[0]

    @property
    def streams(self) -> List[Stream]:
        streams = []
        for vm in self.videos:
            streams.append(Stream(meta.VIDEO, vm))
        for am in self.audios:
            streams.append(Stream(meta.AUDIO, am))
        return streams

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}\n{pformat(asdict(self))}'
