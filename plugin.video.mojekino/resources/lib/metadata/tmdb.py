# -*- coding: utf-8 -*-
"""Katalog z The Movie Database (TMDB). Vyžaduje vlastní API klíč uživatele."""
import datetime
import time
from concurrent.futures import ThreadPoolExecutor

from resources.lib import http
from resources.lib.metadata import MetadataError

API = 'https://api.themoviedb.org/3'
IMG = 'https://image.tmdb.org/t/p/'

HOUR = 3600
DAY = 24 * HOUR
PEOPLE_LIMIT = 30           # kolik herců u titulu nabídnout
CREW_JOBS = ('Director', 'Screenplay', 'Writer', 'Creator')


def _year(date):
    try:
        return int((date or '')[:4])
    except ValueError:
        return 0


def _img(path, size):
    return (IMG + size + path) if path else None


def _days_ago(days):
    return (datetime.date.today() - datetime.timedelta(days=days)).isoformat()


def to_media(kind, raw):
    """Převede položku z TMDB na jednotný slovník media."""
    if kind == 'movie':
        title, original, date = raw.get('title'), raw.get('original_title'), raw.get('release_date')
    else:
        title, original, date = raw.get('name'), raw.get('original_name'), raw.get('first_air_date')
    return {
        'kind': kind,
        'tmdb_id': raw.get('id'),
        'title': title or original or '',
        'original_title': original or title or '',
        'year': _year(date),
        'premiered': date or '',
        'plot': raw.get('overview') or '',
        'poster': _img(raw.get('poster_path'), 'w500'),
        'fanart': _img(raw.get('backdrop_path'), 'w1280'),
        'rating': raw.get('vote_average') or 0,
        'votes': raw.get('vote_count') or 0,
        'language': raw.get('original_language') or '',
    }


