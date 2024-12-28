from unittest import mock

from django.test import TestCase
from fffw.encoding import Stream
from fffw.graph import VIDEO, AUDIO
from fffw.wrapper import ensure_binary

from video_transcoding.tests import base
from video_transcoding.transcoding import transcoder, profiles, inputs, codecs, \
    outputs


class TranscoderTestCase(base.ProfileMixin, base.MetadataMixin, TestCase):
    def setUp(self):
        self.profile = self.default_profile()
        self.meta = self.make_meta(30.0, uri='src.ts')

        self.transcoder = transcoder.Transcoder(
            'src.ts',
            'dst.ts',
            profile=self.profile,
            meta=self.meta,
        )

    def test_call(self):
        with (
            mock.patch.object(self.transcoder, 'process',
                              return_value=mock.sentinel.rv) as m
        ):
            result = self.transcoder()
        self.assertEqual(result, mock.sentinel.rv)
        m.assert_called_once_with()

    def test_process(self):
        with (
            mock.patch.object(self.transcoder, 'prepare_ffmpeg',
                              return_value=mock.sentinel.ff) as prepare_ffmpeg,
            mock.patch.object(self.transcoder, 'run') as run,
            mock.patch.object(self.transcoder, 'get_result_metadata',
                              return_value=mock.sentinel.rv) as get_result_metadata
        ):
            result = self.transcoder.process()

        prepare_ffmpeg.assert_called_once_with(self.meta)
        run.assert_called_once_with(mock.sentinel.ff)
        get_result_metadata.assert_called_once_with('dst.ts')
        self.assertEqual(result, mock.sentinel.rv)

    def test_run(self):
        ff = mock.MagicMock()
        ff.run.return_value = (0, 'output', 'error')

        self.transcoder.run(ff)

        ff.run.assert_called_once_with()

        ff.run.return_value = (1, 'output', 'error')

        with self.assertRaises(RuntimeError) as ctx:
            self.transcoder.run(ff)
        self.assertEqual(ctx.exception.args[0], 'error')

        ff.run.return_value = (2, 'output', '')
        with self.assertRaises(RuntimeError) as ctx:
            self.transcoder.run(ff)
        self.assertEqual(ctx.exception.args[0],
                         'invalid ffmpeg return code 2')

    def test_prepare_ffmpeg(self):
        with (
            mock.patch.object(
                self.transcoder, 'prepare_input',
                return_value=mock.sentinel.source) as prepare_input,
            mock.patch.object(
                self.transcoder, 'prepare_video_codecs',
                return_value=mock.sentinel.video_codecs) as prepare_video_codecs,
            mock.patch.object(
                self.transcoder, 'prepare_output',
                return_value=mock.sentinel.dst) as prepare_output,
            mock.patch.object(
                self.transcoder, 'scale_and_encode',
                return_value=mock.Mock(
                    ffmpeg=mock.sentinel.ffmpeg)) as scale_and_encode,
        ):
            ffmpeg = self.transcoder.prepare_ffmpeg(mock.sentinel.src)
        prepare_input.assert_called_once_with(mock.sentinel.src)
        prepare_video_codecs.assert_called_once_with()
        prepare_output.assert_called_once_with(mock.sentinel.video_codecs)
        scale_and_encode.assert_called_once_with(
            mock.sentinel.source, mock.sentinel.video_codecs, mock.sentinel.dst
        )
        self.assertEqual(ffmpeg, mock.sentinel.ffmpeg)

    def test_scale_and_encode(self):
        self.profile.video.append(profiles.VideoTrack(
            frame_rate=30,
            width=1280,
            height=720,
            profile='main',
            pix_fmt='yuv420p',
            buf_size=1_500_000,
            gop_size=30,
            max_rate=750_000,
            id='v',
            force_key_frames='1.0',
            codec='libx264',
            preset='slow',
            constant_rate_factor=23,
        ))
        source = inputs.Input(streams=(Stream(VIDEO, meta=self.meta.video),
                                       Stream(AUDIO, meta=self.meta.audio)))

        video_codecs = [
            codecs.VideoCodec('libx264', bitrate=1_500_000),
            codecs.VideoCodec('libx264', bitrate=750_000),
        ]

        dst = outputs.Output(codecs=video_codecs, output_file='out.m3u8')

        simd = self.transcoder.scale_and_encode(source, video_codecs, dst)

        fc = ';'.join([
            '[0:v:0]split[v:split0][v:split1]',
            '[v:split0]scale=w=1920:h=1080[vout0]',
            '[v:split1]scale=w=1280:h=720[vout1]',
        ])
        # ffmpeg
        expected = [
            '-loglevel', 'repeat+level+info',
            '-y',
            '-filter_complex', fc,
            '-map', '[vout0]',
            '-c:v:0', 'libx264',
            '-b:v:0', 1500000,
            '-map', '[vout1]',
            '-c:v:1', 'libx264',
            '-b:v:1', 750000,
            '-an',
            'out.m3u8'
        ]

        self.assertEqual(simd.ffmpeg.get_args(), ensure_binary(expected))

    def test_prepare_input(self):
        src = self.transcoder.prepare_input(self.meta)
        self.assertIsInstance(src, inputs.Input)
        self.assertEqual(src.input_file, self.meta.uri)
        self.assertEqual(len(src.streams), len(self.meta.streams))
        for x, y in zip(src.streams, self.meta.streams):
            self.assertIsInstance(x, Stream)
            self.assertEqual(x.kind, y.kind)
            self.assertEqual(x.meta, y.meta)

    def test_prepare_output(self):
        video_codecs = [
            codecs.VideoCodec('libx264', bitrate=1_500_000),
            codecs.VideoCodec('libx264', bitrate=750_000),
        ]
        dst = self.transcoder.prepare_output(video_codecs)
        expected = outputs.FileOutput(
            output_file='dst.ts',
            method='PUT',
            codecs=video_codecs,
            format='mpegts',
            muxdelay='0',
            avoid_negative_ts='disabled',
            copyts=True,
        )
        self.assertEqual(dst, expected)

    def test_prepare_video_codecs(self):
        video_codecs = self.transcoder.prepare_video_codecs()
        self.assertEqual(len(video_codecs), len(self.profile.video))
        for c, v in zip(video_codecs, self.profile.video):
            expected = codecs.VideoCodec(
                codec=v.codec,
                force_key_frames=v.force_key_frames,
                constant_rate_factor=v.constant_rate_factor,
                preset=v.preset,
                max_rate=v.max_rate,
                buf_size=v.buf_size,
                profile=v.profile,
                pix_fmt=v.pix_fmt,
                gop=v.gop_size,
                rate=v.frame_rate,
            )
            self.assertEqual(c, expected)

    def test_get_result_metadata(self):
        target = 'video_transcoding.transcoding.extract.VideoResultExtractor'
        with mock.patch(target) as m:
            m.return_value.get_meta_data.return_value = self.meta

            result = self.transcoder.get_result_metadata('uri')

        m.assert_called_once_with()
        m.return_value.get_meta_data.assert_called_once_with('uri')
        self.assertEqual(result, self.meta)
