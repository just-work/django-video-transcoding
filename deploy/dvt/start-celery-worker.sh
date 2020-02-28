#!/usr/bin/env bash
celery worker -A video_transcoding.celery --loglevel=debug -c 1

