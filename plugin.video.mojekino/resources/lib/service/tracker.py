# -*- coding: utf-8 -*-
"""Sledování přehrávání: ukládá, kde jste skončili, a označuje zhlédnuté.

Doplněk při spuštění videa zapíše do vlastnosti hlavního okna, co pouští
(viz actions/play.py). Služba si to přečte a průběžně ukládá pozici.
"""
import json
import time

import xbmc
import xbmcgui

from resources.lib import context as ctx
from resources.lib import kodi, upnext
from resources.lib.actions.play import HOME_WINDOW, PLAYING_PROPERTY

WATCHED_RATIO = 0.90      # od kolika procent se titul počítá jako zhlédnutý
MIN_POSITION = 60         # kratší přehrání se jako rozkoukané neukládá (sekundy)
SAVE_EVERY = 30           # jak často ukládat pozici během přehrávání
MAX_START_DELAY = 180     # jak staré „právě spouštím“ ještě bereme vážně
END_GUARD = 20            # kolik sekund před koncem dílu rozhodnout, zda playlist smí pokračovat


def playlist_continues():
    """Smí Kodi po konci dílu samo přejít na další díl v playlistu?

    Jen když se má další díl spustit rovnou: zapnuté automatické přehrání, bez dotazu předem
    a bez okénka Up Next (ty spouští další díl přes službu).
    """
    return (kodi.setting_bool('autoplay_next', True) and not kodi.setting_bool('autoplay_ask', False)
            and not upnext.active())


class Tracker(xbmc.Player):
    def __init__(self):
        super(Tracker, self).__init__()
        self.current = None
        self.position = 0.0
        self.duration = 0.0
        self.saved_at = 0
        self.subs_due = 0          # kdy otevřít hledání titulků (0 = ne)
        self.finished_episode = None

    # ---- události přehrávače ----
    def onAVStarted(self):
        self._finish(ended=False)
        window = xbmcgui.Window(HOME_WINDOW)
        raw = window.getProperty(PLAYING_PROPERTY)
        window.clearProperty(PLAYING_PROPERTY)
        if not raw:
            return                       # hraje něco jiného než náš doplněk
        try:
            data = json.loads(raw)
        except ValueError:
            return
        if time.time() - int(data.get('started', 0)) > MAX_START_DELAY:
            return
        self.current = data
        self.position = self.duration = 0.0
        self.saved_at = time.time()
        self.subs_due = time.time() + 4 if data.get('subs') else 0
        kodi.debug('sleduji přehrávání: %s' % data)
        if data.get('upnext') and upnext.active() and kodi.setting_bool('autoplay_next', True):
            upnext.send(data['upnext'])

    def onPlayBackStopped(self):
        self._finish(ended=False)

    def onPlayBackError(self):
        self._finish(ended=False)

    def onPlayBackEnded(self):
        self._finish(ended=True)

    # ---- průběžné ukládání ----
    def poll(self):
        """Volá se každých pár sekund ze smyčky služby."""
        if not self.current:
            return
        try:
            if self.isPlayingVideo():
                self.position = float(self.getTime())
                self.duration = float(self.getTotalTime()) or self.duration
        except RuntimeError:
            return
        if self.subs_due and time.time() >= self.subs_due:
            self.subs_due = 0
            # okno Kodi pro stažení titulků (vyžaduje nainstalovaný doplněk pro titulky)
            xbmc.executebuiltin('ActivateWindow(SubtitleSearch)')
        if (self.current.get('next_url') and self.duration
                and self.duration - self.position <= END_GUARD and not playlist_continues()):
            # Další díl je v playlistu kvůli tlačítku „další“. Sám se ale spustit nemá (vypnuto,
            # dotaz předem, nebo okénko Up Next) - odebereme ho, než Kodi na konci dílu přejde dál.
            xbmc.PlayList(xbmc.PLAYLIST_VIDEO).remove(self.current['next_url'])
            self.current['next_url'] = ''
        if time.time() - self.saved_at >= SAVE_EVERY:
            self._save(ended=False)

    def _finish(self, ended):
        if self.current:
            self._save(ended)
            episode = self.current.get('kind') == 'episode'
            # další díl spustí buď playlist (je v něm), nebo Up Next, nebo služba (autoplay.offer)
            if (ended and episode and not self.current.get('next_url') and not upnext.active()
                    and kodi.setting_bool('autoplay_next', True)):
                self.finished_episode = dict(self.current)
        self.current = None
        self.subs_due = 0

    def pop_finished_episode(self):
        """Díl, který právě dohrál do konce (jednou), nebo None."""
        item, self.finished_episode = self.finished_episode, None
        return item

    def _save(self, ended):
        self.saved_at = time.time()
        item = self.current
        database = ctx.db()
        key = (item['kind'], int(item['tmdb_id']), int(item.get('season') or 0), int(item.get('episode') or 0))
        previous = database.progress_get(*key)
        ratio = self.position / self.duration if self.duration else 0
        if (ended and self.duration) or ratio >= WATCHED_RATIO:
            database.progress_set(*key, position=0, duration=self.duration, watched=True)
        elif self.position >= MIN_POSITION:
            # už dříve zhlédnutý titul zůstane zhlédnutý i při novém rozkoukání
            database.progress_set(*key, position=self.position, duration=self.duration,
                                  watched=bool(previous and previous['watched']))
