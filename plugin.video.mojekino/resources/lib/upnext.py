# -*- coding: utf-8 -*-
"""Spolupráce s doplňkem Up Next (service.upnext).

Up Next ke konci dílu ukáže okénko „Další díl za X s“ s obrázkem a tlačítky Přehrát / Zavřít.
Doplněk mu na začátku přehrávání pošle, jaký díl hraje, jaký následuje a adresu dalšího dílu
(`play_url`). Up Next si ji při zobrazení okénka sám zařadí do playlistu (při „Zavřít“ ji zase
odebere), takže další díl pak spustí Kodi přes doplněk jako každou jinou položku playlistu.

Ověřeno proti zdrojovému kódu Up Next 1.3.7. Důležité: má-li playlist další položku už ve chvíli,
kdy má okénko vyskočit, bere ji Up Next jako „cizí playlist“ a ve výchozím nastavení nenabídne
nic. Proto služba další díl těsně před okénkem z playlistu odebírá (viz service/tracker.py).
"""
import base64
import binascii
import json

import xbmc
import xbmcgui

from resources.lib import kodi

UPNEXT_ID = 'service.upnext'
PLAY_ACTION = '%s_play_action' % kodi.ADDON_ID
NOTIFY_TIME = 40                          # kolik sekund před koncem dílu má okénko vyskočit
DIALOG_PROPERTY = 'service.upnext.dialog'  # Up Next ji nastaví na hlavním okně, dokud je okénko vidět
HOME_WINDOW = 10000


def installed():
    return bool(xbmc.getCondVisibility('System.AddonIsEnabled(%s)' % UPNEXT_ID))


def active():
    """Má okénko dalšího dílu obsluhovat Up Next? (zapnuto v nastavení a Up Next je nainstalovaný)"""
    return kodi.setting_bool('use_upnext', True) and installed()


def dialog_open():
    """Je právě vidět okénko Up Next?"""
    return xbmcgui.Window(HOME_WINDOW).getProperty(DIALOG_PROPERTY) == 'true'


def _episode(show, ep, tmdb_id):
    art = {'thumb': ep.get('thumb') or show.get('fanart') or show.get('poster') or '',
           'tvshow.poster': show.get('poster') or '', 'tvshow.fanart': show.get('fanart') or ''}
    return {
        'episodeid': int(tmdb_id) * 10000 + int(ep['season']) * 1000 + int(ep['episode']),
        'tvshowid': int(tmdb_id),
        'title': ep.get('name') or kodi.t('episode_n', ep['episode']),
        'art': art,
        'season': int(ep['season']),
        'episode': int(ep['episode']),
        'showtitle': show.get('title', ''),
        'plot': ep.get('plot', ''),
        'playcount': 0,
        'rating': ep.get('rating') or 0,
        'firstaired': ep.get('air_date', ''),
        'runtime': int(ep.get('runtime') or 0) * 60,
    }


def payload(show, current, following, tmdb_id, play_url=''):
    """Data pro Up Next: hrající díl, následující díl a jak další díl spustit.

    `play_url` je adresa dalšího dílu v doplňku - Up Next ji zařadí do playlistu. `play_info`
    zůstává pro případ, že by Up Next adresu nepoužil a poslal zpět signál (zpracuje služba).
    """
    data = {
        'current_episode': _episode(show, current, tmdb_id),
        'next_episode': _episode(show, following, tmdb_id),
        'play_info': {'tmdb_id': int(tmdb_id), 'season': int(following['season']),
                      'episode': int(following['episode'])},
        'notification_time': NOTIFY_TIME,
    }
    if play_url:
        data['play_url'] = play_url
    return data


def send(data):
    """Pošle Up Next informace o dílech (volá služba, když přehrávání opravdu začalo)."""
    encoded = base64.b64encode(json.dumps(data).encode('utf-8')).decode('ascii')
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'JSONRPC.NotifyAll',
               'params': {'sender': '%s.SIGNAL' % kodi.ADDON_ID, 'message': 'upnext_data', 'data': [encoded]}}
    xbmc.executeJSONRPC(json.dumps(request))


def _decode(raw):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    for decoder in (base64.b64decode, binascii.unhexlify):
        try:
            result = json.loads(decoder(value).decode('utf-8'))
        except (TypeError, ValueError, binascii.Error, UnicodeDecodeError):
            continue
        if isinstance(result, dict):
            return result
    return None


def play_request(method, data):
    """Z oznámení Kodi vytáhne žádost Up Next o přehrání dalšího dílu: {'tmdb_id', 'season', 'episode'} nebo None."""
    if not method or not method.endswith(PLAY_ACTION):
        return None
    info = _decode(data)
    if not info:
        return None
    info = info.get('play_info', info)
    try:
        return {'tmdb_id': int(info['tmdb_id']), 'season': int(info['season']), 'episode': int(info['episode'])}
    except (KeyError, TypeError, ValueError):
        return None
