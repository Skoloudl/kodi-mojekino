# -*- coding: utf-8 -*-
"""Stavba položek seznamu (ListItem) pro Kodi."""
import xbmcgui
import xbmcplugin

from resources.lib import kodi
from resources.lib.kodi import t, url_for

ICON_FOLDER = 'DefaultFolder.png'
ICON_MOVIES = 'DefaultMovies.png'
ICON_SHOWS = 'DefaultTVShows.png'
ICON_SEARCH = 'DefaultAddonsSearch.png'
ICON_LIST = 'DefaultPlaylist.png'
ICON_NEW = 'DefaultRecentlyAddedMovies.png'
ICON_HISTORY = 'DefaultAddonsRecentlyUpdated.png'
ICON_USER = 'DefaultUser.png'
ICON_SETTINGS = 'DefaultAddonProgram.png'
ICON_GENRE = 'DefaultGenre.png'
ICON_NEXT = 'DefaultFolder.png'
ICON_VIDEO = 'DefaultVideo.png'


class Listing(object):
    """Sbírá položky jedné obrazovky a nakonec je předá Kodi."""

    def __init__(self, content=None):
        self._items = []
        self._content = content

    def add(self, url, item, is_folder):
        self._items.append((url, item, is_folder))

    def folder(self, label, action, icon=ICON_FOLDER, plot='', context=None, **params):
        item = xbmcgui.ListItem(label)
        item.setArt({'icon': icon, 'thumb': icon})
        if plot:
            item.getVideoInfoTag().setPlot(plot)
        if context:
            item.addContextMenuItems(context)
        self.add(url_for(action, **params), item, True)

    def action(self, label, action, icon=ICON_FOLDER, plot='', **params):
        """Položka, která něco provede (neotevírá další seznam)."""
        item = xbmcgui.ListItem(label)
        item.setArt({'icon': icon, 'thumb': icon})
        if plot:
            item.getVideoInfoTag().setPlot(plot)
        self.add(url_for(action, **params), item, False)

    def finish(self, cache=True, update=False):
        handle = kodi.handle()
        if self._content:
            xbmcplugin.setContent(handle, self._content)
        xbmcplugin.addDirectoryItems(handle, self._items, len(self._items))
        xbmcplugin.endOfDirectory(handle, succeeded=True, updateListing=update, cacheToDisc=cache)


def fail():
    """Ukončí obrazovku bez výsledku (chyba, zrušeno)."""
    xbmcplugin.endOfDirectory(kodi.handle(), succeeded=False)


def _art(item, poster=None, fanart=None, thumb=None, fallback=ICON_VIDEO):
    art = {'icon': poster or thumb or fallback, 'thumb': thumb or poster or fallback}
    if poster:
        art['poster'] = poster
    if fanart:
        art['fanart'] = fanart
    item.setArt(art)


def _tag(item, media_type, title, plot='', year=0, rating=0, votes=0, premiered='', original=''):
    tag = item.getVideoInfoTag()
    tag.setMediaType(media_type)
    tag.setTitle(title)
    if original:
        tag.setOriginalTitle(original)
    if plot:
        tag.setPlot(plot)
    if year:
        tag.setYear(int(year))
    if rating:
        tag.setRating(float(rating), int(votes or 0), 'tmdb', True)
    if premiered:
        tag.setPremiered(premiered)
    return tag


def _apply_progress(tag, progress, resume_point=True):
    """Zhlédnuté označí fajfkou, rozkoukané pozicí (Kodi pak nabídne pokračování).

    `resume_point=False`: pozici si hlídá doplněk sám (díly seriálů - viz episode_item).
    """
    if not progress:
        return False
    if progress.get('watched'):
        tag.setPlaycount(1)
        return True
    if resume_point and progress.get('position') and progress.get('duration'):
        tag.setResumePoint(float(progress['position']), float(progress['duration']))
    return False


def format_time(seconds):
    """12:34 nebo 1:02:03."""
    seconds = int(seconds or 0)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return '%d:%02d:%02d' % (hours, minutes, secs) if hours else '%d:%02d' % (minutes, secs)


def _mark_entry(kind, tmdb_id, season, episode, watched):
    return (t('ctx_mark_unwatched') if watched else t('ctx_mark_watched'),
            'RunPlugin(%s)' % url_for('mark_watched', kind=kind, id=tmdb_id, season=season, episode=episode,
                                      value=0 if watched else 1))


