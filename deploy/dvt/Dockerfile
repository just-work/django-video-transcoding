FROM python:3.8 AS dvt-common

RUN apt-get update && apt-get upgrade -y && apt-get install -y
RUN apt-get install -y apt-utils
RUN apt-get install -y build-essential mediainfo libx264-dev ffmpeg

WORKDIR /app/src/
ADD ./requires.txt /app/
RUN cd /app/ && pip install --no-cache-dir -r requires.txt

FROM dvt-common AS dvt-admin
ADD ./deploy/dvt/start-django-dev.sh /app/
RUN chmod +x /app/*.sh
EXPOSE 8000
ADD ./src/ /app/src/
ADD ./db/ /app/db/

FROM dvt-common AS dvt-celery
ADD ./deploy/dvt/start-celery-worker.sh /app/
RUN chmod +x /app/*.sh
ADD ./src/ /app/src/
ADD ./db/ /app/db/
