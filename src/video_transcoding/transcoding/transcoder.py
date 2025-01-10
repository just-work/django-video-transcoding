import abc
import os.path
from itertools import product
from typing import List, Dict, Any, Literal, cast
from urllib.parse import urljoin

from fffw import encoding
from fffw.encoding.vector import SIMD, Vector
from fffw.graph import VIDEO, AUDIO

from video_transcoding import defaults
from video_transcoding.transcoding import codecs, inputs, outputs, extract
from video_transcoding.transcoding.metadata import Metadata
from video_transcoding.transcoding.profiles import Profile
from video_transcoding.utils import LoggerMixin


class Processor(LoggerMixin, abc.ABC):
    """
    A single processing step abstract class.
    """
    requires_video: bool = True
    requires_audio: bool = True

    def __init__(self, src: str, dst: str, *,
                 profile: Profile,
                 meta: Metadata) -> None:
        super().__init__()
        self.src = src
        self.dst = dst
        self.profile = profile
        self.meta = meta

    def __call__(self) -> Metadata:
        return self.process()

    def process(self) -> Metadata:
        ff = self.prepare_ffmpeg(self.meta)
        self.run(ff)
        # Get result media info
        dst = self.get_result_metadata(self.dst)
        return dst

    @abc.abstractmethod
    def get_result_metadata(self, uri: str) -> Metadata:  # pragma: no cover
        """
        Get result metadata.

        :param uri: analyzed media
        :return: metadata object with video and audio stream
        """
        raise NotImplementedError()

    @staticmethod
    def run(ff: encoding.FFMPEG) -> None:
        """ Starts ffmpeg process and captures errors from it's logs"""
        return_code, output, error = ff.run()
        if return_code != 0:
            # Check return code and error messages
            error = error or f"invalid ffmpeg return code {return_code}"
            raise RuntimeError(error)

    @abc.abstractmethod
    def prepare_ffmpeg(self, src: Metadata
                       ) -> encoding.FFMPEG:  # pragma: no cover
        raise NotImplementedError


class Transcoder(Processor):
    """
    Source transcoding logic.
    """
    requires_audio = False

    def get_result_metadata(self, uri: str) -> Metadata:
        dst = extract.VideoResultExtractor().get_meta_data(uri)
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
        dst = self.prepare_output(video_codecs)

        simd = self.scale_and_encode(source, video_codecs, dst)

        return simd.ffmpeg

    def scale_and_encode(self,
                         source: inputs.Input,
                         video_codecs: List[codecs.VideoCodec],
                         dst: outputs.Output) -> SIMD:
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
        return simd

    @staticmethod
    def prepare_input(src: Metadata) -> encoding.Input:
        return inputs.input_file(src.uri, *src.streams)

    def prepare_output(self,
                       video_codecs: List[encoding.VideoCodec],
                       ) -> encoding.Output:
        return outputs.FileOutput(
            output_file=self.dst,
            method='PUT',
            codecs=[*video_codecs],
            format='mpegts',
            muxdelay='0',
            avoid_negative_ts='disabled',
            copyts=True,
        )

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


class Splitter(Processor):
    """
    Source splitting logic.
    """

    def get_result_metadata(self, uri: str) -> Metadata:
        dst = extract.SplitExtractor().get_meta_data(uri)
        # Mediainfo takes metadata from first HLS chunk in a playlist, so
        # we need to force some fields from source metadata
        if len(self.meta.videos) != len(dst.videos):  # pragma: no cover
            raise RuntimeError("Streams mismatch")
        for s, d in zip(self.meta.videos, dst.videos):
            d.bitrate = s.bitrate
        if len(self.meta.audios) != len(dst.audios):  # pragma: no cover
            raise RuntimeError("Streams mismatch")
        for s, d in zip(self.meta.audios, dst.audios):
            d.bitrate = s.bitrate
        return dst

    def prepare_ffmpeg(self, src: Metadata) -> encoding.FFMPEG:
        source = inputs.input_file(self.src, *src.streams)
        video_codecs = [source.video > codecs.Copy(kind=VIDEO)]
        audio_codecs = [source.audio > codecs.Copy(kind=AUDIO)]
        video_out = self.prepare_output(video_codecs)
        audio_out = self.prepare_output(audio_codecs)
        ff = encoding.FFMPEG(input=source, loglevel='level+info')
        ff > video_out
        ff > audio_out
        return ff

    def prepare_output(self, codecs_list: List[encoding.Codec]) -> encoding.Output:
        return outputs.SegmentOutput(**self.get_output_kwargs(codecs_list))

    def get_output_kwargs(self, codecs_list: List[encoding.Codec]) -> Dict[str, Any]:
        kinds = {c.kind for c in codecs_list}
        kind = cast(Literal["video", "audio"], kinds.pop().name.lower())
        return dict(
            codecs=codecs_list,
            format='stream_segment',
            segment_format='mkv',
            avoid_negative_ts='disabled',
            copyts=True,
            segment_list=urljoin(self.dst, f'source-{kind}.m3u8'),
            segment_list_type='m3u8',
            segment_time=defaults.VIDEO_CHUNK_DURATION,
            output_file=urljoin(self.dst, f'source-{kind}-%05d.mkv'),
        )


