# -*- coding: utf-8 -*-
"""Hledání filmů, seriálů a souborů včetně historie hledání."""
from resources.lib import context as ctx
from resources.lib import kodi, ui
from resources.lib.kodi import t, url_for
from resources.lib.router import route

_KIND_LABEL = {'movie': 'search_movie', 'tv': 'search_show', 'ws': 'search_files'}
_KIND_ICON = {'movie': ui.ICON_MOVIES, 'tv': ui.ICON_SHOWS, 'ws': ui.ICON_VIDEO}


def _results_url(kind, query):
    if kind == 'ws':
        return url_for('ws_search', q=query)
    return url_for('list', kind=kind, cat='search', q=query)


@route('search')
def search(params):
    listing = ui.Listing()
    for kind in ('movie', 'tv', 'ws'):
        listing.action(t(_KIND_LABEL[kind]), 'search_new', ui.ICON_SEARCH, kind=kind)
    rows = ctx.db().search_list()
    for row in rows:
        kind = row['kind'] if row['kind'] in _KIND_ICON else 'movie'
        label = '%s  [COLOR gray]%s[/COLOR]' % (row['query'], t('search_kind_' + kind))
        if kind == 'ws':
            listing.folder(label, 'ws_search', _KIND_ICON[kind], q=row['query'])
        else:
            listing.folder(label, 'list', _KIND_ICON[kind], kind=kind, cat='search', q=row['query'])
    if rows:
        listing.action(t('search_clear'), 'search_clear', ui.ICON_SETTINGS)
    listing.finish(cache=False)


@route('search_new')
def search_new(params):
    kind = params.get('kind', 'movie')
    query = kodi.keyboard(t(_KIND_LABEL.get(kind, 'search_movie'))).strip()
    if not query:
        return
    ctx.db().search_add(kind, query)
    kodi.go_to(_results_url(kind, query))


@route('search_clear')
def search_clear(params):
    if kodi.yesno(t('confirm_clear')):
        ctx.db().search_clear()
        kodi.refresh()