class Tmdb(object):
    def __init__(self, api_key, cache, language='cs-CZ', include_adult=False, min_runtime=0):
        """`cache` má metody cache_info(key) a cache_set(key, value, ttl) - viz db.Database."""
        self._key = (api_key or '').strip()
        self._cache = cache
        self._language = language
        self._adult = include_adult
        self._min_runtime = min_runtime     # kratší filmy (v minutách) se v seznamech nezobrazují
        self._stamps = []      # časy načtení dat použitých při posledním volání listing()

    @property
    def has_key(self):
        return bool(self._key)

    @property
    def language(self):
        return self._language

    def _auth(self, query):
        """Doplní přihlášení k TMDB a vrátí hlavičky dotazu."""
        headers = {'Accept': 'application/json'}
        if self._key.startswith('eyJ'):      # dlouhý „API Read Access Token“
            headers['Authorization'] = 'Bearer ' + self._key
        else:                                 # krátký „API Key“
            query['api_key'] = self._key
        return headers

    def _get(self, path, params=None, ttl=3 * HOUR, language=None, fresh=False):
        if not self._key:
            raise MetadataError(MetadataError.NO_KEY)
        query = dict(params or {})
        query['language'] = language or self._language
        cache_key = 'tmdb:%s:%s' % (path, sorted(query.items()))
        cached = None if fresh else self._cache.cache_info(cache_key)
        if cached is not None:
            self._stamps.append(cached[1] - ttl)
            return cached[0]
        headers = self._auth(query)
        try:
            data = http.get_json(API + path, params=query, headers=headers)
        except http.HttpError as e:
            if e.status == 401:
                raise MetadataError(MetadataError.BAD_KEY)
            raise MetadataError(MetadataError.NETWORK, str(e))
        self._cache.cache_set(cache_key, data, ttl)
        self._stamps.append(int(time.time()))
        return data

    def check_key(self):
        """Ověří klíč (vyhodí MetadataError, když neplatí)."""
        self._get('/configuration', ttl=60, fresh=True)
        return True

    def _fetch_many(self, requests, workers=6):
        """Více dotazů souběžně, bez dočasné paměti. Výsledky ve stejném pořadí, None = dotaz selhal."""
        if not self._key:
            raise MetadataError(MetadataError.NO_KEY)

        def one(request):
            path, params = request
            query = dict(params, language=self._language)
            headers = self._auth(query)
            try:
                return http.get_json(API + path, params=query, headers=headers)
            except http.HttpError:
                return None
        if len(requests) <= 1:
            return [one(r) for r in requests]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(one, requests))

    def enrich(self, kind, items):
        """Doplní do slovníků media délku filmu (runtime) nebo počet řad a dílů seriálu.

        Údaje se ukládají natrvalo, takže se každý titul stahuje jen jednou
        (u seriálů se po týdnu obnoví, protože řady přibývají).
        """
        ids = [m['tmdb_id'] for m in items]
        known = self._cache.extras_get(kind, ids)
        limit = time.time() - 7 * DAY
        missing = [i for i in ids if i not in known
                   or (kind == 'tv' and (known[i]['updated_at'] or 0) < limit)
                   or (kind == 'movie' and known[i]['collection_id'] is None)]
        if missing:
            fetched = []
            for tmdb_id, raw in zip(missing, self._fetch_many([('/%s/%s' % (kind, i), {}) for i in missing])):
                if raw is None:
                    continue
                series = raw.get('belongs_to_collection') or {}
                fetched.append((tmdb_id, int(raw.get('runtime') or 0), int(raw.get('number_of_seasons') or 0),
                                int(raw.get('number_of_episodes') or 0), int(series.get('id') or 0),
                                series.get('name') or ''))
            if fetched:
                self._cache.extras_set(kind, fetched)
                known = self._cache.extras_get(kind, ids)
        for media in items:
            row = known.get(media['tmdb_id'])
            if row:
                media['runtime'], media['seasons'], media['episodes'] = row['runtime'], row['seasons'], row['episodes']
                if kind == 'movie' and row['collection_id'] is not None:
                    media['collection_id'], media['collection_name'] = row['collection_id'], row['collection_name']
        return items

    def catalog_pages(self, kind, numbers):
        """Stránky nejznámějších titulů pro abecední index.

        Vrací (seznam media, celkový počet stran, počet stránek, které se nepodařilo stáhnout).
        """
        params = {'sort_by': 'vote_count.desc', 'include_adult': 'false'}
        if kind == 'movie' and self._min_runtime:
            params['with_runtime.gte'] = self._min_runtime
        results = self._fetch_many([('/discover/' + kind, dict(params, page=n)) for n in numbers])
        if all(r is None for r in results):
            raise MetadataError(MetadataError.NETWORK)
        items, total, failed = [], 0, 0
        for data in results:
            if data is None:
                failed += 1
                continue
            total = min(int(data.get('total_pages') or 1), 500)
            items += [to_media(kind, raw) for raw in data.get('results', []) if raw.get('id')]
        return items, total, failed

    # ---- seznamy ----
    def _listing_request(self, kind, category, page, genre, query, ref=None):
        params = {'page': page}
        ttl = 3 * HOUR
        today = datetime.date.today().isoformat()
        if category == 'search':
            path = '/search/' + kind
            params['query'] = query or ''
            ttl = HOUR
        elif category == 'similar':        # doporučení k titulu `ref`
            path = '/%s/%s/recommendations' % (kind, ref)
            ttl = DAY
        elif category == 'similar_fallback':
            path = '/%s/%s/similar' % (kind, ref)
            ttl = DAY
        elif category == 'genre':
            path = '/discover/' + kind
            params.update({'with_genres': genre, 'sort_by': 'popularity.desc', 'vote_count.gte': 30})
        elif category == 'trending':
            path = '/trending/%s/week' % kind
        elif category == 'top':
            path = '/%s/top_rated' % kind
        elif category == 'new' and kind == 'movie':
            # filmy, které v posledních měsících vyšly digitálně nebo na disku
            path = '/discover/movie'
            params.update({'with_release_type': '4|5', 'release_date.gte': _days_ago(120),
                           'release_date.lte': today, 'sort_by': 'popularity.desc', 'vote_count.gte': 15})
        elif category == 'new':
            path = '/discover/tv'
            params.update({'first_air_date.gte': _days_ago(120), 'first_air_date.lte': today,
                           'sort_by': 'popularity.desc', 'vote_count.gte': 5})
        elif category == 'cinema':
            path = '/movie/now_playing'
            params['region'] = 'CZ'
        elif category == 'onair':
            path = '/tv/on_the_air'
        else:
            path = '/%s/popular' % kind
        if path.startswith(('/search/', '/discover/')):
            params['include_adult'] = 'true' if self._adult else 'false'
        if path == '/discover/movie' and self._min_runtime:
            params['with_runtime.gte'] = self._min_runtime
        return path, params, ttl

    def listing(self, kind, category, page=1, genre=None, query=None, per_page=1, fresh=False, ref=None):
        """Jedna stránka seznamu. Vrátí (seznam media, počet stran, čas načtení dat).

        TMDB vrací po 20 položkách; `per_page` říká, kolik takových dávek spojit do jedné stránky.
        `fresh=True` data načte znovu ze serveru místo z dočasné paměti.
        """
        per_page = max(1, int(per_page))
        first = (page - 1) * per_page + 1
        self._stamps = []
        items, seen, total = [], set(), first
        for tmdb_page in range(first, first + per_page):
            if tmdb_page > total:
                break
            path, params, ttl = self._listing_request(kind, category, tmdb_page, genre, query, ref)
            data = self._get(path, params, ttl=ttl, fresh=fresh)
            total = min(int(data.get('total_pages') or 1), 500)
            for raw in data.get('results', []):
                if raw.get('id') and raw['id'] not in seen:
                    seen.add(raw['id'])
                    items.append(to_media(kind, raw))
        pages = max(1, (total + per_page - 1) // per_page)
        if category == 'similar' and not items and page == 1:
            # TMDB k titulu nemá doporučení - zkusíme aspoň tituly podobné žánrem a klíčovými slovy
            return self.listing(kind, 'similar_fallback', page, genre, query, per_page, fresh, ref)
        return items, pages, (min(self._stamps) if self._stamps else None)

    # ---- filmové série ----
    def collection_of(self, movie_id):
        """Série, do které film patří, jako (číslo, název), nebo (0, '')."""
        series = self.detail('movie', movie_id).get('belongs_to_collection') or {}
        return int(series.get('id') or 0), series.get('name') or ''

    def collection(self, collection_id):
        """Vrátí (název série, filmy v pořadí podle data uvedení)."""
        data = self._get('/collection/%s' % collection_id, ttl=DAY)
        parts = [to_media('movie', raw) for raw in data.get('parts', []) if raw.get('id')]
        parts.sort(key=lambda m: m['premiered'] or '9999')       # neohlášené díly na konec
        return data.get('name') or '', parts

    # ---- obsazení a osoby ----
    def people(self, kind, tmdb_id):
        """Tvůrci a herci titulu: seznam slovníků {id, name, role, job, photo}; tvůrci první."""
        result, seen = [], set()

        def add(person, role, job):
            if person.get('id') and (person['id'], job) not in seen:
                seen.add((person['id'], job))
                result.append({'id': person['id'], 'name': person.get('name') or '', 'role': role or '', 'job': job,
                               'photo': _img(person.get('profile_path'), 'w185')})

        if kind == 'movie':
            data = self._get('/movie/%s/credits' % tmdb_id, ttl=7 * DAY)
            for person in data.get('crew', []):
                if person.get('job') == 'Director':
                    add(person, '', 'director')
            for person in data.get('crew', []):
                if person.get('job') in ('Screenplay', 'Writer'):
                    add(person, '', 'writer')
            for person in data.get('cast', [])[:PEOPLE_LIMIT]:
                add(person, person.get('character'), 'actor')
        else:
            for person in self.detail('tv', tmdb_id).get('created_by', []):
                add(person, '', 'creator')
            data = self._get('/tv/%s/aggregate_credits' % tmdb_id, ttl=7 * DAY)
            for person in data.get('cast', [])[:PEOPLE_LIMIT]:
                roles = person.get('roles') or [{}]
                add(person, roles[0].get('character'), 'actor')
        return result

    def person(self, person_id):
        """Vrátí (jméno, filmy, seriály) osoby; známější tituly první."""
        name = self._get('/person/%s' % person_id, ttl=30 * DAY).get('name') or ''
        result = {}
        for kind in ('movie', 'tv'):
            data = self._get('/person/%s/%s_credits' % (person_id, kind), ttl=7 * DAY)
            entries = list(data.get('cast', []))
            entries += [c for c in data.get('crew', []) if c.get('job') in CREW_JOBS]
            titles, seen = [], set()
            for raw in entries:
                if not raw.get('id') or raw['id'] in seen or (raw.get('adult') and not self._adult):
                    continue
                seen.add(raw['id'])
                titles.append(to_media(kind, raw))
            titles.sort(key=lambda m: m['votes'], reverse=True)
            result[kind] = titles
        return name, result['movie'], result['tv']

    def genres(self, kind):
        data = self._get('/genre/%s/list' % kind, ttl=7 * DAY)
        return [(g['id'], g['name']) for g in data.get('genres', [])]

    # ---- detaily ----
    def detail(self, kind, tmdb_id):
        return self._get('/%s/%s' % (kind, tmdb_id), ttl=12 * HOUR)

    def media(self, kind, tmdb_id):
        return to_media(kind, self.detail(kind, tmdb_id))

    def imdb_id(self, kind, tmdb_id):
        """Číslo titulu na IMDb (podle něj hledají doplňky pro titulky)."""
        if kind == 'movie':
            return self.detail('movie', tmdb_id).get('imdb_id') or ''
        return self._get('/tv/%s/external_ids' % tmdb_id, ttl=30 * DAY).get('imdb_id') or ''

    def episode_total(self, tmdb_id):
        return int(self.detail('tv', tmdb_id).get('number_of_episodes') or 0)

    def english_title(self, kind, tmdb_id):
        data = self._get('/%s/%s' % (kind, tmdb_id), ttl=7 * DAY, language='en-US')
        return data.get('title' if kind == 'movie' else 'name') or ''

    def titles(self, kind, tmdb_id):
        """Všechny názvy, pod kterými může být titul uložen (český, původní, anglický)."""
        media = self.media(kind, tmdb_id)
        names = [media['title'], media['original_title']]
        try:
            names.append(self.english_title(kind, tmdb_id))
        except MetadataError:
            pass
        unique = []
        for name in names:
            if name and name.lower() not in [u.lower() for u in unique]:
                unique.append(name)
        return media, unique

    def seasons(self, tmdb_id):
        """Vrátí (media seriálu, seznam sezón)."""
        raw = self.detail('tv', tmdb_id)
        show = to_media('tv', raw)
        seasons = []
        for s in raw.get('seasons', []):
            if not s.get('episode_count'):
                continue
            seasons.append({
                'season': s.get('season_number', 0),
                'name': s.get('name') or '',
                'episodes': s.get('episode_count', 0),
                'plot': s.get('overview') or '',
                'premiered': s.get('air_date') or '',
                'poster': _img(s.get('poster_path'), 'w500') or show['poster'],
            })
        return show, seasons

    def last_aired(self, tmdb_id, fresh=False):
        """Poslední odvysílaný díl jako (sezóna, díl) nebo (0, 0)."""
        raw = self._get('/tv/%s' % tmdb_id, ttl=12 * HOUR, fresh=fresh)
        last = raw.get('last_episode_to_air') or {}
        return int(last.get('season_number') or 0), int(last.get('episode_number') or 0)

    def episodes(self, tmdb_id, season, fresh=False):
        data = self._get('/tv/%s/season/%s' % (tmdb_id, season), ttl=6 * HOUR, fresh=fresh)
        today = datetime.date.today().isoformat()
        result = []
        for e in data.get('episodes', []):
            air = e.get('air_date') or ''
            result.append({
                'season': int(e.get('season_number') or season),
                'episode': int(e.get('episode_number') or 0),
                'name': e.get('name') or '',
                'plot': e.get('overview') or '',
                'air_date': air,
                'aired': bool(air) and air <= today,
                'thumb': _img(e.get('still_path'), 'w500'),
                'rating': e.get('vote_average') or 0,
                'runtime': e.get('runtime') or 0,
            })
        return result
