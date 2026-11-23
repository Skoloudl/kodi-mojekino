# -*- coding: utf-8 -*-
"""Přehrávání: nalezení streamů, výběr a předání odkazu přehrávači Kodi."""
import json
import time

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib import context as ctx
from resources.lib import kodi, parser, streams, ui, upnext
from resources.lib.episodes import next_episode, next_unwatched
from resources.lib.kodi import t
from resources.lib.metadata import MetadataError
from resources.lib.providers import NAMES, ProviderError
from resources.lib.router import route

AUTO_TRIES = 3
RESUME_MIN = 60                           # kratší rozkoukání se nenabízí (jako ve službě)
HOME_WINDOW = 10000
PLAYING_PROPERTY = 'mojekino.playing'     # co se právě spouští - čte služba, která sleduje průběh

_ERROR_TEXT = {
    ProviderError.NOT_LOGGED_IN: 'err_not_logged',
    ProviderError.BAD_CREDENTIALS: 'err_bad_credentials',
    ProviderError.NOT_FOUND: 'err_file_not_found',
    ProviderError.UNAVAILABLE: 'err_file_unavailable',
    ProviderError.TOO_MANY: 'err_too_many',
    ProviderError.PASSWORD: 'err_file_password',
    ProviderError.NETWORK: 'err_network',
    ProviderError.UNKNOWN: 'err_unknown',
}


def provider_error_text(error):
    return t(_ERROR_TEXT.get(error.code, 'err_unknown'))


def _cancel(direct=False):
    """Oznámí Kodi, že se nic nepřehraje. `direct` = nevolal nás seznam doplňku, není komu co hlásit."""
    if not direct and kodi.handle() >= 0:
        xbmcplugin.setResolvedUrl(kodi.handle(), False, xbmcgui.ListItem())


def _kodi_waits(direct=False):
    """Čeká Kodi na odkaz k položce, kterou právě rozbaluje (přehratelná položka, PlayMedia, playlist)?"""
    return not direct and kodi.handle() >= 0


def _start(link, item, track=None, direct=False, queue=None, resume_at=0):
    """Spustí přehrávání.

    Tři případy:
      * Kodi čeká na odkaz (přehratelná položka nebo položka playlistu) - odkaz mu předáme;
        je-li to položka playlistu (`track['queued']`), zařadí se za ni další díl.
      * Kodi na nic nečeká (díl spuštěný ze seznamu doplňku, služba) a je známý další díl -
        spustí se playlist [tento díl, další díl], takže v přehrávači funguje přeskočení dílu.
        Další díl je v playlistu jen jako odkaz do doplňku; stream se k němu hledá až na něm.
      * jinak se odkaz pustí přímo přehrávačem.

    Playlist se nesmí spouštět, když Kodi čeká na odkaz: odmítnutý odkaz by Kodi připsalo
    prvnímu dílu playlistu a hned přeskočilo na další (chyba verze 0.7.0).
    """
    window = xbmcgui.Window(HOME_WINDOW)
    waits = _kodi_waits(direct)
    queued = bool(track and track.get('queued'))
    if waits and not queued:
        queue = None                  # samostatná položka - playlist z ní udělat nejde
    if track:
        data = dict(track, started=int(time.time()), next_url=queue[0] if queue else '')
        window.setProperty(PLAYING_PROPERTY, json.dumps(data))
    else:
        window.clearProperty(PLAYING_PROPERTY)
    item.setPath(link)
    if waits:
        xbmcplugin.setResolvedUrl(kodi.handle(), True, item)
        if queue:
            xbmc.PlayList(xbmc.PLAYLIST_VIDEO).add(queue[0], queue[1])
        return
    if resume_at:
        item.setProperty('StartOffset', '%d' % resume_at)
    if queue:
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        playlist.clear()
        playlist.add(link, item)
        playlist.add(queue[0], queue[1])
        xbmc.Player().play(playlist)
    else:
        xbmc.Player().play(link, item)


