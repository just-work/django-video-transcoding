Installation
============

This page describes installing needed components on a linux host system. For 
Docker example see `docker-compose.yml`.

System requirements
-------------------

1. [ffmpeg](http://ffmpeg.org/)
2. [mediainfo](https://mediaarea.net/en/MediaInfo)

```shell
apt-get install ffmpeg mediainfo
```

Python requirements
-------------------

```shell
pip install django-video-transcoding
```

Django integration
------------------

Add `video_transcoding` to project settings

```python
INSTALLED_APPS.append("video_transcoding")
```

Celery configuration
--------------------

`video_transcoding.celery` contains Celery application that can use environment 
variables for configuration. This application can be used as a starting point
for configuring own app.

| env                                       | description        |
|-------------------------------------------|--------------------|
| `VIDEO_TRANSCODING_CELERY_BROKER_URL`     | celery broker      |
| `VIDEO_TRANSCODING_CELERY_RESULT_BACKEND` | result backend     |
| `VIDEO_TRANSCODING_CELERY_CONCURRENCY`    | worker concurrency |

### Proper shutdown

Processing video files is a very long operation, so waiting for celery task 
complition while shutting down is inacceptable. On the other hand, if celery
worker processes are killed, lost tasks an zombie ffmpeg processes may appear.

For correct soft shutdown, a USR1 signal must be passed to celery child 
processes. This signal is treated by celery internals as `SoftTimeLimitExceeded`
exception, and `django-video-transcoding` handles it terminating `ffmpeg` child
processes correctly.

```python
import os, signal
from celery.signals import worker_shutting_down

@worker_shutting_down.connect
def send_term_to_children(**_) -> None:
    os.killpg(os.getpid(), signal.SIGUSR1)
```

Video origin and edge hosts
---------------------------

Serving video-on-demand content in the Internet requires special segmenting 
software to make HLS or MPEG/Dash fragments from mp4 files.
It may be `nginx` with Kaltura `nginx-vod-module` or anything else.

### Setting up nginx

There is an example of `nginx` setup for docker in `deploy/storage` which can
be used as starting point, and that's all. Streaming protocols are not a part
of this project, as this part is very specific for each project.

### Getting video sources

`django-video-transcoding` supports downloading video sources from any link that
can be handled with `requests` library. It's recommended to use HTTP-enabled 
storage.

As `ffmpeg` can use HTTP links directly, there is a flag allowing to skip 
source download step and start transcoding immediately:

```bash
export VIDEO_DOWNLOAD_SOURCE=1
```

### Storing transcoding results

`django-video-transcoding` stores transcode results by `HTTP PUT` request,
so results storage must support it. `nginx` with `dav` module is preferred.

For rendundancy, multiple storage hosts are supported:

```bash
export VIDEO_ORIGINS=http://storage-1/writable/,http://storage-2/writable/
```

### Generating streaming links

`django-video-transcoding` supports edge-server load balancing by generating
multiple links to video streams. Video player should support choosing single
server from multiple links.

```bash
export VIDEO_EDGES=http://edge-1/streaming/,http://edge-1/streaming/
```

### Generating manifest links

By default, `django-video-transcoding` generates HLS manifest links for
`nginx-vod-module`, but link format may be adopted to any streaming software.

```bash
export VIDEO_URL={edge}/hls/{filename}1080p.mp4/index.m3u8
```

See `video_transcoding.models.Video.format_video_url`.
