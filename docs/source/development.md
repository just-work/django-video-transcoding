Development
===========

This document describes how to develop and extend 
`django-video-transcoding`.

Developing
----------

### Running tests

```shell
$> src/manage.py test
```

### Type checking

```shell 
$> pip install mypy django-stubs
$> cd src && mypy \
    --config-file=../mypy.ini \
    -p video_transcoding \
    -p django_stubs_ext
```

Configuration
-------------

* All configuration is stored in `video_transcoding.defaults` module.
* Most important variables are configured from ENV
* `settings.VIDEO_TRANSCODING_CONFIG` may be used for overriding defaults.


Extending
---------

### Celery application

* if you are running transcoder in docker, make sure that celery master process
  has pid 1 (docker will send SIGTERM to it by default)
* when using separate celery app, send SIGUSR1 from master to workers to trigger
  soft shutdown handling
  (see `video_transcoding.celery.send_term_to_children`)
* celery master should set process group in order to send SIGUSR1 to workeres
  (see `video_transcoding.celery.set_same_process_group`)

### Transcoding implementation

* extend `video_transcoding.tasks.TranscodeVideo` to change task behavior
* top-level transcoding strategy is selected in `TranscodeVideo.init_strategy`,
  see `video_transcoding.strategy.ResumableStrategy` as an example
* see `video_transcoding.transcoding.transcoder` module for low-level 
  transcoding steps examples
* dealing with different intermediate files requires metadata extraction and
  specific logic for this process is implemented in 
  `video_transcoding.transcoding.extract.Extractor` subclasses. 
* missing metadata is restored by different analyzers in 
  `video_transcoding.transcoding.analysis` module.

### Model inheritance

* For preset-related models use `<Model>Base` abstract models defined in 
  `video_transcoding.models`.
* For overriding `Video` model set `VIDEO_TRANSCODING_CONFIG["VIDEO_MODEL"]`
  key to `app_label.ModelName` in `settings`.
* Connect other django models to `Video` using
  `video_transcoding.models.get_video_model()`.
* When `Video` is overridden, video model admin is not registered automatically. 
  As with migrations, this should be done manually.
