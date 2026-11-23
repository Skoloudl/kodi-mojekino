# -*- coding: utf-8 -*-
"""Hlavní menu a procházení katalogu (filmy, seriály, sezóny, díly)."""
import datetime
import json
import traceback

import xbmcgui

from resources.lib import context as ctx
from resources.lib import availability, catalog, kodi, ui
from resources.lib.episodes import watched_in_season
from resources.lib.kodi import t
from resources.lib.metadata import MetadataError
from resources.lib.router import route

MOVIE_CATEGORIES = (('new', 'cat_new'), ('popular', 'cat_popular'), ('trending', 'cat_trending'),
                    ('top', 'cat_top'), ('cinema', 'cat_cinema'))
SHOW_CATEGORIES = (('popular', 'cat_popular'), ('trending', 'cat_trending'), ('onair', 'cat_onair'),
                   ('new', 'cat_new_shows'), ('top', 'cat_top'))


def _sosac_label():
    """Popisek účtu Streamuj.tv se stavem premium z poslední kontroly."""
    label = t('menu_sosac_account')
    if not ctx.sosac().is_logged_in():
        return '%s  [COLOR orange]%s[/COLOR]' % (label, t('account_not_logged'))
    try:
        state = json.loads(ctx.db().meta_get('sosac_state', '') or '{}')
    except ValueError:
        state = {}
    if not state.get('known'):
        return label
    if not state.get('vip'):
        return '%s  [COLOR red]%s[/COLOR]' % (label, t('premium_inactive_short'))
    if state.get('days') is None:
        return '%s  [COLOR lime]%s[/COLOR]' % (label, t('premium_short'))
    days = int(state['days'])
    color = 'orange' if days <= kodi.setting_int('vip_warn_days', 7) else 'lime'
    text = t('premium_until_short', state['until'], days) if state.get('until') else t('premium_days_short', days)
    return '%s  [COLOR %s]%s[/COLOR]' % (label, color, text)


def _account_label():
    """Popisek položky účtu se stavem VIP z poslední kontroly."""
    label = t('menu_account')
    try:
        state = json.loads(ctx.db().meta_get('vip_state', '') or '{}')
    except ValueError:
        state = {}
    if not ctx.provider().is_logged_in():
        return '%s  [COLOR orange]%s[/COLOR]' % (label, t('account_not_logged'))
    if not state:
        return label
    if not state.get('vip'):
        return '%s  [COLOR red]%s[/COLOR]' % (label, t('vip_inactive_short'))
    days = int(state.get('days') or 0)
    color = 'orange' if days <= kodi.setting_int('vip_warn_days', 7) else 'lime'
    return '%s  [COLOR %s]%s[/COLOR]' % (label, color, t('vip_days_short', days))


@route('root')
def root(params):
    listing = ui.Listing()
    database = ctx.db()
    if not ctx.tmdb().has_key:
        listing.action('[COLOR orange]%s[/COLOR]' % t('menu_setup_tmdb'), 'tmdb_help', ui.ICON_SETTINGS,
                       plot=t('tmdb_help_text'))
    listing.folder(t('menu_movies'), 'movies', ui.ICON_MOVIES)
    listing.folder(t('menu_shows'), 'shows', ui.ICON_SHOWS)
    unseen = database.news_unseen_count()
    guard_label = t('menu_guard')
    if unseen:
        guard_label += '  [COLOR lime]%s[/COLOR]' % t('news_count', unseen)
    listing.folder(guard_label, 'guard', ui.ICON_NEW, plot=t('guard_plot'))
    listing.folder(t('menu_my'), 'my', ui.ICON_LIST)
    listing.folder(t('menu_continue'), 'continue', ui.ICON_HISTORY)
    listing.folder(t('menu_search'), 'search', ui.ICON_SEARCH)
    listing.folder(t('menu_history'), 'history', ui.ICON_HISTORY)
    listing.action(_account_label(), 'account', ui.ICON_USER)
    if kodi.setting_bool('src_sosac', True):
        listing.action(_sosac_label(), 'account_sosac', ui.ICON_USER)
    listing.action('%s  [COLOR gray]%s[/COLOR]' % (t('menu_settings'), t('version_label', kodi.version())),
                   'settings', ui.ICON_SETTINGS)
    listing.finish(cache=False)


