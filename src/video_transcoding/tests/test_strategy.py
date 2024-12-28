import json
from dataclasses import asdict
from unittest import mock

from django.test import TestCase

from video_transcoding import strategy, defaults
from video_transcoding.tests import base
from video_transcoding.transcoding import profiles, workspace


class ResumableStrategyTestCase(base.ProfileMixin, base.MetadataMixin,
                                TestCase):
    def setUp(self):
        super().setUp()
        self.profile = self.default_profile()
        source_uri = 'https://example.com/source.mp4'
        basename = 'basename'
        self.strategy = strategy.ResumableStrategy(
            source_uri=source_uri,
            basename=basename,
            preset=profiles.DEFAULT_PRESET
        )
        self.tmp_ws = base.MemoryWorkspace(f'tmp-{basename}')
        self.dst_ws = base.MemoryWorkspace(f'dst-{basename}')
        self.strategy.ws = self.tmp_ws
        self.strategy.store = self.dst_ws
        self.strategy.initialize()

    def test_strategy_init(self):
        source_uri = 'https://example.com/source.mp4'
        basename = 'basename'
        s = strategy.ResumableStrategy(
            source_uri=source_uri,
            basename=basename,
            preset=profiles.DEFAULT_PRESET
        )
        uri = s.ws.get_absolute_uri(s.ws.root).geturl()
        root = f"{defaults.VIDEO_TEMP_URI.replace('dav://', 'http://')}"
        self.assertEqual(uri, f'{root}{basename}/')
        uri = s.store.get_absolute_uri(s.store.root).geturl()
        root = f"{defaults.VIDEO_RESULTS_URI.replace('dav://', 'http://')}"
        self.assertEqual(uri, f'{root}{basename}/')

    def test_main_flow(self):
        with (
            mock.patch.object(self.strategy, 'process',
                              return_value=mock.sentinel.rv) as p,
            mock.patch.object(self.strategy, 'initialize') as i,
            mock.patch.object(self.strategy, 'cleanup') as c,
        ):
            result = self.strategy()

        self.assertEqual(result, mock.sentinel.rv)
        p.assert_called_once_with()
        i.assert_called_once_with()
        c.assert_called_once_with(is_error=False)

    def test_error_flow(self):
        with (
            mock.patch.object(self.strategy, 'process',
                              side_effect=Exception()) as p,
            mock.patch.object(self.strategy, 'initialize') as i,
            mock.patch.object(self.strategy, 'cleanup') as c,
        ):
            with self.assertRaises(Exception):
                self.strategy()

        p.assert_called_once_with()
        i.assert_called_once_with()
        c.assert_called_once_with(is_error=True)

    def test_initialize(self):
        self.strategy.initialize()
        expected = {
            'tmp-basename': {
                'sources': {},
                'results': {}
            }
        }
        self.assertEqual(self.tmp_ws.tree, expected)
        expected = {'dst-basename': {}}
        self.assertEqual(self.dst_ws.tree, expected)

    def test_cleanup(self):
        self.tmp_ws.tree = {
            'tmp-basename': {'sources': {}, 'results': {}}
        }
        self.dst_ws.tree = {
            'dst-basename': {}
        }

        self.strategy.cleanup(is_error=False)

        self.assertEqual(self.tmp_ws.tree, {})
        self.assertEqual(self.dst_ws.tree, {'dst-basename': {}})

        self.strategy.cleanup(is_error=True)

        self.assertEqual(self.dst_ws.tree, {})

    def test_process(self):
        with (
            mock.patch.object(
                self.strategy, 'analyze_source',
                return_value=mock.sentinel.src_rv) as analyze_source,
            mock.patch.object(
                self.strategy, 'select_profile',
                return_value=mock.sentinel.profile_rv) as select_profile,
            mock.patch.object(
                self.strategy, 'split') as split,
            mock.patch.object(
                self.strategy, 'get_segment_list',
                return_value=['s1', 's2']) as get_segment_list,
            mock.patch.object(
                self.strategy, 'process_segment',
                side_effect=[
                    mock.sentinel.s1_rv,
                    mock.sentinel.s2_rv
                ]) as process_segment,
            mock.patch.object(
                self.strategy, 'merge_metadata',
                side_effect=[
                    mock.sentinel.m1_rv,
                    mock.sentinel.m2_rv
                ]) as merge_metadata,
            mock.patch.object(
                self.strategy, 'merge',
                return_value=mock.sentinel.merge_rv) as merge,
        ):
            result = self.strategy.process()

        analyze_source.assert_called_once_with()
        select_profile.assert_called_once_with(mock.sentinel.src_rv)
        self.assertEqual(self.strategy.profile, mock.sentinel.profile_rv)
        split.assert_called_once_with(mock.sentinel.src_rv)
        get_segment_list.assert_called_once_with()
        process_segment.assert_has_calls([
            mock.call('s1'),
            mock.call('s2'),
        ])
        merge_metadata.assert_has_calls([
            mock.call(None, mock.sentinel.s1_rv),
            mock.call(mock.sentinel.m1_rv, mock.sentinel.s2_rv),
        ])
        merge.assert_called_once_with(['s1', 's2'], meta=mock.sentinel.m2_rv)
        self.assertEqual(result, mock.sentinel.merge_rv)

    def test_merge_metadata(self):
        result_meta = None
        segment_meta = self.make_meta(600.0)

        result_meta = self.strategy.merge_metadata(result_meta, segment_meta)
        self.assertEqual(result_meta, segment_meta)

        segment_meta = self.make_meta(300.0)

        result_meta = self.strategy.merge_metadata(result_meta, segment_meta)

        expected = self.make_meta(600.0, 300.0)

        self.assertEqual(result_meta, expected)

    def test_analyze_source_exists(self):
        expected = self.make_meta(30.0)
        # noinspection PyTypeChecker
        content = json.dumps(asdict(expected))
        self.tmp_ws.tree['tmp-basename']['sources']['source.json'] = content
        with mock.patch.object(self.strategy, '_analyze_source') as m:
            meta = self.strategy.analyze_source()
        m.assert_not_called()
        # reused metadata from json
        self.assertEqual(meta, expected)

    def test_analyze_source_missing(self):
        expected = self.make_meta(30.0)
        # noinspection PyTypeChecker
        content = json.dumps(asdict(expected))
        with mock.patch.object(self.strategy, '_analyze_source',
                               return_value=expected) as m:
            meta = self.strategy.analyze_source()
        m.assert_called_once_with()
        self.assertEqual(meta, expected)
        c = self.tmp_ws.tree['tmp-basename']['sources']['source.json']
        self.assertEqual(c, content)

    def test_analyze_source_call(self):
        t = 'video_transcoding.transcoding.extract.SourceExtractor'
        with mock.patch(t) as m:
            m.return_value.get_meta_data.return_value = mock.sentinel.rv
            src = self.strategy._analyze_source()
        self.assertEqual(src, mock.sentinel.rv)
        m.assert_called_once_with()
        method = m.return_value.get_meta_data
        method.assert_called_once_with(self.strategy.source_uri)

    def test_select_profile_exists(self):
        src = self.make_meta(30.0)
        expected = self.profile
        # noinspection PyTypeChecker
        content = json.dumps(asdict(expected))
        self.tmp_ws.tree['tmp-basename']['sources']['profile.json'] = content
        with mock.patch.object(self.strategy, '_select_profile') as m:
            profile = self.strategy.select_profile(src)
        m.assert_not_called()
        self.assertEqual(profile, expected)

    def test_select_profile_missing(self):
        src = self.make_meta(30.0)
        expected = self.profile
        # noinspection PyTypeChecker
        content = json.dumps(asdict(expected))
        with mock.patch.object(self.strategy, '_select_profile',
                               return_value=expected) as m:
            profile = self.strategy.select_profile(src)
        m.assert_called_once_with(src)
        self.assertEqual(profile, expected)
        c = self.tmp_ws.tree['tmp-basename']['sources']['profile.json']
        self.assertEqual(c, content)

    def test_select_profile_call(self):
        src = self.make_meta(30.0)
        with mock.patch.object(self.strategy.preset, 'select_profile',
                               return_value=mock.sentinel.rv) as m:
            profile = self.strategy._select_profile(src)
        self.assertEqual(profile, mock.sentinel.rv)
        m.assert_called_once_with(src.videos[0], src.audios[0])

    def test_split_exists(self):
        src = self.make_meta(600.0)
        split = self.make_meta(30.0)
        # noinspection PyTypeChecker
        content = json.dumps(asdict(split))
        self.tmp_ws.tree['tmp-basename']['sources']['split.json'] = content
        with mock.patch.object(self.strategy, '_split') as m:
            result = self.strategy.split(src)
        m.assert_not_called()
        self.assertEqual(result, split)

    def test_split_missing(self):
        src = self.make_meta(600.0)
        split = self.make_meta(30.0)
        # noinspection PyTypeChecker
        content = json.dumps(asdict(split))
        with mock.patch.object(self.strategy, '_split',
                               return_value=split) as m:
            result = self.strategy.split(src)
        m.assert_called_once_with(src)
        self.assertEqual(result, split)
        c = self.tmp_ws.tree['tmp-basename']['sources']['split.json']
        self.assertEqual(c, content)

    def test_split_call(self):
        src = self.make_meta(600.0)
        split = self.make_meta(30.0)
        t = 'video_transcoding.transcoding.transcoder.Splitter'
        self.strategy.profile = self.profile
        with mock.patch(t) as m:
            m.return_value.return_value = split
            result = self.strategy._split(src)
        self.assertEqual(result, split)
        m.assert_called_once_with(
            self.strategy.source_uri,
            'memory:tmp-basename/sources/split.json',
            profile=self.profile,
            meta=src
        )
        m.return_value.assert_called_once_with()

    def test_get_segment_list(self):
        content = '\n'.join((
            '#M3U8',
            ''  # m3u8 comment',
            's1',
            ''  # another comment',
            's2',
        ))
        self.tmp_ws.tree['tmp-basename']['sources']['source-video.m3u8'] = content
        segments = self.strategy.get_segment_list()
        self.assertListEqual(segments, ['s1', 's2'])

    def test_process_segment_exists(self):
        meta = self.make_meta(30.0)
        # noinspection PyTypeChecker
        content = json.dumps(asdict(meta))
        self.tmp_ws.tree['tmp-basename']['results']['s1.json'] = content
        with mock.patch.object(self.strategy, '_process_segment') as m:
            result = self.strategy.process_segment('s1')
        self.assertEqual(result, meta)
        m.assert_not_called()

    def test_process_segment_missing(self):
        meta = self.make_meta(30.0)
        # noinspection PyTypeChecker
        content = json.dumps(asdict(meta))
        with mock.patch.object(self.strategy, '_process_segment',
                               return_value=meta) as m:
            result = self.strategy.process_segment('s1')
        self.assertEqual(result, meta)
        c = self.tmp_ws.tree['tmp-basename']['results']['s1.json']
        self.assertEqual(c, content)
        m.assert_called_once_with('s1')

    def test_process_segment_call(self):
        src = self.make_meta(30.0)
        dst = self.make_meta(60.0)
        self.strategy.profile = self.profile
        target = 'video_transcoding.transcoding.transcoder.Transcoder'
        with (
            mock.patch.object(self.strategy, 'get_segment_meta',
                              return_value=src) as m,
            mock.patch(target) as t
        ):
            t.return_value.return_value = dst

            result = self.strategy._process_segment('s1')

        m.assert_called_once_with(workspace.File('tmp-basename', 'sources', 's1'))
        t.assert_called_once_with(
            'memory:tmp-basename/sources/s1',
            'memory:tmp-basename/results/s1',
            profile=self.profile,
            meta=src
        )
        self.assertEqual(result, dst)

    def test_merge_call(self):
        src = self.make_meta(30.0)
        dst = self.make_meta(60.0)
        self.strategy.profile = self.profile
        target = 'video_transcoding.transcoding.transcoder.Segmentor'
        with (
            mock.patch.object(
                self.strategy, 'write_concat_file',
                return_value='memory:tmp-basename/results/concat.ffconcat') as m,
            mock.patch(target) as t
        ):
            t.return_value.return_value = dst
            result = self.strategy.merge(['s1', 's2'], src)

        m.assert_called_once_with(['s1', 's2'])
        t.assert_called_once_with(
            video_source='memory:tmp-basename/results/concat.ffconcat',
            audio_source='memory:tmp-basename/sources/source-audio.m3u8',
            dst='memory:dst-basename/index.m3u8',
            profile=self.profile,
            meta=src
        )
        t.return_value.assert_called_once_with()
        self.assertEqual(result, dst)

    def test_write_concat_file(self):
        result = self.strategy.write_concat_file(['s1', 's2'])
        self.assertEqual(result, 'memory:tmp-basename/results/concat.ffconcat')
        content = self.tmp_ws.tree['tmp-basename']['results']['concat.ffconcat']
        self.assertEqual(content, '\n'.join([
            "ffconcat version 1.0",
            "file 's1'",
            "file 's2'",
        ]))

    def test_get_segment_meta(self):
        src = workspace.File('tmp-basename', 'sources', 's1')
        meta = self.make_meta(30.0)
        target = 'video_transcoding.transcoding.extract.VideoSegmentExtractor'
        with mock.patch(target) as m:
            m.return_value.get_meta_data.return_value = meta
            result = self.strategy.get_segment_meta(src)
        m.assert_called_once_with()
        m.return_value.get_meta_data.assert_called_once_with(
            'memory:tmp-basename/sources/s1'
        )
        self.assertEqual(result, meta)
