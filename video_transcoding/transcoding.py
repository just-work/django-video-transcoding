from pprint import pformat
from typing import Optional, Dict, Any

import pymediainfo
from fffw.encoding import FFMPEG, VideoCodec, AudioCodec, Muxer
from fffw.graph import SourceFile

from video_transcoding.utils import LoggerMixin

# Ключи метаданных видео
AUDIO_CODEC = 'audio_codec'
VIDEO_CODEC = 'video_codec'
AUDIO_DURATION = 'audio_duration'
VIDEO_DURATION = 'video_duration'

MEDIA_INFO_MSG_FORMAT = """%s media info:
VIDEO:
%s
AUDIO: 
%s
"""

# Параметры транскодирования видео
TRANSCODING_OPTIONS = {
    VIDEO_CODEC: {
        'vcodec': 'libx264',
        'vbitrate': 5_000_000,
        'size': '1920x1080'
    },
    AUDIO_CODEC: {
        'acodec': 'aac',
        'abitrate': 192000
    },
}

Metadata = Dict[str, Any]
""" Словарь, описывающий метаданные видеофайла."""


class TranscodeError(Exception):
    """ Ошибка обработки видео."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class Transcoder(LoggerMixin):
    """ Транскодер видео."""

    def __init__(self, source: str, destination: str):
        """
        :param source: ссылка на исходный файл (HTTP)
        :param destination: путь до результата во временной папке
        """
        super().__init__()
        self.source = source
        self.destination = destination

    def get_media_info(self, filename: str) -> Metadata:
        """
        Получает метаданные о видеофайле и возвращает их в удобном для работы
        формате.
        :param filename: путь или ссылка до видеофайла
        :returns: одноуровневый словарь информации о видеофайле
        """
        result: pymediainfo.MediaInfo = pymediainfo.MediaInfo.parse(filename)
        video: Optional[pymediainfo.Track] = None
        audio: Optional[pymediainfo.Track] = None
        for track in result.tracks:
            if track.track_type == 'Video':
                video = track
            if track.track_type == 'Audio':
                audio = track

        self.logger.info(MEDIA_INFO_MSG_FORMAT,
                         filename,
                         pformat(getattr(video, '__dict__', None)),
                         pformat(getattr(audio, '__dict__', None)))

        if video is None:
            raise TranscodeError("missing video stream")
        if audio is None:
            raise TranscodeError("missing audio stream")

        media_info = {
            'width': int(video.width),
            'height': int(video.height),
            'aspect': float(video.display_aspect_ratio),
            'par': float(video.pixel_aspect_ratio),
            VIDEO_DURATION: float(video.duration),
            'video_bitrate': float(video.bit_rate),
            'video_frame_rate': float(video.frame_rate),
            'audio_bitrate': float(audio.bit_rate),
            'audio_sampling_rate': float(audio.sampling_rate),
            AUDIO_DURATION: float(audio.duration),
        }
        self.logger.info("Parsed media info:\n%s", pformat(media_info))
        return media_info

    def transcode(self):
        """ Выполняет транскодирование видео."""
        # Получаем метаданные исходника, чтобы потом использовать в проверках
        source_media_info = self.get_media_info(self.source)

        # Настраиваем общие флаги ffmpeg
        ff = FFMPEG(overwrite=True, loglevel='repeat+level+info')
        # Инициализируем исходник
        ff < SourceFile(self.source)

        # Настраиваем кодеки, формат и путь до результата
        cv0 = VideoCodec(**TRANSCODING_OPTIONS[VIDEO_CODEC])
        ca0 = AudioCodec(**TRANSCODING_OPTIONS[AUDIO_CODEC])
        out0 = Muxer(self.destination, format='mp4')

        # Добавляем выходной файл к параметрам ffmpeg
        ff.add_output(out0, cv0, ca0)

        # Запускаем ffmpeg
        self.run(ff)

        # Получаем метаданные результата
        dest_media_info = self.get_media_info(self.destination)

        # Проверяем результат на корректность
        self.validate(source_media_info, dest_media_info)

    @staticmethod
    def validate(source_media_info: Metadata, dest_media_info: Metadata):
        """
        Проверяет корректность транскодирования видео.

        :param source_media_info: метаданные исходника
        :param dest_media_info: метаданные результата
        """
        src_duration = max(source_media_info[VIDEO_DURATION],
                           source_media_info[AUDIO_DURATION])
        dst_duration = min(dest_media_info[VIDEO_DURATION],
                           dest_media_info[AUDIO_DURATION])
        if dst_duration < 0.95 * src_duration:
            # Проверяем, что длительность результата соответствует длительности
            # результата обработки (проверка на битые исходники)
            raise TranscodeError(f"incomplete file: {dst_duration}")

    def run(self, ff: FFMPEG):
        """ Запускает ffmpeg и следит за его логами."""
        return_code, error = ff.run()
        self.logger.info("ffmpeg return code is %s", return_code)
        if error or return_code != 0:
            # Проверяем код возврата ffmpeg и наличие сообщений об ошибках
            error = error or f"invalid ffmpeg return code {return_code}"
            raise TranscodeError(error)
