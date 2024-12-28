from unittest import TestCase, mock

from fffw.encoding import Stream
from fffw.graph import VIDEO

from video_transcoding.transcoding import inputs
from video_transcoding.transcoding.ffprobe import FFProbe


class FFProbeWrapperTestCase(TestCase):
    def test_handle_stdout(self):
        f = FFProbe()
        m = mock.MagicMock()
        with mock.patch.object(f, 'logger',
                               new_callable=mock.PropertyMock(return_value=m)):
            s = mock.sentinel.stdout
            out = f.handle_stdout(s)
            self.assertIs(out, s)
            m.assert_not_called()

    def test_handle_stderr_error(self):
        f = FFProbe()
        m = mock.MagicMock()
        with mock.patch.object(f, 'logger',
                               new_callable=mock.PropertyMock(return_value=m)):
            line = 'perfix [error] suffix'
            out = f.handle_stderr(line)
            self.assertEqual(out, '')
            m.error.assert_called_once_with(line)

    def test_handle_stderr_debug(self):
        f = FFProbe()
        m = mock.MagicMock()
        with mock.patch.object(f, 'logger',
                               new_callable=mock.PropertyMock(return_value=m)):
            line = 'debug'
            out = f.handle_stderr(line)
            self.assertEqual(out, '')
            m.assert_not_called()


class InputsTestCase(TestCase):
    def test_init_inputs(self):
        src = inputs.input_file('filename', Stream(kind=VIDEO),
                                allowed_extensions='m3u8')
        self.assertIsInstance(src, inputs.Input)
        self.assertEqual(src.allowed_extensions, 'm3u8')
