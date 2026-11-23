# -*- coding: utf-8 -*-
"""Náhrada modulů Kodi (xbmc, xbmcgui...) pro testy mimo Kodi.

Zaznamenává, co doplněk „zobrazil“, aby se to dalo v testech ověřit.
"""
import os
import sys
import tempfile
import types

STATE = {
    'settings': {},        # hodnoty nastavení (texty)
    'items': [],           # položky posledního seznamu
    'content': None,
    'ended': None,         # výsledek endOfDirectory
    'resolved': None,      # (úspěch, cesta)
    'notifications': [],
    'dialogs': [],         # zobrazené ok/yesno
    'builtins': [],
    'answers': {'yesno': False, 'select': 0, 'input': [], 'numeric': '', 'cancel_progress': False},
    'resolved_item': None,
    'window': {},          # vlastnosti hlavního okna
    'player': {'playing': False, 'time': 0.0, 'total': 0.0},
    'clock': 0.0,          # o kolik sekund „poskočil čas“ (dotaz s automatickým zavřením)
    'visible': False,      # odpověď na xbmc.getCondVisibility (otevřené okno Kodi)
    'addons': set(),       # nainstalované a zapnuté doplňky (System.AddonIsEnabled)
    'playlist': [],        # playlist videí: (adresa, položka)
    'jsonrpc': [],         # odeslané požadavky JSON-RPC
    'profile': tempfile.mkdtemp(prefix='mojekino-test-'),
}


def reset():
    STATE.update(items=[], content=None, ended=None, resolved=None, notifications=[], dialogs=[], builtins=[],
                 direct=None, playlist_started=False, jsonrpc=[])


class _Tag(object):
    def __init__(self):
        self.values = {}

    def __getattr__(self, name):
        if not name.startswith('set'):
            raise AttributeError(name)

        def setter(*args, **kwargs):
            self.values[name[3:]] = args[0] if len(args) == 1 else args
        return setter


class ListItem(object):
    def __init__(self, label='', label2='', path=''):
        self.label, self.label2, self.path = label, label2, path
        self.art, self.props, self.context = {}, {}, []
        self.tag = _Tag()

    def getLabel(self):
        return self.label

    def setArt(self, art):
        self.art.update(art)

    def setProperty(self, key, value):
        self.props[key] = value

    def addContextMenuItems(self, items, replaceItems=False):
        self.context.extend(items)

    def getVideoInfoTag(self):
        return self.tag

    def setPath(self, path):
        self.path = path


class Dialog(object):
    def notification(self, heading, message, icon=None, time=5000, sound=True):
        STATE['notifications'].append(message)

    def ok(self, heading, message):
        STATE['dialogs'].append(('ok', message))
        return True

    def yesno(self, heading, message, **kwargs):
        STATE['dialogs'].append(('yesno', message))
        if kwargs.get('autoclose') and STATE['answers'].get('timeout'):
            STATE['clock'] += kwargs['autoclose'] / 1000.0      # okno viselo, dokud nevypršel čas
            return False
        return STATE['answers']['yesno']

    def select(self, heading, items, useDetails=False, **kwargs):
        STATE['dialogs'].append(('select', [getattr(i, 'label', i) for i in items]))
        STATE['select_items'] = list(items)
        if STATE['answers'].get('selects'):                   # postupné odpovědi (několik výběrů za sebou)
            return STATE['answers']['selects'].pop(0)
        return STATE['answers']['select']

    def contextmenu(self, items):
        STATE['dialogs'].append(('menu', list(items)))
        return STATE['answers'].get('menu', 0)

    def input(self, heading, defaultt='', type=0, option=0, autoclose=0):
        answers = STATE['answers']['input']
        return answers.pop(0) if answers else ''

    def numeric(self, type, heading, defaultt=''):
        return STATE['answers'].get('numeric', '')


class Window(object):
    def __init__(self, window_id=0):
        pass

    def setProperty(self, key, value):
        STATE['window'][key] = value

    def getProperty(self, key):
        return STATE['window'].get(key, '')

    def clearProperty(self, key):
        STATE['window'].pop(key, None)


class DialogProgress(object):
    def create(self, heading, message=''):
        STATE['dialogs'].append(('progress', message))

    def update(self, percent=0, message=''):
        pass

    def iscanceled(self):
        return STATE['answers'].get('cancel_progress', False)

    def close(self):
        pass


class DialogProgressBG(object):
    def create(self, heading, message=''):
        STATE['busy_shown'] = True

    def update(self, percent=0, heading='', message=''):
        pass

    def close(self):
        pass


