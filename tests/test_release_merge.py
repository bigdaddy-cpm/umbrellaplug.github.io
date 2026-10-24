"""Offline regression checks for custom features overlapping upstream 6.7.92.

Run: python -B -m unittest discover -s tests -v
Kodi APIs and HTTP are mocked; these are not on-device playback tests.
"""
import ast
from collections import Counter
from contextlib import closing
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / 'omega/plugin.video.umbrella'
MODULES = ADDON / 'resources/lib/modules'


def module(name):
    spec = importlib.util.spec_from_file_location(name, MODULES / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def methods(path, class_name, names, namespace):
    """Execute actual methods without importing Kodi's process-wide globals."""
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    selected = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in selected} == set(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return type(class_name, (), {name: namespace[name] for name in names})()


def source_methods(names, **namespace):
    return methods(MODULES / 'sources.py', 'Sources', names, namespace)


class ReleaseStructure(unittest.TestCase):
    def test_python_syntax_in_all_four_trees(self):
        for target in ('matrix', 'nexus', 'omega', 'piers'):
            for path in (ROOT / target / 'plugin.video.umbrella').rglob('*.py'):
                with self.subTest(file=str(path.relative_to(ROOT))):
                    text = path.read_text(encoding='utf-8-sig')
                    ast.parse(text, filename=str(path), feature_version=(3, 8))
                    compile(text, str(path), 'exec')

    def test_no_new_duplicate_localization_ids(self):
        for target in ('matrix', 'nexus', 'omega', 'piers'):
            path = ROOT / target / 'plugin.video.umbrella/resources/language/resource.language.en_gb/strings.po'
            ids = re.findall(r'^msgctxt "#(\d+)"', path.read_text(encoding='utf-8'), re.M)
            # Upstream already repeats 30021; custom and newly merged IDs must be unique.
            self.assertFalse([key for key, count in Counter(ids).items()
                              if count != 1 and key != '30021'], target)

    def test_settings_and_labels(self):
        settings = ET.parse(ADDON / 'resources/settings.xml')
        nodes = {node.attrib['id']: node for node in settings.findall('.//setting')}
        text = (ADDON / 'resources/language/resource.language.en_gb/strings.po').read_text(encoding='utf-8')
        labels = dict(re.findall(r'msgctxt "#(\d+)"\s+msgid "(.*)"', text))
        for setting in ('aiostreams.enable', 'aiostreams.instance', 'aiostreams.uuid',
                        'aiostreams.password', 'anime.seasons.episode.group.fallback'):
            self.assertTrue(labels[nodes[setting].attrib['label']])
        self.assertEqual(nodes['anime.seasons.episode.group.fallback'].findtext('default'), 'false')
        for key, expected in {'40824': 'Automatically skip intro', '40826': 'Automatically skip recap',
                              '40828': 'Shared service options', '40830': 'Export Settings',
                              '40900': 'AIOStreams'}.items():
            self.assertEqual(labels[key], expected)
        self.assertEqual(nodes['aiostreams.password'].findtext('control/hidden'), 'true')


class AnimeFallback(unittest.TestCase):
    def setUp(self):
        self.settings = {'anime.seasons.episode.group.fallback': 'true'}
        self.request = Mock()
        self.source = source_methods(['_anime_episode_group_remap'],
            getSetting=lambda key: self.settings.get(key, ''), jsloads=json.loads,
            client=SimpleNamespace(request=self.request), log_utils=Mock())

    def responses(self, groups):
        self.request.side_effect = [json.dumps(value) for value in (
            {'results': [{'id': 210024}]}, {'results': groups}, {'id': 164},
            {'groups': [{'order': 4, 'episodes': [{'id': 164, 'order': 9}]}]})]

    def test_disabled_does_not_call_tmdb(self):
        self.settings['anime.seasons.episode.group.fallback'] = 'false'
        self.assertEqual(self.source._anime_episode_group_remap('73223', '1', '164'), ('1', '164'))
        self.request.assert_not_called()

    def test_seasons_group_wins_over_airdate(self):
        self.responses([{'id': 'aired', 'type': 1}, {'id': 'seasons', 'name': 'Seasons', 'type': 6}])
        self.assertEqual(self.source._anime_episode_group_remap('73223', '1', '164'), ('4', '10'))
        self.assertIn('/episode_group/seasons?', self.request.call_args.args[0])

    def test_original_airdate_used_when_no_seasons_group(self):
        self.responses([{'id': 'aired', 'type': 1}, {'id': 'absolute', 'type': 2}])
        self.assertEqual(self.source._anime_episode_group_remap('73223', '1', '164'), ('4', '10'))
        self.assertIn('/episode_group/aired?', self.request.call_args.args[0])

    def test_absolute_only_does_not_remap(self):
        self.responses([{'id': 'absolute', 'type': 2}])
        self.assertEqual(self.source._anime_episode_group_remap('73223', '1', '164'), ('1', '164'))
        self.assertEqual(self.request.call_count, 2)

    def test_non_anime_and_network_failures_keep_original(self):
        for response in ('{"results": []}', RuntimeError('offline')):
            self.request.side_effect = [response]
            self.assertEqual(self.source._anime_episode_group_remap('1', '1', '29'), ('1', '29'))

    def test_scrape_and_prescrape_keep_playback_metadata(self):
        for prescrape in (False, True):
            src = source_methods(['getSources'])
            src._anime_episode_group_remap = Mock(return_value=('4', '10'))
            src.get_season_info = Mock(return_value=(4, 'false'))
            src.getSources_silent = Mock(return_value=[])
            src.getSources_dialog = Mock(return_value=[])
            meta = {'tmdb': '73223', 'season': '1', 'episode': '164'}
            src.getSources('Episode', '2017', 'tt123', '73223', '', '1', '164', 'Anime', '', meta, prescrape)
            call = src.getSources_silent if prescrape else src.getSources_dialog
            self.assertEqual(call.call_args.args[4:6], ('4', '10'))
            self.assertEqual(meta, {'tmdb': '73223', 'season': '1', 'episode': '164'})
            self.assertEqual((src.original_scrape_season, src.original_scrape_episode), ('1', '164'))
            self.assertEqual(src.scrape_tmdb, '73223')


class AIOStreams(unittest.TestCase):
    def setUp(self):
        self.get = Mock()
        self.settings = {'aiostreams.instance': 'Custom', 'aiostreams.custom_url': 'https://example.invalid/',
                         'aiostreams.uuid': 'test-id', 'aiostreams.password': 'test-password'}
        self.source = methods(ADDON / 'resources/lib/internal_scrapers/aiostreams.py', 'source',
            ['sources', '_search_request', '_convert'], {
                'getSetting': lambda key: self.settings.get(key, ''),
                'requests': SimpleNamespace(get=self.get), 'log_utils': Mock(), 'urlencode': urlencode,
                'scrape_utils': SimpleNamespace(clean_name=lambda value: value,
                    get_release_quality=lambda *args: ('1080p', []), convert_size=lambda *args, **kwargs: (1, '1 GB')),
                'source_utils': SimpleNamespace(getFileType=lambda *args: 'MKV / 6CH')})
        self.data = {'imdb': 'tt123', 'tvshowtitle': 'Anime', 'season': '4', 'episode': '10',
                     'original_season': '1', 'original_episode': '164'}

    def response(self, streams):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'success': True, 'data': {'results': streams}})

    def test_retry_empty_primary_using_original_numbering(self):
        self.get.side_effect = [self.response([]), self.response([{'url': 'https://example.invalid/play'}])]
        self.assertEqual(len(self.source.sources(self.data, {})), 1)
        self.assertEqual([call.kwargs['params']['id'] for call in self.get.call_args_list], ['tt123:4:10', 'tt123:1:164'])
        self.assertEqual(self.get.call_args.kwargs['auth'], ('test-id', 'test-password'))

    def test_retry_failed_primary(self):
        self.get.side_effect = [TimeoutError('timeout'), self.response([{'url': 'https://example.invalid/play'}])]
        self.assertEqual(len(self.source.sources(self.data, {})), 1)
        self.assertEqual(self.get.call_count, 2)

    def test_primary_success_does_not_retry_and_deduplicates(self):
        stream = {'url': 'https://example.invalid/play'}
        self.get.return_value = self.response([stream, stream])
        self.assertEqual(len(self.source.sources(self.data, {})), 1)
        self.assertEqual(self.get.call_count, 1)

    def test_movie_request_and_missing_imdb(self):
        self.get.return_value = self.response([])
        self.source.sources({'imdb': 'tt123'}, {})
        self.assertEqual(self.get.call_args.kwargs['params'], {'type': 'movie', 'id': 'tt123', 'format': 'true'})
        self.get.reset_mock()
        self.assertEqual(self.source.sources({'imdb': ''}, {}), [])
        self.get.assert_not_called()

    def test_result_details_and_headers_survive(self):
        result = self.source._convert({'url': 'https://example.invalid/play', 'addon': 'Sootio',
            'service': 'realdebrid', 'cached': True, 'filename': 'Example.1080p.mkv',
            'requestHeaders': {'Referer': 'https://example.invalid/'}})
        self.assertEqual(result['source'], 'Sootio')
        self.assertEqual(result['provider'], 'aiostreams')
        for label in ('REAL-DEBRID', 'CACHED', 'MKV', '6CH'):
            self.assertIn(label, result['info'])
        self.assertEqual(result['quality'], '1080p')
        self.assertTrue(result['direct'])
        self.assertIn('|Referer=', result['url'])
        self.assertIsNone(self.source._convert({'url': 'magnet:?xt=example'}))


