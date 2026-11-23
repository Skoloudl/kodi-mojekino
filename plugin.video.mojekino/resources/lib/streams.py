# -*- coding: utf-8 -*-
"""Hledání streamů k titulu: dotazy na poskytovatele, kontrola shody a řazení.

Čistý Python bez závislosti na Kodi - používá ho menu i služba na pozadí.
"""
import difflib
import re
from concurrent.futures import ThreadPoolExecutor

from resources.lib import parser
from resources.lib.providers import NAMES, TRANSCODED, ProviderError, StreamFile

CACHE_TTL = 30 * 60
SEARCH_LIMIT = 60
PROBE_LIMIT = 40          # při zjišťování jazyků do seznamů stačí méně výsledků
_RE_YEAR = re.compile(r'\b(19[2-9]\d|20[0-4]\d)\b')
COLOR_CZSK = 'FF1CD6A4'       # barvy Kodi: AARRGGBB
PROVIDER_COLORS = {'webshare': 'FF40A0FF', 'sosac': 'FFFFA030', 'hellspy': 'FFFF6FB5', 'prehrajto': 'FFB48CFF'}


class Prefs(object):
    """Preference uživatele pro výběr streamu."""

    def __init__(self, language='cz', max_quality=0, hide_cam=True, min_size_mb=0):
        self.language = language          # 'cz' | 'en' | 'any'
        self.max_quality = max_quality    # 0 = bez omezení, jinak 720 / 1080 / 2160
        self.hide_cam = hide_cam
        self.min_size_mb = min_size_mb


class Candidate(object):
    def __init__(self, file, info, score):
        self.file = file
        self.info = info
        self.score = score

    @property
    def label(self):
        # u převáděného videa neříká velikost původního souboru o streamu nic
        text = describe(self.info, 0 if self.file.provider in TRANSCODED else self.file.size)
        if self.file.provider in NAMES:
            text += '  [COLOR gray]%s[/COLOR]' % NAMES[self.file.provider]
        return text

    # ---- řádek ve výběru streamu: obrázek kvality + dva řádky textu ----
    @property
    def badge(self):
        """Název obrázku se štítkem kvality (resources/media/<název>.png)."""
        quality = self.info['quality'] if self.info['quality'] in (2160, 1080, 720, 480) else 0
        extra = '_cam' if self.info['source'] == 'cam' else '_hdr' if self.info['hdr'] else '_3d' if self.info['3d'] else ''
        return 'q%d%s' % (quality, extra)

    @property
    def title(self):
        """První řádek: jazyky zvuku (český a slovenský zeleně), velikost a technické údaje."""
        info = self.info
        langs = []
        for lang in info['audio']:
            text = '[B]%s[/B]' % lang.upper()
            langs.append('[COLOR %s]%s[/COLOR]' % (COLOR_CZSK, text) if lang in ('cz', 'sk') else text)
        parts = [' '.join(langs) or '[COLOR gray]?[/COLOR]']
        if self.file.size and self.file.provider not in TRANSCODED:
            parts.append('[B]%s[/B]' % format_size(self.file.size))
        details = [info['codec'], 'HDR' if info['hdr'] else '', '3D' if info['3d'] else '', info['channels'],
                   'Atmos' if info['atmos'] else '', 'CAM' if info['source'] == 'cam' else '']
        if info['subs']:
            details.append('tit. ' + '+'.join(lang.upper() for lang in info['subs']))
        details = [d for d in details if d]
        if details:
            parts.append('[COLOR gray]%s[/COLOR]' % ' · '.join(details))
        return '  '.join(parts)

    @property
    def detail(self):
        """Druhý řádek: zdroj (barevně) a název souboru."""
        name = NAMES.get(self.file.provider)
        if not name:
            return self.file.name
        return '[COLOR %s]%s[/COLOR]  %s' % (PROVIDER_COLORS.get(self.file.provider, 'gray'), name, self.file.name)


