FROM python:latest

RUN apt-get update && apt-get install -y libmediainfo-dev ffmpeg

WORKDIR /app/src/
ADD ./requirements.txt /app/
RUN cd /app/ && pip install --no-cache-dir -r requirements.txt

ADD ./deploy/dvt/start-django-dev.sh /app/
ADD ./deploy/dvt/start-celery-worker.sh /app/
RUN chmod +x /app/*.sh
EXPOSE 8000
ADD ./src/ /app/src/
