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
from video_transcoding.transcoding.metadata import Metadata, rational
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

    def get_result_metadata(self, uri: str) -> Metadata:
        """
        Get result metadata.

        :param uri: analyzed media
        :return: metadata object with video and audio stream
        """
        self.logger.debug("Analyzing %s", uri)
        mi = Analyzer().get_meta_data(uri)
        if self.requires_video and not mi.videos:
            raise ValueError("missing video stream")
        if self.requires_audio and not mi.audios:
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

    @abc.abstractmethod
    def prepare_ffmpeg(self, src: Metadata) -> encoding.FFMPEG:
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
        audio_codecs = self.prepare_audio_codecs(source)
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

        return simd.ffmpeg

    @staticmethod
    def prepare_input(src: Metadata) -> encoding.Input:
        return inputs.input_file(src.uri, *src.streams)

    def prepare_output(self,
                       audio_codecs: List[encoding.Copy],
                       video_codecs: List[encoding.VideoCodec],
                       ) -> encoding.Output:
        return outputs.FileOutput(
            output_file=self.dst,
            method='PUT',
            codecs=[*video_codecs, *audio_codecs],
            format='mpegts',
            muxdelay='0',
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

    @staticmethod
    def prepare_audio_codecs(source: encoding.Input) -> List[encoding.Copy]:
        audio_codecs = []
        for stream in source.streams:
            if stream.kind != AUDIO:
                continue
            audio_codecs.append(codecs.Copy(
                kind=AUDIO,
            ))
        return audio_codecs


class Splitter(Processor):
    """
    Source splitting logic.
    """

    def get_result_metadata(self, uri: str) -> Metadata:
        dst = extract.SplitExtractor().get_meta_data(uri)
        # Mediainfo takes metadata from first HLS chunk in a playlist, so
        # we need to force some fields from source metadata
        if len(self.meta.videos) != len(dst.videos):
            raise RuntimeError("Streams mismatch")
        for s, d in zip(self.meta.videos, dst.videos):
            d.bitrate = s.bitrate
        if len(self.meta.audios) != len(dst.audios):
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
            segment_format='nut',
            segment_format_options={},
            segment_list=urljoin(self.dst, f'source-{kind}.m3u8'),
            segment_list_type='m3u8',
            segment_time=defaults.VIDEO_CHUNK_DURATION,
            min_seg_duration=defaults.VIDEO_CHUNK_DURATION,
            output_file=urljoin(self.dst, f'source-{kind}-%05d.nut'),
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
        dst = super().get_result_metadata(uri)
        data = Analyzer().ffprobe(uri)
        # ffprobe uses audio stream as audio#0 and HLS audio group linked to
        # variants as audio#1. Video streams receive indices 2-N and thus
        # don't correspond to mediainfo streams.

        ffprobe_audio = [s for s in data.values() if s['codec_type'] == 'audio']
        for a, ff, src in zip(dst.audios, ffprobe_audio, self.meta.audios):
            # Set bitrate from "source" metadata
            a.bitrate = src.bitrate
            # Replace segment duration with source duration
            a.duration = src.duration
            a.scenes = src.scenes
            # Recompute samples from source duration
            a.samples = round(a.duration * a.sampling_rate)

        ffprobe_video = [s for s in data.values() if s['codec_type'] == 'video']
        for v, ff, src in zip(dst.videos, ffprobe_video, self.meta.videos):
            # Mediainfo estimates bitrate from first chunk which is error-prone.
            # Replace it with nominal bitrate from HLS manifest.
            bandwidth = int(ff['tags']['variant_bitrate'])
            # remove 10% overhead, see
            # https://github.com/FFmpeg/FFmpeg/blob/n7.0.1/libavformat/hlsenc.c#L1493
            v.bitrate = round(bandwidth / 1.1)
            # Replace segment duration with source duration
            v.duration = src.duration
            v.scenes = src.scenes
            # Set frame rate from ffprobe data
            v.frame_rate = rational(ff['avg_frame_rate'])
            # Compute frames from frame rate and duration
            v.frames = round(v.duration * v.frame_rate)
        return dst

    def prepare_ffmpeg(self, src: Metadata) -> encoding.FFMPEG:
        video_streams = [s for s in src.streams if s.kind == VIDEO]
        video_source = inputs.input_file(self.src, *video_streams,
                                         allowed_extensions='nut')
        video_codecs = [s > codecs.Copy(kind=VIDEO, bitrate=s.meta.bitrate)
                        for s in video_source.streams
                        if s.kind == VIDEO]
        # We need bitrate hints for HLS bandwidth tags
        for vc, vt in zip(video_codecs, self.profile.video):
            vc.bitrate = vt.max_rate

        audio_streams = [s for s in src.streams if s.kind == AUDIO]
        audio_source = inputs.input_file(self.audio, *audio_streams)
        audio_codecs = [audio_source.audio > c for c in self.prepare_audio_codecs()]

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
            var_stream_map=self.get_var_stream_map(codecs_list),
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
