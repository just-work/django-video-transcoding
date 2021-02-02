# django-video-transcoding
Simple video transcoding application for Django Framework

[![build](https://github.com/just-work/django-video-transcoding/workflows/build/badge.svg?branch=master)](https://github.com/just-work/django-video-transcoding/actions?query=event%3Apush+branch%3Amaster+workflow%3Abuild)
[![codecov](https://codecov.io/gh/just-work/django-video-transcoding/branch/master/graph/badge.svg)](https://codecov.io/gh/just-work/django-video-transcoding)
[![Updates](https://pyup.io/repos/github/just-work/django-video-transcoding/shield.svg)](https://pyup.io/repos/github/just-work/django-video-transcoding/)
[![PyPI version](https://badge.fury.io/py/django-video-transcoding.svg)](http://badge.fury.io/py/django-video-transcoding)

## Installation

### System requirements

In case of latest Ubuntu LTS (20.04):

1. ffmpeg-4.x
  ```shell script
  $> sudo apt install ffmpeg
  ```
2. mediainfo
  ```shell script
  $> sudo apt install mediainfo 
  ```
3. RabbitMQ
  ```shell script
  $> sudo apt install rabbitmq-server
```

### django-video-transcoding

```shell script
pip install django-video-transcoding
```

### Configure Django

Edit your project `settings.py`
```python
INSTALLED_APPS += ['video_transcoding']
```

### Env

Common env variables used in django web server and celery

```
DJANGO_SETTINGS_MODULE=YOUR_PROJECT.settings
VIDEO_TRANSCODING_CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:15672/
```

Web-server-only env variables:

```
VIDEO_DOWNLOAD_SOURCE=0
VIDEO_EDGES='http://edge-1.localhost,http://edge-2.localhost'
```

Celery-only env variables:

```
VIDEO_TEMP_DIR=/tmp
VIDEO_TRANSCODING_CELERY_CONCURRENCY=2
VIDEO_ORIGINS='http://origin-1.localhost/video,http://origin-2.localhost/video'
```

Start celery worker

```shell script
$> celery worker -A video_transcoding.celery
```

## Demo project

### Run admin, storage and celery worker

```shell script
docker-compose up
```

* http://localhost:8000/admin/ - Django admin (credentials are `admin:admin`)
* http://storage.localhost:8080/videos/ - WebDAV for sources & results
* http://storage.localhost:8080/hls/ - HLS stream endpoint

### Transcode something

* `curl -T cat.mp4 http://storage.localhost:8080/videos/sources/cat.mp4`
* Create new video with link above
* Wait till video will change status to DONE.
* On video change form admin page there is a sample video player. 


## Develop

### Tests

```
src/manage.py test
```

### Type checking

```
$> pip install mypy django-stubs
$> cd src && /data/dvt/virtualenv/bin/dmypy run -- \
   --config-file ../mypy.ini -p video_transcoding

```

TBD:

* [x] travis-ci
* [ ] sphinx docs - autodoc + manual
* [x] coverage
* [x] typing
* [x] badges
* [x] video hosting demo project with docker-compose, nginx and player demo


## Production

### Graceful shutdown

* if you are running transcoder in docker, make sure that celery master process
    has pid 1 (docker will send SIGTERM to it by default)
* when using separate celery app, send SIGUSR1 from master to workers to trigger
    soft shutdown handling
    (see `video_transcoding.celery.send_term_to_children`)
