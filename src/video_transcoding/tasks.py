import dataclasses
import os
from dataclasses import asdict
from typing import Optional, List
from uuid import UUID

import celery
import requests
from billiard.exceptions import SoftTimeLimitExceeded
from django.db.transaction import atomic

from video_transcoding import models, defaults
from video_transcoding.celery import app
from video_transcoding.transcoding import (
    profiles, transcoder, workspace, metadata,
)
from video_transcoding.utils import LoggerMixin

DESTINATION_FILENAME = '{basename}.mp4'

CONNECT_TIMEOUT = 1
DOWNLOAD_TIMEOUT = 60 * 60
UPLOAD_TIMEOUT = 60 * 60


class TranscodeVideo(LoggerMixin, celery.Task):
    """ Video processing task."""
    routing_key = 'video_transcoding'

    def run(self, video_id: int) -> Optional[str]:
        """
        Process video.

        1. Locks video changing status from QUEUED to PROCESS
        2. Transcodes video and stores result to origins
        3. Changes video status to DONE, stores result basename
        4. On errors changes video status ERROR, stores error message

        :param video_id: Video id.
        """
        status = models.Video.DONE
        error = meta = None
        video = self.lock_video(video_id)
        try:
            meta = self.process_video(video)
        except SoftTimeLimitExceeded as e:
            # celery graceful shutdown
            status = models.Video.QUEUED
            error = repr(e)
            raise self.retry(countdown=10)
        except Exception as e:
            status = models.Video.ERROR
            error = repr(e)
        finally:
            self.unlock_video(video_id, status, error, meta)
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
                     meta: Optional[dict],
                     ) -> None:
        """
        Marks video with final status.

        :param video_id: Video primary key
        :param status: final video status (Video.DONE, Video.ERROR)
        :param error: error message
        :param meta: resulting media metadata
        :raises RuntimeError: in case of unexpected video status or task id
        """
        try:
            video = self.select_for_update(video_id, models.Video.PROCESS)
        except (models.Video.DoesNotExist, ValueError) as e:
            # if video is locked or task_id differs from current task, do
            # nothing because video is modified somewhere else.
            raise RuntimeError("Can't unlock locked video %s: %s",
                               video_id, repr(e))

        video.change_status(status, error=error, metadata=meta)

    def process_video(self, video: models.Video) -> dict:
        """
        Video processing workflow.

        1. Create temporary directory
        2. Transcode source file
        3. Upload resulting file to origins
        4. Cleanup temporary directory

        :param video: Video object
        :returns: resulting file metadata.
        """
        src = metadata.Analyzer().get_meta_data(video.source)
        preset = self.init_preset(video.preset)
        profile = preset.select_profile(
            src.video, src.audio,
            container=profiles.Container(format='mp4'))

        basename = video.basename
        if basename is None:  # pragma: no cover
            raise RuntimeError("basename for video not set")

        tmp_dir_name = os.path.join(defaults.VIDEO_TEMP_DIR, basename.hex)
        ws = workspace.FileSystemWorkspace(tmp_dir_name)
        try:
            ws.create_collection(ws.root)
            dst = ws.root.file(f'{basename}.mp4')
            destination = ws.get_absolute_uri(dst)

            transcode = transcoder.Transcoder(
                video.source, destination.geturl(),
                profile=profile,
            )
            dst = transcode()
            self.store(destination.path)
            return asdict(dst)
        except Exception as e:
            self.logger.exception("Error %s", repr(e))
            raise
        finally:
            ws.delete_collection(ws.root)

    def store(self, destination: str) -> None:
        """
        Stores transcoded video to origin list

        :param destination: transcoded video path.
        """
        self.logger.info("Start saving %s to origins", destination)
        filename = os.path.basename(destination)
        timeout = (CONNECT_TIMEOUT, UPLOAD_TIMEOUT)
        for origin in defaults.VIDEO_ORIGINS:
            ws = workspace.WebDAVWorkspace(origin)
            ws.create_collection(ws.root)
            f = ws.root.file(filename)
            url = ws.get_absolute_uri(f).geturl()
            self.logger.debug("Uploading %s to %s", destination, url)
            with open(destination, 'rb') as f:
                response = requests.put(url, data=f, timeout=timeout)
                response.raise_for_status()
            self.logger.info("Uploaded to %s", url)
        self.logger.info("%s save finished", destination)

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


class ResumableTranscodeVideo(TranscodeVideo):
    def process_video(self, video: models.Video) -> dict:
        src = metadata.Analyzer().get_meta_data(video.source)
        preset = self.init_preset(video.preset)
        profile = preset.select_profile(
            src.video, src.audio,
            container=profiles.Container(
                format='m3u8',
                segment_duration=10),
        )

        root = defaults.VIDEO_TEMP_URI.rstrip('/')
        base = f'{root}/{video.basename.hex}/'
        ws = workspace.WebDAVWorkspace(base)

        root = defaults.VIDEO_ORIGINS[0].rstrip('/')
        base = f'{root}/{video.basename.hex}/'
        store = workspace.WebDAVWorkspace(base)
        try:
            sources = ws.ensure_collection('sources')
            dst = sources.file(f'source.m3u8')
            destination = ws.get_absolute_uri(dst)

            split = transcoder.Splitter(
                video.source, destination.geturl(),
                profile=profile,
            )

            meta = split()
            self.logger.debug("Split: %s", meta)

            concat = ['ffconcat version 1.0']
            segments = []
            playlist = ws.read(dst)
            for line in playlist.splitlines(keepends=False):
                if line.startswith('#'):
                    continue
                segments.append(line)
                concat.append(f"file '{line}'")

            results = ws.ensure_collection('results')

            f = results.file('concat.ffconcat')
            ws.write(f, '\n'.join(concat))

            profile.container = profiles.Container(
                format='mpegts',
                copyts=True,
            )

            for fn in segments:
                src = sources.file(fn)
                dst = results.file(fn)
                transcode = transcoder.Transcoder(
                    ws.get_absolute_uri(src).geturl(),
                    ws.get_absolute_uri(dst).geturl(),
                    profile=profile,
                )

                meta = transcode()
                self.logger.debug("Transcoded: %s", meta)

            profile.container = profiles.Container(
                format='m3u8',
                segment_duration=defaults.VIDEO_SEGMENT_DURATION,
            )

            destination = store.root.file('master.m3u8')
            segment = transcoder.HLSSegmentor(
                ws.get_absolute_uri(f).geturl(),
                store.get_absolute_uri(destination).geturl(),
                profile=profile,
                meta=meta,
            )

            result = segment()
            return dataclasses.asdict(result)
        except Exception as e:
            self.logger.exception("Error %s", repr(e))
            raise
        finally:
            self.logger.error('cleanup %s', ws.root)
            ws.delete_collection(ws.root)


resumable_transcode: ResumableTranscodeVideo = app.register_task(
    ResumableTranscodeVideo())
