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
SUBS_CZ = ('cze', 'ces', 'cs', 'cz', 'czech', 'čeština', 'cestina')
SUBS_SK = ('slo', 'slk', 'sk', 'slovak', 'slovenčina', 'slovencina')
END_GUARD = 20            # kolik sekund před koncem dílu rozhodnout, zda playlist smí pokračovat
UPNEXT_HANDOVER = upnext.NOTIFY_TIME + 6   # kdy uvolnit playlist pro Up Next (těsně před jeho okénkem)
UPNEXT_FALLBACK = 8       # okénko se neukázalo - kolik sekund před koncem vrátit další díl do playlistu
UPNEXT_SEEK_BACK = 10     # o kolik se musí přetočit zpět, aby se další díl do playlistu vrátil


def next_mode():
    """Kdo po konci dílu spustí další díl.

      'off'      - nikdo (automatické přehrání je vypnuté)
      'upnext'   - okénko doplňku Up Next
      'ask'      - služba po vlastním dotazu s odpočtem
      'playlist' - Kodi samo přejde na další položku playlistu
    """
    if not kodi.setting_bool('autoplay_next', True):
        return 'off'
    if upnext.active():
        return 'upnext'
    if kodi.setting_bool('autoplay_ask', False):
        return 'ask'
    return 'playlist'


def _has_next(playlist):
    """Je v playlistu za právě hrající položkou ještě něco?"""
    return playlist.size() - 1 > max(playlist.getposition(), 0)


class Tracker(xbmc.Player):
    def __init__(self):
        super(Tracker, self).__init__()
        self.current = None
        self.position = 0.0
        self.duration = 0.0
        self.saved_at = 0
        self.subs_due = 0          # kdy otevřít hledání titulků (0 = ne)
        self.finished_episode = None
        self.upnext_shown = False  # okénko Up Next se u tohoto dílu ukázalo - dál rozhoduje ono
        self.handed = False        # další díl je z playlistu odebraný, aby ho mohl zařadit Up Next

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
        self.upnext_shown = self.handed = False
        kodi.debug('sleduji přehrávání: %s' % data)
        self._apply_subtitles(data)
        if data.get('upnext') and next_mode() == 'upnext':
            upnext.send(data['upnext'])

    def _apply_subtitles(self, data):
        """Titulky podle nastavení: Kodi (nic se nemění), zapnout české/slovenské, nebo vypnout.

        Týká se titulků, které jsou ve streamu jako samostatná stopa nebo v souboru. Titulky vpálené
        přímo do obrazu jsou součást videa a vypnout se nedají - ty žádný přehrávač neumí skrýt.
        """
        mode = kodi.setting_int('subs_mode', 0)
        if mode not in (1, 2):
            return
        try:
            if mode == 2:
                self.showSubtitles(False)
                return
            if data.get('czsk_audio'):
                return                                  # český nebo slovenský zvuk - titulky netřeba
            available = [str(name or '').lower() for name in self.getAvailableSubtitleStreams()]
            for names in (SUBS_CZ, SUBS_SK):
                for index, name in enumerate(available):
                    if name in names or any(name.startswith(n) for n in names if len(n) > 3):
                        self.setSubtitleStream(index)
                        self.showSubtitles(True)
                        self.subs_due = 0               # titulky už jsou, hledat nové netřeba
                        kodi.debug('zapnuty titulky ve streamu: %s' % name)
                        return
        except RuntimeError:
            kodi.debug('titulky se nepodařilo nastavit')

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
        if self.duration:
            self._guard_next(self.duration - self.position)
        if time.time() - self.saved_at >= SAVE_EVERY:
            self._save(ended=False)

    def _guard_next(self, remaining):
        """Hlídá další díl v playlistu podle toho, kdo ho má po konci dílu spustit (viz next_mode)."""
        mode = next_mode()
        if mode == 'upnext' and not self.upnext_shown and upnext.dialog_open():
            self.upnext_shown = True
            kodi.debug('Up Next ukázal okénko - další díl řídí on')
        url = self.current.get('next_url')
        if not url:
            return
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        if mode in ('off', 'ask'):
            # Další díl je v playlistu jen kvůli tlačítku „další“. Sám se spustit nemá (vypnuto, nebo
            # se služba nejdřív zeptá) - odebereme ho, než Kodi na konci dílu přejde dál.
            if remaining <= END_GUARD:
                playlist.remove(url)
                self.current['next_url'] = ''
            return
        if mode != 'upnext' or self.upnext_shown:
            return
        # Up Next nabídne další díl jen tehdy, když v playlistu žádný není (jinak ho má za cizí
        # playlist a mlčí). Těsně před jeho okénkem proto další díl odebereme a Up Next si ho zařadí
        # sám. Kdyby se okénko neukázalo (Up Next vypnutý, chyba), díl před koncem zase vrátíme,
        # aby se další díl spustil v každém případě.
        if not self.handed:
            if upnext.NOTIFY_TIME + 1 < remaining <= UPNEXT_HANDOVER:
                playlist.remove(url)
                self.handed = True
        elif ((remaining <= UPNEXT_FALLBACK or remaining > UPNEXT_HANDOVER + UPNEXT_SEEK_BACK)
              and not _has_next(playlist)):
            playlist.add(url)
            self.handed = False
            if remaining <= UPNEXT_FALLBACK:
                kodi.log('Up Next okénko neukázal - další díl spustí playlist')

    def _finish(self, ended):
        if self.current:
            self._save(ended)
            episode = self.current.get('kind') == 'episode'
            # Další díl spustí playlist (je-li v něm) nebo Up Next. Služba (autoplay.offer) ho spouští,
            # když v playlistu není: po dotazu, u dílu puštěného samostatně, nebo když se Up Next neozval.
            mode = next_mode()
            if (ended and episode and not self.current.get('next_url')
                    and (mode in ('ask', 'playlist') or (mode == 'upnext' and not self.upnext_shown))):
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
