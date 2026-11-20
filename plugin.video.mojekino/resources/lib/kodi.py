# -*- coding: utf-8 -*-
"""Tenká vrstva nad Kodi API: nastavení, texty, dialogy, logování."""
import sys
from urllib.parse import urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib import strings

ADDON_ID = 'plugin.video.mojekino'
BASE_URL = 'plugin://%s/' % ADDON_ID


def addon():
    # vždy nová instance - služba na pozadí tak vidí čerstvé hodnoty nastavení
    return xbmcaddon.Addon(ADDON_ID)


def version():
    return addon().getAddonInfo('version')


def icon():
    return addon().getAddonInfo('icon')


def profile_dir():
    path = xbmcvfs.translatePath(addon().getAddonInfo('profile'))
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)
    return path


def handle():
    try:
        return int(sys.argv[1])
    except (IndexError, ValueError):
        return -1


def url_for(action, **params):
    query = {'action': action}
    for key, value in params.items():
        if value is not None:
            query[key] = value
    return BASE_URL + '?' + urlencode(query)


# ---- nastavení ----
def setting(key, default=''):
    value = addon().getSetting(key)
    return value if value != '' else default


def setting_bool(key, default=False):
    value = addon().getSetting(key)
    if value == '':
        return default
    return value.lower() == 'true'


def setting_int(key, default=0):
    try:
        return int(float(addon().getSetting(key)))
    except (TypeError, ValueError):
        return default


def open_settings():
    addon().openSettings()


# ---- texty ----
def t(key, *args):
    """Přeložený text podle klíče ze strings.py (s českou zálohou, kdyby překlad chyběl)."""
    string_id, czech, _english = strings.STRINGS[key]
    text = addon().getLocalizedString(string_id) or czech
    if args:
        try:
            text = text.format(*args)
        except (IndexError, KeyError):
            pass
    return text


# ---- logování ----
def log(message, level=xbmc.LOGINFO):
    xbmc.log('[%s] %s' % (ADDON_ID, message), level)


def debug(message):
    if setting_bool('debug'):
        log(message, xbmc.LOGINFO)


def error(message):
    log(message, xbmc.LOGERROR)


# ---- dialogy ----
def notify(message, heading=None, is_error=False, time_ms=6000):
    kind = xbmcgui.NOTIFICATION_ERROR if is_error else icon()
    xbmcgui.Dialog().notification(heading or t('addon_name'), message, kind, time_ms)


def ok(message, heading=None):
    xbmcgui.Dialog().ok(heading or t('addon_name'), message)


def yesno(message, heading=None, yes=None, no=None):
    kwargs = {}
    if yes:
        kwargs['yeslabel'] = yes
    if no:
        kwargs['nolabel'] = no
    return xbmcgui.Dialog().yesno(heading or t('addon_name'), message, **kwargs)


def select(heading, items, use_details=False):
    return xbmcgui.Dialog().select(heading, items, useDetails=use_details)


def menu(items):
    """Krátká nabídka jako kontextové menu Kodi (např. Pokračovat / Od začátku). Vrací index nebo -1."""
    return xbmcgui.Dialog().contextmenu(items)


def keyboard(heading, default='', hidden=False):
    option = xbmcgui.ALPHANUM_HIDE_INPUT if hidden else 0
    return xbmcgui.Dialog().input(heading, default, type=xbmcgui.INPUT_ALPHANUM, option=option)


def number(heading):
    """Dotaz na číslo; vrátí int nebo 0 při zrušení."""
    try:
        return int(xbmcgui.Dialog().numeric(0, heading))
    except (TypeError, ValueError):
        return 0


def execute(command):
    xbmc.executebuiltin(command)


def refresh():
    xbmc.executebuiltin('Container.Refresh')


def go_to(url):
    xbmc.executebuiltin('Container.Update(%s)' % url)
