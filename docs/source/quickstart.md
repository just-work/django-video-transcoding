Quick Start
===========

This document describes how to start transcoding for development purposes.

## Demo project

### Code checkout

```sh
git clone git@github.com:just-work/django-video-transcoding.git
cd django-video-transcoding
```

### Run admin, storage and celery worker

```sh
docker-compose up
```

* <http://localhost:8000/admin/> - Django admin (credentials are `admin:admin`)
* <http://storage.localhost:8080/videos/> - WebDAV for sources & results
* <http://storage.localhost:8080/hls/> - HLS stream endpoint

### Transcode something

* `curl -T cat.mp4 http://storage.localhost:8080/videos/sources/cat.mp4`
* Create new video with link above
* Wait till video will change status to DONE.
* On video change form admin page there is a sample video player. 

## Development environment

Development environment is deployed with `docker-compose`. It contains several 
containers:

1. `rabbitmq` - celery task broker container
2. `admin` - django admin container
3. `celery` - transcoder worker container
4. `storage` - multi-purpose `nginx` container:
    * `HTTP` server for sources 
    * `WebDAV` write-enabled server for transcoded files (`origin` role)
    * `VOD` server for `HLS` streaming with caching 
        (combines `origin` and `edge` roles)

* `SQLite` database file is used for simplicity, it is shared via `database` 
    volume between `admin` and `celery` containers
* `videos` volume is used by `storage` container for sources, transcoding 
    results and hls chunks cache