def _queue_entry(tmdb, media, tmdb_id, season, episode):
    """Další díl do playlistu: (adresa, položka, díl), nebo None, když žádný není."""
    try:
        ep = next_episode(tmdb, tmdb_id, season, episode)
    except MetadataError:
        return None
    if not ep:
        return None
    url = kodi.url_for('play', kind='episode', id=tmdb_id, season=ep['season'], episode=ep['episode'],
                       auto=1, queued=1)
    _url, item, _folder = ui.episode_item(media, ep['season'], ep['episode'], ep.get('name', ''),
                                          ep.get('plot', ''), ep.get('thumb'), ep.get('air_date', ''),
                                          ep.get('rating', 0), ep.get('runtime', 0))
    item.setProperty('IsPlayable', 'true')      # položku playlistu Kodi rozbalí přes doplněk
    return url, item, ep


def _ask_resume(progress):
    """Rozkoukaný díl: pokračovat, nebo od začátku? Vrací pozici (0 = od začátku), None = zrušeno."""
    if not progress or progress['watched'] or (progress['position'] or 0) < RESUME_MIN:
        return 0
    position = int(progress['position'])
    choice = kodi.menu([t('resume_from', ui.format_time(position)), t('play_from_start')])
    if choice < 0:
        return None
    return position if choice == 0 else 0


def _require_login(provider):
    if provider.is_logged_in():
        return True
    _cancel()
    if kodi.yesno(t('login_required'), yes=t('login_now'), no=t('later')):
        kodi.execute('RunPlugin(%s)' % kodi.url_for('account'))
    return False


# ---------------------------------------------------------------- filtr ve výběru streamu
FACETS = ('provider', 'audio', 'quality', 'subs')
FACET_TEXTS = {'provider': 'filter_facet_provider', 'audio': 'filter_facet_audio',
               'quality': 'filter_facet_quality', 'subs': 'filter_facet_subs'}
UNKNOWN = '?'          # zvuk bez označení jazyka
NO_SUBS = '-'          # stream bez titulků
FILTER_MIN = 8         # u kratších seznamů z jednoho zdroje se filtr nenabízí
_QUALITY_NAMES = {'q2160': '4K', 'q1080': '1080p', 'q720': '720p', 'q480': 'SD'}


def _values(candidate, facet):
    """Hodnoty, kterými se stream hlásí do daného filtru (zvuk i titulky jich mohou mít víc)."""
    info = candidate.info
    if facet == 'provider':
        return [candidate.file.provider]
    if facet == 'audio':
        return list(info['audio']) or [UNKNOWN]
    if facet == 'quality':
        return ['q%d' % (info['quality'] if info['quality'] in (2160, 1080, 720, 480) else 0)]
    return list(info['subs']) or [NO_SUBS]


def _matches(candidate, state, skip=None):
    for facet in FACETS:
        if facet != skip and state.get(facet) and state[facet] not in _values(candidate, facet):
            return False
    return True


def _value_label(facet, value):
    if facet == 'provider':
        return NAMES.get(value, value)
    if facet == 'audio':
        return t('filter_audio_unknown') if value == UNKNOWN else value.upper()
    if facet == 'quality':
        return _QUALITY_NAMES.get(value, t('filter_quality_unknown'))
    return t('filter_no_subs') if value == NO_SUBS else t('filter_subs_lang', value.upper())


def _facet_options(found, state, facet):
    """[(hodnota, počet)] pro daný filtr. Počty platí pro streamy, které vyhovují ostatním filtrům."""
    counts = {}
    for candidate in found:
        if _matches(candidate, state, skip=facet):
            for value in _values(candidate, facet):
                counts[value] = counts.get(value, 0) + 1
    if facet == 'provider':
        return list(counts.items())                                   # pořadí podle nejlepšího streamu
    if facet == 'quality':
        return sorted(counts.items(), key=lambda item: -int(item[0][1:]))
    first = ('cz', 'sk', 'en')
    return sorted(counts.items(), key=lambda item: (item[0] in (UNKNOWN, NO_SUBS),
                                                    first.index(item[0]) if item[0] in first else len(first),
                                                    item[0]))


def _active_text(state):
    return ' · '.join(_value_label(f, state[f]) for f in FACETS if state.get(f))


def _filterable(found):
    return len(set(c.file.provider for c in found)) > 1 or len(found) >= FILTER_MIN


