from os import getenv as e

from django.conf import settings
from kombu import Queue

CELERY_APP_NAME = 'video_transcoding'

try:
    VIDEO_TRANSCODING_CELERY_CONF = getattr(
        settings, 'VIDEO_TRANSCODING_CELERY_CONF',
    )
except AttributeError:
    video_transcoding_timeout = int(e('VIDEO_TRANSCODING_TIMEOUT', 0))
    if video_transcoding_timeout:  # pragma: no cover
        queue_arguments = {
            # Prevent RabbitMQ closing broker connection while running
            # a long transcoding task
            'x-consumer-timeout': video_transcoding_timeout * 1000
        }
    else:
        queue_arguments = {}
    VIDEO_TRANSCODING_CELERY_CONF = {
        'broker_url': e('VIDEO_TRANSCODING_CELERY_BROKER_URL',
                        'amqp://guest:guest@rabbitmq:5672/'),
        'result_backend': e('VIDEO_TRANSCODING_CELERY_RESULT_BACKEND', None),
        'task_default_exchange': CELERY_APP_NAME,
        'task_default_exchange_type': 'topic',
        'task_default_queue': CELERY_APP_NAME,
        'worker_prefetch_multiplier': 1,
        'worker_concurrency': e('VIDEO_TRANSCODING_CELERY_CONCURRENCY'),
        'task_acks_late': True,
        'task_reject_on_worker_lost': True,
        'task_queues': [
            Queue(
                CELERY_APP_NAME,
                routing_key=CELERY_APP_NAME,
                queue_arguments=queue_arguments
            ),
        ]
    }

# delay between sending celery task and applying it
VIDEO_TRANSCODING_COUNTDOWN = int(e('VIDEO_TRANSCODING_COUNTDOWN', 10))
# delay between applying celery task and locking video
VIDEO_TRANSCODING_WAIT = int(e('VIDEO_TRANSCODING_WAIT', 0))

# URI for shared files
VIDEO_TEMP_URI = e('VIDEO_TEMP_URI', 'file:///data/tmp/')
# URI for result files
VIDEO_RESULTS_URI = e('VIDEO_RESULTS_URI', 'file:///data/results/')

# Video streamer public urls (comma-separated)
VIDEO_EDGES = e('VIDEO_EDGES', 'http://localhost:8000/media/').split(',')

# Edge video manifest url template
VIDEO_URL = e('VIDEO_URL', '{edge}/results/{filename}/index.m3u8')

# HTTP Request timeouts
VIDEO_CONNECT_TIMEOUT = float(e('VIDEO_CONNECT_TIMEOUT', 1))
VIDEO_REQUEST_TIMEOUT = float(e('VIDEO_REQUEST_TIMEOUT', 1))

# Processing segment duration
VIDEO_CHUNK_DURATION = int(e('VIDEO_CHUNK_DURATION', 60))

VIDEO_MODEL = 'video_transcoding.Video'

_default_config = locals()
_local_config = getattr(settings, 'VIDEO_TRANSCODING_CONFIG', {})
for k, v in _local_config.items():
    if k not in _default_config:  # pragma: no cover
        raise KeyError(k)
    _default_config[k] = v
