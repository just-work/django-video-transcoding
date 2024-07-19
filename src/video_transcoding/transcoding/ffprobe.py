from dataclasses import dataclass

from fffw.wrapper import BaseWrapper, param


@dataclass
class FFProbe(BaseWrapper):
    """
    ffprobe command line basic wrapper.

    >>> from fffw.encoding.codecs import VideoCodec, AudioCodec
    >>> from fffw.encoding.filters import Scale
    >>> from fffw.encoding.outputs import output_file
    >>> ff = FFProbe('/tmp/input.mp4', show_streams=True, show_format=True,
    ...     output_format='json')
    >>> ff.get_cmd()
    'ffprobe -show_streams -show_format -of json /tmp/input.mp4'
    >>>
    """
    command = 'ffprobe'
    input: str = param(name='i')
    show_streams: bool = param(default=False)
    show_format: bool = param(default=False)
    output_format: str = param(name='of')
    loglevel: str = param()

    def handle_stderr(self, line: str) -> str:
        if '[error]' in line:
            self.logger.error(line)
        return ''

    def handle_stdout(self, line: str) -> str:
        return line