def _edit_filter(found, state):
    """Okno filtru: zdroj, zvuk, kvalita, titulky. Každý řádek ukazuje zvolenou hodnotu a otevře její nabídku."""
    while True:
        shown = sum(1 for c in found if _matches(c, state))
        if not shown:
            state.clear()
            continue
        rows, actions = [], []
        for facet in FACETS:
            options = _facet_options(found, state, facet)
            if len(options) < 2 and not state.get(facet):
                continue                                              # není z čeho vybírat
            value = _value_label(facet, state[facet]) if state.get(facet) else t('filter_any')
            rows.append(t(FACET_TEXTS[facet], value))
            actions.append(facet)
        rows.append('[COLOR lime]%s[/COLOR]' % t('filter_show', shown))
        actions.append('show')
        if any(state.get(f) for f in FACETS):
            rows.append(t('filter_reset'))
            actions.append('reset')
        index = kodi.select(t('filter_heading'), rows)
        if index < 0 or actions[index] == 'show':
            return
        if actions[index] == 'reset':
            state.clear()
            continue
        facet = actions[index]
        options = _facet_options(found, state, facet)
        labels = [t('filter_any_count', sum(1 for c in found if _matches(c, state, skip=facet)))]
        labels += ['%s (%d)' % (_value_label(facet, value), number) for value, number in options]
        picked = kodi.select(t(FACET_TEXTS[facet], '').rstrip(': '), labels)
        if picked == 0:
            state.pop(facet, None)
        elif picked > 0:
            state[facet] = options[picked - 1][0]


def _choose(found, pick, state=None):
    """Nechá vybrat stream a vrátí kandidáta, nebo None (zrušeno). Při automatickém výběru vždy prvního.

    U delších seznamů a při více zdrojích je nahoře řádek „Filtr“ (zdroj, zvuk, kvalita, titulky), který
    seznam zúží. `state` si pamatuje zvolený filtr, aby po neúspěšném přehrání zůstal.
    """
    if kodi.setting_bool('auto_select') and not pick:
        return found[0]
    state = state if state is not None else {}
    filterable = _filterable(found)
    while True:
        shown = [c for c in found if _matches(c, state)]
        items = []
        if filterable:
            if state:
                head = xbmcgui.ListItem('[COLOR yellow]%s[/COLOR]' % t('filter_row_on', _active_text(state)),
                                        t('filter_row_shown', len(shown), len(found)))
            else:
                counts = {}
                for candidate in found:
                    counts[candidate.file.provider] = counts.get(candidate.file.provider, 0) + 1
                head = xbmcgui.ListItem('[COLOR yellow]%s[/COLOR]' % t('filter_row'),
                                        ' · '.join('%s %d' % (NAMES.get(s, s), n) for s, n in counts.items()))
            head.setArt({'icon': ui.ICON_SEARCH, 'thumb': ui.ICON_SEARCH})
            items.append(head)
        for candidate in shown:
            # obrázek se štítkem kvality (4K / 1080 / 720...), vedle něj jazyk a velikost, pod tím zdroj a soubor
            row = xbmcgui.ListItem(candidate.title, candidate.detail)
            badge = kodi.media(candidate.badge + '.png')
            row.setArt({'icon': badge, 'thumb': badge})
            items.append(row)
        index = kodi.select(t('pick_stream', len(shown)), items, use_details=True)
        if index < 0:
            return None
        if filterable:
            if index == 0:
                _edit_filter(found, state)
                continue
            index -= 1
        return shown[index]


def _resolve(sources, candidate):
    """Odkaz na soubor od poskytovatele, ze kterého kandidát pochází."""
    provider = sources.get(candidate.file.provider) or next(iter(sources.values()))
    return provider.resolve(candidate.file.ident)


def _resolve_chosen(sources, found, pick, silent=False):
    """Nechá vybrat stream a získá odkaz. Vrací (kandidát, odkaz) nebo (None, None).

    `sources` = {id poskytovatele: poskytovatel}. `silent` = bez dotazů (automatické přehrání dalšího dílu).
    """
    auto = silent or (kodi.setting_bool('auto_select') and not pick)
    if auto:
        last_error = None
        for candidate in found[:AUTO_TRIES]:
            try:
                return candidate, _resolve(sources, candidate)
            except ProviderError as e:
                last_error = e
                if e.code not in (ProviderError.NOT_FOUND, ProviderError.UNAVAILABLE, ProviderError.PASSWORD):
                    break
        kodi.notify(provider_error_text(last_error), is_error=True)
        return None, None
    state = {}
    while True:
        candidate = _choose(found, pick, state)
        if candidate is None:
            return None, None
        try:
            return candidate, _resolve(sources, candidate)
        except ProviderError as e:
            kodi.notify(provider_error_text(e), is_error=True)
            if e.code not in (ProviderError.NOT_FOUND, ProviderError.UNAVAILABLE, ProviderError.PASSWORD):
                return None, None
            # soubor už neexistuje - nabídneme výběr znovu