@route('settings')
def settings(params):
    kodi.open_settings()


@route('tmdb_help')
def tmdb_help(params):
    kodi.ok(t('tmdb_help_text'), t('menu_setup_tmdb'))
    kodi.open_settings()


@route('movies')
def movies(params):
    listing = ui.Listing()
    for category, label in MOVIE_CATEGORIES:
        listing.folder(t(label), 'list', ui.ICON_NEW if category == 'new' else ui.ICON_MOVIES,
                       kind='movie', cat=category)
    listing.folder(t('cat_genres'), 'genres', ui.ICON_GENRE, kind='movie')
    listing.folder(t('cat_az'), 'az', ui.ICON_LIST, kind='movie')
    listing.action(t('search_movie'), 'search_new', ui.ICON_SEARCH, kind='movie')
    listing.finish()


@route('shows')
def shows(params):
    listing = ui.Listing()
    for category, label in SHOW_CATEGORIES:
        listing.folder(t(label), 'list', ui.ICON_NEW if category == 'new' else ui.ICON_SHOWS,
                       kind='tv', cat=category)
    listing.folder(t('cat_genres'), 'genres', ui.ICON_GENRE, kind='tv')
    listing.folder(t('cat_az'), 'az', ui.ICON_LIST, kind='tv')
    listing.action(t('search_show'), 'search_new', ui.ICON_SEARCH, kind='tv')
    listing.finish()


@route('genres')
def genres(params):
    kind = params.get('kind', 'movie')
    listing = ui.Listing()
    for genre_id, name in ctx.tmdb().genres(kind):
        listing.folder(name, 'list', ui.ICON_GENRE, kind=kind, cat='genre', genre=genre_id)
    listing.finish()


def _when(timestamp):
    """Čas jako „14:32“ (dnes) nebo „12.11. 14:32“."""
    moment = datetime.datetime.fromtimestamp(int(timestamp))
    if moment.date() == datetime.date.today():
        return moment.strftime('%H:%M')
    return moment.strftime('%d.%m. %H:%M')


def prepare(kind, items, tmdb, database, hide_shorts=True):
    """Vyřadí skryté tituly a krátké filmy a doplní délku / počet řad."""
    hidden = database.hidden_ids(kind)
    items = [m for m in items if m['tmdb_id'] not in hidden]
    if items and ctx.wants_extras():
        try:
            tmdb.enrich(kind, items)
        except MetadataError:
            pass                           # bez doplňujících údajů se seznam zobrazí taky
    shortest = ctx.min_runtime() if hide_shorts else 0
    if kind == 'movie' and shortest:
        # krátké filmy (bonusy, epizody vedené jako film); neznámá délka se neskrývá
        items = [m for m in items if not 0 < (m.get('runtime') or 0) < shortest]
    if items and ctx.wants_langs():
        try:
            availability.fill(kind, items, ctx.provider(), ctx.prefs(), database)
        except Exception:
            kodi.error('zjišťování jazyků selhalo:\n%s' % traceback.format_exc())
    return items


def add_media(listing, kind, items, database):
    saved = database.watch_ids(kind)
    progress = database.progress_movies() if kind == 'movie' else {}
    for media in items:
        if kind == 'movie':
            listing.add(*ui.movie_item(media, in_watchlist=media['tmdb_id'] in saved,
                                       progress=progress.get(media['tmdb_id'])))
        else:
            listing.add(*ui.show_item(media, followed=media['tmdb_id'] in saved))


def _list_params(params):
    """Parametry, které určují seznam (bez čísla strany)."""
    return {'kind': params.get('kind', 'movie'), 'cat': params.get('cat', 'popular'),
            'genre': params.get('genre'), 'q': params.get('q'), 'ref': params.get('ref')}


