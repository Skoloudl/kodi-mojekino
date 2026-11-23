# -*- coding: utf-8 -*-
"""Pravidelné úlohy služby.

Každá úloha je záznam v seznamu JOBS: (název, funkce vracející interval v sekundách
nebo 0 = vypnuto, funkce úlohy). Novou úlohu stačí napsat a přidat do JOBS.
Úloha vrací True, když proběhla, a False, když se má zkusit znovu při dalším kole.
"""
import datetime

import xbmc

from resources.lib import context as ctx
from resources.lib import catalog, kodi
from resources.lib.actions.account import save_sosac_state, save_vip_state
from resources.lib.kodi import t
from resources.lib.metadata import MetadataError
from resources.lib.providers import ProviderError
from resources.lib.watcher import Watcher

HOUR = 3600


def vip_check(monitor):
    """Ověří účet a upozorní na neaktivní nebo končící VIP (nejvýš jednou denně)."""
    provider = ctx.provider()
    if not provider.is_logged_in():
        return True
    database = ctx.db()
    try:
        account = provider.account()
    except ProviderError as e:
        if e.code in (ProviderError.BAD_CREDENTIALS, ProviderError.NOT_LOGGED_IN):
            kodi.notify(t('err_session_expired_short'), is_error=True, time_ms=10000)
            return True
        return False           # síť není dostupná - zkusíme později
    save_vip_state(database, account)
    if not kodi.setting_bool('vip_notify', True):
        return True
    today = datetime.date.today().isoformat()
    if database.meta_get('vip_notice_day') == today:
        return True
    if not account.vip:
        kodi.notify(t('vip_inactive'), is_error=True, time_ms=12000)
        database.meta_set('vip_notice_day', today)
    elif account.vip_days <= kodi.setting_int('vip_warn_days', 7):
        kodi.notify(t('vip_expiring', account.vip_days), time_ms=12000)
        database.meta_set('vip_notice_day', today)
    return True


def sosac_check(monitor):
    """Ověří účet Streamuj.tv a upozorní na neaktivní nebo končící premium (nejvýš jednou denně)."""
    if not kodi.setting_bool('src_sosac', True):
        return True
    source = ctx.sosac()
    if not source.is_logged_in():
        return True
    database = ctx.db()
    try:
        account = source.account()
    except ProviderError as e:
        if e.code == ProviderError.BAD_CREDENTIALS:
            kodi.notify(t('sosac_session_bad'), is_error=True, time_ms=10000)
            return True
        return False           # síť není dostupná - zkusíme později
    save_sosac_state(database, account)
    if not account.known or not kodi.setting_bool('vip_notify', True):
        return True
    today = datetime.date.today().isoformat()
    if database.meta_get('sosac_notice_day') == today:
        return True
    if not account.vip:
        kodi.notify(t('premium_inactive'), is_error=True, time_ms=12000)
        database.meta_set('sosac_notice_day', today)
    elif account.vip_days is not None and account.vip_days <= kodi.setting_int('vip_warn_days', 7):
        kodi.notify(t('premium_expiring', account.vip_days), time_ms=12000)
        database.meta_set('sosac_notice_day', today)
    return True


def watcher(monitor):
    """Zkontroluje seznamy a oznámí nové filmy a díly."""
    if xbmc.Player().isPlayingVideo():
        return False           # během přehrávání nerušíme
    database = ctx.db()
    if not database.watch_list('movie') and not database.watch_list('tv'):
        return True
    job = Watcher(database, ctx.tmdb(), ctx.watch_providers(), ctx.prefs(),
                  czsk_only=kodi.setting_bool('watcher_czsk_only'),
                  should_stop=monitor.abortRequested,
                  sleep=lambda seconds: monitor.waitForAbort(seconds))
    found = job.run()
    kodi.debug('hlídač: nalezeno %d, chyb %d' % (len(found), job.errors))
    if found and kodi.setting_bool('watcher_notify', True):
        kodi.notify(found[0] if len(found) == 1 else t('news_found', len(found)), t('news_heading'), time_ms=10000)
    return True


def cleanup(monitor):
    ctx.db().cache_cleanup()
    return True


def catalog_refresh(monitor):
    """Sestaví nebo po týdnu obnoví abecední seznam (na pozadí, mimo přehrávání)."""
    tmdb = ctx.tmdb()
    if not tmdb.has_key or xbmc.Player().isPlayingVideo():
        return False
    database = ctx.db()
    for kind in ('movie', 'tv'):
        if monitor.abortRequested():
            return False
        if not catalog.is_stale(database, kind, tmdb.language):
            continue
        try:
            count = catalog.build(tmdb, database, kind, ctx.catalog_pages(), should_stop=monitor.abortRequested)
        except MetadataError:
            return False
        kodi.debug('abecední seznam %s: %d titulů' % (kind, count))
    return True


def _watcher_interval():
    if not kodi.setting_bool('watcher_enabled', True):
        return 0
    return max(1, kodi.setting_int('watcher_interval', 6)) * HOUR


JOBS = [
    ('vip', lambda: 12 * HOUR, vip_check),
    ('sosac', lambda: 12 * HOUR, sosac_check),
    ('watcher', _watcher_interval, watcher),
    ('cleanup', lambda: 24 * HOUR, cleanup),
    ('catalog', lambda: 12 * HOUR, catalog_refresh),
]
