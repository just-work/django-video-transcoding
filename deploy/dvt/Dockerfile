FROM ubuntu:24.04

RUN apt-get update && apt-get install -y libmediainfo-dev ffmpeg python3-dev python3-pip python-is-python3

WORKDIR /app/src/
ADD ./requirements.txt /app/
RUN cd /app/ && pip install --break-system-packages --no-cache-dir -r requirements.txt

ADD ./deploy/dvt/start-django-dev.sh /app/
ADD ./deploy/dvt/start-celery-worker.sh /app/
RUN chmod +x /app/*.sh
EXPOSE 8000
ADD ./src/ /app/src/
