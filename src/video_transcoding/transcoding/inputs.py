from dataclasses import dataclass
from typing import Any

from fffw.encoding import inputs, Stream
from fffw.wrapper import param


@dataclass
class Input(inputs.Input):
    allowed_extensions: str = param()


def input_file(filename: str, *streams: Stream, **kwargs: Any) -> Input:
    kwargs['input_file'] = filename
    if streams:
        # skip empty streams list to force Input.streams default_factory
        kwargs['streams'] = streams
    return Input(**kwargs)
