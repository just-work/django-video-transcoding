Quick Start
===========

This document describes how to start django-video-transcoding as a service
with demo docker-compose config.

## Code checkout

```sh
git clone git@github.com:just-work/django-video-transcoding.git
cd django-video-transcoding
```

## Run admin, webdav and celery worker

```sh
docker-compose up
```

* <http://localhost:8000/admin/> - Django admin (credentials are `admin:admin`)
* <http://localhost:8000/media/> - Transcoded HLS streams served by Django 
* <http://sources.local/> - WebDAV for sources

### Transcode something

* Add `sources.local` to hosts file
* `curl -T cat.mp4 http://sources.local/`
* Create new video with link above
* Wait till video will change status to DONE.
* On video change form admin page there is a sample video player. 

## Development environment

Development environment is deployed with `docker-compose`. It contains several 
containers:

1. `rabbitmq` - celery task broker container
2. `admin` - django admin container
3. `celery` - transcoder worker container
4. `sources` - `WebDAV` write-enabled server for source files

* `SQLite` database file is used for simplicity, it is shared via `database` 
    volume between `admin` and `celery` containers
* `sources` volume is used by `sources` container for sources video
* `tmp` volume is used by `celery` container for temporary files
* `results` volume is used by `celery` container for saving transcoded HLS 
  streams which are then served by `admin` container for CORS bypass 
