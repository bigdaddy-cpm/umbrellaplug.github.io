"""Regression coverage for official 6.7.93-97 plus custom integrations."""
import ast
from datetime import datetime
import json
import re
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from test_release_merge import ADDON, MODULES, ROOT, module, source_methods


class CacheFailures(unittest.TestCase):
    def test_cache_failure_keeps_episode_and_pack_results(self):
        logger = Mock()
        namespace = {'database': sqlite3, 'log_utils': logger}
        tree = ast.parse((MODULES / 'sources.py').read_text(encoding='utf-8'))
        helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_write_provider_cache')
        exec(compile(ast.Module(body=[helper], type_ignores=[]), '<cache helper>', 'exec'), namespace)
        helper = namespace['_write_provider_cache']
        for pack in ('', 'season', 'show'):
            with self.subTest(pack=pack):
                cursor = Mock()
                def execute(query, values):
                    if query.startswith('INSERT'):
                        raise sqlite3.OperationalError('database is locked')
                    return SimpleNamespace(fetchone=lambda: None)
                cursor.execute.side_effect = execute
                connection = Mock()
                connection.cursor.return_value = cursor
                database = SimpleNamespace(connect=lambda *a, **kw: connection)
                source = source_methods(['_getEpisodeSource'], database=database, sourceFile='unused',
                    datetime=datetime, log_utils=logger, _write_provider_cache=helper)
                source.hostprDict, source.scraper_sources = {}, []
                source.dev_disable_season_filter = source.dev_disable_show_filter = False
                source.total_seasons = 4
                provider = Mock()
                result = [{'url': 'fresh', 'provider': 'example', 'last_season': 4}]
                provider.sources.return_value = result
                provider.sources_packs.return_value = result
                mapping = module('episode_mapping')
                with patch.dict(sys.modules, {'resources.lib.modules.episode_mapping': mapping}):
                    source._getEpisodeSource('tt123', '2', '3', {'season': '2', 'episode': '3'}, 'example', lambda: provider, pack)
                self.assertEqual(source.scraper_sources[0]['url'], 'fresh')
                cursor.connection.rollback.assert_called_once()

    def test_unavailable_cursor_is_not_fatal(self):
        namespace = {'database': sqlite3, 'log_utils': Mock()}
        tree = ast.parse((MODULES / 'sources.py').read_text(encoding='utf-8'))
        helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_write_provider_cache')
        exec(compile(ast.Module(body=[helper], type_ignores=[]), '<cache helper>', 'exec'), namespace)
        self.assertFalse(namespace['_write_provider_cache'](None, 'INSERT', ()))


class SettingsBackups(unittest.TestCase):
    def setUp(self):
        self.backup = module('settings_backup')
        self.types = {'aiostreams.enable': 'boolean', 'aiostreams.priority': 'integer',
                      'anime.seasons.episode.group.fallback': 'boolean'}
        self.settings = {'aiostreams.enable': 'true', 'aiostreams.priority': '1',
            'aiostreams.instance': 'Custom', 'aiostreams.custom_url': 'https://example.invalid/config-secret/manifest.json',
            'aiostreams.uuid': 'test-id', 'aiostreams.password': 'test-secret',
            'anime.seasons.episode.group.fallback': 'true'}
        self.get = lambda key: self.settings.get(key, '')

    def test_preference_backup_never_contains_connection_secrets(self):
        data = self.backup.serialize_preferences(self.get, self.types)
        for secret in ('test-secret', 'test-id', 'config-secret'):
            self.assertNotIn(secret, data)
        self.assertEqual(json.loads(data)['settings']['anime.seasons.episode.group.fallback'], 'true')

    def test_account_opt_in_roundtrip(self):
        choose = Mock(return_value=True)
        data = self.backup.serialize_backup(self.get, self.types, choose)
        self.assertEqual(choose.call_args.args[0], 'aiostreams')
        preferences, accounts = self.backup.parse_backup(data, self.types)
        self.assertEqual(preferences['aiostreams.enable'], 'true')
        self.assertEqual(accounts['aiostreams']['aiostreams.password'], 'test-secret')

    def test_opt_out_omits_secrets_and_dependent_enable(self):
        data = self.backup.serialize_backup(self.get, self.types, lambda *args: False)
        self.assertNotIn('test-secret', data)
        self.assertNotIn('config-secret', data)
        parsed = json.loads(data)
        self.assertNotIn('aiostreams.enable', parsed['settings'])
        self.assertEqual(parsed['accounts'], {})

    def test_disabled_provider_does_not_export_account(self):
        self.settings['aiostreams.enable'] = 'false'
        choose = Mock(return_value=True)
        data = json.loads(self.backup.serialize_backup(self.get, self.types, choose))
        choose.assert_not_called()
        self.assertEqual(data['accounts'], {})

    def test_missing_account_cannot_enable_provider_on_import(self):
        data = {'format': self.backup.FORMAT, 'version': 2,
                'settings': {'aiostreams.enable': 'true', 'anime.seasons.episode.group.fallback': 'true'}, 'accounts': {}}
        values, accounts = self.backup.parse_backup(json.dumps(data), self.types)
        self.assertNotIn('aiostreams.enable', values)


class Kodi22Integration(unittest.TestCase):
    def test_all_custom_settings_use_current_language_folder(self):
        for target in ('matrix', 'nexus', 'omega', 'piers'):
            addon = ROOT / target / 'plugin.video.umbrella'
            text = (addon / 'resources/language/resource.language.en_gb/strings.po').read_text(encoding='utf-8')
            labels = dict(re.findall(r'msgctxt "#(\d+)"\s+msgid "(.*)"', text))
            settings = ET.parse(addon / 'resources/settings.xml')
            self.assertEqual(labels['40830'], 'Export Settings')
            for index, key in enumerate(('aiostreams.enable', 'aiostreams.instance', 'aiostreams.custom_url', 'aiostreams.uuid', 'aiostreams.password'), 40901):
                node = settings.find(f".//setting[@id='{key}']")
                self.assertEqual(node.attrib['label'], str(index))
                self.assertTrue(labels[str(index)])
            self.assertFalse((addon / 'resources/language/English').exists())

    def test_queued_metadata_and_route_fallback_preserve_episode_identity(self):
        normalizer = module('playback_metadata')
        result = normalizer.normalize('{"season": 1, "episode": 29, "title": "The Moon Fairy"}', season=2, episode=5, tmdb='123')
        self.assertEqual((result['season'], result['episode']), (1, 29))
        self.assertEqual(result['tmdb'], '123')
        self.assertEqual(normalizer.normalize('not JSON', season=1, episode=29)['episode'], 29)

    def test_release_version_exceeds_published_custom_release(self):
        self.assertEqual(ET.parse(ADDON / 'addon.xml').getroot().attrib['version'], '6.7.98')


if __name__ == '__main__':
    unittest.main()
