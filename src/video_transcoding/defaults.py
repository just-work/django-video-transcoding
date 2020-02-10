from os import getenv as e

from kombu import Queue


CELERY_APP_NAME = 'video_transcoding'


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
        Queue(CELERY_APP_NAME, routing_key=CELERY_APP_NAME),
    ]
}

# Directory for large output files
VIDEO_TEMP_DIR = '/tmp'

# A list of WebDAV endpoints for storing video results
VIDEO_ORIGINS = e('VIDEO_ORIGINS',
                  'http://video.localhost:80/origin-1/').split(',')