@route('list')
def media_list(params):
    base = _list_params(params)
    kind, category = base['kind'], base['cat']
    page = max(1, int(params.get('page', 1)))

    tmdb = ctx.tmdb()
    database = ctx.db()
    items, pages, fetched = tmdb.listing(kind, category, page=page, genre=base['genre'], query=base['q'],
                                         per_page=ctx.page_batches(), ref=base['ref'])
    items = prepare(kind, items, tmdb, database)
    listing = ui.Listing('movies' if kind == 'movie' else 'tvshows')

    # řádek s číslem strany a časem načtení; stiskem jde přeskočit na jinou stranu nebo seznam obnovit
    if items:
        label = t('nav_jump', page, pages)
        if fetched:
            label += '  [COLOR gray]· %s[/COLOR]' % t('nav_updated', _when(fetched))
        listing.action(label, 'list_nav', ui.ICON_NEXT, plot=t('nav_plot'), page=page, pages=pages, **base)
    add_media(listing, kind, items, database)
    if not items and page == 1:
        kodi.notify(t('nothing_found'))
    if page < pages:
        listing.folder(t('next_page', page + 1, pages), 'list', ui.ICON_NEXT, page=page + 1, **base)
    if pages > 1:
        listing.action(t('nav_goto'), 'list_nav', ui.ICON_NEXT, plot=t('nav_plot'), page=page, pages=pages, **base)
    listing.finish(cache=False)


@route('list_nav')
def list_nav(params):
    """Nabídka u seznamu: skok na stranu, nové načtení, první strana."""
    base = _list_params(params)
    page = int(params.get('page', 1))
    pages = int(params.get('pages', 1))
    options = [t('nav_goto'), t('nav_refresh')]
    if page > 1:
        options.append(t('nav_first'))
    choice = kodi.select(t('nav_page', page, pages), options)
    if choice == 0:
        target = kodi.number(t('nav_goto_prompt', pages))
        if target and target != page:
            kodi.go_to(kodi.url_for('list', page=min(max(target, 1), pages), **base))
    elif choice == 1:
        ctx.tmdb().listing(base['kind'], base['cat'], page=page, genre=base['genre'], query=base['q'],
                           per_page=ctx.page_batches(), fresh=True, ref=base['ref'])
        kodi.refresh()
    elif choice == 2:
        kodi.go_to(kodi.url_for('list', page=1, **base))


# ---------------------------------------------------------------- abecední seznam
def _build_catalog(kind):
    """Sestaví abecední index s ukazatelem průběhu. Vrací True, když se povedlo."""
    dialog = xbmcgui.DialogProgress()
    dialog.create(t('addon_name'), t('az_building'))
    try:
        count = catalog.build(ctx.tmdb(), ctx.db(), kind, ctx.catalog_pages(),
                              progress=lambda done, total: dialog.update(int(100.0 * done / total), t('az_building')),
                              should_stop=dialog.iscanceled)
    finally:
        dialog.close()
    if not count:
        kodi.notify(t('az_failed'), is_error=True)
    return bool(count)


@route('az')
def az(params):
    kind = params.get('kind', 'movie')
    database = ctx.db()
    if database.catalog_count(kind, include_hidden=True) == 0 and not _build_catalog(kind):
        ui.fail()
        return
    listing = ui.Listing()
    built = database.meta_get('catalog_built_' + kind)
    info = t('az_info', database.catalog_count(kind), _when(built) if built else '?')
    listing.action('[COLOR gray]%s[/COLOR]' % info, 'az_build', ui.ICON_SETTINGS, plot=t('az_rebuild'), kind=kind)
    for letter, count in database.catalog_letters(kind):
        listing.folder('%s  [COLOR gray](%d)[/COLOR]' % ('0–9' if letter == '#' else letter.upper(), count),
                       'az_list', ui.ICON_LIST, kind=kind, letter=letter)
    listing.finish(cache=False)


@route('az_build')
def az_build(params):
    if _build_catalog(params.get('kind', 'movie')):
        kodi.refresh()


