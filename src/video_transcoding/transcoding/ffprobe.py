from dataclasses import dataclass
from typing import Optional

from fffw.encoding import ffprobe


@dataclass
class FFProbe(ffprobe.FFProbe):
    """
    Extends ffprobe wrapper with new arguments and output filtering.
    """
    allowed_extensions: Optional[str] = None

    def handle_stderr(self, line: str) -> str:
        if '[error]' in line:
            self.logger.error(line)
        return ''

    def handle_stdout(self, line: str) -> str:
        return line