def _wants_subtitles(info):
    """Nabídnout titulky? Jen když stream nemá český/slovenský zvuk ani titulky."""
    if not kodi.setting_bool('subs_auto', True):
        return False
    known = set(info['audio']) | set(info['subs'])
    return not (known & {'cz', 'sk'})


@route('play')
def play(params, direct=False):
    """Najde streamy a spustí přehrávání. `direct` = spustit rovnou přehrávačem (volá služba)."""
    kind = params.get('kind', 'movie')
    tmdb_id = int(params['id'])
    pick = params.get('pick') == '1'
    auto = params.get('auto') == '1'          # další díl po dokoukání - bez dotazů
    providers = ctx.stream_providers()
    if not providers:
        # žádný zdroj: Webshare nepřihlášený a další zdroje vypnuté
        if auto:
            _cancel(direct)
        else:
            _require_login(ctx.provider())
        return False
    sources = dict((p.id, p) for p in providers)
    tmdb = ctx.tmdb()
    database = ctx.db()
    # díl spuštěný ze seznamu doplňku: Kodi na nic nečeká a pokračování nabízí doplněk sám
    interactive = not auto and not _kodi_waits(direct) and not direct
    resume_at = 0
    if kind != 'movie' and interactive:
        resume_at = _ask_resume(database.progress_get('episode', tmdb_id, int(params['season']),
                                                      int(params['episode'])))
        if resume_at is None:
            return False
    busy = None
    if interactive:
        busy = xbmcgui.DialogProgressBG()      # Kodi u spuštěného doplňku samo nic neukazuje
        busy.create(t('addon_name'), t('searching_streams'))
    errors = []
    try:
        try:
            # číslo IMDb: podle něj Sosáč najde titul přesně a doplňky pro titulky správné titulky
            imdb = tmdb.imdb_id('movie' if kind == 'movie' else 'tv', tmdb_id)
        except MetadataError:
            imdb = ''
        if kind == 'movie':
            media, titles = tmdb.titles('movie', tmdb_id)
            found = streams.find_movie(providers, titles, media['year'], ctx.prefs(), cache=database, imdb=imdb,
                                       errors=errors)
        else:
            media, titles = tmdb.titles('tv', tmdb_id)
            found = streams.find_episode(providers, titles, int(params['season']), int(params['episode']),
                                         ctx.prefs(), cache=database, imdb=imdb, year=media.get('year') or 0,
                                         errors=errors)
    finally:
        if busy:
            busy.close()
    if errors:
        names = ', '.join(NAMES.get(source, source) for source, _error in errors)
        kodi.error('zdroje bez odpovědi: %s' % '; '.join('%s: %s' % pair for pair in errors))
        if not auto:
            kodi.notify(t('source_failed', names), is_error=not found)

    if kind == 'movie':
        season = episode = 0
        _url, item, _folder = ui.movie_item(media, progress=database.progress_get('movie', tmdb_id))
        manual_query = media['title']
        subtitle = ''
    else:
        season, episode = int(params['season']), int(params['episode'])
        # další díly téhož seriálu nabízíme ve stejném jazyce a kvalitě jako ten naposledy přehraný
        found = streams.order_like(found, database.meta_get('last_stream_%d' % tmdb_id, ''))
        info = {}
        for ep in tmdb.episodes(tmdb_id, season):
            if ep['episode'] == episode:
                info = ep
                break
        _url, item, _folder = ui.episode_item(media, season, episode, info.get('name', ''), info.get('plot', ''),
                                              info.get('thumb'), info.get('air_date', ''), info.get('rating', 0),
                                              info.get('runtime', 0),
                                              progress=database.progress_get('episode', tmdb_id, season, episode))
        manual_query = '%s S%02dE%02d' % (media['title'], season, episode)
        subtitle = 'S%02dE%02d' % (season, episode)
        if info.get('name'):
            subtitle += ' · ' + info['name']

    if not found:
        _cancel(direct)
        if auto:
            kodi.notify(t('autoplay_none'))
        elif kodi.yesno(t('no_streams', manual_query), yes=t('ctx_manual_search'), no=t('close')):
            kodi.execute('ActivateWindow(Videos,%s,return)' % kodi.url_for('ws_search', q=manual_query))
        return False

    candidate, link = _resolve_chosen(sources, found, pick, silent=auto)
    if not link:
        _cancel(direct)
        return False
    kodi.debug('Přehrávám: %s' % candidate.file.name)
    record = 'movie' if kind == 'movie' else 'episode'
    database.history_add(record, tmdb_id, media['title'], subtitle,
                         media.get('poster'), media.get('fanart'), season, episode)
    if record == 'episode':
        database.meta_set('last_stream_%d' % tmdb_id, candidate.file.name)
    if imdb:
        item.getVideoInfoTag().setIMDBNumber(imdb)
    track = {'kind': record, 'tmdb_id': tmdb_id, 'season': season, 'episode': episode,
             'title': media['title'], 'subs': _wants_subtitles(candidate.info), 'queued': params.get('queued') == '1',
             'czsk_audio': streams.has_czsk_audio(candidate.info)}
    queue = None
    if record == 'episode':
        entry = _queue_entry(tmdb, media, tmdb_id, season, episode)
        if entry:
            queue = entry[:2]
            current = dict(info, season=season, episode=episode)
            track['upnext'] = upnext.payload(media, current, entry[2], tmdb_id, play_url=entry[0])
    _start(link, item, track=track, direct=direct, queue=queue, resume_at=resume_at)
    return True


