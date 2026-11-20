# -*- coding: utf-8 -*-
"""Pořadí dílů: který díl následuje a který je další k přehrání.

Čistý Python bez závislosti na Kodi - používá ho menu i služba na pozadí.
"""


def next_episode(tmdb, tmdb_id, season, episode):
    """Následující už odvysílaný díl po (season, episode), nebo None."""
    for ep in tmdb.episodes(tmdb_id, season):
        if ep['episode'] > episode and ep['aired']:
            return ep
    # v sezóně už nic není - zkusíme první díl další sezóny
    _show, seasons = tmdb.seasons(tmdb_id)
    later = sorted(s['season'] for s in seasons if s['season'] > season)
    if later:
        for ep in tmdb.episodes(tmdb_id, later[0]):
            if ep['aired']:
                return ep
    return None


def next_unwatched(tmdb, database, tmdb_id):
    """Další díl k přehrání: první nezhlédnutý po posledním zhlédnutém (jinak úplně první díl)."""
    progress = database.progress_episodes(tmdb_id)
    watched = set(key for key, row in progress.items() if row['watched'])
    season, episode = max(watched) if watched else (1, 0)
    for _ in range(500):                      # pojistka proti nekonečné smyčce
        ep = next_episode(tmdb, tmdb_id, season, episode)
        if ep is None:
            return None
        if (ep['season'], ep['episode']) not in watched:
            return ep
        season, episode = ep['season'], ep['episode']
    return None


def watched_in_season(progress, season):
    """Počet zhlédnutých dílů sezóny z mapy database.progress_episodes()."""
    return sum(1 for (s, _e), row in progress.items() if s == season and row['watched'])