@route('az_list')
def az_list(params):
    kind = params.get('kind', 'movie')
    letter = params.get('letter', 'a')
    page = max(1, int(params.get('page', 1)))
    size = ctx.page_batches() * 20
    database = ctx.db()
    total = database.catalog_count(kind, letter)
    pages = max(1, (total + size - 1) // size)
    items = prepare(kind, database.catalog_page(kind, letter, size, (page - 1) * size), ctx.tmdb(), database)
    listing = ui.Listing('movies' if kind == 'movie' else 'tvshows')
    if pages > 1:
        listing.action(t('nav_jump', page, pages), 'az_nav', ui.ICON_NEXT, kind=kind, letter=letter,
                       page=page, pages=pages)
    add_media(listing, kind, items, database)
    if page < pages:
        listing.folder(t('next_page', page + 1, pages), 'az_list', ui.ICON_NEXT, kind=kind, letter=letter,
                       page=page + 1)
    listing.finish(cache=False)


@route('az_nav')
def az_nav(params):
    page, pages = int(params.get('page', 1)), int(params.get('pages', 1))
    target = kodi.number(t('nav_goto_prompt', pages))
    if target and target != page:
        kodi.go_to(kodi.url_for('az_list', kind=params.get('kind', 'movie'), letter=params.get('letter', 'a'),
                                page=min(max(target, 1), pages)))


@route('seasons')
def seasons(params):
    tmdb_id = int(params['id'])
    show, season_list = ctx.tmdb().seasons(tmdb_id)
    listing = ui.Listing('seasons')
    progress = ctx.db().progress_episodes(tmdb_id)
    for season in season_list:
        label = season['name'] or t('season_n', season['season'])
        total = season['episodes']
        watched = min(watched_in_season(progress, season['season']), total)
        # ukazatel „zhlédnuto / celkem“; zeleně, když je sezóna dokoukaná
        item = xbmcgui.ListItem('%s  [COLOR %s][%d/%d][/COLOR]' % (label, 'lime' if watched >= total else 'gray',
                                                                  watched, total))
        ui.set_episode_counts(item, watched, total)
        item.setArt({'poster': season['poster'], 'thumb': season['poster'], 'icon': season['poster'] or ui.ICON_SHOWS,
                     'fanart': show.get('fanart') or ''})
        tag = item.getVideoInfoTag()
        tag.setMediaType('season')
        tag.setTitle(label)
        tag.setTvShowTitle(show['title'])
        tag.setSeason(int(season['season']))
        tag.setPlot(season['plot'] or show.get('plot', ''))
        listing.add(kodi.url_for('episodes', id=tmdb_id, season=season['season']), item, True)
    listing.finish(cache=False)


def _episode_langs(tmdb, database, tmdb_id, aired):
    """Jazyky streamů pro díly jedné řady: {(tmdb_id, řada, díl): jazyky}."""
    if not aired or not ctx.wants_langs():
        return {}
    try:
        _media, titles = tmdb.titles('tv', tmdb_id)
        wanted = dict(((tmdb_id, ep['season'], ep['episode']), (titles, 0)) for ep in aired)
        return availability.lookup('episode', wanted, ctx.provider(), ctx.prefs(), database)
    except Exception:
        kodi.error('zjišťování jazyků selhalo:\n%s' % traceback.format_exc())
        return {}


@route('episodes')
def episodes(params):
    tmdb_id = int(params['id'])
    season = int(params['season'])
    tmdb = ctx.tmdb()
    show = tmdb.media('tv', tmdb_id)
    listing = ui.Listing('episodes')
    database = ctx.db()
    progress = database.progress_episodes(tmdb_id)
    all_episodes = tmdb.episodes(tmdb_id, season)
    langs = _episode_langs(tmdb, database, tmdb_id, [ep for ep in all_episodes if ep['aired']])
    for ep in all_episodes:
        if ep['aired']:
            key = (ep['season'], ep['episode'])
            listing.add(*ui.episode_item(show, ep['season'], ep['episode'], ep['name'], ep['plot'], ep['thumb'],
                                         ep['air_date'], ep['rating'], ep['runtime'],
                                         progress=progress.get(key), langs=langs.get((tmdb_id,) + key)))
        else:
            # ještě neodvysílaný díl - jen informace, nejde přehrát
            when = ep['air_date'] or t('date_unknown')
            listing.action('[COLOR gray]%d. %s  (%s)[/COLOR]' % (ep['episode'], ep['name'] or t('episode_n', ep['episode']), when),
                           'not_aired', ui.ICON_SHOWS, plot=ep['plot'], date=when)
    listing.finish(cache=False)


@route('not_aired')
def not_aired(params):
    kodi.notify(t('not_aired', params.get('date', '')))
