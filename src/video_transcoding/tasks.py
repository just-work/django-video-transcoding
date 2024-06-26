import io
import os
import shutil
import tempfile
from dataclasses import asdict
from typing import Optional, List
from uuid import UUID, uuid4
import hashlib
import celery
import requests
from billiard.exceptions import SoftTimeLimitExceeded
from django.db.transaction import atomic

from video_transcoding.transcoding import profiles, transcoder
from video_transcoding import models, defaults
from video_transcoding.celery import app
from video_transcoding.transcoding.metadata import Metadata
from video_transcoding.utils import LoggerMixin

DESTINATION_FILENAME = '{basename}.mp4'

CONNECT_TIMEOUT = 1
DOWNLOAD_TIMEOUT = 60 * 60
UPLOAD_TIMEOUT = 60 * 60


class TranscodeVideo(LoggerMixin, celery.Task):
    """ Video processing task."""
    name = 'video.transcode'
    routing_key = 'video_transcoding'

    def run(self, video_id: int, download: bool = False) -> Optional[str]:
        """
        Process video.

        1. Locks video changing status from QUEUED to PROCESS
        2. Transcodes video and stores result to origins
        3. Changes video status to DONE, stores result basename
        4. On errors changes video status ERROR, stores error message

        :param video_id: Video id.
        :param download: Download source file to tmp dir before processing.
        """
        status = models.Video.DONE
        error = basename = metadata = None
        video = self.lock_video(video_id)
        try:
            basename = uuid4().hex
            metadata = self.process_video(video, basename, download=download)
        except SoftTimeLimitExceeded as e:
            # celery graceful shutdown
            status = models.Video.QUEUED
            basename = None
            error = repr(e)
            raise self.retry(countdown=10)
        except Exception as e:
            basename = None
            status = models.Video.ERROR
            error = repr(e)
        finally:
            self.unlock_video(video_id, status, error, basename, metadata)
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
            video = models.Video.objects.select_for_update(
                skip_locked=True, of=('self',)).get(pk=video_id)
        except models.Video.DoesNotExist:
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
        try:
            video = self.select_for_update(video_id, models.Video.QUEUED)
        except (models.Video.DoesNotExist, ValueError) as e:
            # if video is locked or task_id is not equal to current task, retry.
            raise self.retry(exc=e)

        video.change_status(models.Video.PROCESS)
        return video

    @atomic
    def unlock_video(self, video_id: int, status: int, error: Optional[str],
                     basename: Optional[str], metadata: Optional[dict],
                     ) -> None:
        """
        Marks video with final status.

        :param video_id: Video primary key
        :param status: final video status (Video.DONE, Video.ERROR)
        :param error: error message
        :param basename: UUID-like result file identifier
        :param metadata: resulting media metadata
        :raises RuntimeError: in case of unexpected video status or task id
        """
        try:
            video = self.select_for_update(video_id, models.Video.PROCESS)
        except (models.Video.DoesNotExist, ValueError) as e:
            # if video is locked or task_id differs from current task, do
            # nothing because video is modified somewhere else.
            raise RuntimeError("Can't unlock locked video %s: %s",
                               video_id, repr(e))

        video.change_status(status, error=error, basename=basename,
                            metadata=metadata)

    def process_video(self, video: models.Video, basename: str,
                      download: bool = False) -> dict:
        """
        Video processing workflow.

        1. Create temporary directory
        2. Transcode source file
        3. Upload resulting file to origins
        4. Cleanup temporary directory

        :param video: Video object
        :param basename: video files common base name
        :param download: download source to temp dir
        :returns: resulting file metadata.
        """
        with tempfile.TemporaryDirectory(dir=defaults.VIDEO_TEMP_DIR,
                                         prefix=f'video-{video.pk}-') as d:
            destination = os.path.join(d, f'{basename}.mp4')
            if download:
                source = os.path.join(d, f'{basename}.src.bin')
                self.download(video.source, source)
            else:
                source = video.source
            metadata = self.transcode(source, destination, video)
            self.store(destination)

        self.logger.info("Processing done")
        return asdict(metadata)

    def download(self, source: str, destination: str) -> None:
        """
        Downloads source to temporary directory
        :param source: source file link
        :param destination: path to downloaded file
        """
        self.logger.info("Start downloading %s to %s", source, destination)
        timeout = (CONNECT_TIMEOUT, DOWNLOAD_TIMEOUT)
        if defaults.CHECKSUM_SOURCE:
            # noinspection PyUnresolvedReferences,PyProtectedMember
            checksum = hashlib.md5()  # type: Optional[hashlib._Hash]
        else:
            checksum = None
        with requests.get(
            source,
            stream=True,
            timeout=timeout,
            allow_redirects=True,
        ) as response:
            response.raise_for_status()
            with open(destination, 'wb') as f:
                encoding = response.headers.get('transfer-encoding')
                if encoding or checksum:
                    self.logger.warning(
                        "Transfer-encoding is %s, not fastest one",
                        encoding or checksum)
                    for chunk in response.iter_content(io.DEFAULT_BUFFER_SIZE):
                        f.write(chunk)
                        if checksum:
                            checksum.update(chunk)
                else:
                    shutil.copyfileobj(response.raw, f)
                content_length = response.headers.get('Content-Length')
                if content_length is not None:
                    size = f.tell()
                    if size != int(content_length):
                        raise ValueError("Partial file", size)
        self.logger.info("Downloading %s finished", source)
        if checksum:
            self.logger.info("Source file checksum: %s", checksum.hexdigest())

    def transcode(self, source: str, destination: str, video: models.Video
                  ) -> Metadata:
        """
        Starts video transcoding

        :param source: source file link (http/ftp or file path)
        :param destination: result temporary file path.
        :param video: video object.
        :returns: resulting media metadata.
        """
        self.logger.info("Start transcoding %s to %s",
                         source, destination)
        if video.preset is None:
            preset = profiles.DEFAULT_PRESET
        else:
            preset = self.init_preset(video.preset)
        t = transcoder.Transcoder(source, destination, preset)
        metadata = t.transcode()
        self.logger.info("Transcoding %s finished", source)
        return metadata

    def store(self, destination: str) -> None:
        """
        Stores transcoded video to origin list

        :param destination: transcoded video path.
        """
        self.logger.info("Start saving %s to origins", destination)
        filename = os.path.basename(destination)
        timeout = (CONNECT_TIMEOUT, UPLOAD_TIMEOUT)
        for origin in defaults.VIDEO_ORIGINS:
            url = os.path.join(origin, filename)
            self.logger.debug("Uploading %s to %s", destination, url)
            with open(destination, 'rb') as f:
                response = requests.put(url, data=f, timeout=timeout)
                response.raise_for_status()
            self.logger.info("Uploaded to %s", url)
        self.logger.info("%s save finished", destination)

    @staticmethod
    def init_preset(preset: models.Preset) -> profiles.Preset:
        """
        Initializes preset entity from database objects.
        """
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
            tracks = [t.name for t in vp.video.all()]
            video_profiles.append(profiles.VideoProfile(
                condition=vc,
                video=tracks,
            ))

        audio_profiles: List[profiles.AudioProfile] = []
        for ap in preset.audio_profiles.all():  # type: models.AudioProfile
            ac = profiles.AudioCondition(**ap.condition)
            tracks = [t.name for t in ap.audio.all()]
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
