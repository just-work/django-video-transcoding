import dataclasses
from pprint import pformat

from fffw.encoding import FFMPEG, input_file, Stream, Scale, output_file
from fffw.encoding.vector import SIMD, Vector
from fffw.graph import VIDEO, AUDIO

from video_transcoding.transcoding import codecs
from video_transcoding.transcoding.metadata import Metadata, Analyzer
from video_transcoding.transcoding.profiles import Preset, Profile
from video_transcoding.utils import LoggerMixin

# Allowed duration difference between source and result
DURATION_DELTA = 0.95


class TranscodeError(Exception):
    """ Video transcoding error."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class Transcoder(LoggerMixin):
    """ Video transcoder.

    >>> t = Transcoder('http://source.localhost/source.mp4', '/tmp/result.mp4')
    >>> t.transcode()
    """

    def __init__(self, source: str, destination: str, preset: Preset):
        """
        :param source: source file link (http/ftp or file path)
        :param destination: result file path
        :param preset: transcoding preset
        """
        super().__init__()
        self.source = source
        self.destination = destination
        self.preset = preset

    def get_media_info(self, filename: str) -> Metadata:
        """
        Transforms video and audio metadata to a dict

        :param filename: analyzed media
        :returns: metadata object with video and audio stream
        """
        audios, videos = Analyzer().get_meta_data(filename)

        if videos is None:
            raise TranscodeError("missing video stream")
        if audios is None:
            raise TranscodeError("missing audio stream")
        media_info = Metadata(videos=videos, audios=audios)
        self.logger.info("Parsed media info:\n%s",
                         pformat(dataclasses.asdict(media_info)))
        return media_info

    def transcode(self) -> Metadata:
        """ Transcodes video

        * checks source mediainfo
        * runs `ffmpeg`
        * validates result

        :returns: metadata with all video and audio stream in resulting file
        """
        # Get source mediainfo to use in validation
        src = self.get_media_info(self.source)

        # Select transcoding profile from source metadata
        profile = self.select_profile(src)

        # Initialize source file descriptor with stream metadata
        source = input_file(self.source,
                            Stream(VIDEO, src.video),
                            Stream(AUDIO, src.audio))

        # Initialize output file with audio and codecs from profile tracks.
        video_tracks = []
        for video in profile.video:
            video_tracks.append(codecs.VideoCodec(
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
        audio_tracks = []
        for audio in profile.audio:
            audio_tracks.append(codecs.AudioCodec(
                codec=audio.codec,
                bitrate=audio.bitrate,
                channels=audio.channels,
                rate=audio.sample_rate,
            ))
        dst = output_file(self.destination,
                          *video_tracks,
                          *audio_tracks,
                          format='mp4')

        # ffmpeg wrapper with vectorized processing capabilities
        simd = SIMD(source, dst,
                    overwrite=True, loglevel='repeat+level+info')

        # per-video-track scaling
        scaling_params = [
            (video.width, video.height) for video in profile.video
        ]
        scaled_video = simd.video.connect(Scale, params=scaling_params)

        # connect scaled video streams to simd video codecs
        scaled_video | Vector(video_tracks)

        # pass audio as is to simd audio codecs
        simd.audio | Vector(audio_tracks)

        # Run ffmpeg
        self.run(simd.ffmpeg)

        # Get result mediainfo
        dest_media_info = self.get_media_info(self.destination)

        # Validate ffmpeg result
        self.validate(src, dest_media_info)

        return dest_media_info

    def select_profile(self, src: Metadata) -> Profile:
        """
        :param src: source metadata
        :return: selected transcoding profile
        """
        profile = self.preset.select_profile(src.video, src.audio)
        return profile

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
        if dst_duration < DURATION_DELTA * src_duration:
            # Check whether result duration corresponds to source duration
            # (damaged source files may be processed successfully but result
            # is shorter)
            raise TranscodeError(f"incomplete file: {dst_duration}")

    @staticmethod
    def run(ff: FFMPEG) -> None:
        """ Starts ffmpeg process and captures errors from it's logs"""
        return_code, output, error = ff.run()
        if return_code != 0:
            # Check return code and error messages
            error = error or f"invalid ffmpeg return code {return_code}"
            raise TranscodeError(error)
