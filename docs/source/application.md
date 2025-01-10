Application
============

This page describes `django-video-transcoding` integration into existing
Django project.

Installation
------------

### Infrastructure requirements

1. [Compatible](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/index.html#broker-instructions)
   message broker for Celery
2. Persistent storage for temporary files
    * i.e. local FS for a single transcoding server
    * S3 persistent volume if transcoding container can move between hosts
3. Persistent storage with HTTP server for transcoded HLS streams
    * i.e. `nginx` or `S3`

### System requirements

1. [ffmpeg-6.1](http://ffmpeg.org/) or later
2. [libmediainfo](https://mediaarea.net/en/MediaInfo)

```shell
apt-get install ffmpeg libmediainfo-dev
```

### Python requirements

```shell
pip install django-video-transcoding
```

### Django integration

Add `video_transcoding` to project settings

```python
INSTALLED_APPS.append("video_transcoding")
```

### Celery configuration

`video_transcoding.celery` contains Celery application that can use environment
variables for configuration. This application can be used as a starting point
for configuring own app.

| env                                   | description              |
|---------------------------------------|--------------------------|
| `VIDEO_TRANSCODING_CELERY_BROKER_URL` | celery broker            |
| `VIDEO_TEMP_URI`                      | URI for temporary files  |
| `VIDEO_RESULTS_URI`                   | URI for transcoded files |

### Serving HLS streams

Demo uses Django Static Files for serving transcoded files, but this is
inacceptable for production usage. Please, configure HTTP server to serve files.
It may be `nginx` to serve static files and/or any `CDN` solution.

| env           | description                  |
|---------------|------------------------------|
| `VIDEO_EDGES` | URIs for serving HLS streams |
| `VIDEO_URL`   | HLS stream url template      |

Environment variables
---------------------

* `VIDEO_TRANSCODING_CELERY_BROKER_URL` (`amqp://guest:guest@rabbitmq:5672/`) - 
  Celery broker url for django-video-transcoding
* `VIDEO_TRANSCODING_CELERY_RESULT_BACKEND` (not set) - Celery result backend
  (not used)
* `VIDEO_TRANSCODING_CELERY_CONCURRENCY` (not set) - Celery concurrency
* `VIDEO_TRANSCODING_TIMEOUT` - task acknowledge timeout for AMQP backend
  (see `x-consumer-timeout` for [RabbitMQ](https://www.rabbitmq.com/docs/consumers#per-queue-delivery-timeouts-using-an-optional-queue-argument))
* `VIDEO_TRANSCODING_COUNTDOWN` (10) - transcoding task delay in seconds
* `VIDEO_TRANSCODING_WAIT` (0) - transcoding start delay in seconds (used if
  task delay is not supported by Celery broker)
* `VIDEO_TEMP_URI` - URI for temporary files (`file:///data/tmp/`). 
  Supports `file`, `http` and `https`. For HTTP uses `PUT` **and** `POST` 
  requests to store files.
* `VIDEO_RESULTS_URI` - URI for transcoded files (`file:///data/results/`).
  Supports `file`, `http` and `https`.
* `VIDEO_EDGES` - comma-separated list of public endpoints for transcoded files.
  By default uses Django static files (`http://localhost:8000/media/`).
* `VIDEO_URL` - public HLS stream template (`{edge}/results/{filename}/index.m3u8`).
  `edge` is one of `VIDEO_EDGES` and `filename` is `Video.basename` value.
* `VIDEO_CONNECT_TIMEOUT` (1) - connect timeout for HTTP requests in seconds.
* `VIDEO_REQUEST_TIMEOUT` (1) - request timeout for HTTP requests in seconds.
* `VIDEO_CHUNK_DURATION` (60) - chunk duration in seconds. Transcoder splits
  source file into chunks and then transcodes them one-by-one to handle 
  container restarts. It's recommended to align this value with 
  `VideoProfile.segment_duration` to prevent short HLS fragments every N seconds.

### Generating streaming links

`django-video-transcoding` supports edge-server load balancing by generating
multiple links to video streams. Video player should support choosing single
server from multiple links.

```bash
export VIDEO_EDGES=http://edge-1/streaming/,http://edge-1/streaming/
```

### Generating manifest links

By default, `django-video-transcoding` generates links to HLS manifests
accessible via HTTP server, but this can be customized.

```bash
export VIDEO_URL={edge}/results/{filename}/index.m3u8
```

See `video_transcoding.models.Video.format_video_url`.