# ---------------------------------------------------------------- shoda názvu
def _title_rest(norm_name, titles):
    """Když název souboru obsahuje některý z názvů titulu, vrátí zbytek názvu, jinak None."""
    padded = ' %s ' % norm_name
    best = None
    for title in titles:
        norm_title = parser.normalize(title)
        if not norm_title:
            continue
        needle = ' %s ' % norm_title
        if needle in padded:
            rest = padded.replace(needle, ' ', 1)
            if best is None or len(rest) < len(best):
                best = rest
    return best


def match_movie(info, titles, year):
    """Odpovídá soubor hledanému filmu? Vrátí None (ne) nebo postih ke skóre."""
    if info['episode']:
        return None
    rest = _title_rest(info['normalized'], titles)
    if rest is None:
        return None
    years = [int(y) for y in _RE_YEAR.findall(rest)]
    if year and years:
        return 0 if any(abs(y - year) <= 1 for y in years) else None
    # bez roku v názvu si nejsme jistí, že jde o správný film
    shortest = min(len(parser.normalize(t)) for t in titles if parser.normalize(t))
    if year and shortest <= 4:
        return None
    return 15


def match_episode(info, titles, season, episode):
    if info['episode'] != (season, episode):
        return None
    return 0 if _title_rest(info['normalized'], titles) is not None else None


# ---------------------------------------------------------------- hodnocení
def has_czsk_audio(info):
    return 'cz' in info['audio'] or 'sk' in info['audio']


def score(info, file, prefs):
    points = 0.0
    audio, subs = info['audio'], info['subs']
    if prefs.language == 'cz':
        if 'cz' in audio:
            points += 100
        elif 'sk' in audio:
            points += 85
        elif 'cz' in subs or 'sk' in subs:
            points += 45
        elif not audio:
            points += 15
    elif prefs.language == 'en':
        if 'en' in audio:
            points += 100
        elif not audio:
            points += 60      # bez označení bývá původní zvuk
        elif 'cz' in subs:
            points += 20

    quality = info['quality']
    points += {2160: 40, 1080: 30, 720: 20, 480: 5}.get(quality, 10)
    if prefs.max_quality and quality > prefs.max_quality:
        points -= 45
    if info['source'] == 'cam':
        points -= 80
    if info['3d']:
        points -= 30
    points += min(file.size / 1073741824.0, 15)
    points += min(file.positive, 10) - 3 * min(file.negative, 10)
    return points