class Segmentor(Processor):
    """
    Result segmentation logic.
    """

    def __init__(self, *,
                 video_source: str, audio_source: str,
                 dst: str, profile: Profile,
                 meta: Metadata) -> None:
        super().__init__(video_source, dst, profile=profile, meta=meta)
        self.audio = audio_source

    def get_result_metadata(self, uri: str) -> Metadata:
        dst = extract.HLSExtractor().get_meta_data(uri)
        return dst

    def prepare_ffmpeg(self, src: Metadata) -> encoding.FFMPEG:
        video_streams = [s for s in src.streams if s.kind == VIDEO]
        video_source = inputs.input_file(self.src, *video_streams,
                                         allowed_extensions='mkv')
        video_codecs = [s > codecs.Copy(kind=VIDEO, bitrate=s.meta.bitrate)
                        for s in video_source.streams
                        if s.kind == VIDEO]
        if len(video_codecs) != len(self.profile.video):  # pragma: no cover
            raise RuntimeError("video streams mismatch")
        # We need bitrate hints for HLS bandwidth tags
        for vc, vt in zip(video_codecs, self.profile.video):
            vc.bitrate = vt.max_rate

        audio_streams = [s for s in src.streams if s.kind == AUDIO]
        audio_source = inputs.input_file(self.audio, *audio_streams)
        audio_codecs = [audio_source.audio > c for c in self.prepare_audio_codecs()]

        if len(audio_codecs) != len(self.profile.audio):  # pragma: no cover
            raise RuntimeError("audio streams mismatch")

        for ac, at in zip(audio_codecs, self.profile.audio):
            ac.bitrate = at.bitrate

        out = self.prepare_output(video_codecs + audio_codecs)
        ff = encoding.FFMPEG(input=video_source,
                             output=out,
                             loglevel='level+info')
        ff.add_input(audio_source)
        return ff

    def prepare_audio_codecs(self) -> List[codecs.AudioCodec]:
        audio_codecs = []
        for audio in self.profile.audio:
            audio_codecs.append(codecs.AudioCodec(
                codec=audio.codec,
                bitrate=audio.bitrate,
                channels=audio.channels,
                rate=audio.sample_rate,
            ))
        return audio_codecs

    def prepare_output(self,
                       codecs_list: List[encoding.Codec]
                       ) -> encoding.Output:
        return outputs.HLSOutput(
            **self.get_output_kwargs(codecs_list)
        )

    def get_output_kwargs(self,
                          codecs_list: List[encoding.Codec]
                          ) -> Dict[str, Any]:
        return dict(
            hls_time=self.profile.container.segment_duration,
            hls_playlist_type='vod',
            codecs=codecs_list,
            muxdelay='0',
            copyts=True,
            avoid_negative_ts='auto',
            var_stream_map=self.get_var_stream_map(codecs_list),
            reset_timestamps=1,
            output_file=urljoin(self.dst, 'playlist-%v.m3u8'),
            hls_segment_filename=urljoin(self.dst, 'segment-%v-%05d.ts'),
            master_pl_name=os.path.basename(self.dst),
        )

    @staticmethod
    def get_var_stream_map(codecs_list: List[encoding.Codec]) -> str:
        audios = []
        videos = []
        for c in codecs_list:
            if c.kind == VIDEO:
                videos.append(c)
            else:
                audios.append(c)
        vsm = []
        for i, a in enumerate(audios):
            vsm.append(f'a:{i},agroup:a{i}:bandwidth:{a.bitrate}')
        for (i, a), (j, v) in product(enumerate(audios), enumerate(videos)):
            vsm.append(f'v:{j},agroup:a{i}:bandwidth:{v.bitrate}')
        var_stream_map = ' '.join(vsm)
        return var_stream_map
