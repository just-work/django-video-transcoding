#!/usr/bin/env bash
celery worker -A video_transcoding.celery --loglevel=debug -P solo -c 1