_options = {}


def _option(name):
    """Hodnota přepínače z nastavení (během jednoho vykreslení se čte jen jednou)."""
    if name not in _options:
        _options[name] = kodi.setting_bool(name, True)
    return _options[name]


def _seasons_text(count):
    if count == 1:
        return t('seasons_1', count)
    return t('seasons_2', count) if 2 <= count <= 4 else t('seasons_5', count)


def langs_text(langs):
    """Jazyky streamů, např. „CZ, EN · tit. CZ“. Prázdné, když se neví nebo streamy nejsou."""
    if not langs or not langs.get('streams') or not _option('show_langs'):
        return ''
    parts = [', '.join(lang.upper() for lang in langs['audio']) or t('langs_unknown')]
    if langs['subs']:
        parts.append(t('langs_subs', ', '.join(lang.upper() for lang in langs['subs'])))
    return ' · '.join(parts)


def _title(media):
    """Název s rokem, hodnocením a délkou, např. „Počátek (2010)  84 % · 148 min“."""
    text = media['title']
    if media.get('year') and _option('show_year'):
        text += ' (%d)' % media['year']
    details = []
    if media.get('rating') and _option('show_rating'):
        details.append('%d %%' % round(float(media['rating']) * 10))
    if _option('show_runtime'):
        if media.get('runtime'):
            details.append(t('minutes', media['runtime']))
        elif media.get('seasons'):
            details.append(_seasons_text(media['seasons']))
    langs = langs_text(media.get('langs'))
    if langs:
        details.append(langs)
    if details:
        text += '  [COLOR gray]%s[/COLOR]' % ' · '.join(details)
    return text


def _explore_entries(kind, media):
    """Položky „Podobné tituly“, „Celá série“ a „Herci a tvůrci“."""
    tmdb_id = media['tmdb_id']
    entries = [(t('ctx_similar'), 'Container.Update(%s)' % url_for('list', kind=kind, cat='similar', ref=tmdb_id))]
    if kind == 'movie':
        series = media.get('collection_id')
        if series:
            entries.append((t('ctx_collection', media.get('collection_name') or ''),
                            'Container.Update(%s)' % url_for('collection', id=series)))
        elif series is None:
            # zatím nevíme, jestli film do nějaké série patří - zjistí se až po stisku
            entries.append((t('ctx_collection_unknown'), 'Container.Update(%s)' % url_for('collection', movie=tmdb_id)))
    entries.append((t('ctx_people'), 'Container.Update(%s)' % url_for('people', kind=kind, id=tmdb_id)))
    return entries


def _hide_entry(kind, media):
    return (t('ctx_hide'), 'RunPlugin(%s)' % url_for('hide', kind=kind, id=media['tmdb_id'], title=media['title']))


def movie_item(media, in_watchlist=False, label=None, extra_context=None, progress=None):
    """Film: přehratelná položka. Vrací (url, ListItem, is_folder)."""
    item = xbmcgui.ListItem(label or _title(media))
    _art(item, media.get('poster'), media.get('fanart'), fallback=ICON_MOVIES)
    tag = _tag(item, 'movie', media['title'], media.get('plot', ''), media.get('year'), media.get('rating'),
               media.get('votes'), media.get('premiered', ''), media.get('original_title', ''))
    tag.setUniqueID(str(media['tmdb_id']), 'tmdb', True)
    # délku vzhled Kodi vypisuje sám (jako 2:28); je-li už v názvu, podruhé ji neposíláme
    if media.get('runtime') and not (label is None and _option('show_runtime')):
        tag.setDuration(int(media['runtime']) * 60)
    item.setProperty('IsPlayable', 'true')
    watched = _apply_progress(tag, progress)

    tmdb_id = media['tmdb_id']
    context = [
        (t('ctx_watch_remove') if in_watchlist else t('ctx_watch_add'),
         'RunPlugin(%s)' % url_for('watch_toggle', kind='movie', id=tmdb_id)),
        _mark_entry('movie', tmdb_id, 0, 0, watched),
        (t('ctx_pick_stream'), 'PlayMedia(%s)' % url_for('play', kind='movie', id=tmdb_id, pick=1)),
        (t('ctx_manual_search'), 'Container.Update(%s)' % url_for('ws_search', q=media['title'])),
    ] + _explore_entries('movie', media) + [_hide_entry('movie', media)]
    item.addContextMenuItems(list(extra_context or []) + context)
    return url_for('play', kind='movie', id=tmdb_id), item, False


