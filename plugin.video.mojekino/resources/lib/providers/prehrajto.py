# -*- coding: utf-8 -*-
"""Přehraj.to: hledání na prehraj.to bez účtu.

Bez účtu jde jen první strana výsledků a video převedené serverem (až 1080p).
Web nemá veřejné API, údaje se čtou ze stránky výsledků a ze stránky videa.
"""
import html
import re
import time
import urllib.parse

from resources.lib import http
from resources.lib.providers import ProviderError, StreamFile, StreamProvider

BASE = 'https://prehraj.to'
PAUSE = 10 * 60              # po odmítnutí pro příliš mnoho dotazů (HTTP 429) zdroj na 10 minut vynecháme
_paused_until = [0.0]
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'

_RE_ITEM = re.compile(r'<a class="video video--small video--link"\s+href="([^"]+)"\s+title="([^"]*)"(.*?)</a>', re.S)
_RE_SIZE = re.compile(r'video__tag--size[^>]*>\s*([\d.,]+)\s*(TB|GB|MB|KB)', re.I)
_RE_SOURCE = re.compile(r'file\s*:\s*"(https?://[^"]+)"\s*,\s*label\s*:\s*[\'"](\d+)p?[\'"]')
_RE_ANY_MP4 = re.compile(r'"(https?://[^"]+\.mp4[^"]*)"')
_UNITS = {'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3, 'TB': 1024 ** 4}


def parse_size(text):
    found = _RE_SIZE.search(text)
    if not found:
        return 0
    try:
        return int(float(found.group(1).replace(',', '.')) * _UNITS[found.group(2).upper()])
    except ValueError:
        return 0


def parse_results(page):
    """Ze stránky výsledků vrátí [(cesta k videu, název, velikost)]."""
    result = []
    for path, title, block in _RE_ITEM.findall(page):
        if path.startswith('/') and title:
            result.append((path, html.unescape(title), parse_size(block)))
    return result


def parse_sources(page):
    """Ze stránky videa vrátí odkazy seřazené od nejvyšší kvality."""
    sources = sorted(((int(q), link) for link, q in _RE_SOURCE.findall(page)), reverse=True)
    if sources:
        return [link for _q, link in sources]
    return _RE_ANY_MP4.findall(page)


class Prehrajto(StreamProvider):
    id = 'prehrajto'
    name = 'Přehraj.to'

    def is_logged_in(self):
        return True

    def _page(self, path):
        try:
            return http.request(BASE + path, headers={'User-Agent': USER_AGENT}, timeout=10,
                                retries=0).decode('utf-8', 'replace')
        except http.HttpError as e:
            if e.status == 404:
                raise ProviderError(ProviderError.NOT_FOUND)
            if e.status == 429:
                # web omezuje počet dotazů z jedné adresy - chvíli ho necháme být
                _paused_until[0] = time.time() + PAUSE
                raise ProviderError(ProviderError.TOO_MANY, str(e))
            raise ProviderError(ProviderError.NETWORK, str(e))

    def search(self, query, limit=50, offset=0, sort=''):
        if offset or time.time() < _paused_until[0]:
            return [], 0                     # bez účtu jen první strana; po HTTP 429 pauza
        page = self._page('/hledej/' + urllib.parse.quote(query))
        files = [StreamFile(self.id, path, title, size) for path, title, size in parse_results(page)[:limit]]
        return files, len(files)

    def resolve(self, ident):
        if not ident.startswith('/'):
            raise ProviderError(ProviderError.NOT_FOUND)
        sources = parse_sources(self._page(ident))
        if not sources:
            raise ProviderError(ProviderError.UNAVAILABLE, 'stránka bez videa')
        return html.unescape(sources[0]) + '|User-Agent=' + urllib.parse.quote(USER_AGENT)