class Addon(object):
    def __init__(self, id=None):
        pass

    def getSetting(self, key):
        return STATE['settings'].get(key, '')

    def getAddonInfo(self, key):
        return {'profile': STATE['profile'], 'version': '0.0.0-test', 'icon': 'icon.png'}.get(key, '')

    def getLocalizedString(self, number):
        return ''

    def openSettings(self):
        STATE['dialogs'].append(('settings', ''))


class Monitor(object):
    def abortRequested(self):
        return False

    def waitForAbort(self, timeout=0):
        return False


class Player(object):
    def isPlayingVideo(self):
        return STATE['player']['playing']

    def isPlaying(self):
        return STATE['player']['playing']

    def getTime(self):
        return STATE['player']['time']

    def getTotalTime(self):
        return STATE['player']['total']

    def showSubtitles(self, visible):
        STATE['subs_shown'] = visible

    def getAvailableSubtitleStreams(self):
        return list(STATE.get('subtitle_streams', []))

    def setSubtitleStream(self, index):
        STATE['subtitle_stream'] = index

    def play(self, item='', listitem=None):
        if isinstance(item, PlayList):
            STATE['playlist_started'] = True
            item = item.paths()[0] if item.paths() else ''
        STATE['resolved'] = (True, item)
        STATE['direct'] = item         # spuštěno přímo přehrávačem, ne přes seznam doplňku


class PlayList(object):
    """Jediný sdílený playlist videí (jako v Kodi)."""

    def __init__(self, playlist_id=1):
        pass

    @staticmethod
    def paths():
        return [path for path, _item in STATE['playlist']]

    def clear(self):
        del STATE['playlist'][:]

    def add(self, url, listitem=None, index=-1):
        STATE['playlist'].append((url, listitem))

    def remove(self, filename):
        STATE['playlist'][:] = [entry for entry in STATE['playlist'] if entry[0] != filename]

    def size(self):
        return len(STATE['playlist'])

    def getposition(self):
        return STATE.get('playlist_position', 0)


def _cond_visibility(condition):
    if condition.startswith('System.AddonIsEnabled('):
        return condition[len('System.AddonIsEnabled('):-1] in STATE['addons']
    return STATE['visible']


def install():
    xbmc = types.ModuleType('xbmc')
    xbmc.LOGINFO, xbmc.LOGERROR = 1, 3
    xbmc.log = lambda message, level=1: None
    xbmc.executebuiltin = lambda command: STATE['builtins'].append(command)
    xbmc.executeJSONRPC = lambda request: STATE['jsonrpc'].append(request) or '{}'
    xbmc.getCondVisibility = _cond_visibility
    xbmc.Monitor, xbmc.Player, xbmc.PlayList = Monitor, Player, PlayList
    xbmc.PLAYLIST_VIDEO = 1

    xbmcgui = types.ModuleType('xbmcgui')
    xbmcgui.ListItem, xbmcgui.Dialog, xbmcgui.DialogProgressBG = ListItem, Dialog, DialogProgressBG
    xbmcgui.Window, xbmcgui.DialogProgress = Window, DialogProgress
    xbmcgui.NOTIFICATION_ERROR = 'error'
    xbmcgui.INPUT_ALPHANUM, xbmcgui.ALPHANUM_HIDE_INPUT = 0, 2

    xbmcplugin = types.ModuleType('xbmcplugin')

    def add_items(handle, items, total=0):
        STATE['items'] = list(items)
        return True

    def end(handle, succeeded=True, updateListing=False, cacheToDisc=True):
        STATE['ended'] = succeeded

    def resolved(handle, succeeded, listitem):
        STATE['resolved'] = (succeeded, listitem.path)
        STATE['resolved_item'] = listitem

    xbmcplugin.addDirectoryItems = add_items
    xbmcplugin.setContent = lambda handle, content: STATE.__setitem__('content', content)
    xbmcplugin.endOfDirectory = end
    xbmcplugin.setResolvedUrl = resolved

    xbmcaddon = types.ModuleType('xbmcaddon')
    xbmcaddon.Addon = Addon

    xbmcvfs = types.ModuleType('xbmcvfs')
    xbmcvfs.translatePath = lambda path: path
    xbmcvfs.exists = os.path.exists
    xbmcvfs.mkdirs = lambda path: os.makedirs(path, exist_ok=True)

    for module in (xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs):
        sys.modules[module.__name__] = module
