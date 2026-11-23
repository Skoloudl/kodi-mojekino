# -*- coding: utf-8 -*-
"""Moje seznamy: filmy ke zhlédnutí, sledované seriály, novinky od hlídače, historie."""
import datetime

import xbmcgui

from resources.lib import context as ctx
from resources.lib import kodi, ui
from resources.lib.db import now
from resources.lib.episodes import next_unwatched
from resources.lib.kodi import t, url_for
from resources.lib.metadata import MetadataError
from resources.lib.router import route
from resources.lib.watcher import Watcher


def _row_media(kind, row):
    """Řádek z databáze jako slovník media."""
    return {
        'kind': kind, 'tmdb_id': row['tmdb_id'], 'title': row['title'] or '',
        'original_title': row.get('original_title') or '', 'year': row.get('year') or 0,
        'plot': row.get('plot') or '', 'poster': row.get('poster'), 'fanart': row.get('fanart'),
    }


def _date(timestamp, with_time=False):
    if not timestamp:
        return ''
    pattern = '%d.%m.%Y %H:%M' if with_time else '%d.%m.%Y'
    return datetime.datetime.fromtimestamp(int(timestamp)).strftime(pattern)


@route('my')
def my(params):
    database = ctx.db()
    listing = ui.Listing()
    unseen = database.news_unseen_count()
    label = t('my_news')
    if unseen:
        label += '  [COLOR lime]%s[/COLOR]' % t('news_count', unseen)
    listing.folder(label, 'news', ui.ICON_NEW, plot=t('my_news_plot'))
    listing.folder('%s  [COLOR gray](%d)[/COLOR]' % (t('my_movies'), len(database.watch_list('movie'))),
                   'my_list', ui.ICON_MOVIES, plot=t('my_movies_plot'), kind='movie')
    listing.folder('%s  [COLOR gray](%d)[/COLOR]' % (t('my_shows'), len(database.watch_list('tv'))),
                   'my_list', ui.ICON_SHOWS, plot=t('my_shows_plot'), kind='tv')
    hidden = len(database.hidden_list())
    if hidden:
        listing.folder('%s  [COLOR gray](%d)[/COLOR]' % (t('my_hidden'), hidden), 'hidden', ui.ICON_LIST,
                       plot=t('hidden_plot'))
    last = database.meta_get('job_last_watcher')
    plot = t('check_now_plot', _date(last, with_time=True)) if last else t('check_never')
    label = t('check_now')
    if last:
        label += '  [COLOR gray]%s[/COLOR]' % t('check_last', _date(last, with_time=True))
    listing.action(label, 'check_now', ui.ICON_SETTINGS, plot=plot)
    listing.finish(cache=False)


@route('my_list')
def my_list(params):
    kind = params.get('kind', 'movie')
    rows = ctx.db().watch_list(kind)
    progress = ctx.db().progress_movies() if kind == 'movie' else {}
    watched_counts = ctx.db().progress_show_counts() if kind == 'tv' else {}
    tmdb = ctx.tmdb()
    listing = ui.Listing('movies' if kind == 'movie' else 'tvshows')
    for row in rows:
        media = _row_media(kind, row)
        if kind == 'movie':
            label = media['title']
            if row['available_at']:
                label += '  [COLOR lime]%s[/COLOR]' % t('available')
            listing.add(*ui.movie_item(media, in_watchlist=True, label=label,
                                       progress=progress.get(row['tmdb_id'])))
        else:
            pending = len(ctx.db().pending_list(row['tmdb_id']))
            label = media['title']
            if pending:
                label += '  [COLOR orange]%s[/COLOR]' % t('pending_count', pending)
            counts = None
            try:
                counts = (watched_counts.get(row['tmdb_id'], 0), tmdb.episode_total(row['tmdb_id']))
            except MetadataError:
                pass                       # bez katalogu jen neukážeme počty dílů
            listing.add(*ui.show_item(media, followed=True, label=label, counts=counts))
    if not rows:
        kodi.notify(t('list_empty'))
    listing.finish(cache=False)


def _episode_code(season, episode):
    return 'S%02dE%02d' % (int(season), int(episode))


