# django-video-transcoding

Simple video transcoding application for Django Framework

[![build](https://github.com/just-work/django-video-transcoding/workflows/build/badge.svg?branch=master)](https://github.com/just-work/django-video-transcoding/actions?query=event%3Apush+branch%3Amaster+workflow%3Abuild)
[![codecov](https://codecov.io/gh/just-work/django-video-transcoding/branch/master/graph/badge.svg)](https://codecov.io/gh/just-work/django-video-transcoding)
[![Updates](https://pyup.io/repos/github/just-work/django-video-transcoding/shield.svg)](https://pyup.io/repos/github/just-work/django-video-transcoding/)
[![PyPI version](https://badge.fury.io/py/django-video-transcoding.svg)](http://badge.fury.io/py/django-video-transcoding)
[![Documentation Status](https://readthedocs.org/projects/django-video-transcoding/badge/?version=latest)](https://django-video-transcoding.readthedocs.io/en/latest/?badge=latest)

## Use as a service

Use `docker-compose.yml` as a source of inspiration.

See [quickstart.md](docs/source/quickstart.md) for details.

### Install a Django app

Use `src/dvt/settings.py` as a source of inspiration.

See [application.md](docs/source/application.md) for details.

### Tests

```
src/manage.py test
```

### Type checking

```
$> pip install mypy django-stubs
$> cd src && dmypy run -- \
   --config-file ../mypy.ini -p video_transcoding

```

## Production

### Graceful shutdown

* if you are running transcoder in docker, make sure that celery master process
  has pid 1 (docker will send SIGTERM to it by default)
* when using separate celery app, send SIGUSR1 from master to workers to trigger
  soft shutdown handling
  (see `video_transcoding.celery.send_term_to_children`)

### Settings

Application settings can be set up via env variables, see `video_transcoding.defaults`.
Also defaults can be overridden this via `django.conf.settings.VIDEO_TRANSCODING_CONFIG`.

### Model inheritance

For preset-related models use `<Model>Base` abstract models defined in `video_transcoding.models`.
For overriding `Video` model set `VIDEO_TRANSCODING_CONFIG["VIDEO_MODEL"]` key to `app_label.ModelName` in `settings`.
Connect other django models to `Video` using `video_transcoding.models.get_video_model()`.
When `Video` is overridden, video model admin is not registered automatically. As with migrations, this should be
done manually.