def start_episode(tmdb_id, season, episode):
    """Najde a rovnou spustí díl bez jakýchkoli dotazů. Volá služba (další díl po dokoukání).

    Běží mimo seznam doplňku, takže Kodi na nic nečeká - přehrávač se spustí přímo.
    Vrací True, když se přehrávání spustilo.
    """
    return bool(play({'kind': 'episode', 'id': str(tmdb_id), 'season': str(season), 'episode': str(episode),
                      'auto': '1'}, direct=True))


@route('play_next')
def play_next(params):
    """Přehraje další nezhlédnutý díl seriálu."""
    tmdb_id = int(params['id'])
    ep = next_unwatched(ctx.tmdb(), ctx.db(), tmdb_id)
    if not ep:
        _cancel()
        kodi.notify(t('no_next_episode'))
        return
    play(dict(params, kind='episode', season=str(ep['season']), episode=str(ep['episode'])))


@route('play_file')
def play_file(params):
    """Přehraje konkrétní soubor z ručního hledání."""
    provider = ctx.provider()
    if not _require_login(provider):
        return
    try:
        link = provider.resolve(params['ident'])
    except ProviderError as e:
        _cancel()
        kodi.notify(provider_error_text(e), is_error=True)
        return
    item = xbmcgui.ListItem(params.get('name', ''))
    item.getVideoInfoTag().setTitle(params.get('name', ''))
    _start(link, item)


@route('ws_search')
def ws_search(params):
    """Ruční hledání souborů přímo u poskytovatele."""
    query = params.get('q', '')
    offset = int(params.get('offset', 0))
    limit = 50
    if not query:
        ui.fail()
        return
    provider = ctx.provider()
    files, total = provider.search(query, limit=limit, offset=offset)
    listing = ui.Listing('videos')
    for f in files:
        if f.protected:
            continue
        info = parser.parse(f.name)
        item = xbmcgui.ListItem('%s  [COLOR gray]%s[/COLOR]' % (streams.describe(info, f.size), f.name))
        item.setArt({'icon': ui.ICON_VIDEO})
        tag = item.getVideoInfoTag()
        tag.setTitle(f.name)
        tag.setPlot(f.name)
        item.setProperty('IsPlayable', 'true')
        listing.add(kodi.url_for('play_file', ident=f.ident, name=f.name), item, False)
    if not files and offset == 0:
        kodi.notify(t('nothing_found'))
    if offset + limit < total and files:
        listing.folder(t('next_results'), 'ws_search', ui.ICON_NEXT, q=query, offset=offset + limit)
    listing.finish()