def show_item(media, followed=False, label=None, extra_context=None, counts=None):
    """Seriál: složka se sezónami. `counts` = (zhlédnuto dílů, celkem dílů)."""
    text = label or _title(media)
    if counts and counts[1]:
        text += '  [COLOR %s][%d/%d][/COLOR]' % ('lime' if counts[0] >= counts[1] else 'gray', counts[0], counts[1])
    item = xbmcgui.ListItem(text)
    _art(item, media.get('poster'), media.get('fanart'), fallback=ICON_SHOWS)
    tag = _tag(item, 'tvshow', media['title'], media.get('plot', ''), media.get('year'), media.get('rating'),
               media.get('votes'), media.get('premiered', ''), media.get('original_title', ''))
    tag.setUniqueID(str(media['tmdb_id']), 'tmdb', True)
    if counts and counts[1]:
        set_episode_counts(item, counts[0], counts[1])
    context = [
        (t('ctx_play_next'), 'RunPlugin(%s)' % url_for('play_next', id=media['tmdb_id'])),
        (t('ctx_follow_remove') if followed else t('ctx_follow_add'),
         'RunPlugin(%s)' % url_for('watch_toggle', kind='tv', id=media['tmdb_id'])),
    ] + _explore_entries('tv', media) + [_hide_entry('tv', media)]
    item.addContextMenuItems(list(extra_context or []) + context)
    return url_for('seasons', id=media['tmdb_id']), item, True


def set_episode_counts(item, watched, total):
    """Počty dílů pro vzhled Kodi (ukazatel zhlédnutých dílů u seriálu a sezóny)."""
    item.setProperty('TotalEpisodes', str(total))
    item.setProperty('WatchedEpisodes', str(watched))
    item.setProperty('UnWatchedEpisodes', str(max(total - watched, 0)))
    if total and watched >= total:
        item.getVideoInfoTag().setPlaycount(1)


def episode_item(show, season, episode, name='', plot='', thumb=None, air_date='', rating=0, runtime=0,
                 label=None, extra_context=None, progress=None, langs=None):
    """Díl seriálu. `langs` = dostupné jazyky streamů (viz availability).

    Díl záměrně NENÍ přehratelná položka (IsPlayable): Kodi pak doplněk jen spustí a nečeká
    na odkaz, takže doplněk může pustit playlist [díl, další díl] a v přehrávači funguje
    přeskočení na další díl. Pokračování od rozkoukaného místa nabízí doplněk sám (actions/play.py).
    """
    title = name or t('episode_n', episode)
    resume = progress and not progress.get('watched') and progress.get('position')
    if label is None:
        label = '%d. %s' % (episode, title)
        available = langs_text(langs)
        if available:
            label += '  [COLOR gray]%s[/COLOR]' % available
    if resume:
        # Kodi tu bod pokračování neukazuje (díl není přehratelná položka) - pozice je v názvu
        label += '  [COLOR yellow]%s[/COLOR]' % t('resume_mark', format_time(progress['position']))
    item = xbmcgui.ListItem(label)
    _art(item, show.get('poster'), show.get('fanart'), thumb=thumb, fallback=ICON_SHOWS)
    tag = _tag(item, 'episode', title, plot, 0, rating, 0, air_date)
    tag.setTvShowTitle(show.get('title', ''))
    tag.setSeason(int(season))
    tag.setEpisode(int(episode))
    if air_date:
        tag.setFirstAired(air_date)
    if runtime:
        tag.setDuration(int(runtime) * 60)
    watched = _apply_progress(tag, progress, resume_point=False)
    tmdb_id = show['tmdb_id']
    context = [
        _mark_entry('episode', tmdb_id, season, episode, watched),
        (t('ctx_pick_stream'),
         'RunPlugin(%s)' % url_for('play', kind='episode', id=tmdb_id, season=season, episode=episode, pick=1)),
        (t('ctx_manual_search'),
         'Container.Update(%s)' % url_for('ws_search', q='%s S%02dE%02d' % (show.get('title', ''), season, episode))),
    ]
    item.addContextMenuItems(list(extra_context or []) + context)
    return url_for('play', kind='episode', id=tmdb_id, season=season, episode=episode), item, False