class UpstreamIntegration(unittest.TestCase):
    def setUp(self):
        self.mapping = module('episode_mapping')
        self.preferences = module('source_preferences')

    def test_anthology_variants_and_custom_query(self):
        src = source_methods(['getEpisodeSource'], control=SimpleNamespace(monitor=SimpleNamespace(abortRequested=lambda: False)))
        src.scrape_tmdb = '225634'
        src.custom_query = 'false'
        src._getEpisodeSource = Mock()
        data = {'imdb': 'tt13207736', 'season': '1', 'episode': '2'}
        with patch.dict(sys.modules, {'resources.lib.modules.episode_mapping': self.mapping}):
            src.getEpisodeSource('tt13207736', '1', '2', data, 'aiostreams', None, '')
            calls = src._getEpisodeSource.call_args_list
            self.assertEqual([call.args[1] for call in calls], ['2', '1'])
            self.assertEqual(calls[0].args[3]['imdb'], 'tt13207736')
            self.assertEqual(calls[1].args[3]['imdb'], '')
            src.custom_query = 'true'
            src._getEpisodeSource.reset_mock()
            src.getEpisodeSource('tt13207736', '1', '2', data, 'aiostreams', None, '')
            self.assertEqual(src._getEpisodeSource.call_count, 1)
            self.assertEqual(src._getEpisodeSource.call_args.args[0], 'tt13207736')

    def test_aiostreams_bypasses_stale_cache_but_keeps_mapping_tags(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'providers.db')
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE rel_src (source, imdb_id, season, episode, sources, added)')
                db.execute('INSERT INTO rel_src VALUES (?, ?, ?, ?, ?, ?)',
                    ('aiostreams', 'tt123', '2', '3', repr([{'url': 'stale'}]), '2026-10-16'))
                db.commit()
            db_handles = []
            def connect(*args, **kwargs):
                connection = sqlite3.connect(*args, **kwargs)
                db_handles.append(connection)
                return connection
            src = source_methods(['_getEpisodeSource'], database=SimpleNamespace(connect=connect),
                                 sourceFile=path, datetime=datetime, log_utils=Mock())
            src.hostprDict, src.scraper_sources = {}, []
            provider = Mock(return_value=SimpleNamespace(sources=lambda *args: [{'url': 'fresh', 'provider': 'aiostreams'}]))
            data = {'season': '2', 'episode': '3', '_scrape_tmdb': '225634', '_scrape_convention': 'anthology'}
            try:
                with patch.dict(sys.modules, {'resources.lib.modules.episode_mapping': self.mapping}):
                    src._getEpisodeSource('tt123', '2', '3', data, 'aiostreams', provider, '')
                self.assertEqual(src.scraper_sources[0]['url'], 'fresh')
                self.assertEqual(src.scraper_sources[0]['scrape_season'], '2')
                self.assertEqual(src.scraper_sources[0]['scrape_tmdb'], '225634')
                with closing(sqlite3.connect(path)) as db:
                    cached = db.execute("SELECT sources FROM rel_src WHERE source='aiostreams'").fetchone()[0]
                    self.assertIn('stale', cached)
                    self.assertNotIn('fresh', cached)
            finally:
                for connection in db_handles:
                    connection.close()

    def test_pack_preference_only_matches_same_hash_and_service(self):
        item = {'package': 'season', 'hash': 'ABC', 'debrid': 'Real-Debrid', 'source': 'cached', 'url': 'magnet:?xt=example'}
        preference = {'hash': 'abc', 'debrid': 'Real-Debrid'}
        items = [item, dict(item, hash='DEF'), dict(item, debrid='TorBox'),
                 dict(item, source='uncached'), dict(item, url='https://example.invalid/play', provider='aiostreams')]
        self.assertEqual(self.preferences.matching(items, preference), [item])

    def test_pack_preference_uses_original_tmdb_season_scope(self):
        self.assertEqual(self.preferences.scope({'tmdb': '73223', 'imdb': 'tt123', 'season': '1', 'episode': '164'}),
                         ('tmdb:73223', '1'))
        self.assertIsNone(self.preferences.scope({'tmdb': '123'}))

    def test_preresolve_rejects_shared_imdb_for_wrong_story(self):
        self.assertFalse(self.mapping.preresolved_matches('tt13207736', '225634', '1', '2',
                                                        'tt13207736', '113988', '1', '2'))
        self.assertTrue(self.mapping.preresolved_matches('tt13207736', '225634', '1', '2',
                                                       'tt13207736', '225634', '1', '2'))

    def test_service_migration_prefers_active_provider(self):
        service = module('service_settings')
        self.assertEqual(service.choose('progressFlatten', {'indicators.alt': '2', 'simkl.progressFlatten': 'false',
                                                            'trakt.progressFlatten': 'true'}), 'false')


if __name__ == '__main__':
    unittest.main()
