# -*- coding: utf-8 -*-
"""Zdroje informací o filmech a seriálech.

Zbytek doplňku pracuje s jednotným slovníkem „media“:

    kind            'movie' | 'tv'
    tmdb_id         číslo titulu
    title           název v jazyce uživatele
    original_title  původní název
    year            rok (int nebo 0)
    plot, poster, fanart, rating, votes, premiered, language

Jiný zdroj (např. ČSFD) stačí napsat tak, aby vracel stejné slovníky.
"""


class MetadataError(Exception):
    NO_KEY = 'no_key'
    BAD_KEY = 'bad_key'
    NETWORK = 'network'

    def __init__(self, code, detail=''):
        super(MetadataError, self).__init__('%s %s' % (code, detail))
        self.code = code
        self.detail = detail
