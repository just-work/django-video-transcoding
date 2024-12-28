import dataclasses
import time
from datetime import timedelta, datetime
from typing import Optional, List, Iterable, Any, Dict, Union
from uuid import UUID, uuid4

import celery
from billiard.exceptions import SoftTimeLimitExceeded
from django.db import close_old_connections
from django.db.transaction import atomic
from django.db.utils import OperationalError

from video_transcoding import models, strategy, defaults
from video_transcoding.celery import app
from video_transcoding.transcoding import profiles
from video_transcoding.utils import LoggerMixin

Video = models.get_video_model()

DESTINATION_FILENAME = '{basename}.mp4'

CONNECT_TIMEOUT = 1
DOWNLOAD_TIMEOUT = 60 * 60
UPLOAD_TIMEOUT = 60 * 60


class TranscodeVideo(LoggerMixin, celery.Task):
    """ Video processing task."""
    routing_key = 'video_transcoding'
    autoretry_for = (OperationalError,)
    inifinite_retry_for = (OperationalError,)
    retry_backoff = True

    def retry(self,
              args: Optional[Iterable[Any]] = None,
              kwargs: Optional[Dict[str, Any]] = None,
              exc: Optional[Exception] = None,
              throw: bool = True,
              eta: Optional[datetime] = None,
              countdown: Optional[Union[float, int]] = None,
              max_retries: Optional[int] = None,
              **options: Any) -> Any:
        if isinstance(exc, self.inifinite_retry_for):
            # increment max_retries by one to achieve unlimited retries
            # for infrastructure errors
            max_retries = (max_retries or self.max_retries) + 1
        return super().retry(args, kwargs, exc, throw, eta, countdown,
                             max_retries, **options)

    def run(self, video_id: int) -> Optional[str]:
        """
        Process video.

        1. Locks video changing status from QUEUED to PROCESS
        2. Transcodes video and stores result to origins
        3. Changes video status to DONE, stores result basename
        4. On errors changes video status ERROR, stores error message

        :param video_id: Video id.
        """
        status = Video.DONE
        error = meta = duration = None
        video = self.lock_video(video_id)
        try:
            meta = self.process_video(video)
            duration = timedelta(seconds=meta['duration'])
        except SoftTimeLimitExceeded as e:
            self.logger.debug("Received SIGUSR1, return video to queue")
            # celery graceful shutdown
            status = Video.QUEUED
            error = repr(e)
            raise self.retry(countdown=10)
        except Exception as e:
            status = Video.ERROR
            error = repr(e)
            self.logger.exception("Processing error %s", error)
        finally:
            # Close possible stale connections after long operation
            close_old_connections()
            self.unlock_video(video_id, status, error, meta, duration)
        return error

    def select_for_update(self, video_id: int, status: int) -> models.Video:
        """ Lock video in DB for current task.

        :param video_id: Video primary key
        :param status: expected video status
        :returns: Video object from db

        :raises models.Video.DoesNotExist: in case of missing or locked
            Video for primary key
        :raises ValueError: in case of unexpected Video status or task_id

        """
        try:
            video = Video.objects.select_for_update(
                skip_locked=True, of=('self',)).get(pk=video_id)
        except Video.DoesNotExist:
            self.logger.error("Can't lock video %s", video_id)
            raise

        if video.task_id != UUID(self.request.id):
            self.logger.error("Unexpected video %s task_id %s",
                              video.id, video.task_id)
            raise ValueError(video.task_id)

        if video.status != status:
            self.logger.error("Unexpected video %s status %s",
                              video.id, video.get_status_display())
            raise ValueError(video.status)
        return video

    @atomic
    def lock_video(self, video_id: int) -> models.Video:
        """
        Gets video in QUEUED status from DB and changes status to PROCESS.

        :param video_id: Video primary key
        :returns: Video object
        :raises Retry: in case of unexpected video status or task_id
        """
        if defaults.VIDEO_TRANSCODING_WAIT:  # pragma: no cover
            # Handle database replication and transaction commit related delay
            time.sleep(defaults.VIDEO_TRANSCODING_WAIT)
        try:
            video = self.select_for_update(video_id, Video.QUEUED)
        except (Video.DoesNotExist, ValueError) as e:
            # if video is locked or task_id is not equal to current task, retry.
            raise self.retry(exc=e)
        if video.basename is None:
            video.basename = uuid4()
        video.change_status(Video.PROCESS, basename=video.basename)
        return video

    @atomic
    def unlock_video(self, video_id: int, status: int, error: Optional[str],
                     meta: Optional[dict], duration: Optional[timedelta],
                     ) -> None:
        """
        Marks video with final status.

        :param video_id: Video primary key
        :param status: final video status (Video.DONE, Video.ERROR)
        :param error: error message
        :param meta: resulting media metadata
        :param duration: media duration
        :raises RuntimeError: in case of unexpected video status or task id
        """
        try:
            video = self.select_for_update(video_id, Video.PROCESS)
        except (Video.DoesNotExist, ValueError) as e:
            # if video is locked or task_id differs from current task, do
            # nothing because video is modified somewhere else.
            raise RuntimeError("Can't unlock locked video %s: %s",
                               video_id, repr(e))

        video.change_status(status,
                            error=error,
                            metadata=meta,
                            duration=duration)

    def process_video(self, video: models.Video) -> dict:
        """
        Makes an HLS adaptation set from video source.
        """
        preset = self.init_preset(video.preset)
        basename = video.basename
        if basename is None:  # pragma: no cover
            raise RuntimeError("basename not set")
        s = self.init_strategy(
            source_uri=video.source,
            basename=basename.hex,
            preset=preset,
        )
        output_meta = s()

        # noinspection PyTypeChecker
        data = dataclasses.asdict(output_meta)
        duration = None
        # cleanup internal metadata and compute duration
        for stream in data['audios'] + data['videos']:
            for f in ('scenes', 'streams', 'start', 'device'):
                stream.pop(f, None)
            if duration is None:
                duration = stream['duration']
            else:
                duration = min(duration, stream['duration'])
        data['duration'] = duration

        return data

    @staticmethod
    def init_strategy(
        source_uri: str,
        basename: str,
        preset: profiles.Preset
    ) -> strategy.Strategy:
        return strategy.ResumableStrategy(
            source_uri=source_uri,
            basename=basename,
            preset=preset,
        )

    @staticmethod
    def init_preset(preset: Optional[models.Preset]) -> profiles.Preset:
        """
        Initializes preset entity from database objects.
        """
        if preset is None:
            return profiles.DEFAULT_PRESET
        video_tracks: List[profiles.VideoTrack] = []
        for vt in preset.video_tracks.all():  # type: models.VideoTrack
            kwargs = dict(**vt.params)
            kwargs['id'] = vt.name
            video_tracks.append(profiles.VideoTrack(**kwargs))

        audio_tracks: List[profiles.AudioTrack] = []
        for at in preset.audio_tracks.all():  # type: models.AudioTrack
            kwargs = dict(**at.params)
            kwargs['id'] = at.name
            audio_tracks.append(profiles.AudioTrack(**kwargs))

        video_profiles: List[profiles.VideoProfile] = []
        for vp in preset.video_profiles.all():  # type: models.VideoProfile
            vc = profiles.VideoCondition(**vp.condition)

            vqs = vp.videoprofiletracks_set.select_related('track')
            tracks = [vpt.track.name for vpt in vqs]
            video_profiles.append(profiles.VideoProfile(
                condition=vc,
                video=tracks,
                segment_duration=vp.segment_duration.total_seconds(),
            ))

        audio_profiles: List[profiles.AudioProfile] = []
        for ap in preset.audio_profiles.all():  # type: models.AudioProfile
            ac = profiles.AudioCondition(**ap.condition)

            aqs = ap.audioprofiletracks_set.select_related('track')
            tracks = [apt.track.name for apt in aqs]
            audio_profiles.append(profiles.AudioProfile(
                condition=ac,
                audio=tracks,
            ))

        return profiles.Preset(
            video_profiles=video_profiles,
            audio_profiles=audio_profiles,
            video=video_tracks,
            audio=audio_tracks,
        )


transcode_video: TranscodeVideo = app.register_task(
    TranscodeVideo())  # type: ignore
