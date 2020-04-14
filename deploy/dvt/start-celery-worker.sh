#!/usr/bin/env bash
exec celery worker -A video_transcoding.celery --loglevel=debug -c 1

