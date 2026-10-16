# -*- coding: UTF-8 -*-
'''AIOStreams (Stremio addon protocol) source adapter for Umbrella.'''

from urllib.parse import urlencode

import requests

from resources.lib.modules.control import setting as getSetting
from resources.lib.modules import log_utils
from resources.lib.modules import scrape_utils
from resources.lib.modules import source_utils


class source:
	priority = 1
	pack_capable = False
	hasMovies = True
	hasEpisodes = True

	def __init__(self):
		self.language = ['en']

	def sources(self, data, hostDict):
		if not data or not data.get('imdb'): return []
		variants = [('primary', data.get('season'), data.get('episode'))]
		original = (data.get('original_season'), data.get('original_episode'))
		if all(value is not None for value in original) and original != variants[0][1:]:
			variants.append(('original', original[0], original[1]))
		credentials = (getSetting('aiostreams.uuid').strip(), getSetting('aiostreams.password'))
		for label, season, episode in variants:
			try:
				url, params = self._search_request(data, season, episode)
				response = requests.get(url, params=params, auth=credentials, headers={'User-Agent': 'Umbrella/AIOStreams'}, timeout=30)
				response.raise_for_status()
				payload = response.json()
				if not payload.get('success'): raise ValueError((payload.get('error') or {}).get('message') or 'AIOStreams search failed')
				streams = (payload.get('data') or {}).get('results', [])
				converted = [item for item in (self._convert(stream) for stream in streams) if item]
				unique = []
				seen = set()
				for item in converted:
					key = item.get('url') or item.get('name')
					if key in seen: continue
					seen.add(key)
					unique.append(item)
				log_utils.log('AIOStreams %s search %s: %d raw, %d playable' % (label, params.get('id'), len(streams), len(unique)), level=log_utils.LOGINFO)
				if unique: return unique
			except Exception:
				log_utils.error('AIOStreams %s request failed: ' % label)
		return []

	def _search_request(self, data, season=None, episode=None):
		instance = getSetting('aiostreams.instance')
		instances = {
			'ElfHosted Public': 'https://aiostreams.elfhosted.com',
			'Yeb Stable': 'https://aiostreams.fortheweak.cloud',
			'MidnightIgnite Stable': 'https://aiostreamsfortheweebsstable.midnightignite.me'
		}
		base = getSetting('aiostreams.custom_url').strip().rstrip('/') if instance == 'Custom' else instances.get(instance, instances['MidnightIgnite Stable'])
		if 'tvshowtitle' in data:
			media_type = 'series'
			video_id = '%s:%s:%s' % (data['imdb'], season if season is not None else data['season'], episode if episode is not None else data['episode'])
		else:
			media_type = 'movie'
			video_id = data['imdb']
		return '%s/api/v1/search' % base, {'type': media_type, 'id': video_id, 'format': 'true'}

	def _convert(self, stream):
		url = stream.get('url')
		if not url or not url.lower().startswith(('http://', 'https://')): return None
		hints = stream.get('behaviorHints') or {}
		request_headers = stream.get('requestHeaders') or (hints.get('proxyHeaders') or {}).get('request') or {}
		if request_headers:
			url = '%s|%s' % (url, urlencode(request_headers))

		name = stream.get('filename') or hints.get('filename') or stream.get('name') or stream.get('title') or 'AIOStreams'
		description = stream.get('description') or stream.get('title') or stream.get('name') or ''
		name_info = scrape_utils.clean_name('%s %s' % (name, description))
		quality, info = scrape_utils.get_release_quality(name_info, url)
		media_info = source_utils.getFileType(name_info.lower(), url)
		if media_info: info.extend(item.strip() for item in media_info.split('/') if item.strip())
		service_id = (stream.get('service') or '').lower()
		service_names = {
			'realdebrid': 'REAL-DEBRID', 'alldebrid': 'ALLDEBRID',
			'premiumize': 'PREMIUMIZE', 'torbox': 'TORBOX',
			'offcloud': 'OFFCLOUD', 'easydebrid': 'EASYDEBRID',
			'debridlink': 'DEBRID-LINK', 'putio': 'PUT.IO',
			'pikpak': 'PIKPAK', 'seedr': 'SEEDR',
			'debrider': 'DEBRIDER', 'easynews': 'EASYNEWS'
		}
		if service_id: info.append(service_names.get(service_id, service_id.replace('_', ' ').upper()))
		if stream.get('cached') is True: info.append('CACHED')
		size_bytes = stream.get('size') or hints.get('videoSize') or (stream.get('streamData') or {}).get('size') or 0
		try:
			size, size_label = scrape_utils.convert_size(float(size_bytes), to='GB')
			if size_label: info.insert(0, size_label)
		except Exception: size = 0
		info = ' | '.join(info)
		source_name = stream.get('addon') or 'direct'
		return {
			'provider': 'aiostreams', 'source': source_name, 'name': name,
			'name_info': name_info, 'quality': quality, 'language': 'en',
			'url': url, 'info': info, 'direct': True, 'debridonly': False,
			'size': size
		}
