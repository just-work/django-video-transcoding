from logging import getLogger


class LoggerMixin:
    """
    A mixin for logger injection.

    Should not be used with Django models, because Logger contains
    non-serializable threading.Lock object.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cls = self.__class__
        self.logger = getLogger(f'{cls.__module__}.{cls.__name__}')
