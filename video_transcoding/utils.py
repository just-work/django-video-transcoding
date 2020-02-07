from logging import getLogger


class LoggerMixin:
    """
    Миксин для добавления логгера к классу.

    Нельзя использовать с моделями Django, т.к. Logger содержит несериализуемый
    threading.Lock
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cls = self.__class__
        self.logger = getLogger(f'{cls.__module__}.{cls.__name__}')
