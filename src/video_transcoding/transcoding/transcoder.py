from typing import List

from fffw import encoding
from fffw.encoding.vector import SIMD, Vector

from video_transcoding import defaults
from video_transcoding.transcoding import codecs
from video_transcoding.transcoding.metadata import Metadata, Analyzer
from video_transcoding.transcoding.profiles import Profile
from video_transcoding.utils import LoggerMixin


class Transcoder(LoggerMixin):
    """
    Source transcoding logic.
    """

    def __init__(self, src: str, dst: str, profile: Profile):
        super().__init__()
        self.src = src
        self.dst = dst
        self.profile = profile

    def __call__(self) -> Metadata:
        """
        Performs source file processing.

        :return: result metadata
        """
        return self.process()

    def get_media_info(self, filename: str) -> Metadata:
        """
        Transforms video and audio metadata to a dict

        :param filename: analyzed media
        :returns: metadata object with video and audio stream
        """
        self.logger.debug("Analyzing %s", filename)
        mi = Analyzer().get_meta_data(filename)
        if not mi.videos:
            raise ValueError("missing video stream")
        if not mi.audios:
            raise ValueError("missing audio stream")
        return mi

    @staticmethod
    def run(ff: encoding.FFMPEG) -> None:
        """ Starts ffmpeg process and captures errors from it's logs"""
        return_code, output, error = ff.run()
        if return_code != 0:
            # Check return code and error messages
            error = error or f"invalid ffmpeg return code {return_code}"
            raise RuntimeError(error)

    @staticmethod
    def validate(source_media_info: Metadata,
                 dest_media_info: Metadata) -> None:
        """
        Validate video transcoding result.

        :param source_media_info: source metadata
        :param dest_media_info: result metadata
        """
        src_duration = max(source_media_info.video.duration,
                           source_media_info.audio.duration)
        dst_duration = min(dest_media_info.video.duration,
                           dest_media_info.audio.duration)
        if dst_duration < defaults.VIDEO_DURATION_TOLERANCE * src_duration:
            # Check whether result duration corresponds to source duration
            # (damaged source files may be processed successfully but result
            # is shorter)
            raise RuntimeError(f"incomplete file: {dst_duration}")

    def process(self) -> Metadata:
        src = self.get_media_info(self.src)
        ff = self.prepare_ffmpeg(src)
        self.run(ff)
        # Get result mediainfo
        dst = self.get_media_info(self.dst)
        # Validate ffmpeg result
        self.validate(src, dst)
        return dst

    def prepare_ffmpeg(self, src: Metadata) -> encoding.FFMPEG:
        """
        Prepares ffmpeg command for a given source
        :param src: input file metadata
        :return: ffmpeg wrapper
        """
        # Initialize source file descriptor with stream metadata
        source = self.prepare_input(src)

        # Initialize output file with audio and codecs from profile tracks.
        video_codecs = self.prepare_video_codecs()
        audio_codecs = self.prepre_audio_codecs()
        dst = self.prepare_output(audio_codecs, video_codecs)

        # ffmpeg wrapper with vectorized processing capabilities
        simd = SIMD(source, dst,
                    overwrite=True, loglevel='repeat+level+info')

        # per-video-track scaling
        scaling_params = [
            (video.width, video.height) for video in self.profile.video
        ]
        scaled_video = simd.video.connect(encoding.Scale, params=scaling_params)

        # connect scaled video streams to simd video codecs
        scaled_video | Vector(video_codecs)

        # pass audio as is to simd audio codecs
        simd.audio | Vector(audio_codecs)

        return simd.ffmpeg

    @staticmethod
    def prepare_input(src: Metadata) -> encoding.Input:
        return encoding.input_file(src.uri, *src.streams)

    def prepare_output(self,
                       audio_codecs: List[encoding.AudioCodec],
                       video_codecs: List[encoding.VideoCodec],
                       ) -> encoding.Output:
        return encoding.output_file(
            self.dst,
            *video_codecs,
            *audio_codecs,
            format=self.profile.container.format
        )

    def prepre_audio_codecs(self) -> List[codecs.AudioCodec]:
        audio_codecs = []
        for audio in self.profile.audio:
            audio_codecs.append(codecs.AudioCodec(
                codec=audio.codec,
                bitrate=audio.bitrate,
                channels=audio.channels,
                rate=audio.sample_rate,
            ))
        return audio_codecs

    def prepare_video_codecs(self) -> List[codecs.VideoCodec]:
        video_codecs = []
        for video in self.profile.video:
            video_codecs.append(codecs.VideoCodec(
                codec=video.codec,
                force_key_frames=video.force_key_frames,
                constant_rate_factor=video.constant_rate_factor,
                preset=video.preset,
                max_rate=video.max_rate,
                buf_size=video.buf_size,
                profile=video.profile,
                pix_fmt=video.pix_fmt,
                gop=video.gop_size,
                rate=video.frame_rate,
            ))
        return video_codecs
