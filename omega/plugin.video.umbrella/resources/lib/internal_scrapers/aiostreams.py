# -*- coding: UTF-8 -*-
'''AIOStreams (Stremio addon protocol) source adapter for Umbrella.'''

from urllib.parse import urlencode

import requests

from resources.lib.modules.control import setting as getSetting
from resources.lib.modules import log_utils
from resources.lib.modules import scrape_utils


class source:
	priority = 1
	pack_capable = False
	hasMovies = True
	hasEpisodes = True

	def __init__(self):
		self.language = ['en']

	def sources(self, data, hostDict):
		if not data or not data.get('imdb'): return []
		try:
			url, params = self._search_request(data)
			response = requests.get(url, params=params, auth=(getSetting('aiostreams.uuid').strip(), getSetting('aiostreams.password')), headers={'User-Agent': 'Umbrella/AIOStreams'}, timeout=30)
			response.raise_for_status()
			payload = response.json()
			if not payload.get('success'): raise ValueError((payload.get('error') or {}).get('message') or 'AIOStreams search failed')
			streams = (payload.get('data') or {}).get('results', [])
			return [item for item in (self._convert(stream) for stream in streams) if item]
		except Exception:
			log_utils.error('AIOStreams request failed: ')
			return []

	def _search_request(self, data):
		base = 'https://aiostreams.elfhosted.com' if getSetting('aiostreams.instance') != 'Custom' else getSetting('aiostreams.custom_url').strip().rstrip('/')
		if 'tvshowtitle' in data:
			media_type = 'series'
			video_id = '%s:%s:%s' % (data['imdb'], data['season'], data['episode'])
		else:
			media_type = 'movie'
			video_id = data['imdb']
		return '%s/api/v1/search' % base, {'type': media_type, 'id': video_id, 'format': 'true'}

	def _convert(self, stream):
		url = stream.get('url')
		if not url or not url.lower().startswith(('http://', 'https://')): return None
		hints = stream.get('behaviorHints') or {}
		request_headers = (hints.get('proxyHeaders') or {}).get('request') or {}
		if request_headers:
			url = '%s|%s' % (url, urlencode(request_headers))

		name = hints.get('filename') or stream.get('name') or stream.get('title') or 'AIOStreams'
		description = stream.get('description') or stream.get('title') or stream.get('name') or ''
		name_info = scrape_utils.clean_name('%s %s' % (name, description))
		quality, info = scrape_utils.get_release_quality(name_info, url)
		size_bytes = hints.get('videoSize') or (stream.get('streamData') or {}).get('size') or 0
		try:
			size, size_label = scrape_utils.convert_size(float(size_bytes), to='GB')
			if size_label: info.insert(0, size_label)
		except Exception: size = 0
		info = ' | '.join(info)
		return {
			'provider': 'aiostreams', 'source': 'direct', 'name': name,
			'name_info': name_info, 'quality': quality, 'language': 'en',
			'url': url, 'info': info, 'direct': True, 'debridonly': False,
			'size': size
		}