def format_size(size):
    if size >= 1073741824:
        return ('%.1f GB' % (size / 1073741824.0)).replace('.', ',')
    return '%d MB' % (size // 1048576)


def describe(info, size):
    """Krátký popis streamu do výběru, např. „[CZ] 1080p · HEVC · 5.1 · 4,2 GB“."""
    langs = '+'.join(l.upper() for l in info['audio']) or '?'
    parts = ['[%s]' % langs]
    if info['subs']:
        parts.append('tit. ' + '+'.join(l.upper() for l in info['subs']))
    details = []
    details.append({2160: '4K', 1080: '1080p', 720: '720p', 480: 'SD'}.get(info['quality'], '?p'))
    if info['source'] == 'cam':
        details.append('CAM')
    if info['codec']:
        details.append(info['codec'])
    if info['hdr']:
        details.append('HDR')
    if info['3d']:
        details.append('3D')
    if info['channels']:
        details.append(info['channels'])
    if info['atmos']:
        details.append('Atmos')
    if size:
        details.append(format_size(size))
    return ' '.join(parts) + ' ' + ' · '.join(details)


_RE_EPISODE_TOKEN = re.compile(r'\bs\d{1,2} ?e\d{1,3}\b|\b\d{1,2}x\d{2,3}\b')


def _pattern(name):
    """Název souboru bez označení dílu - stejná série souborů má tento vzor skoro shodný."""
    return _RE_EPISODE_TOKEN.sub(' ', parser.normalize(parser.split_extension(name)[0]))


def order_like(found, like_name):
    """Seřadí kandidáty tak, aby první byl co nejpodobnější dříve přehranému souboru.

    Pořadí důležitosti: stejný jazyk zvuku, stejná kvalita, podobnost názvu, běžné skóre.
    """
    if not like_name:
        return found
    reference = parser.parse(like_name)
    pattern = _pattern(like_name)

    def key(candidate):
        info = candidate.info
        similarity = difflib.SequenceMatcher(None, _pattern(candidate.file.name), pattern).ratio()
        return (sorted(info['audio']) == sorted(reference['audio']),
                info['quality'] == reference['quality'],
                round(similarity, 1), candidate.score)
    return sorted(found, key=key, reverse=True)


# ---------------------------------------------------------------- hledání
def _search_all(provider, queries, cache, limit=SEARCH_LIMIT):
    """Spustí dotazy, sloučí výsledky bez duplicit. Výsledek krátce drží v cache."""
    key = 'streams:%s:%s' % (provider.id, '|'.join(queries))
    if cache is not None:
        cached = cache.cache_get(key)
        if cached is not None:
            return [StreamFile.from_dict(d) for d in cached]
    seen, files = set(), []
    for query in queries:
        found, _total = provider.search(query, limit=limit)
        for f in found:
            if f.ident not in seen:
                seen.add(f.ident)
                files.append(f)
    if cache is not None:
        cache.cache_set(key, [f.to_dict() for f in files], CACHE_TTL)
    return files


def _rank(files, matcher, prefs):
    result = []
    for f in files:
        if f.protected:
            continue
        info = parser.parse(f.name)
        if info['extension'] == '' and '.' in f.name and f.name.rsplit('.', 1)[1].lower() in ('rar', 'zip', '7z', 'srt', 'sub', 'nfo', 'txt', 'iso'):
            continue
        penalty = matcher(info)
        if penalty is None:
            continue
        cap = TRANSCODED.get(f.provider)
        if cap:
            # převedené video: kvalita nejvýš `cap`, H.264 bez HDR; o kousek pod původním souborem
            info = dict(info, quality=min(info['quality'] or cap, cap), codec='H264', hdr=False, atmos=False)
            penalty += 10
        if prefs.hide_cam and info['source'] == 'cam':
            continue
        if prefs.min_size_mb and f.size and f.size < prefs.min_size_mb * 1048576:
            continue                     # velikost 0 = neznámá (Sosáč), takový soubor nevyřazujeme
        sized = f if not cap else StreamFile(f.provider, f.ident, f.name, 0, f.positive, f.negative)
        result.append(Candidate(f, info, score(info, sized, prefs) - penalty))
    result.sort(key=lambda c: c.score, reverse=True)
    # stejný soubor bývá nahraný vícekrát - necháme jen nejlépe hodnocenou kopii
    unique, seen = [], set()
    for c in result:
        key = (c.file.name.lower(), c.file.size)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _movie_one(provider, titles, year, prefs, cache, imdb):
    matcher = lambda i: match_movie(i, titles, year)
    finder = getattr(provider, 'find', None)
    direct = finder('movie', titles, year, imdb=imdb) if finder else None
    if direct is not None:
        return _rank(direct, matcher, prefs)
    queries = [('%s %s' % (t, year)).strip() for t in titles]
    found = _rank(_search_all(provider, queries, cache), matcher, prefs)
    if len(found) < 3:
        # málo výsledků - zkusíme ještě hledat bez roku
        extra = _rank(_search_all(provider, titles, cache), matcher, prefs)
        known = set(c.file.ident for c in found)
        found += [c for c in extra if c.file.ident not in known]
        found.sort(key=lambda c: c.score, reverse=True)
    return found


def _episode_one(provider, titles, season, episode, prefs, cache, imdb, year):
    matcher = lambda i: match_episode(i, titles, season, episode)
    finder = getattr(provider, 'find', None)
    direct = finder('tv', titles, year, season, episode, imdb=imdb) if finder else None
    if direct is not None:
        return _rank(direct, matcher, prefs)
    queries = ['%s S%02dE%02d' % (t, season, episode) for t in titles]
    found = _rank(_search_all(provider, queries, cache), matcher, prefs)
    if not found:
        alt = ['%s %dx%02d' % (t, season, episode) for t in titles[:2]]
        found = _rank(_search_all(provider, alt, cache), matcher, prefs)
    return found


def _gather(providers, search, cache, errors=None):
    """Prohledá všechny poskytovatele a výsledky sloučí podle skóre.

    První poskytovatel (Webshare) běží v hlavním vlákně a smí používat cache v databázi,
    ostatní souběžně ve vedlejších vláknech bez ní. Výpadek vedlejšího zdroje hledání
    nezastaví; chyba hlavního se vyvolá, jen když nic nenašel nikdo jiný.
    Do `errors` (seznam) se zapíše (id zdroje, chyba) za každý zdroj, který neodpověděl.
    """
    if not isinstance(providers, (list, tuple)):
        providers = [providers]
    if not providers:
        return []
    primary, extras = providers[0], list(providers[1:])

    def run_extra(provider):
        try:
            return search(provider.detached(), None), None
        except Exception as e:       # vedlejší zdroj nesmí shodit hledání ostatních
            return [], (getattr(provider, 'id', '?'), e)

    pool = ThreadPoolExecutor(max_workers=len(extras)) if extras else None
    futures = [pool.submit(run_extra, p) for p in extras] if pool else []
    error, found = None, []
    try:
        found = search(primary, cache)
    except ProviderError as e:
        error = e
        if errors is not None:
            errors.append((getattr(primary, 'id', '?'), e))
    for future in futures:
        result, failure = future.result()
        found += result
        if failure and errors is not None:
            errors.append(failure)
    if pool:
        pool.shutdown(wait=False)
    if error and not found:
        if errors and errors[0][1] is error:
            del errors[0]             # chybu hlavního zdroje ohlásí volající sám (výjimka)
        raise error
    found.sort(key=lambda c: c.score, reverse=True)
    # HellSpy a Přehraj.to sdílí soubory - stejný soubor (název + velikost) necháme jen jednou
    unique, seen = [], set()
    for c in found:
        key = (c.file.name.lower(), c.file.size) if c.file.size else (c.file.provider, c.file.ident)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def find_movie(providers, titles, year, prefs, cache=None, imdb='', errors=None):
    """Streamy k filmu. `providers` = poskytovatel nebo seznam (první je hlavní)."""
    titles = [t for t in titles if t][:3]
    return _gather(providers, lambda p, c: _movie_one(p, titles, year, prefs, c, imdb), cache, errors)


def find_episode(providers, titles, season, episode, prefs, cache=None, imdb='', year=0, errors=None):
    titles = [t for t in titles if t][:3]
    return _gather(providers, lambda p, c: _episode_one(p, titles, season, episode, prefs, c, imdb, year), cache,
                   errors)


# ---------------------------------------------------------------- úsporné hledání pro seznamy
def _two(titles):
    """Nejvýš dva různé názvy (český a původní)."""
    unique = []
    for title in titles:
        if title and title.lower() not in [u.lower() for u in unique]:
            unique.append(title)
    return unique[:2]


def probe_movie(provider, titles, year, prefs):
    """Jaké streamy má film - s co nejméně dotazy (jen kvůli jazykům v seznamu)."""
    titles = _two(titles)
    if not titles:
        return []
    matcher = lambda info: match_movie(info, titles, year)
    queries = [('%s %s' % (title, year or '')).strip() for title in titles]
    found = _rank(_search_all(provider, queries, None, PROBE_LIMIT), matcher, prefs)
    if len(found) < 3 and year:
        # hledání s rokem občas vrací hlavně cizí soubory z téhož roku - zkusíme i bez něj
        known = set(c.file.ident for c in found)
        extra = _rank(_search_all(provider, titles, None, PROBE_LIMIT), matcher, prefs)
        found += [c for c in extra if c.file.ident not in known]
    return found


def probe_show(provider, titles, prefs):
    """Jaké streamy má seriál. Bere se první díl: bývá nahraný ve všech jazycích, ve kterých seriál je,
    a hledání podle samotného názvu seriálu vrací hlavně soubory bez označení jazyka."""
    return probe_episode(provider, titles, 1, 1, prefs)


def probe_episode(provider, titles, season, episode, prefs):
    titles = _two(titles)
    if not titles:
        return []
    queries = ['%s S%02dE%02d' % (title, season, episode) for title in titles]
    return _rank(_search_all(provider, queries, None, PROBE_LIMIT),
                 lambda info: match_episode(info, titles, season, episode), prefs)
