"""Offline regressions for the official 6.7.98 merge; no account/network calls."""
import ast
import re
import unittest
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

from test_release_merge import ADDON, MODULES, ROOT


def functions(path, names, **namespace):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in selected} == set(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


class TraktAuthentication(unittest.TestCase):
    def setUp(self):
        self.helpers = functions(MODULES / 'trakt.py', ['traktRequestURL', 'traktVerificationURL'],
            urljoin=urljoin, urlparse=urlparse, urlunparse=urlunparse, parse_qsl=parse_qsl,
            urlencode=urlencode, BASE_URL='https://api.trakt.tv', AUTH_URL='https://auth.trakt.tv')

    def test_oauth_routes_to_auth_host(self):
        for endpoint in ('device/code', 'device/token', 'token', 'revoke'):
            for prefix in ('', '/', 'https://api.trakt.tv/', 'https://auth.trakt.tv/'):
                with self.subTest(endpoint=endpoint, prefix=prefix):
                    self.assertEqual(self.helpers['traktRequestURL'](prefix + 'oauth/' + endpoint),
                                     'https://auth.trakt.tv/oauth/' + endpoint)

    def test_data_requests_stay_on_api(self):
        for prefix in ('', '/', 'https://api.trakt.tv/'):
            self.assertEqual(self.helpers['traktRequestURL'](prefix + 'sync/last_activities'),
                             'https://api.trakt.tv/sync/last_activities')

    def test_complete_verification_link_is_preserved(self):
        link = 'https://auth.trakt.tv/activate?code=example'
        self.assertEqual(self.helpers['traktVerificationURL']({'verification_url_complete': link}), link)

    def test_verification_link_keeps_query_and_encodes_code(self):
        result = self.helpers['traktVerificationURL']({
            'verification_url': 'https://auth.trakt.tv/activate?source=kodi', 'user_code': 'A+B C'})
        self.assertEqual(dict(parse_qsl(urlparse(result).query)), {'source': 'kodi', 'code': 'A+B C'})


class AirdateSearch(unittest.TestCase):
    def setUp(self):
        self.helpers = functions(MODULES / 'scrape_utils.py',
            ['episode_airdate', 'episode_identifier', 'airdate_sources'], re=re)
        self.data = {'tvshowtitle': 'Example', 'season': '2', 'episode': '7', 'premiered': '2026-10-27'}

    def test_date_validation(self):
        for value, expected in [('2026-10-27', '2026.10.27'), ('2026.10.27', '2026.10.27'),
                                ('2026-02-30', None), ('2026-1-2', None), ('0', None), (None, None)]:
            self.assertEqual(self.helpers['episode_airdate']({'premiered': value}), expected)

    def test_numbered_metadata_preserved_and_duplicate_results_removed(self):
        calls = []
        def search(instance, data, hosts):
            calls.append(dict(data))
            if '_umbrella_airdate_query' in data:
                return [{'url': 'https://example.invalid/shared'}, {'url': 'https://example.invalid/dated'}]
            return [{'url': 'https://example.invalid/shared'}]
        result = self.helpers['airdate_sources'](search)(None, self.data, {})
        self.assertEqual(len(result), 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]['_umbrella_airdate_query'], '2026.10.27')
        self.assertEqual((calls[1]['season'], calls[1]['episode']), ('2', '7'))
        self.assertNotIn('_umbrella_airdate_query', self.data)

    def test_movie_or_invalid_date_does_not_run_second_search(self):
        for data in ({'title': 'Movie', 'premiered': '2026-10-27'}, dict(self.data, premiered='invalid')):
            calls = []
            def search(instance, value, hosts):
                calls.append(value)
                return [{'url': 'https://example.invalid/numbered'}]
            self.assertEqual(len(self.helpers['airdate_sources'](search)(None, data, {})), 1)
            self.assertEqual(len(calls), 1)

    def test_numbered_identifier_remains_default(self):
        self.assertEqual(self.helpers['episode_identifier'](self.data, 'S02E07'), 'S02E07')
        self.assertEqual(self.helpers['episode_identifier'](
            dict(self.data, _umbrella_airdate_query='2026.10.27'), 'S02E07'), '2026.10.27')


class MergeIntegrity(unittest.TestCase):
    def test_premiumize_reads_current_invocation(self):
        text = (ADDON / 'resources/lib/debrid/premiumize.py').read_text(encoding='utf-8')
        self.assertNotIn('from sys import argv', text)
        self.assertEqual(text.count('int(sys.argv[1])'), 2)

    def test_upstream_code_consistent_in_four_trees(self):
        for relative in ('modules/trakt.py', 'modules/scrape_utils.py', 'debrid/premiumize.py',
                         'internal_scrapers/easynews.py', 'internal_scrapers/filepursuit.py',
                         'internal_scrapers/gdrive.py', 'internal_scrapers/plexshare.py'):
            expected = (ADDON / 'resources/lib' / relative).read_text(encoding='utf-8')
            for target in ('matrix', 'nexus', 'piers'):
                self.assertEqual((ROOT / target / 'plugin.video.umbrella/resources/lib' / relative)
                                 .read_text(encoding='utf-8'), expected, (target, relative))
