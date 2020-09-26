#!/usr/bin/env bash
exec celery --app video_transcoding.celery worker --loglevel=DEBUG -c 1

