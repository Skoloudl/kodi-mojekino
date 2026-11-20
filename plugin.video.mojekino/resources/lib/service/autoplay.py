# -*- coding: utf-8 -*-
"""Automatické přehrání dalšího dílu po dokoukání - rovnou, nebo (podle nastavení) po dotazu.

Další díl si služba najde a spustí sama přes přehrávač. Záměrně se nevolá
PlayMedia(plugin://…): to by Kodi při hledání streamu drželo v čekacím okně a ve
spojení s vlastním oknem služby to na Raspberry Pi vedlo k zamrznutí celého Kodi.
"""
import time

import xbmc
import xbmcgui

from resources.lib import context as ctx
from resources.lib import kodi
from resources.lib.actions import play
from resources.lib.episodes import next_episode
from resources.lib.kodi import t
from resources.lib.metadata import MetadataError
from resources.lib.providers import ProviderError

COUNTDOWN = 10      # sekund, po kterých se dotaz sám potvrdí
SETTLE = 1          # po konci dílu necháme Kodi chvíli dokončit návrat z přehrávače
IDLE_WAIT = 8       # jak dlouho nejvýš čekat, než Kodi zavře svá okna
YES_BUTTON = getattr(xbmcgui, 'DLG_YESNO_YES_BTN', 11)

_BUSY = 'Window.IsActive(busydialog) | Window.IsActive(busydialognocancel) | System.HasActiveModalDialog'


def _now():
    return time.time()


def _playing():
    return xbmc.Player().isPlaying()


def _wait_idle(monitor):
    """Počká, až Kodi nic nespouští a nemá otevřené žádné okno. False = nerušit."""
    for _ in range(IDLE_WAIT):
        if _playing():
            return False             # uživatel (nebo Kodi samo) už pustil něco jiného
        if not xbmc.getCondVisibility(_BUSY):
            return True
        if monitor.waitForAbort(1):
            return False
    return False


def _ask(text):
    """Dotaz s tlačítky „Přehrát hned“ a „Zrušit“. Po uplynutí času platí „přehrát“."""
    dialog = xbmcgui.Dialog()
    message = '%s\n%s' % (text, t('autoplay_countdown', COUNTDOWN))
    labels = dict(nolabel=t('autoplay_cancel'), yeslabel=t('autoplay_now'), autoclose=COUNTDOWN * 1000)
    started = _now()
    try:
        answer = dialog.yesno(t('autoplay_heading'), message, defaultbutton=YES_BUTTON, **labels)
    except TypeError:                # starší Kodi neumí předvolit tlačítko
        answer = dialog.yesno(t('autoplay_heading'), message, **labels)
    if answer:
        return True
    # „ne“ vrací Kodi při zrušení i při vypršení času - rozlišíme je podle toho, jak dlouho okno viselo
    return _now() - started >= COUNTDOWN - 0.5


def offer(item, monitor):
    """`item` je díl, který právě skončil (slovník ze sledování přehrávání). True = spuštěn další."""
    tmdb_id = int(item['tmdb_id'])
    try:
        ep = next_episode(ctx.tmdb(), tmdb_id, int(item['season']), int(item['episode']))
    except MetadataError:
        return False
    if not ep:
        return False
    if monitor.waitForAbort(SETTLE) or not _wait_idle(monitor):
        return False

    text = '%s  S%02dE%02d' % (item.get('title', ''), ep['season'], ep['episode'])
    if ep.get('name'):
        text += ' · ' + ep['name']
    if kodi.setting_bool('autoplay_ask', False):
        if not _ask(text):
            return False
        # okno dotazu je teď zavřené; ještě ověříme, že se mezitím nezačalo hrát něco jiného
        if monitor.waitForAbort(0.5) or not _wait_idle(monitor):
            return False

    kodi.notify(text, t('autoplay_heading'), time_ms=5000)
    return _start(tmdb_id, ep['season'], ep['episode'])


def _start(tmdb_id, season, episode):
    try:
        return play.start_episode(tmdb_id, season, episode)
    except MetadataError:
        kodi.notify(t('err_tmdb_network'), is_error=True)
    except ProviderError as e:
        kodi.notify(play.provider_error_text(e), is_error=True)
    return False


def play_now(request):
    """Up Next žádá o přehrání dalšího dílu (uživatel zvolil Přehrát nebo vypršel odpočet)."""
    return _start(request['tmdb_id'], request['season'], request['episode'])
