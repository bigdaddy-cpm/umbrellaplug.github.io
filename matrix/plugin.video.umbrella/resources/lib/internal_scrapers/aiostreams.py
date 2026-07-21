# -*- coding: UTF-8 -*-
'''AIOStreams (Stremio addon protocol) source adapter for Umbrella.'''

from urllib.parse import urlencode
import requests
from resources.lib.modules.control import setting as getSetting
from resources.lib.modules import log_utils, scrape_utils, source_utils

class source:
	priority = 1
	pack_capable = False
	hasMovies = True
	hasEpisodes = True
	def __init__(self): self.language = ['en']
	def sources(self, data, hostDict):
		if not data or not data.get('imdb'): return []
		try:
			url, params = self._search_request(data)
			response = requests.get(url, params=params, auth=(getSetting('aiostreams.uuid').strip(), getSetting('aiostreams.password')), headers={'User-Agent': 'Umbrella/AIOStreams'}, timeout=30)
			response.raise_for_status()
			payload = response.json()
			if not payload.get('success'): raise ValueError((payload.get('error') or {}).get('message') or 'AIOStreams search failed')
			return [item for item in (self._convert(stream) for stream in (payload.get('data') or {}).get('results', [])) if item]
		except Exception:
			log_utils.error('AIOStreams request failed: ')
			return []
	def _search_request(self, data):
		base = 'https://aiostreamsfortheweebsstable.midnightignite.me' if getSetting('aiostreams.instance') != 'Custom' else getSetting('aiostreams.custom_url').strip().rstrip('/')
		media_type = 'series' if 'tvshowtitle' in data else 'movie'
		video_id = '%s:%s:%s' % (data['imdb'], data['season'], data['episode']) if media_type == 'series' else data['imdb']
		return '%s/api/v1/search' % base, {'type': media_type, 'id': video_id, 'format': 'true'}
	def _convert(self, stream):
		url = stream.get('url')
		if not url or not url.lower().startswith(('http://', 'https://')): return None
		hints = stream.get('behaviorHints') or {}
		headers = stream.get('requestHeaders') or (hints.get('proxyHeaders') or {}).get('request') or {}
		if headers: url = '%s|%s' % (url, urlencode(headers))
		name = stream.get('filename') or hints.get('filename') or stream.get('name') or stream.get('title') or 'AIOStreams'
		description = stream.get('description') or stream.get('title') or stream.get('name') or ''
		name_info = scrape_utils.clean_name('%s %s' % (name, description))
		quality, info = scrape_utils.get_release_quality(name_info, url)
		media_info = source_utils.getFileType(name_info.lower(), url)
		if media_info: info.extend(item.strip() for item in media_info.split('/') if item.strip())
		try:
			size, label = scrape_utils.convert_size(float(stream.get('size') or hints.get('videoSize') or (stream.get('streamData') or {}).get('size') or 0), to='GB')
			if label: info.insert(0, label)
		except Exception: size = 0
		source_name = stream.get('addon') or 'direct'
		return {'provider': 'aiostreams', 'source': source_name, 'name': name, 'name_info': name_info, 'quality': quality, 'language': 'en', 'url': url, 'info': ' | '.join(info), 'direct': True, 'debridonly': False, 'size': size}
