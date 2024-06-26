from dataclasses import dataclass
from typing import Tuple, List, cast

import pymediainfo
from fffw.graph.meta import VideoMeta, AudioMeta, from_media_info, VIDEO, AUDIO

from video_transcoding.utils import LoggerMixin


@dataclass
class Metadata:
    videos: List[VideoMeta]
    audios: List[AudioMeta]

    @property
    def video(self) -> VideoMeta:
        return self.videos[0]

    @property
    def audio(self) -> AudioMeta:
        return self.audios[0]


class Analyzer(LoggerMixin):
    def get_meta_data(self, filename: str
                      ) -> Tuple[List[AudioMeta], List[VideoMeta]]:
        result: pymediainfo.MediaInfo = pymediainfo.MediaInfo.parse(filename)
        for t in result.tracks:
            if t.track_type in ('Video', 'Image'):
                self.fix_par(t)
                self.fix_frames(t)
            elif t.track_type == 'Audio':
                self.fix_samples(t)
        metadata = from_media_info(result)
        video_meta: List[VideoMeta] = []
        audio_meta: List[AudioMeta] = []
        for m in metadata:
            if m.kind == VIDEO:
                video_meta.append(cast(VideoMeta, m))
            if m.kind == AUDIO:
                audio_meta.append(cast(AudioMeta, m))
        return audio_meta, video_meta

    def fix_par(self, t: pymediainfo.Track) -> None:
        """
        Fix PAR to satisfy equation DAR = width / height * PAR.
        """
        data = t.__dict__
        dar = float(data.get('display_aspect_ratio', 0))
        par = float(data.get('pixel_aspect_ratio', 0))
        width = int(data.get('width', 0))
        height = int(data.get('height', 0))

        if not (width and height):
            # not enough info to fix PAR
            self.logger.debug(
                "width or height unknown, can't restore PAR metadata")
            return
        ratio = width / height

        if not par and dar:
            self.logger.debug("restoring par from dar")
            par = dar / ratio
        elif not dar and par:
            self.logger.debug("restoring dar from par")
            dar = par * ratio
        elif not dar and not par:
            self.logger.debug("setting aspects to defaults")
            par = 1.0
            dar = ratio

        # at this moment we know all 4 variables, checking equation
        if abs(dar - ratio * par) >= 0.001:  # see fffw.meta.VideoMeta.validate
            # par is least reliable value, using it to fix equation
            par = dar / ratio
        data['display_aspect_ratio'] = f'{dar:.3f}'
        data['pixel_aspect_ratio'] = f'{par:.3f}'

    def fix_frames(self, t: pymediainfo.Track) -> None:
        """
        Fix frames count to satisfy equation:

        Duration = FPS * frames
        """
        data = t.__dict__
        duration = float(
            data.get('duration', 0)) / 1000  # duration in seconds
        frame_rate = float(data.get('frame_rate', 0))
        frames = int(data.get('frame_count', 0))

        if not duration and frames and frame_rate:
            self.logger.debug("restoring video duration")
            duration = frames / frame_rate
        elif not frames and duration and frame_rate:
            self.logger.debug("restoring frames")
            frames = round(duration * frame_rate)
        elif not frame_rate and duration and frames:
            self.logger.debug("restoging frame_rate")
            frame_rate = frames / duration
        elif not all([frames, frame_rate, duration]):
            # 2 of 3 variables are unknown, or even all of them.
            # can't restore metadata
            return

        # checking equation
        if abs(frames - duration * frame_rate) > 1:
            # frames is least reliable value
            frame_rate = frames / duration

        data['frame_rate'] = f'{frame_rate:.3f}'
        data[
            'duration'] = f'{duration * 1000.0:.3f}'  # milliseconds again
        data['frame_count'] = f'{frames}'

    def fix_samples(self, t: pymediainfo.Track) -> None:
        """
        Fix sample count to satisfy equation:

        Duration = Sampling rate * samples
        """
        data = t.__dict__
        duration = float(data.get('duration', 0)) / 1000  # duration in seconds
        sampling_rate = float(data.get('sampling_rate', 0))
        samples = int(data.get('samples_count', 0))

        if not duration and samples and sampling_rate:
            self.logger.debug("restoring audio duration")
            duration = samples / sampling_rate
        elif not samples and duration and sampling_rate:
            self.logger.debug("restoring samples")
            samples = round(duration * sampling_rate)
        elif not sampling_rate and duration and samples:
            self.logger.debug("restoging sampling_rate")
            sampling_rate = samples / duration
        elif not all([samples, sampling_rate, duration]):
            # 2 of 3 variables are unknown, or even all of them.
            # can't restore metadata
            return

        # fix sampling rate type
        sampling_rate = round(sampling_rate)
        # handle duration rounding
        duration = round(duration, 3)

        # checking equation
        if abs(samples - duration * sampling_rate) > 1:
            # samples is least reliable data, because sampling rate
            # has common values like 48000,
            # and duration is more reliable.
            samples = round(duration * sampling_rate)

        data['sampling_rate'] = f'{sampling_rate}'
        data['duration'] = f'{duration * 1000.0:.3f}'  # milliseconds again
        data['samples_count'] = f'{samples}'
