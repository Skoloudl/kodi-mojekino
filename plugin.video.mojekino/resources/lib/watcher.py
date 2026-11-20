# -*- coding: utf-8 -*-
"""Hlídač novinek: kontroluje filmy ze seznamu a nové díly sledovaných seriálů.

Čistý Python bez závislosti na Kodi. Volá ho služba na pozadí i položka
„Zkontrolovat nyní“.
"""
import datetime
import time

from resources.lib import streams
from resources.lib.db import now
from resources.lib.metadata import MetadataError
from resources.lib.providers import ProviderError

MAX_PENDING_PER_SHOW = 10     # kolik čekajících dílů jednoho seriálu zkusit za jeden běh
PENDING_MAX_AGE_DAYS = 120    # starší čekající díly se přestanou hlídat
PAUSE_SECONDS = 1.0           # pauza mezi dotazy, ať nezatěžujeme servery


class Watcher(object):
    def __init__(self, database, tmdb, provider, prefs, czsk_only=False,
                 should_stop=None, progress=None, sleep=time.sleep):
        self.db = database
        self.tmdb = tmdb
        self.provider = provider
        self.prefs = prefs
        self.czsk_only = czsk_only
        self.should_stop = should_stop or (lambda: False)
        self.progress = progress or (lambda done, total, title: None)
        self.sleep = sleep
        self.errors = 0

    def run(self):
        """Projde seznamy a vrátí nově nalezené položky jako seznam textů."""
        movies = [r for r in self.db.watch_list('movie') if not r['available_at']]
        shows = self.db.watch_list('tv') if self.tmdb.has_key else []
        total = len(movies) + len(shows)
        found, done = [], 0
        for row in movies:
            if self.should_stop():
                return found
            self.progress(done, total, row['title'])
            self._guard(self._check_movie, row, found)
            done += 1
        for row in shows:
            if self.should_stop():
                return found
            self.progress(done, total, row['title'])
            self._guard(self._check_show, row, found)
            done += 1
        self.progress(total, total, '')
        return found

    def _guard(self, func, row, found):
        try:
            func(row, found)
        except (ProviderError, MetadataError):
            self.errors += 1      # výpadek sítě apod. - zkusíme to při příští kontrole
        self.sleep(PAUSE_SECONDS)

    def _filter(self, candidates):
        if self.czsk_only:
            return [c for c in candidates if streams.has_czsk_audio(c.info)]
        return candidates

    def _titles(self, kind, row):
        if self.tmdb.has_key:
            try:
                return self.tmdb.titles(kind, row['tmdb_id'])[1]
            except MetadataError:
                pass
        return [t for t in (row['title'], row['original_title']) if t]

    # ---- filmy ----
    def _check_movie(self, row, found):
        candidates = self._filter(streams.find_movie(
            self.provider, self._titles('movie', row), row['year'] or 0, self.prefs))
        fields = {'checked_at': now()}
        if candidates:
            fields['available_at'] = now()
            if self.db.news_add('movie', row['tmdb_id'], row['title'], candidates[0].label,
                                row['poster'], row['fanart']):
                found.append(row['title'])
        self.db.watch_update('movie', row['tmdb_id'], **fields)

    # ---- seriály ----
    def _check_show(self, row, found):
        tmdb_id = row['tmdb_id']
        known = (row['last_season'] or 0, row['last_episode'] or 0)
        latest = self.tmdb.last_aired(tmdb_id, fresh=True)
        if latest > known:
            if known != (0, 0):
                for season in range(max(known[0], 1), latest[0] + 1):
                    for ep in self.tmdb.episodes(tmdb_id, season, fresh=True):
                        number = (ep['season'], ep['episode'])
                        if ep['aired'] and known < number <= latest:
                            self.db.pending_add(tmdb_id, ep['season'], ep['episode'], ep['name'], ep['air_date'])
            self.db.watch_update('tv', tmdb_id, last_season=latest[0], last_episode=latest[1])

        limit_date = (datetime.date.today() - datetime.timedelta(days=PENDING_MAX_AGE_DAYS)).isoformat()
        titles = None
        for ep in self.db.pending_list(tmdb_id)[:MAX_PENDING_PER_SHOW]:
            if self.should_stop():
                return
            if ep['air_date'] and ep['air_date'] < limit_date:
                self.db.pending_remove(tmdb_id, ep['season'], ep['episode'])
                continue
            if titles is None:
                titles = self._titles('tv', row)
            candidates = self._filter(streams.find_episode(
                self.provider, titles, ep['season'], ep['episode'], self.prefs))
            if candidates:
                subtitle = 'S%02dE%02d' % (ep['season'], ep['episode'])
                if ep['name']:
                    subtitle += ' · ' + ep['name']
                if self.db.news_add('episode', tmdb_id, row['title'], subtitle, row['poster'], row['fanart'],
                                    ep['season'], ep['episode']):
                    found.append('%s %s' % (row['title'], subtitle.split(' · ')[0]))
                self.db.pending_remove(tmdb_id, ep['season'], ep['episode'])
            self.sleep(PAUSE_SECONDS)
        self.db.watch_update('tv', tmdb_id, checked_at=now())
