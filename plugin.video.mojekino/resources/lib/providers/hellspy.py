# -*- coding: utf-8 -*-
"""HellSpy: veřejné hledání videí na hellspy.to, bez účtu.

Přehrává se video převedené serverem (obvykle 720p), ne původní soubor.
"""
import json
import urllib.parse

from resources.lib import http
from resources.lib.providers import ProviderError, StreamFile, StreamProvider

API = 'https://api.hellspy.to/gw'
USER_AGENT = 'Mozilla/5.0 (X11; Linux armv7l) Kodi/21'
PAGE = 64


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class HellSpy(StreamProvider):
    id = 'hellspy'
    name = 'HellSpy'

    def is_logged_in(self):
        return True

    def _json(self, url, params=None):
        try:
            raw = http.request(url, params=params, headers={'User-Agent': USER_AGENT}, timeout=10)
        except http.HttpError as e:
            code = ProviderError.NOT_FOUND if e.status == 404 else ProviderError.NETWORK
            raise ProviderError(code, str(e))
        try:
            return json.loads(raw.decode('utf-8'))
        except ValueError:
            raise ProviderError(ProviderError.UNKNOWN, 'neplatná odpověď HellSpy')

    def search(self, query, limit=50, offset=0, sort=''):
        data = self._json(API + '/search', {'query': query, 'offset': offset, 'limit': min(limit, PAGE)})
        files = []
        for item in data.get('items') or []:
            video_id, file_hash, title = item.get('id'), item.get('fileHash'), item.get('title')
            if not video_id or not file_hash or not title:
                continue
            files.append(StreamFile(self.id, '%s/%s' % (video_id, file_hash), title, _int(item.get('size'))))
        return files, offset + len(files) + (1 if len(files) >= min(limit, PAGE) else 0)

    def resolve(self, ident):
        data = self._json(API + '/video/' + urllib.parse.quote(ident, safe='/'))
        conversions = data.get('conversions') or {}
        best = sorted(conversions.items(), key=lambda pair: _int(pair[0]), reverse=True)
        for _quality, link in best:
            if link:
                return link + '|User-Agent=' + urllib.parse.quote(USER_AGENT)
        raise ProviderError(ProviderError.UNAVAILABLE, 'žádný převod videa')
