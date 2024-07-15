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
# URI for shared files
VIDEO_TEMP_URI = e('VIDEO_TEMP_URI', 'http://storage.localhost:8080/tmp/')

# A list of WebDAV endpoints for storing video results
VIDEO_ORIGINS = e('VIDEO_ORIGINS',
                  'http://storage.localhost:8080/videos/').split(',')

# Video streamer public urls (comma-separated)
VIDEO_EDGES = e('VIDEO_EDGES', 'http://storage.localhost:8080/').split(',')

# Edge video manifest url template
VIDEO_URL = '{edge}/hls/{filename}1080p.mp4/index.m3u8'

# HTTP Request timeouts
VIDEO_CONNECT_TIMEOUT = float(e('VIDEO_CONNECT_TIMEOUT', 1))
VIDEO_REQUEST_TIMEOUT = float(e('VIDEO_REQUEST_TIMEOUT', 1))

# Processing segment duration
VIDEO_CHUNK_DURATION = int(e('VIDEO_CHUNK_DURATION', 60))

# HLS playlists segment duration
VIDEO_SEGMENT_DURATION = int(e('VIDEO_SEGMENT_DURATION', 2))
