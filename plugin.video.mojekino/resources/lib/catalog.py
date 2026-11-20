# -*- coding: utf-8 -*-
"""Abecední seznam: vlastní index nejznámějších titulů uložený v databázi doplňku.

TMDB neumí vypsat tituly od zvoleného písmene, proto si doplněk jednou týdně stáhne
seznam nejznámějších filmů a seriálů (podle počtu hlasů) a abecedně je řadí sám.

Čistý Python bez závislosti na Kodi.
"""
from resources.lib import parser
from resources.lib.db import now

BATCH = 10                   # kolik stránek katalogu stahovat najednou
MAX_AGE = 7 * 24 * 3600      # po jaké době index obnovit


def sort_key(title):
    """Klíč pro řazení: malá písmena bez diakritiky a interpunkce."""
    return parser.normalize(title)


def letter_of(key):
    first = key[:1]
    return first if 'a' <= first <= 'z' else '#'


def is_stale(database, kind, language):
    """Je potřeba index (znovu) sestavit?"""
    if database.catalog_count(kind, include_hidden=True) == 0:
        return True
    if database.meta_get('catalog_lang_' + kind) != language:
        return True
    try:
        built = int(database.meta_get('catalog_built_' + kind, 0) or 0)
    except ValueError:
        built = 0
    return now() - built > MAX_AGE


def build(tmdb, database, kind, pages, progress=None, should_stop=None):
    """Stáhne `pages` stránek nejznámějších titulů a uloží je. Vrací počet titulů (0 = nezměněno)."""
    rows, seen = [], set()
    requested = failed = 0
    for start in range(1, pages + 1, BATCH):
        if should_stop and should_stop():
            return 0
        numbers = list(range(start, min(start + BATCH, pages + 1)))
        batch, total_pages, missing = tmdb.catalog_pages(kind, numbers)
        requested += len(numbers)
        failed += missing
        for media in batch:
            key = sort_key(media.get('title') or '')
            if not key or media['tmdb_id'] in seen:
                continue
            seen.add(media['tmdb_id'])
            rows.append(dict(media, sort_key=key, letter=letter_of(key)))
        if progress:
            progress(min(numbers[-1], pages), pages)
        if total_pages and numbers[-1] >= total_pages:
            break
    # při výpadku sítě si nenecháme přepsat dobrý index děravým
    if not rows or failed * 5 > requested:
        return 0
    database.catalog_replace(kind, rows)
    database.meta_set('catalog_built_' + kind, now())
    database.meta_set('catalog_lang_' + kind, tmdb.language)
    return len(rows)
