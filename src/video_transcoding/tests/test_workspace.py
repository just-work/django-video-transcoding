from functools import partial
from unittest import mock

import requests
from django.test import TestCase

from video_transcoding import defaults
from video_transcoding.transcoding import workspace


class ResourceTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.file = workspace.File('first', 'second', 'file.txt')
        self.dir = workspace.Collection('first', 'second', 'dir')
        self.root = workspace.Collection()

    def test_basename(self):
        self.assertEqual(self.file.basename, 'file.txt')
        self.assertEqual(self.root.basename, '')

    def test_path(self):
        self.assertEqual(self.file.path, '/first/second/file.txt')
        self.assertEqual(self.root.path, '')

    def test_parent(self):
        self.assertIsInstance(self.file.parent, workspace.Collection)
        self.assertEqual(self.file.parent.path, '/first/second')
        self.assertIsNone(self.root.parent)

    def test_repr(self):
        self.assertIsInstance(repr(self.file), str)
        self.assertIsInstance(repr(self.dir), str)

    def test_trailing_slash(self):
        self.assertEqual(self.dir.trailing_slash, '/')
        self.assertEqual(self.file.trailing_slash, '')

    def test_child(self):
        c = self.dir.collection('new')
        self.assertIsInstance(c, workspace.Collection)
        self.assertEqual(c.path, '/first/second/dir/new')
        c = self.root.collection('new')
        self.assertEqual(c.path, '/new')
        f = self.dir.file('new.txt')
        self.assertIsInstance(f, workspace.File)
        self.assertEqual(f.path, '/first/second/dir/new.txt')


class FileSystemWorkspaceTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.ws = workspace.FileSystemWorkspace('/tmp/dir')
        self.file = workspace.File('first', 'second', 'file.txt')
        self.dir = workspace.Collection('first', 'second', 'dir')

    def test_get_absolute_uri(self):
        uri = self.ws.get_absolute_uri(self.file).geturl()
        self.assertEqual(uri, 'file:///tmp/dir/first/second/file.txt')
        uri = self.ws.get_absolute_uri(self.dir).geturl()
        self.assertEqual(uri, 'file:///tmp/dir/first/second/dir/')

    @mock.patch('os.makedirs')
    def test_ensure_collection(self, m: mock.Mock):
        c = self.ws.ensure_collection('/another/collection')
        self.assertIsInstance(c, workspace.Collection)
        self.assertEqual(c.path, '/another/collection')
        m.assert_called_once_with('/tmp/dir/another/collection/', exist_ok=True)

    @mock.patch('os.makedirs')
    def test_create_collection(self, m: mock.Mock):
        c = workspace.Collection('another', 'collection')
        self.ws.create_collection(c)
        m.assert_called_once_with('/tmp/dir/another/collection/', exist_ok=True)

    @mock.patch('shutil.rmtree')
    def test_delete_collection(self, m: mock.Mock):
        c = workspace.Collection('another', 'collection')
        self.ws.delete_collection(c)
        m.assert_called_once_with('/tmp/dir/another/collection/')

        m.side_effect = FileNotFoundError()
        try:
            self.ws.delete_collection(c)
        except FileNotFoundError:  # pragma: no cover
            self.fail("exception raised")

    @mock.patch('os.path.exists')
    def test_exists(self, m: mock.Mock):
        m.return_value = True
        self.assertTrue(self.ws.exists(self.file))
        m.assert_called_once_with('/tmp/dir/first/second/file.txt')
        m.reset_mock()
        m.return_value = False
        self.assertFalse(self.ws.exists(self.dir))
        m.assert_called_once_with('/tmp/dir/first/second/dir/')

    @mock.patch('builtins.open',
                new_callable=partial(mock.mock_open, read_data='read_data'))
    def test_read(self, m: mock.Mock):
        content = self.ws.read(self.file)
        self.assertEqual(content, 'read_data')
        m.assert_called_once_with('/tmp/dir/first/second/file.txt', 'r')

    @mock.patch('builtins.open', new_callable=mock.mock_open)
    def test_write(self, m: mock.Mock):
        self.ws.write(self.file, 'content')
        m.return_value.write.assert_called_once_with('content')


class WebDAVWorkspaceTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.ws = workspace.WebDAVWorkspace('https://domain.com/path')
        self.file = workspace.File('first', 'second', 'file.txt')
        self.dir = workspace.Collection('first', 'second', 'dir')
        self.session_patcher = mock.patch('requests.Session.request')
        self.session_mock = self.session_patcher.start()
        self.response = requests.Response()
        self.response.status_code = requests.status_codes.codes.ok
        self.session_mock.return_value = self.response
        timeout = (
            defaults.VIDEO_CONNECT_TIMEOUT,
            defaults.VIDEO_REQUEST_TIMEOUT,
        )
        self.session_kwargs = {'timeout': timeout}
        self.status_patcher = mock.patch.object(self.response,
                                                'raise_for_status')
        self.status_mock = self.status_patcher.start()

    def tearDown(self):
        super().tearDown()
        self.session_patcher.stop()
        self.status_patcher.stop()

    def test_get_absolute_uri(self):
        uri = self.ws.get_absolute_uri(self.file).geturl()
        self.assertEqual(uri, 'https://domain.com/path/first/second/file.txt')
        uri = self.ws.get_absolute_uri(self.dir).geturl()
        self.assertEqual(uri, 'https://domain.com/path/first/second/dir/')
        self.ws = workspace.WebDAVWorkspace('https://domain.com')
        uri = self.ws.get_absolute_uri(workspace.Collection()).geturl()
        self.assertEqual(uri, 'https://domain.com')
        uri = self.ws.get_absolute_uri(self.file).geturl()
        self.assertEqual(uri, 'https://domain.com/first/second/file.txt')
        uri = self.ws.get_absolute_uri(self.dir).geturl()
        self.assertEqual(uri, 'https://domain.com/first/second/dir/')

    def test_ensure_collection(self):
        c = self.ws.ensure_collection('/another/collection')
        self.assertIsInstance(c, workspace.Collection)
        self.assertEqual(c.path, '/another/collection')
        kw = self.session_kwargs
        self.session_mock.assert_has_calls([
            mock.call('MKCOL', 'https://domain.com/path/', **kw),
            mock.call('MKCOL', 'https://domain.com/path/another/', **kw),
            mock.call('MKCOL', 'https://domain.com/path/another/collection/',
                      **kw),
        ])
        self.status_mock.assert_called()

    def test_ensure_collection_exists(self):
        self.response.status_code = requests.codes.method_not_allowed
        c = self.ws.ensure_collection('/another/collection')
        self.assertIsInstance(c, workspace.Collection)
        self.status_mock.assert_not_called()

        self.response.status_code = requests.codes.server_error
        self.status_mock.side_effect = requests.exceptions.HTTPError
        with self.assertRaises(requests.exceptions.HTTPError):
            self.ws.ensure_collection('/another/collection')
        self.status_mock.assert_called()

    def test_create_collection(self):
        c = workspace.Collection('another', 'collection')

        self.ws.create_collection(c)

        kw = self.session_kwargs
        self.session_mock.assert_has_calls([
            mock.call('MKCOL', 'https://domain.com/path/', **kw),
            mock.call('MKCOL', 'https://domain.com/path/another/', **kw),
            mock.call('MKCOL', 'https://domain.com/path/another/collection/',
                      **kw),
        ])
        self.status_mock.assert_called()

    def test_create_collection_strip(self):
        c = workspace.Collection()

        self.ws.create_collection(c)

        kw = self.session_kwargs
        self.session_mock.assert_has_calls([
            mock.call('MKCOL', 'https://domain.com/path/', **kw),
        ])
        self.status_mock.assert_called()

    def test_create_collection_root(self):
        self.ws = workspace.WebDAVWorkspace('https://domain.com')
        c = workspace.Collection()

        self.ws.create_collection(c)
        kw = self.session_kwargs
        self.session_mock.assert_has_calls([
            mock.call('MKCOL', 'https://domain.com/', **kw),
        ])

    def test_delete_collection(self):
        c = workspace.Collection('another', 'collection')

        self.ws.delete_collection(c)

        self.session_mock.assert_has_calls([
            mock.call('DELETE', 'https://domain.com/path/another/collection/',
                      **self.session_kwargs)
        ])
        self.status_mock.assert_called()

        self.response.status_code = requests.codes.not_found
        try:
            self.ws.delete_collection(c)
        except requests.exceptions.HTTPError:  # pragma: no cover
            self.fail("exception raised")

    def test_exists(self):
        self.assertTrue(self.ws.exists(self.file))
        self.session_mock.assert_has_calls([
            mock.call('HEAD', 'https://domain.com/path/first/second/file.txt',
                      **self.session_kwargs),
        ])
        self.status_mock.assert_called()

        self.session_mock.reset_mock()
        self.response.status_code = requests.codes.not_found
        self.assertFalse(self.ws.exists(self.dir))
        self.session_mock.assert_has_calls([
            mock.call('HEAD', 'https://domain.com/path/first/second/dir/',
                      **self.session_kwargs),
        ])

    def test_read(self):
        self.response._content = b'read_data'
        content = self.ws.read(self.file)
        self.assertEqual(content, 'read_data')
        self.session_mock.assert_has_calls([
            mock.call('GET', 'https://domain.com/path/first/second/file.txt',
                      **self.session_kwargs)
        ])
        self.status_mock.assert_called()

    def test_write(self):
        self.ws.write(self.file, 'content')
        self.session_mock.assert_has_calls([
            mock.call('PUT', 'https://domain.com/path/first/second/file.txt',
                      data='content')
        ])
        self.status_mock.assert_called()


class InitWorkspaceTestCase(TestCase):
    def test_init_file(self):
        ws = workspace.init('file:///tmp/root')
        self.assertIsInstance(ws, workspace.FileSystemWorkspace)
        uri = ws.get_absolute_uri(ws.root).geturl()
        self.assertEqual(uri, 'file:///tmp/root/')

    def test_init_dav(self):
        ws = workspace.init('dav://domain.com/root/')
        self.assertIsInstance(ws, workspace.WebDAVWorkspace)
        uri = ws.get_absolute_uri(ws.root).geturl()
        self.assertEqual(uri, 'http://domain.com/root/')

    def test_init_davs(self):
        ws = workspace.init('davs://domain.com/root/')
        self.assertIsInstance(ws, workspace.WebDAVWorkspace)
        uri = ws.get_absolute_uri(ws.root).geturl()
        self.assertEqual(uri, 'https://domain.com/root/')

    def test_init_value_error(self):
        with self.assertRaises(ValueError):
            workspace.init('not_a_scheme://domain.com/')
