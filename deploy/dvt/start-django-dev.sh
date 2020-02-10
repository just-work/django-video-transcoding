#!/usr/bin/env bash

python /app/src/manage.py migrate --noinput && \
python /app/src/manage.py createsuperuser --noinput 2>/dev/null || true && \

python /app/src/manage.py runserver --noreload 0.0.0.0:8000
