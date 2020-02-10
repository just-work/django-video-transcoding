from logging import getLogger
from typing import Any


class LoggerMixin:
    """
    A mixin for logger injection.

    Should not be used with Django models, because Logger contains
    non-serializable threading.Lock object.
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)  # type: ignore
        cls = self.__class__
        self.logger = getLogger(f'{cls.__module__}.{cls.__name__}')
