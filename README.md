# django-video-transcoding
Simple video transcoding application for Django Framework

[![Build Status](https://travis-ci.org/just-work/django-video-transcoding.svg?branch=master)](https://travis-ci.org/just-work/django-video-transcoding)
[![codecov](https://codecov.io/gh/just-work/django-video-transcoding/branch/master/graph/badge.svg)](https://codecov.io/gh/just-work/django-video-transcoding)
[![Updates](https://pyup.io/repos/github/just-work/django-video-transcoding/shield.svg)](https://pyup.io/repos/github/just-work/django-video-transcoding/)

## Installation

### System requirements

In case of latest Ubuntu LTS (18.04):

1. ffmpeg-4.0
  ```shell script
  $> sudo add-apt-repository ppa:jonathonf/ffmpeg-4
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
VIDEO_TRANSCODING_CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:15672/
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



TBD:

* [x] travis-ci
* [ ] sphinx docs - autodoc + manual
* [x] coverage
* [ ] typing
* [x] badges
