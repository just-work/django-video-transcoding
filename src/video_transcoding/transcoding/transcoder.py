import abc
import os.path
from itertools import product
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from fffw import encoding
from fffw.encoding.vector import SIMD, Vector
from fffw.graph import VIDEO, AUDIO

from video_transcoding.transcoding import codecs, outputs
from video_transcoding.transcoding.metadata import Metadata, Analyzer
from video_transcoding.transcoding.profiles import Profile
from video_transcoding.utils import LoggerMixin


class Processor(LoggerMixin, abc.ABC):
    """
    A single processing step abstract class.
    """

    def __init__(self, src: str, dst: str, *,
                 profile: Profile,
                 meta: Optional[Metadata] = None) -> None:
        super().__init__()
        self.src = src
        self.dst = dst
        self.profile = profile
        self.meta = meta

    def __call__(self) -> Metadata:
        return self.process()

    def process(self) -> Metadata:
        if self.meta is None:
            self.meta = self.get_media_info(self.src)
        ff = self.prepare_ffmpeg(self.meta)
        self.run(ff)
        # Get result mediainfo
        dst = self.get_media_info(self.dst)
        return dst

    def get_media_info(self, uri: str,
                       requires_audio: bool = True,
                       requires_video: bool = True) -> Metadata:
        """
        Transforms video and audio metadata to a dict

        :param uri: analyzed media
        :param requires_audio: throw an error if audio stream is missing
        :param requires_video: throw an error if video stream is missing
        :return: metadata object with video and audio stream
        """
        self.logger.debug("Analyzing %s", uri)
        mi = Analyzer().get_meta_data(uri)
        if requires_video and not mi.videos:
            raise ValueError("missing video stream")
        if requires_audio and not mi.audios:
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

    def get_media_info(self,
                       uri: str,
                       requires_audio: bool = False,
                       requires_video: bool = True) -> Metadata:
        # Changed requires_audio default to False
        return super().get_media_info(uri, requires_audio, requires_video)

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
        return encoding.input_file(src.uri, *src.streams)

    def prepare_output(self,
                       audio_codecs: List[encoding.Copy],
                       video_codecs: List[encoding.VideoCodec],
                       ) -> encoding.Output:
        return outputs.FileOutput(
            output_file=self.dst,
            method='PUT',
            codecs=[*video_codecs, *audio_codecs],
            format=self.profile.container.format,
            muxdelay='0',
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

    def prepare_ffmpeg(self, src: Metadata) -> encoding.FFMPEG:
        source = encoding.input_file(self.src, *src.streams)
        bitrate = source.video.meta.bitrate
        codecs_list = [source.video > codecs.Copy(kind=VIDEO, bitrate=bitrate)]
        codecs_list.extend([source.audio > c
                            for c in self.prepre_audio_codecs()])
        out = self.prepare_output(codecs_list)
        return encoding.FFMPEG(input=source, output=out, loglevel='level+info')

    def prepare_output(self,
                       codecs_list: List[encoding.Codec]
                       ) -> encoding.Output:
        return outputs.HLSOutput(
            **self.get_output_kwargs(codecs_list)
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

    def get_output_kwargs(self,
                          codecs_list: List[encoding.Codec]
                          ) -> Dict[str, Any]:
        return dict(
            hls_time=self.profile.container.segment_duration,
            hls_playlist_type='vod',
            codecs=codecs_list,
            muxdelay='0',
            copyts=True,
            output_file=urljoin(self.dst, 'playlist-%v.m3u8'),
            hls_segment_filename=urljoin(self.dst, 'segment-%v-%05d.ts'),
            master_pl_name=os.path.basename(self.dst),
            var_stream_map=self.get_var_stream_map(codecs_list)
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
            vsm.append(f'a:{i},name:audio-{i}')
        for (i, a), (j, v) in product(enumerate(audios), enumerate(videos)):
            vsm.append(f'v:{j},name:video-{i}')
        var_stream_map = ' '.join(vsm)
        return var_stream_map


class Segmentor(Processor):
    """
    Result segmentation logic.
    """

    def __init__(self, *,
                 video_source: str, audio_source: str,
                 dst: str, profile: Profile,
                 meta: Optional[Metadata] = None) -> None:
        super().__init__(video_source, dst, profile=profile, meta=meta)
        self.audio = audio_source

    def prepare_ffmpeg(self, src: Metadata) -> encoding.FFMPEG:
        video_streams = [s for s in src.streams if s.kind == VIDEO]
        video_source = encoding.input_file(self.src, *video_streams)
        video_codecs = [s > codecs.Copy(kind=VIDEO, bitrate=s.meta.bitrate)
                        for s in video_source.streams
                        if s.kind == VIDEO]
        # We need bitrate hints for HLS bandwidth tags
        for vc, vt in zip(video_codecs, self.profile.video):
            vc.bitrate = vt.max_rate

        audio_streams = [s for s in src.streams if s.kind == AUDIO]
        audio_source = encoding.input_file(self.audio, *audio_streams)
        audio_codecs = [s > codecs.Copy(kind=AUDIO, bitrate=s.meta.bitrate)
                        for s in audio_source.streams
                        if s.kind == AUDIO]

        for ac, at in zip(audio_codecs, self.profile.audio):
            ac.bitrate = at.bitrate

        out = self.prepare_output(video_codecs + audio_codecs)
        ff = encoding.FFMPEG(input=video_source,
                             output=out,
                             loglevel='level+info')
        ff.add_input(audio_source)
        return ff

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
            vsm.append(f'a:{i},agroup:a{i}')
        for (i, a), (j, v) in product(enumerate(audios), enumerate(videos)):
            vsm.append(f'v:{j},agroup:a{i}')
        var_stream_map = ' '.join(vsm)
        return var_stream_map
