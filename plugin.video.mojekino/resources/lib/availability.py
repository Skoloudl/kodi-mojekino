# -*- coding: utf-8 -*-
"""Dostupné jazyky: v jakém zvuku a s jakými titulky má titul streamy.

Doplněk nemá server, který by to věděl předem. Proto se u poskytovatele zeptá na každý
titul zvlášť (souběžně, s časovým limitem) a výsledek si na pár dní zapamatuje.
Co se do limitu nestihne, doplní se při příštím otevření seznamu.

Čistý Python bez závislosti na Kodi.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from resources.lib import streams
from resources.lib.providers import ProviderError

WORKERS = 5                  # kolik dotazů u poskytovatele běží najednou
BUDGET = 10                  # kolik sekund smí zjišťování zdržet jeden seznam
TTL_FOUND = 3 * 24 * 3600    # jak dlouho věřit výsledku, když streamy jsou
TTL_EMPTY = 6 * 3600         # ...a když zatím nejsou (nové tituly přibývají rychle)
_ORDER = ('cz', 'sk', 'en')


def _sorted(langs):
    return sorted(langs, key=lambda lang: (_ORDER.index(lang) if lang in _ORDER else len(_ORDER), lang))


def summarize(found):
    """Ze seznamu kandidátů vrátí (jazyky zvuku, jazyky titulků, počet streamů)."""
    audio, subs = set(), set()
    for candidate in found:
        audio.update(candidate.info['audio'])
        subs.update(candidate.info['subs'])
    return _sorted(audio), _sorted(subs), len(found)


def _unpack(row):
    return {'audio': [x for x in (row['audio'] or '').split(',') if x],
            'subs': [x for x in (row['subs'] or '').split(',') if x],
            'streams': row['streams'] or 0}


def lookup(kind, wanted, provider, prefs, database, budget=BUDGET, clock=time.time):
    """Zjistí jazyky pro více titulů najednou.

    `wanted` = {klíč: (názvy, rok)}, kde klíč je (tmdb_id, řada, díl); u filmu a seriálu
    jsou řada i díl 0. Vrací {klíč: {'audio': [...], 'subs': [...], 'streams': počet}}
    pro tituly, o kterých už něco ví - ostatní ve výsledku chybí.
    """
    result, missing = {}, []
    stored = database.langs_get(kind, set(key[0] for key in wanted))
    current = clock()
    for key in wanted:
        row = stored.get(key)
        if row and current - (row['updated_at'] or 0) < (TTL_FOUND if row['streams'] else TTL_EMPTY):
            result[key] = _unpack(row)
        else:
            missing.append(key)
            if row:
                result[key] = _unpack(row)       # starý údaj je lepší než žádný
    if not missing or budget <= 0:
        return result

    searcher = provider.detached()               # vlákna nesmí sahat do databáze doplňku
    deadline = current + budget

    def probe(key):
        if clock() >= deadline:
            return None                          # nestihlo se - příště
        titles, year = wanted[key]
        try:
            if kind == 'movie':
                found = streams.probe_movie(searcher, titles, year, prefs)
            elif kind == 'tv':
                found = streams.probe_show(searcher, titles, prefs)
            else:
                found = streams.probe_episode(searcher, titles, key[1], key[2], prefs)
        except ProviderError:
            return None                          # výpadek sítě neukládáme jako „nic není“
        return summarize(found)

    if len(missing) == 1:
        answers = [probe(missing[0])]
    else:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            answers = list(pool.map(probe, missing))

    rows = []
    for key, answer in zip(missing, answers):
        if answer is None:
            continue
        audio, subs, count = answer
        rows.append((key[0], key[1], key[2], ','.join(audio), ','.join(subs), count))
        result[key] = {'audio': audio, 'subs': subs, 'streams': count}
    if rows:
        database.langs_set(kind, rows)
    return result


def fill(kind, items, provider, prefs, database, budget=BUDGET):
    """Doplní do slovníků media klíč `langs` (filmy a seriály v seznamu)."""
    wanted = {}
    for media in items:
        titles = [media.get('title'), media.get('original_title')]
        wanted[(media['tmdb_id'], 0, 0)] = ([x for x in titles if x], media.get('year') or 0)
    found = lookup(kind, wanted, provider, prefs, database, budget)
    for media in items:
        langs = found.get((media['tmdb_id'], 0, 0))
        if langs:
            media['langs'] = langs
    return items