def _short_date(iso):
    """2026-11-28 -> 28.11. (letos) nebo 28.11.2027."""
    try:
        day = datetime.datetime.strptime(iso, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return iso or ''
    return day.strftime('%d.%m.') if day.year == datetime.date.today().year else day.strftime('%d.%m.%Y')


def _show_status(database, tmdb, tmdb_id):
    """Stav hlídaného seriálu jako barevný text: díly čekající na stream a kdy vyjde další díl."""
    parts = []
    pending = database.pending_list(tmdb_id)
    if pending:
        text = _episode_code(pending[0]['season'], pending[0]['episode'])
        if len(pending) > 1:
            text += ' ' + t('guard_more', len(pending) - 1)
        parts.append('[COLOR orange]%s[/COLOR]' % t('guard_waiting', text))
    info = None
    if tmdb.has_key:
        try:
            info = tmdb.next_to_air(tmdb_id)
        except MetadataError:
            info = None
    if info and info['next']:
        upcoming = info['next']
        parts.append('[COLOR gray]%s[/COLOR]' % t('guard_next_air', _episode_code(upcoming['season'], upcoming['episode']),
                                                 _short_date(upcoming['air_date']) or '?'))
    elif info and info['ended']:
        parts.append('[COLOR gray]%s[/COLOR]' % t('guard_ended'))
    elif not pending:
        parts.append('[COLOR gray]%s[/COLOR]' % t('guard_up_to_date'))
    return '  '.join(parts)


@route('guard')
def guard(params):
    """Hlídané: nahoře nové díly a filmy, které hlídač našel, pod nimi hlídané tituly se stavem."""
    database = ctx.db()
    tmdb = ctx.tmdb()
    shows, movies = database.watch_list('tv'), database.watch_list('movie')
    listing = ui.Listing('videos')
    if not shows and not movies:
        listing.action('[COLOR orange]%s[/COLOR]' % t('guard_empty'), 'guard_help', ui.ICON_SETTINGS,
                       plot=t('guard_help'))
    new_mark = '[COLOR lime]● %s[/COLOR]  ' % t('guard_new')
    # 1. nalezené novinky, které ještě nejsou zhlédnuté - dají se rovnou pustit
    for row in database.news_list(limit=60):
        record = 'movie' if row['kind'] == 'movie' else 'episode'
        progress = database.progress_get(record, row['tmdb_id'], row['season'], row['episode'])
        if progress and progress['watched']:
            continue
        when = '  [COLOR gray]%s[/COLOR]' % _date(row['found_at'])
        remove = [(t('ctx_news_remove'), 'RunPlugin(%s)' % url_for('news_remove', id=row['id']))]
        media = _row_media('movie' if record == 'movie' else 'tv', row)
        if record == 'movie':
            listing.add(*ui.movie_item(media, in_watchlist=True, label=new_mark + row['title'] + when,
                                       extra_context=remove, progress=progress))
        else:
            name = (row['subtitle'] or '').split(' · ', 1)
            remove.append((t('ctx_open_show'), 'Container.Update(%s)' % url_for('seasons', id=row['tmdb_id'])))
            listing.add(*ui.episode_item(media, row['season'], row['episode'], name[1] if len(name) > 1 else '',
                                         label='%s%s – %s%s' % (new_mark, row['title'], row['subtitle'] or '', when),
                                         extra_context=remove, progress=progress))
    # 2. hlídané seriály: co čeká na stream a kdy vyjde další díl
    for row in shows:
        media = _row_media('tv', row)
        status = _show_status(database, tmdb, row['tmdb_id'])
        listing.add(*ui.show_item(media, followed=True, label=media['title'] + ('  ' + status if status else '')))
    # 3. hlídané filmy
    progress = database.progress_movies()
    for row in movies:
        media = _row_media('movie', row)
        state = ('[COLOR lime]%s[/COLOR]' % t('available') if row['available_at']
                 else '[COLOR orange]%s[/COLOR]' % t('guard_movie_waiting'))
        listing.add(*ui.movie_item(media, in_watchlist=True, label='%s  %s' % (media['title'], state),
                                   progress=progress.get(row['tmdb_id'])))
    last = database.meta_get('job_last_watcher')
    label = t('check_now')
    if last:
        label += '  [COLOR gray]%s[/COLOR]' % t('check_last', _date(last, with_time=True))
    listing.action(label, 'check_now', ui.ICON_SETTINGS,
                   plot=t('check_now_plot', _date(last, with_time=True)) if last else t('check_never'))
    listing.finish(cache=False)
    database.news_mark_seen()


@route('guard_help')
def guard_help(params):
    kodi.ok(t('guard_help'), t('menu_guard'))


@route('watch_toggle')
def watch_toggle(params):
    kind = params.get('kind', 'movie')
    tmdb_id = int(params['id'])
    database = ctx.db()
    if database.watch_has(kind, tmdb_id):
        database.watch_remove(kind, tmdb_id)
        kodi.notify(t('removed_movie') if kind == 'movie' else t('removed_show'))
    else:
        tmdb = ctx.tmdb()
        media = tmdb.media(kind, tmdb_id)
        season = episode = 0
        if kind == 'tv':
            # hlídáme až díly odvysílané po přidání do seznamu
            season, episode = tmdb.last_aired(tmdb_id, fresh=True)
        database.watch_add(media, season, episode)
        kodi.notify(t('added_movie', media['title']) if kind == 'movie' else t('added_show', media['title']))
    kodi.refresh()


@route('hide')
def hide(params):
    ctx.db().hidden_add(params.get('kind', 'movie'), int(params['id']), params.get('title', ''))
    kodi.notify(t('hidden_added', params.get('title', '')))
    kodi.refresh()


@route('hidden')
def hidden(params):
    """Skryté tituly; stiskem se titul znovu zobrazí v seznamech."""
    listing = ui.Listing()
    for row in ctx.db().hidden_list():
        kind = 'movie' if row['kind'] == 'movie' else 'tv'
        listing.action('%s  [COLOR gray]%s[/COLOR]' % (row['title'] or row['tmdb_id'], t('search_kind_' + kind)),
                       'unhide', ui.ICON_MOVIES if kind == 'movie' else ui.ICON_SHOWS, plot=t('hidden_plot'),
                       kind=row['kind'], id=row['tmdb_id'])
    listing.finish(cache=False)


@route('unhide')
def unhide(params):
    ctx.db().hidden_remove(params.get('kind', 'movie'), int(params['id']))
    kodi.refresh()


@route('news')
def news(params):
    database = ctx.db()
    rows = database.news_list()
    listing = ui.Listing('videos')
    for row in rows:
        mark = '' if row['seen'] else '[COLOR lime]●[/COLOR] '
        when = '  [COLOR gray]%s[/COLOR]' % _date(row['found_at'])
        remove = [(t('ctx_news_remove'), 'RunPlugin(%s)' % url_for('news_remove', id=row['id']))]
        media = _row_media('movie' if row['kind'] == 'movie' else 'tv', row)
        if row['kind'] == 'movie':
            label = '%s%s  [COLOR gray]%s[/COLOR]%s' % (mark, row['title'], row['subtitle'] or '', when)
            listing.add(*ui.movie_item(media, in_watchlist=True, label=label, extra_context=remove,
                                       progress=database.progress_get('movie', row['tmdb_id'])))
        else:
            name = (row['subtitle'] or '').split(' · ', 1)
            label = '%s%s – %s%s' % (mark, row['title'], row['subtitle'] or '', when)
            listing.add(*ui.episode_item(media, row['season'], row['episode'], name[1] if len(name) > 1 else '',
                                         label=label, extra_context=remove,
                                         progress=database.progress_get('episode', row['tmdb_id'], row['season'],
                                                                        row['episode'])))
    if rows:
        listing.action(t('news_clear'), 'news_remove', ui.ICON_SETTINGS)
    else:
        kodi.notify(t('news_empty'))
    listing.finish(cache=False)
    database.news_mark_seen()


@route('news_remove')
def news_remove(params):
    news_id = params.get('id')
    if news_id is None and not kodi.yesno(t('confirm_clear')):
        return
    ctx.db().news_remove(int(news_id) if news_id is not None else None)
    kodi.refresh()


@route('check_now')
def check_now(params):
    """Ruční spuštění hlídače s ukazatelem průběhu."""
    database = ctx.db()
    bar = xbmcgui.DialogProgressBG()
    bar.create(t('addon_name'), t('checking'))

    def progress(done, total, title):
        bar.update(int(100.0 * done / total) if total else 100, t('addon_name'), title or t('checking'))

    try:
        watcher = Watcher(database, ctx.tmdb(), ctx.watch_providers(), ctx.prefs(),
                          czsk_only=kodi.setting_bool('watcher_czsk_only'), progress=progress)
        found = watcher.run()
    finally:
        bar.close()
    database.meta_set('job_last_watcher', now())
    if found:
        kodi.notify(found[0] if len(found) == 1 else t('news_found', len(found)), t('news_heading'))
    elif watcher.errors:
        kodi.notify(t('check_errors'), is_error=True)
    else:
        kodi.notify(t('check_nothing'))
    kodi.refresh()


def _played_rows(listing, rows, database, remove_action=None, in_progress=False):
    """Vykreslí řádky historie / rozkoukaných titulů se stavem zhlédnutí."""
    for row in rows:
        context = []
        if remove_action:
            context.append((t('ctx_history_remove'), 'RunPlugin(%s)' % url_for(remove_action, id=row['id'])))
        if in_progress:
            context.append((t('ctx_continue_remove'), 'RunPlugin(%s)' % url_for(
                'mark_watched', kind=row['kind'], id=row['tmdb_id'], season=row['season'], episode=row['episode'],
                value=0)))
        media = _row_media('movie' if row['kind'] == 'movie' else 'tv', row)
        when = '  [COLOR gray]%s[/COLOR]' % _date(row.get('updated_at') or row['played_at'])
        if row['kind'] == 'movie':
            listing.add(*ui.movie_item(media, label=row['title'] + when, extra_context=context,
                                       progress=database.progress_get('movie', row['tmdb_id'])))
        else:
            name = (row['subtitle'] or '').split(' · ', 1)
            context.append((t('ctx_open_show'), 'Container.Update(%s)' % url_for('seasons', id=row['tmdb_id'])))
            listing.add(*ui.episode_item(media, row['season'], row['episode'], name[1] if len(name) > 1 else '',
                                         label='%s – %s%s' % (row['title'], row['subtitle'] or '', when),
                                         extra_context=context,
                                         progress=database.progress_get('episode', row['tmdb_id'], row['season'],
                                                                        row['episode'])))


@route('history')
def history(params):
    database = ctx.db()
    rows = database.history_list()
    listing = ui.Listing('videos')
    _played_rows(listing, rows, database, remove_action='history_remove')
    if rows:
        listing.action(t('history_clear'), 'history_remove', ui.ICON_SETTINGS)
    else:
        kodi.notify(t('history_empty'))
    listing.finish(cache=False)


@route('continue')
def continue_watching(params):
    """Rozkoukané filmy a díly - po spuštění Kodi nabídne pokračování od místa, kde jste skončili."""
    database = ctx.db()
    rows = database.progress_continue()
    listing = ui.Listing('videos')
    _played_rows(listing, rows, database, in_progress=True)
    shown = len(rows) + _next_up_rows(listing, database, set((r['tmdb_id'], r['season'], r['episode'])
                                                              for r in rows if r['kind'] == 'episode'))
    if not shown:
        kodi.notify(t('continue_empty'))
    listing.finish(cache=False)


def _next_up_rows(listing, database, skip):
    """Ke každému sledovanému seriálu přidá další díl k přehrání. Vrací počet přidaných řádků."""
    tmdb = ctx.tmdb()
    if not tmdb.has_key:
        return 0
    added = 0
    for tmdb_id in database.progress_shows():
        try:
            ep = next_unwatched(tmdb, database, tmdb_id)
            if not ep or (tmdb_id, ep['season'], ep['episode']) in skip:
                continue
            show = tmdb.media('tv', tmdb_id)
        except MetadataError:
            continue
        label = '%s – S%02dE%02d' % (show['title'], ep['season'], ep['episode'])
        if ep['name']:
            label += ' · ' + ep['name']
        label += '  [COLOR lime]%s[/COLOR]' % t('next_up')
        listing.add(*ui.episode_item(show, ep['season'], ep['episode'], ep['name'], ep['plot'], ep['thumb'],
                                     ep['air_date'], ep['rating'], ep['runtime'], label=label))
        added += 1
    return added


@route('mark_watched')
def mark_watched(params):
    ctx.db().progress_mark(params.get('kind', 'movie'), int(params['id']), int(params.get('season', 0)),
                           int(params.get('episode', 0)), params.get('value') == '1')
    kodi.refresh()


@route('history_remove')
def history_remove(params):
    history_id = params.get('id')
    if history_id is None and not kodi.yesno(t('confirm_clear')):
        return
    ctx.db().history_remove(int(history_id) if history_id is not None else None)
    kodi.refresh()
