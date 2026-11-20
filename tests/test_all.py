#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy doplňku mimo Kodi.

    python3 tests/test_all.py

Síť se nepoužívá: katalog i poskytovatel jsou nahrazeni atrapami.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'plugin.video.mojekino'))

import kodistubs  # noqa: E402

kodistubs.install()

from resources.lib import context as ctx  # noqa: E402
from resources.lib import catalog, episodes, parser, plugin, streams, ui  # noqa: E402
from resources.lib.db import Database  # noqa: E402
from resources.lib.md5crypt import md5crypt, webshare_password_hash  # noqa: E402
from resources.lib.providers import AccountInfo, ProviderError, StreamFile  # noqa: E402
from resources.lib.service import autoplay, jobs, runner  # noqa: E402
from resources.lib.service.tracker import Tracker  # noqa: E402
from resources.lib.watcher import Watcher  # noqa: E402

STATE = kodistubs.STATE
GB = 1073741824
REAL_EXTRA_PROVIDERS = ctx.extra_providers      # ScreenTests ji nahrazují atrapou bez sítě


# ------------------------------------------------------------------ atrapy
class FakeProvider(object):
    id = 'fake'
    name = 'Fake'

    def __init__(self):
        self.files = []
        self.logged = True
        self.vip = True
        self.vip_days = 100
        self.broken = set()
        self.queries = []

    def is_logged_in(self):
        return self.logged

    def account(self):
        return AccountInfo(self.logged, 'tester', self.vip, self.vip_days, '2030-01-01 00:00:00')

    def search(self, query, limit=50, offset=0, sort=''):
        self.queries.append(query)
        words = parser.normalize(query).split()
        hits = [f for f in self.files if all(w in parser.normalize(f.name).split() for w in words)]
        return hits[offset:offset + limit], len(hits)

    def detached(self):
        return self

    def resolve(self, ident):
        if ident in self.broken:
            raise ProviderError(ProviderError.NOT_FOUND)
        return 'https://example.invalid/stream/' + ident

    def add(self, ident, name, size=2 * GB):
        self.files.append(StreamFile('fake', ident, name, size))


class FakeTmdb(object):
    has_key = True
    language = 'cs-CZ'
    CATALOG = ['Avatar', 'Árie', 'Amélie z Montmartru', 'Batman začíná', '2001: Vesmírná odysea', 'Želvy Ninja',
               'Zelená míle', '(500) Days of Summer', 'Anděl Páně']

    def __init__(self):
        self.calls = []
        self.last = (1, 2)
        self.movie = {'kind': 'movie', 'tmdb_id': 10, 'title': 'Počátek', 'original_title': 'Inception',
                      'year': 2010, 'plot': 'Sen ve snu.', 'poster': 'p.jpg', 'fanart': 'f.jpg',
                      'rating': 8.4, 'votes': 100, 'premiered': '2010-07-15', 'language': 'en'}
        self.show = {'kind': 'tv', 'tmdb_id': 20, 'title': 'Testovací seriál', 'original_title': 'Test Show',
                     'year': 2020, 'plot': '', 'poster': None, 'fanart': None, 'rating': 7, 'votes': 5,
                     'premiered': '2020-01-01', 'language': 'en'}

    def listing(self, kind, category, page=1, genre=None, query=None, per_page=1, fresh=False, ref=None):
        self.calls.append({'page': page, 'per_page': per_page, 'fresh': fresh, 'cat': category, 'ref': ref})
        if kind == 'movie':
            # druhá položka je krátký film vedený na TMDB jako samostatný titul
            short = dict(self.movie, tmdb_id=11, title='TO: Příběh z Derry', original_title='A Story of Derry')
            return [dict(self.movie), short], 3, 1700000000
        return [dict(self.show)], 3, 1700000000

    def enrich(self, kind, items):
        for media in items:
            if kind == 'movie':
                media['runtime'] = 29 if media['tmdb_id'] == 11 else 148
                media['collection_id'] = 77 if media['tmdb_id'] in (10, 12) else 0
                media['collection_name'] = 'Sny' if media['collection_id'] else ''
            else:
                media['seasons'], media['episodes'] = 2, 3
        return items

    def collection_of(self, movie_id):
        return (77, 'Sny') if movie_id == 10 else (0, '')

    def collection(self, collection_id):
        return 'Sny', [dict(self.movie), dict(self.movie, tmdb_id=12, title='Počátek 2', year=2014),
                       dict(self.movie, tmdb_id=11, title='Počátek: krátký bonus', year=2011)]

    def people(self, kind, tmdb_id):
        if tmdb_id != 10:
            return []
        return [{'id': 50, 'name': 'Christopher Nolan', 'role': '', 'job': 'director', 'photo': None},
                {'id': 60, 'name': 'Leonardo DiCaprio', 'role': 'Cobb', 'job': 'actor', 'photo': 'leo.jpg'}]

    def person(self, person_id):
        movies = [dict(self.movie, tmdb_id=200 + i, title='Film %02d' % i) for i in range(45)]
        return 'Christopher Nolan', movies, [dict(self.show)]

    def catalog_pages(self, kind, numbers):
        self.catalog_calls = getattr(self, 'catalog_calls', 0) + 1
        if 1 not in numbers:
            return [], 1, 0
        items = [dict(self.movie if kind == 'movie' else self.show, tmdb_id=100 + i, title=title,
                      original_title=title) for i, title in enumerate(self.CATALOG)]
        return items, 1, 0

    def genres(self, kind):
        return [(28, 'Akční'), (35, 'Komedie')]

    def media(self, kind, tmdb_id):
        return dict(self.movie if kind == 'movie' else self.show)

    def titles(self, kind, tmdb_id):
        media = self.media(kind, tmdb_id)
        return media, [media['title'], media['original_title']]

    def seasons(self, tmdb_id):
        return dict(self.show), [{'season': 1, 'name': 'Řada 1', 'episodes': 3, 'plot': '', 'premiered': '',
                                  'poster': None}]

    def last_aired(self, tmdb_id, fresh=False):
        return self.last

    def imdb_id(self, kind, tmdb_id):
        return 'tt1375666' if kind == 'movie' else 'tt0000020'

    def episode_total(self, tmdb_id):
        return 3

    def episodes(self, tmdb_id, season, fresh=False):
        import datetime
        today = datetime.date.today()
        result = []
        for number in (1, 2, 3, 4):
            result.append({'season': season, 'episode': number, 'name': 'Díl %d' % number, 'plot': '',
                           'air_date': (today - datetime.timedelta(days=4 - number)).isoformat()
                           if number < 4 else '2999-01-01',
                           'aired': number < 4, 'thumb': None, 'rating': 0, 'runtime': 40})
        return result


def call(action, _handle='1', **params):
    """Spustí akci doplňku. `_handle='-1'` = Kodi na nic nečeká (RunPlugin, klik na díl seriálu)."""
    kodistubs.reset()
    ui._options.clear()            # v Kodi je každé vykreslení nový proces, nastavení se čte znovu
    query = '&'.join('%s=%s' % (k, v) for k, v in dict(params, action=action).items())
    sys.argv = ['plugin://plugin.video.mojekino/', _handle, '?' + query]
    plugin.run(sys.argv)
    return STATE


def labels():
    return [item.label for _url, item, _folder in STATE['items']]


# ------------------------------------------------------------------ testy jádra
class CoreTests(unittest.TestCase):
    def test_md5crypt_matches_openssl(self):
        self.assertEqual(md5crypt('tajneheslo', 'abcd1234'), '$1$abcd1234$GMGnUEcGza99LujtuR9Cd1')
        self.assertEqual(md5crypt('ž-ř dlouhé heslo k otestování 123', 'Xy'), '$1$Xy$fG1BtspFksPvmUxK/tQIu/')
        self.assertEqual(len(webshare_password_hash('x', 'abcd1234')), 40)

    def test_parser_quality_and_language(self):
        info = parser.parse('Pocatek-Inception-2010-Bluray-AAC.5.1-1080p.H.264-1920x800-cz dabing.m4v')
        self.assertEqual((info['quality'], info['codec'], info['channels']), (1080, 'H264', '5.1'))
        self.assertEqual(info['audio'], ['cz'])
        self.assertEqual(info['years'], [2010])
        info = parser.parse('Film.2019.2160p.UHD.HDR.x265.EN.CZ.titulky.mkv')
        self.assertEqual((info['quality'], info['codec'], info['hdr']), (2160, 'HEVC', True))
        self.assertIn('en', info['audio'])
        self.assertIn('cz', info['subs'])
        info = parser.parse('Počátek (2010)(CZ ENG)[1080pHD][Remux].mkv')
        self.assertEqual((info['quality'], info['audio']), (1080, ['cz', 'en']))
        self.assertEqual(parser.parse('Neco.2020.HDCAM.avi')['source'], 'cam')
        self.assertFalse(parser.parse('Neco.2020.HDRip.avi')['hdr'])

    def test_parser_episode(self):
        self.assertEqual(parser.parse('Serial.S03E05.720p.mkv')['episode'], (3, 5))
        self.assertEqual(parser.parse('Serial 3x05 cz.avi')['episode'], (3, 5))
        self.assertIsNone(parser.parse('Film 1920x1080 2015.mkv')['episode'])

    def test_language_words_in_title_are_ignored(self):
        info = parser.parse('Sen.En.Noci.2015.1080p.CZ.mkv')
        self.assertEqual(info['audio'], ['cz'])

    def test_match_movie(self):
        titles = ['Počátek', 'Inception']
        ok = parser.parse('Pocatek.2010.1080p.CZ.mkv')
        self.assertEqual(streams.match_movie(ok, titles, 2010), 0)
        self.assertIsNone(streams.match_movie(parser.parse('Pocatek.konce.2019.mkv'), titles, 2010))
        self.assertIsNone(streams.match_movie(parser.parse('Jiny.film.2010.mkv'), titles, 2010))
        self.assertIsNone(streams.match_movie(parser.parse('Inception.S01E01.mkv'), titles, 2010))
        # rok, který je součástí názvu, se nepočítá jako rok vydání
        self.assertEqual(streams.match_movie(parser.parse('Blade.Runner.2049.2017.mkv'), ['Blade Runner 2049'], 2017), 0)

    def test_ranking_prefers_czech_and_quality(self):
        provider = FakeProvider()
        provider.add('a', 'Inception.2010.720p.EN.mkv')
        provider.add('b', 'Pocatek.2010.1080p.CZ.dabing.mkv')
        provider.add('c', 'Pocatek.2010.HDCAM.CZ.mkv')
        provider.add('d', 'Pocatek.2010.2160p.CZ.mkv', 20 * GB)
        found = streams.find_movie(provider, ['Počátek', 'Inception'], 2010, streams.Prefs())
        self.assertEqual([c.file.ident for c in found], ['d', 'b', 'a'])       # CAM je skrytý
        limited = streams.find_movie(provider, ['Počátek', 'Inception'], 2010, streams.Prefs(max_quality=1080))
        self.assertEqual(limited[0].file.ident, 'b')
        english = streams.find_movie(provider, ['Počátek', 'Inception'], 2010, streams.Prefs(language='en'))
        self.assertEqual(english[0].file.ident, 'a')

    def test_order_like_prefers_same_language_and_quality(self):
        provider = FakeProvider()
        provider.add('big', 'Serial.S01E02.2160p.EN.HDR.mkv', 12 * GB)
        provider.add('cz720', 'Serial.S01E02.720p.CZ.mkv')
        provider.add('cz1080', 'Serial.S01E02.1080p.CZ.WEB-DL.x264-ABC.mkv')
        provider.add('cz1080b', 'Serial S01E02 FullHD 1080p CZ dabing.mkv')
        found = streams.find_episode(provider, ['Serial'], 1, 2, streams.Prefs(language='any'))
        self.assertEqual(found[0].file.ident, 'big')
        like = streams.order_like(found, 'Serial.S01E01.1080p.CZ.WEB-DL.x264-ABC.mkv')
        self.assertEqual(like[0].file.ident, 'cz1080')             # stejná série souborů
        self.assertEqual(like[1].file.ident, 'cz1080b')            # stejný jazyk i kvalita
        self.assertEqual(like[-1].file.ident, 'big')
        self.assertEqual(streams.order_like(found, ''), found)

    def test_duplicates_and_protected_are_dropped(self):
        provider = FakeProvider()
        provider.add('a', 'Pocatek.2010.1080p.CZ.mkv')
        provider.add('b', 'Pocatek.2010.1080p.CZ.mkv')
        provider.files.append(StreamFile('fake', 'c', 'Pocatek.2010.720p.CZ.mkv', 2 * GB, protected=True))
        found = streams.find_movie(provider, ['Počátek'], 2010, streams.Prefs())
        self.assertEqual(len(found), 1)

    def test_database_migrates_and_stores(self):
        path = os.path.join(STATE['profile'], 'unit.db')
        database = Database(path)
        database.meta_set('a', 1)
        database.cache_set('k', {'x': 1}, 60)
        database.close()
        database = Database(path)                       # druhé otevření nesmí nic rozbít
        self.assertEqual(database.meta_get('a'), '1')
        self.assertEqual(database.cache_get('k'), {'x': 1})
        database.cache_set('old', 1, -5)
        self.assertIsNone(database.cache_get('old'))
        self.assertTrue(database.news_add('movie', 1, 'Film'))
        self.assertFalse(database.news_add('movie', 1, 'Film'))      # stejná novinka jen jednou
        database.close()

    def test_database_upgrade_keeps_data(self):
        import sqlite3
        from resources.lib.db import MIGRATIONS
        path = os.path.join(STATE['profile'], 'old.db')
        old = sqlite3.connect(path)                     # databáze, jak ji vytvořila verze 0.1.0
        old.executescript(MIGRATIONS[0])
        old.execute('PRAGMA user_version = 1')
        old.execute("INSERT INTO meta (key, value) VALUES ('webshare_token', 'abc')")
        old.execute("INSERT INTO watchlist (kind, tmdb_id, title) VALUES ('movie', 5, 'Film')")
        old.commit()
        old.close()
        database = Database(path)
        self.assertEqual(database.meta_get('webshare_token'), 'abc')
        self.assertTrue(database.watch_has('movie', 5))
        database.progress_set('movie', 5, 0, 0, 120, 6000, False)
        self.assertEqual(database.progress_get('movie', 5)['position'], 120.0)
        database.close()


class TmdbClientTests(unittest.TestCase):
    """Skutečný klient TMDB s podvrženou sítí."""

    def setUp(self):
        from resources.lib import http
        from resources.lib.metadata.tmdb import Tmdb
        self.http = http
        self.real_get = http.get_json
        self.requests = []

        def fake_get(url, params=None, headers=None, timeout=15):
            path = url.split('/3', 1)[1]
            self.requests.append(dict(params, _path=path))
            if path.endswith('/recommendations'):
                found = [] if path.startswith('/movie/10/') else [{'id': 7, 'title': 'Doporučený'}]
                return {'results': found, 'total_pages': 1}
            if path.endswith('/similar'):
                return {'results': [{'id': 8, 'title': 'Podobný'}], 'total_pages': 1}
            if path.startswith('/collection/'):
                return {'name': 'Trilogie', 'parts': [
                    {'id': 3, 'title': 'Třetí', 'release_date': '2003-01-01'},
                    {'id': 1, 'title': 'První', 'release_date': '2001-01-01'},
                    {'id': 4, 'title': 'Chystaný', 'release_date': ''},
                    {'id': 2, 'title': 'Druhý', 'release_date': '2002-01-01'}]}
            if path.startswith('/movie/') and path.endswith('/credits'):
                return {'crew': [{'id': 51, 'name': 'Střihač', 'job': 'Editor'},
                                 {'id': 52, 'name': 'Scenárista', 'job': 'Screenplay'},
                                 {'id': 50, 'name': 'Režisér', 'job': 'Director'}],
                        'cast': [{'id': 60 + i, 'name': 'Herec %d' % i, 'character': 'Role %d' % i,
                                  'profile_path': '/h.jpg'} for i in range(40)]}
            if path.endswith('/aggregate_credits'):
                return {'cast': [{'id': 61, 'name': 'Herečka', 'roles': [{'character': 'Doktorka'}]}]}
            if path.startswith('/person/'):
                if path.endswith('/movie_credits'):
                    return {'cast': [{'id': 1, 'title': 'Malý', 'vote_count': 5},
                                     {'id': 2, 'title': 'Velký', 'vote_count': 900},
                                     {'id': 9, 'title': 'Pro dospělé', 'vote_count': 50, 'adult': True}],
                            'crew': [{'id': 2, 'title': 'Velký', 'job': 'Director', 'vote_count': 900},
                                     {'id': 3, 'title': 'Režírovaný', 'job': 'Director', 'vote_count': 100},
                                     {'id': 4, 'title': 'Jen produkce', 'job': 'Producer', 'vote_count': 999}]}
                if path.endswith('/tv_credits'):
                    return {'cast': [{'id': 30, 'name': 'Seriál', 'vote_count': 10}]}
                return {'name': 'Jan Novák'}
            if path.count('/') == 2 and path.rsplit('/', 1)[1].isdigit():     # detail titulu
                if path.endswith('/999'):
                    raise http.HttpError('HTTP 500', status=500)
                return {'runtime': 95, 'number_of_seasons': 3, 'number_of_episodes': 30,
                        'belongs_to_collection': {'id': 77, 'name': 'Trilogie'} if path.startswith('/movie/') else None,
                        'created_by': [{'id': 70, 'name': 'Tvůrce'}]}
            page = int(params['page'])
            results = [{'id': page * 100 + i, 'title': 'Film %d' % (page * 100 + i),
                        'release_date': '2020-01-01'} for i in range(20)]
            return {'results': results if page <= 7 else [], 'total_pages': 7}
        http.get_json = fake_get
        self.real_fake = fake_get
        self.Tmdb = Tmdb
        self.db = Database(':memory:')

    def tearDown(self):
        self.http.get_json = self.real_get

    def test_pages_are_merged(self):
        tmdb = self.Tmdb('key', self.db)
        items, pages, fetched = tmdb.listing('movie', 'popular', page=2, per_page=3)
        self.assertEqual(len(items), 60)
        self.assertEqual([r['page'] for r in self.requests], [4, 5, 6])
        self.assertEqual(pages, 3)                       # 7 dávek po třech = 3 stránky
        self.assertTrue(fetched)
        items, _pages, _fetched = tmdb.listing('movie', 'popular', page=3, per_page=3)
        self.assertEqual(len(items), 20)                 # poslední stránka je kratší, nic se nenačítá navíc
        self.assertEqual(len(self.requests), 4)

    def test_cache_and_refresh(self):
        tmdb = self.Tmdb('key', self.db)
        tmdb.listing('movie', 'popular', page=1, per_page=2)
        tmdb.listing('movie', 'popular', page=1, per_page=2)
        self.assertEqual(len(self.requests), 2)          # podruhé z dočasné paměti
        tmdb.listing('movie', 'popular', page=1, per_page=2, fresh=True)
        self.assertEqual(len(self.requests), 4)

    def test_enrich_fetches_each_title_once(self):
        tmdb = self.Tmdb('key', self.db)
        items = [{'tmdb_id': i, 'title': 'F%d' % i} for i in (1, 2, 3, 999)]
        tmdb.enrich('movie', items)
        self.assertEqual([m.get('runtime') for m in items], [95, 95, 95, None])   # 999 selhal, ostatní ne
        self.assertEqual(len(self.requests), 4)
        tmdb.enrich('movie', items[:3])
        self.assertEqual(len(self.requests), 4)                    # podruhé už z databáze
        shows = [{'tmdb_id': 5, 'title': 'S'}]
        tmdb.enrich('tv', shows)
        self.assertEqual((shows[0]['seasons'], shows[0]['episodes']), (3, 30))
        self.db.execute("UPDATE extras SET updated_at=1 WHERE kind='tv'")
        tmdb.enrich('tv', shows)                                   # u seriálu se po týdnu obnoví
        self.assertEqual(len(self.requests), 6)

    def test_short_films_filter_and_catalog_pages(self):
        tmdb = self.Tmdb('key', self.db, min_runtime=40)
        tmdb.listing('movie', 'new')
        self.assertEqual(self.requests[-1]['with_runtime.gte'], 40)
        tmdb.listing('tv', 'new')
        self.assertNotIn('with_runtime.gte', self.requests[-1])
        tmdb.listing('movie', 'popular')
        self.assertNotIn('with_runtime.gte', self.requests[-1])
        items, total, failed = tmdb.catalog_pages('movie', [1, 2, 3])
        self.assertEqual((len(items), total, failed), (60, 7, 0))
        self.assertEqual(self.requests[-1]['sort_by'], 'vote_count.desc')
        count = catalog.build(tmdb, self.db, 'movie', 20)
        self.assertEqual(count, 140)                               # 7 dostupných stránek po 20
        self.assertFalse(catalog.is_stale(self.db, 'movie', 'cs-CZ'))
        self.assertTrue(catalog.is_stale(self.db, 'movie', 'en-US'))      # jiný jazyk = sestavit znovu
        self.assertTrue(catalog.is_stale(self.db, 'tv', 'cs-CZ'))

    def test_catalog_survives_network_failure(self):
        tmdb = self.Tmdb('key', self.db)
        catalog.build(tmdb, self.db, 'movie', 7)

        def broken(url, params=None, headers=None, timeout=15):
            raise self.http.HttpError('timeout')
        self.http.get_json = broken
        with self.assertRaises(Exception):
            catalog.build(tmdb, self.db, 'movie', 7)
        self.assertEqual(self.db.catalog_count('movie'), 140)      # starý index zůstal
        # částečný výpadek (víc než pětina stránek) index také nepřepíše
        good = self.real_fake

        def flaky(url, params=None, headers=None, timeout=15):
            if int(params.get('page', 1)) % 2:
                raise self.http.HttpError('timeout')
            return good(url, params, headers, timeout)
        self.http.get_json = flaky
        self.assertEqual(catalog.build(tmdb, self.db, 'movie', 6), 0)
        self.assertEqual(self.db.catalog_count('movie'), 140)
        # menší, ale úplný index je v pořádku (např. po zmenšení seznamu v nastavení)
        self.http.get_json = good
        self.assertEqual(catalog.build(tmdb, self.db, 'movie', 2), 40)

    def test_similar_falls_back_when_no_recommendations(self):
        tmdb = self.Tmdb('key', self.db)
        items, _pages, _fetched = tmdb.listing('movie', 'similar', ref=5)
        self.assertEqual([m['title'] for m in items], ['Doporučený'])
        items, _pages, _fetched = tmdb.listing('movie', 'similar', ref=10)      # bez doporučení
        self.assertEqual([m['title'] for m in items], ['Podobný'])
        self.assertEqual(self.requests[-1]['_path'], '/movie/10/similar')

    def test_collection_people_and_person(self):
        tmdb = self.Tmdb('key', self.db)
        self.assertEqual(tmdb.collection_of(10), (77, 'Trilogie'))
        name, parts = tmdb.collection(77)
        self.assertEqual(name, 'Trilogie')
        self.assertEqual([m['title'] for m in parts], ['První', 'Druhý', 'Třetí', 'Chystaný'])
        people = tmdb.people('movie', 10)
        self.assertEqual([p['name'] for p in people[:3]], ['Režisér', 'Scenárista', 'Herec 0'])
        self.assertEqual((people[0]['job'], people[2]['role'], people[2]['photo'][-6:]), ('director', 'Role 0', '/h.jpg'))
        self.assertEqual(len(people), 2 + 30)                      # střihač ne, herců nejvýš 30
        people = tmdb.people('tv', 20)
        self.assertEqual([(p['name'], p['job'], p['role']) for p in people],
                         [('Tvůrce', 'creator', ''), ('Herečka', 'actor', 'Doktorka')])
        name, movies, shows = tmdb.person(5)
        self.assertEqual(name, 'Jan Novák')
        self.assertEqual([m['title'] for m in movies], ['Velký', 'Režírovaný', 'Malý'])   # známější první, bez duplicit
        self.assertEqual([m['title'] for m in shows], ['Seriál'])
        _name, movies, _shows = self.Tmdb('key', Database(':memory:'), include_adult=True).person(5)
        self.assertIn('Pro dospělé', [m['title'] for m in movies])

    def test_enrich_learns_collection_for_old_rows(self):
        tmdb = self.Tmdb('key', self.db)
        items = [{'tmdb_id': 1, 'title': 'F'}]
        tmdb.enrich('movie', items)
        self.assertEqual((items[0]['collection_id'], items[0]['collection_name']), (77, 'Trilogie'))
        # řádek uložený verzí 0.4.0 sérii neznal - při dalším zobrazení se doplní
        self.db.execute("UPDATE extras SET collection_id=NULL, collection_name=NULL")
        before = len(self.requests)
        fresh = [{'tmdb_id': 1, 'title': 'F'}]
        tmdb.enrich('movie', fresh)
        self.assertEqual(len(self.requests), before + 1)
        self.assertEqual(fresh[0]['collection_id'], 77)

    def test_adult_switch(self):
        self.Tmdb('key', self.db).listing('movie', 'search', query='x')
        self.assertEqual(self.requests[-1]['include_adult'], 'false')
        self.Tmdb('key', self.db, include_adult=True).listing('movie', 'genre', genre=18)
        self.assertEqual(self.requests[-1]['include_adult'], 'true')
        self.Tmdb('key', self.db).listing('movie', 'popular')
        self.assertNotIn('include_adult', self.requests[-1])


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(':memory:')
        self.tmdb = FakeTmdb()
        self.provider = FakeProvider()

    def watcher(self, **kwargs):
        return Watcher(self.db, self.tmdb, self.provider, streams.Prefs(), sleep=lambda s: None, **kwargs)

    def test_movie_is_reported_once_when_it_appears(self):
        self.db.watch_add(self.tmdb.movie)
        self.assertEqual(self.watcher().run(), [])
        self.provider.add('a', 'Pocatek.2010.1080p.CZ.mkv')
        self.assertEqual(self.watcher().run(), ['Počátek'])
        self.assertEqual(self.watcher().run(), [])
        self.assertEqual(self.db.news_unseen_count(), 1)

    def test_czsk_only_filter(self):
        self.db.watch_add(self.tmdb.movie)
        self.provider.add('a', 'Inception.2010.1080p.EN.mkv')
        self.assertEqual(self.watcher(czsk_only=True).run(), [])
        self.assertEqual(self.watcher().run(), ['Počátek'])

    def test_new_episodes_are_tracked_until_available(self):
        self.db.watch_add(self.tmdb.show, 1, 2)          # při přidání byl poslední díl S01E02
        self.assertEqual(self.watcher().run(), [])
        self.tmdb.last = (1, 3)                          # odvysílán nový díl, stream ještě není
        self.assertEqual(self.watcher().run(), [])
        self.assertEqual(len(self.db.pending_list(20)), 1)
        self.provider.add('e3', 'Test.Show.S01E03.1080p.CZ.mkv')
        self.assertEqual(self.watcher().run(), ['Testovací seriál S01E03'])
        self.assertEqual(self.db.pending_list(20), [])
        self.assertEqual(self.watcher().run(), [])

    def test_network_errors_do_not_stop_the_run(self):
        self.db.watch_add(self.tmdb.movie)

        def broken(query, limit=50, offset=0, sort=''):
            raise ProviderError(ProviderError.NETWORK)
        self.provider.search = broken
        job = self.watcher()
        self.assertEqual(job.run(), [])
        self.assertEqual(job.errors, 1)


# ------------------------------------------------------------------ test obrazovek
class ScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmdb = FakeTmdb()
        cls.provider = FakeProvider()
        cls.provider.add('m1', 'Pocatek.2010.1080p.CZ.mkv')
        cls.provider.add('m2', 'Inception.2010.720p.EN.mkv')
        cls.provider.add('e1', 'Test.Show.S01E01.1080p.CZ.mkv')
        cls.provider.add('e2a', 'Test.Show.S01E02.2160p.EN.GROUP.mkv', 9 * GB)
        cls.provider.add('e2b', 'Test.Show.S01E02.1080p.CZ.mkv')
        ctx.tmdb = lambda: cls.tmdb
        ctx.provider = lambda: cls.provider
        ctx.extra_providers = lambda: []            # další zdroje (síť) se zkouší zvlášť

    def setUp(self):
        # jazyky v seznamech se zkouší zvlášť (jinak by každý seznam hledal streamy)
        STATE['settings'] = {'tmdb_api_key': 'x', 'show_langs': 'false'}
        STATE['answers'] = {'yesno': False, 'select': 0, 'input': [], 'numeric': '', 'cancel_progress': False}
        STATE['window'].clear()
        STATE['player'].update(playing=False, time=0.0, total=0.0)
        self.provider.logged = True
        self.provider.broken = set()

    def test_menus_render(self):
        for action, minimum in (('root', 6), ('movies', 6), ('shows', 6), ('my', 4), ('search', 3)):
            call(action)
            self.assertTrue(STATE['ended'], action)
            self.assertGreaterEqual(len(STATE['items']), minimum, action)
        call('root')
        self.assertIn('verze 0.0.0-test', labels()[-1])            # verze je vidět v hlavním menu

    def test_catalogue(self):
        call('list', kind='movie', cat='popular')
        self.assertEqual(STATE['content'], 'movies')
        self.assertIn('Strana 1 z 3', labels()[0])               # řádek s číslem strany a časem načtení
        self.assertIn('načteno', labels()[0])
        self.assertEqual(labels()[1], 'Počátek (2010)  [COLOR gray]84 % · 148 min[/COLOR]')   # rok, hodnocení, délka
        self.assertFalse(any('Derry' in label for label in labels()))   # krátký film se neukazuje
        self.assertIsNone(STATE['items'][1][1].tag.values.get('Duration'))   # délka je už v názvu
        self.assertIn('Přejít na stranu', labels()[-1])           # skok na stranu je i dole
        self.assertIn('2/3', labels()[-2])                       # odkaz na další stranu
        self.assertEqual(self.tmdb.calls[-1]['per_page'], 2)     # výchozí velikost stránky = 40 položek
        url, item, folder = STATE['items'][1]
        self.assertFalse(folder)
        self.assertEqual(item.props.get('IsPlayable'), 'true')
        call('list', kind='tv', cat='popular')
        self.assertTrue(STATE['items'][1][2])
        self.assertEqual(labels()[1], 'Testovací seriál (2020)  [COLOR gray]70 % · 2 řady[/COLOR]')
        STATE['settings'].update(show_year='false', show_runtime='false', show_rating='false', hide_shorts='false')
        call('list', kind='movie', cat='popular')
        self.assertEqual(labels()[1:3], ['Počátek', 'TO: Příběh z Derry'])   # vše vypnuto = jen názvy, i krátké
        STATE['settings'] = {'tmdb_api_key': 'x'}
        call('genres', kind='movie')
        self.assertEqual(labels(), ['Akční', 'Komedie'])
        call('seasons', id=20)
        self.assertEqual(STATE['content'], 'seasons')
        call('episodes', id=20, season=1)
        self.assertEqual(len(STATE['items']), 4)
        self.assertNotIn('IsPlayable', STATE['items'][3][1].props)   # neodvysílaný díl nejde přehrát

    def test_play_movie_with_dialog(self):
        STATE['answers']['select'] = 1
        call('play', kind='movie', id=10)
        self.assertEqual(STATE['resolved'], (True, 'https://example.invalid/stream/m2'))
        call('history')
        self.assertIn('Počátek', labels()[0])

    def test_play_auto_select_skips_missing_file(self):
        STATE['settings']['auto_select'] = 'true'
        self.provider.broken = {'m1'}
        call('play', kind='movie', id=10)
        self.assertEqual(STATE['resolved'], (True, 'https://example.invalid/stream/m2'))

    def test_play_episode_and_cancel(self):
        call('play', kind='episode', id=20, season=1, episode=1)
        self.assertEqual(STATE['resolved'], (True, 'https://example.invalid/stream/e1'))
        STATE['answers']['select'] = -1
        call('play', kind='episode', id=20, season=1, episode=1)
        self.assertEqual(STATE['resolved'][0], False)

    def test_play_without_streams_or_login(self):
        call('play', kind='episode', id=20, season=1, episode=3)
        self.assertEqual(STATE['resolved'][0], False)
        self.assertEqual(STATE['dialogs'][0][0], 'yesno')
        self.provider.logged = False
        call('play', kind='movie', id=10)
        self.assertEqual(STATE['resolved'][0], False)

    def test_lists_and_check_now(self):
        database = ctx.db()
        database.watch_remove('movie', 10)
        database.news_remove()
        call('watch_toggle', kind='movie', id=10)
        self.assertTrue(database.watch_has('movie', 10))
        call('my_list', kind='movie')
        self.assertEqual(len(STATE['items']), 1)
        call('check_now')
        self.assertEqual(STATE['notifications'][-1], 'Počátek')
        call('news')
        self.assertIn('Počátek', labels()[0])
        self.assertEqual(database.news_unseen_count(), 0)
        call('watch_toggle', kind='movie', id=10)
        self.assertFalse(database.watch_has('movie', 10))
        call('watch_toggle', kind='tv', id=20)
        self.assertEqual(database.watch_list('tv')[0]['last_episode'], 2)
        call('my_list', kind='tv')
        self.assertTrue(STATE['items'][0][2])
        call('watch_toggle', kind='tv', id=20)

    def test_search_and_manual_search(self):
        STATE['answers']['input'] = ['pocatek']
        call('search_new', kind='movie')
        self.assertIn('cat=search', STATE['builtins'][-1])
        call('search')
        self.assertTrue(any('pocatek' in label for label in labels()))
        call('ws_search', q='pocatek')
        self.assertEqual(len(STATE['items']), 1)
        call('play_file', ident='m1', name='x')
        self.assertEqual(STATE['resolved'], (True, 'https://example.invalid/stream/m1'))

    def test_account_dialog_and_missing_key(self):
        call('account')
        self.assertIn('VIP: aktivní', STATE['dialogs'][0][1])
        self.assertIn('Zbývá dní: 100', STATE['dialogs'][0][1])
        STATE['settings'] = {}
        real = ctx.tmdb
        try:
            from resources.lib.metadata.tmdb import Tmdb
            ctx.tmdb = lambda: Tmdb('', ctx.db())
            call('list', kind='movie', cat='popular')
            self.assertEqual(STATE['ended'], False)
            self.assertEqual(STATE['dialogs'][0][0], 'ok')        # návod, jak získat klíč
        finally:
            ctx.tmdb = real

    def test_list_navigation(self):
        STATE['answers'].update(select=0, numeric='3')            # „Přejít na stranu…“ -> 3
        call('list_nav', kind='movie', cat='popular', page=1, pages=3)
        self.assertIn('page=3', STATE['builtins'][-1])
        STATE['answers'].update(select=0, numeric='99')           # mimo rozsah -> poslední strana
        call('list_nav', kind='movie', cat='popular', page=1, pages=3)
        self.assertIn('page=3', STATE['builtins'][-1])
        STATE['answers'].update(select=0, numeric='')             # zrušeno -> nic
        call('list_nav', kind='movie', cat='popular', page=1, pages=3)
        self.assertEqual(STATE['builtins'], [])
        STATE['answers']['select'] = 1                            # „Načíst seznam znovu“
        call('list_nav', kind='movie', cat='popular', page=2, pages=3)
        self.assertTrue(self.tmdb.calls[-1]['fresh'])
        self.assertEqual(STATE['builtins'][-1], 'Container.Refresh')
        STATE['settings']['page_size'] = '3'                      # 100 položek = 5 dávek
        call('list', kind='movie', cat='popular')
        self.assertEqual(self.tmdb.calls[-1]['per_page'], 5)

    def test_watched_marks_and_manual_toggle(self):
        database = ctx.db()
        call('mark_watched', kind='movie', id=10, value=1)
        call('list', kind='movie', cat='popular')
        item = STATE['items'][1][1]
        self.assertEqual(item.tag.values.get('Playcount'), 1)
        self.assertTrue(any('nezhlédnuté' in label for label, _cmd in item.context))
        call('mark_watched', kind='movie', id=10, value=0)
        call('list', kind='movie', cat='popular')
        self.assertNotIn('Playcount', STATE['items'][1][1].tag.values)
        self.assertIsNone(database.progress_get('movie', 10))

    def test_tracker_saves_position_and_watched(self):
        database = ctx.db()
        database.progress_mark('episode', 20, 1, 1, False)
        tracker = Tracker()
        call('play', kind='episode', id=20, season=1, episode=1)
        self.assertIn('mojekino.playing', STATE['window'])
        tracker.onAVStarted()
        self.assertNotIn('mojekino.playing', STATE['window'])
        STATE['player'].update(playing=True, time=600.0, total=2400.0)
        tracker.poll()
        STATE['player']['playing'] = False
        tracker.onPlayBackStopped()
        row = database.progress_get('episode', 20, 1, 1)
        self.assertEqual((row['position'], row['watched']), (600.0, 0))
        call('continue')                                           # je v Rozkoukaných s pozicí
        self.assertEqual(len(STATE['items']), 1)
        # u dílů nabízí pokračování doplněk sám - pozice je v názvu, ne jako bod pokračování Kodi
        self.assertIsNone(STATE['items'][0][1].tag.values.get('ResumePoint'))
        self.assertIn('10:00', STATE['items'][0][1].label)
        call('episodes', id=20, season=1)
        self.assertIn('▶ 10:00', STATE['items'][0][1].label)
        self.assertNotIn('IsPlayable', STATE['items'][0][1].props)     # klik spustí doplněk, Kodi nečeká
        # dokoukání do konce -> zhlédnuto, z Rozkoukaných zmizí
        call('play', kind='episode', id=20, season=1, episode=1)
        tracker.onAVStarted()
        STATE['player'].update(playing=True, time=2300.0, total=2400.0)
        tracker.poll()
        tracker.onPlayBackStopped()
        self.assertEqual(database.progress_get('episode', 20, 1, 1)['watched'], 1)
        call('continue')                                           # místo rozkoukaného dílu je tam další díl
        self.assertEqual(len(STATE['items']), 1)
        self.assertIn('S01E02', labels()[0])
        self.assertIn('další díl', labels()[0])
        # video z jiného doplňku se nesleduje
        tracker.onAVStarted()
        self.assertIsNone(tracker.current)
        # příliš krátké přehrání pozici nepřepíše
        database.progress_mark('movie', 10, 0, 0, False)
        call('play', kind='movie', id=10)
        tracker.onAVStarted()
        STATE['player'].update(playing=True, time=20.0, total=6000.0)
        tracker.poll()
        tracker.onPlayBackStopped()
        self.assertIsNone(database.progress_get('movie', 10))
        database.progress_mark('episode', 20, 1, 1, False)

    def test_episode_counters_and_next_episode(self):
        database = ctx.db()
        for number in (1, 2, 3):
            database.progress_mark('episode', 20, 1, number, False)
        self.assertEqual(episodes.next_unwatched(self.tmdb, database, 20)['episode'], 1)
        call('mark_watched', kind='episode', id=20, season=1, episode=1, value=1)
        call('seasons', id=20)
        self.assertIn('[1/3]', labels()[0])
        self.assertEqual(STATE['items'][0][1].props['WatchedEpisodes'], '1')
        self.assertEqual(episodes.next_unwatched(self.tmdb, database, 20)['episode'], 2)
        call('continue')                                           # nabídne další díl k přehrání
        self.assertTrue(any('S01E02' in label and 'další díl' in label for label in labels()))
        call('watch_toggle', kind='tv', id=20)
        call('my_list', kind='tv')
        self.assertIn('[1/3]', labels()[0])
        self.assertTrue(any('další díl' in label for label, _cmd in STATE['items'][0][1].context))
        call('watch_toggle', kind='tv', id=20)
        # „Přehrát další díl“: po dílu 1 (1080p CZ) vybere u dílu 2 stejný jazyk a kvalitu, ne největší soubor
        STATE['settings']['auto_select'] = 'true'
        database.meta_set('last_stream_20', 'Test.Show.S01E01.1080p.CZ.mkv')
        call('play_next', id=20)
        self.assertEqual(STATE['resolved'], (True, 'https://example.invalid/stream/e2b'))
        # po zhlédnutí všech odvysílaných dílů už další není
        for number in (2, 3):
            database.progress_mark('episode', 20, 1, number, True)
        self.assertIsNone(episodes.next_unwatched(self.tmdb, database, 20))
        call('play_next', id=20)
        self.assertEqual(STATE['resolved'][0], False)
        call('seasons', id=20)
        self.assertEqual(STATE['items'][0][1].tag.values.get('Playcount'), 1)   # celá sezóna zhlédnuta
        for number in (1, 2, 3):
            database.progress_mark('episode', 20, 1, number, False)

    def test_autoplay_next_episode(self):
        import json
        import xbmc
        from unittest import mock
        monitor = xbmc.Monitor()
        database = ctx.db()
        database.progress_mark('episode', 20, 1, 1, False)
        tracker = Tracker()
        # s dotazem předem se další díl z playlistu před koncem odebere a nabídne ho služba
        STATE['settings']['autoplay_ask'] = 'true'
        call('play', _handle='-1', kind='episode', id=20, season=1, episode=1)
        tracker.onAVStarted()
        STATE['player'].update(playing=True, time=2390.0, total=2400.0)
        tracker.poll()
        self.assertEqual(len(STATE['playlist']), 1)
        STATE['player']['playing'] = False
        tracker.onPlayBackEnded()
        finished = tracker.pop_finished_episode()
        self.assertEqual(finished['episode'], 1)
        self.assertIsNone(tracker.pop_finished_episode())          # nabídne se jen jednou
        # spuštění službou: další díl se pustí rovnou, bez jakéhokoli okna
        STATE['settings']['autoplay_ask'] = 'false'
        STATE['player']['playing'] = False
        STATE['answers']['select'] = -1
        kodistubs.reset()
        self.assertTrue(autoplay.offer(finished, monitor))
        self.assertEqual(STATE['dialogs'], [])
        self.assertEqual(STATE['direct'], 'https://example.invalid/stream/e2b')
        self.assertEqual(STATE['builtins'], [])
        self.assertIn('S01E02', STATE['notifications'][0])
        # se zapnutým dotazem: vyprší sám -> spustí se přímo přehrávačem, bez PlayMedia a bez výběru streamu
        STATE['settings']['autoplay_ask'] = 'true'
        STATE['answers']['timeout'] = True
        kodistubs.reset()
        with mock.patch.object(autoplay, '_now', lambda: STATE['clock']):
            self.assertTrue(autoplay.offer(finished, monitor))
        self.assertIn('S01E02', STATE['dialogs'][0][1])
        self.assertEqual(STATE['direct'], 'https://example.invalid/stream/e2b')
        self.assertEqual(STATE['builtins'], [])
        self.assertEqual([d for d in STATE['dialogs'] if d[0] == 'select'], [])
        self.assertEqual(json.loads(STATE['window']['mojekino.playing'])['episode'], 2)
        # „Přehrát hned“
        STATE['answers'].update(timeout=False, yesno=True)
        kodistubs.reset()
        self.assertTrue(autoplay.offer(finished, monitor))
        self.assertEqual(STATE['direct'], 'https://example.invalid/stream/e2b')
        # „Zrušit“ nebo Zpět před vypršením času
        STATE['answers']['yesno'] = False
        kodistubs.reset()
        self.assertFalse(autoplay.offer(finished, monitor))
        self.assertIsNone(STATE['direct'])
        # Kodi má otevřené jiné okno nebo už něco hraje -> služba se do toho neplete, ani se neptá
        STATE['answers']['yesno'] = True
        STATE['settings']['autoplay_ask'] = 'false'
        STATE['visible'] = True
        kodistubs.reset()
        self.assertFalse(autoplay.offer(finished, monitor))
        self.assertEqual(STATE['dialogs'], [])
        STATE['visible'] = False
        STATE['player']['playing'] = True
        self.assertFalse(autoplay.offer(finished, monitor))
        self.assertEqual(STATE['dialogs'], [])
        self.assertIsNone(STATE['direct'])
        STATE['player']['playing'] = False
        # pro další díl není stream -> jen oznámení
        self.provider.broken = {'e2a', 'e2b'}
        kodistubs.reset()
        self.assertFalse(autoplay.offer(finished, monitor))
        self.assertIsNone(STATE['direct'])
        self.assertTrue(STATE['notifications'])
        self.provider.broken = set()
        # po posledním odvysílaném dílu se nic nenabízí
        kodistubs.reset()
        self.assertFalse(autoplay.offer(dict(finished, episode=3), monitor))
        self.assertEqual(STATE['dialogs'], [])
        STATE['answers']['yesno'] = False
        # zastavení uprostřed další díl nespouští; vypnutá volba také ne
        call('play', kind='episode', id=20, season=1, episode=1)
        tracker.onAVStarted()
        tracker.onPlayBackStopped()
        self.assertIsNone(tracker.pop_finished_episode())
        STATE['settings']['autoplay_next'] = 'false'
        call('play', kind='episode', id=20, season=1, episode=1)
        tracker.onAVStarted()
        STATE['player'].update(playing=True, time=2390.0, total=2400.0)
        tracker.poll()
        tracker.onPlayBackEnded()
        self.assertIsNone(tracker.pop_finished_episode())
        for number in (1, 2):
            database.progress_mark('episode', 20, 1, number, False)

    def test_episode_playlist_allows_skipping(self):
        import json
        tracker = Tracker()
        database = ctx.db()
        # Kodi čeká na odkaz (přehratelná položka odjinud) -> jen ten díl, žádný playlist:
        # odmítnutý odkaz + playlist vedl v 0.7.0 k přeskočení prvního dílu
        del STATE['playlist'][:]
        call('play', kind='episode', id=20, season=1, episode=1)
        self.assertFalse(STATE['playlist_started'])
        self.assertEqual(STATE['playlist'], [])
        self.assertEqual(STATE['resolved'], (True, 'https://example.invalid/stream/e1'))
        self.assertEqual(json.loads(STATE['window']['mojekino.playing'])['next_url'], '')
        # klik na díl v seznamu doplňku: Kodi nečeká, doplněk pustí playlist sám
        call('play', _handle='-1', kind='episode', id=20, season=1, episode=1)
        self.assertTrue(STATE['busy_shown'])                     # při hledání je vidět, že se něco děje
        # díl běží jako playlist [stream dílu, odkaz na další díl] -> v přehrávači funguje „další“
        self.assertTrue(STATE['playlist_started'])
        self.assertEqual(STATE['resolved'], (True, 'https://example.invalid/stream/e1'))
        paths = [path for path, _item in STATE['playlist']]
        self.assertEqual(paths[0], 'https://example.invalid/stream/e1')
        self.assertIn('episode=2', paths[1])
        self.assertIn('queued=1', paths[1])
        self.assertEqual(STATE['playlist'][1][1].props.get('IsPlayable'), 'true')
        playing = json.loads(STATE['window']['mojekino.playing'])
        self.assertEqual(playing['next_url'], paths[1])
        # výchozí nastavení: na konci přejde na další díl sám playlist, služba nic nespouští
        tracker.onAVStarted()
        STATE['player'].update(playing=True, time=2390.0, total=2400.0)
        tracker.poll()
        self.assertEqual(len(STATE['playlist']), 2)
        tracker.onPlayBackEnded()
        self.assertIsNone(tracker.pop_finished_episode())
        self.assertTrue(database.progress_get('episode', 20, 1, 1)['watched'])
        # Kodi došlo na další díl v playlistu: stream se vybere bez dotazu a za něj se zařadí další
        STATE['answers']['select'] = -1
        call('play', kind='episode', id=20, season=1, episode=2, auto=1, queued=1)
        self.assertFalse(STATE['playlist_started'])
        self.assertEqual(STATE['resolved'], (True, 'https://example.invalid/stream/e2b'))
        self.assertEqual([d for d in STATE['dialogs'] if d[0] == 'select'], [])
        self.assertIn('episode=3', STATE['playlist'][-1][0])
        # poslední odvysílaný díl už nic dalšího nezařadí a hraje se jako dřív
        self.provider.add('e3', 'Test.Show.S01E03.1080p.CZ.mkv')
        STATE['answers']['select'] = 0
        del STATE['playlist'][:]
        call('play', _handle='-1', kind='episode', id=20, season=1, episode=3)
        self.assertFalse(STATE['playlist_started'])
        self.assertEqual(STATE['playlist'], [])
        self.assertEqual(STATE['resolved'], (True, 'https://example.invalid/stream/e3'))
        self.provider.files = [f for f in self.provider.files if f.ident != 'e3']
        # vypnuté automatické přehrání: „další“ funguje, ale před koncem se další díl odebere
        STATE['settings']['autoplay_next'] = 'false'
        call('play', _handle='-1', kind='episode', id=20, season=1, episode=1)
        tracker.onAVStarted()
        STATE['player'].update(time=1000.0)
        tracker.poll()
        self.assertEqual(len(STATE['playlist']), 2)             # uprostřed dílu zůstává
        STATE['player'].update(time=2390.0)
        tracker.poll()
        self.assertEqual(len(STATE['playlist']), 1)
        tracker.onPlayBackEnded()
        self.assertIsNone(tracker.pop_finished_episode())
        for number in (1, 2):
            database.progress_mark('episode', 20, 1, number, False)

    def test_resume_menu_for_episodes(self):
        database = ctx.db()
        database.progress_set('episode', 20, 1, 1, position=600, duration=2400, watched=False)
        try:
            STATE['answers']['menu'] = 0                                # „Pokračovat od 10:00“
            call('play', _handle='-1', kind='episode', id=20, season=1, episode=1)
            self.assertEqual(STATE['dialogs'][0], ('menu', ['Pokračovat od 10:00', 'Přehrát od začátku']))
            self.assertEqual(STATE['playlist'][0][1].props.get('StartOffset'), '600')
            STATE['answers']['menu'] = 1                                # „Přehrát od začátku“
            call('play', _handle='-1', kind='episode', id=20, season=1, episode=1)
            self.assertIsNone(STATE['playlist'][0][1].props.get('StartOffset'))
            STATE['answers']['menu'] = -1                               # Zpět = nic se nespustí
            call('play', _handle='-1', kind='episode', id=20, season=1, episode=1)
            self.assertFalse(STATE['playlist_started'])
            self.assertIsNone(STATE['direct'])
            # automaticky spuštěný další díl se neptá
            STATE['answers']['menu'] = -1
            call('play', _handle='-1', kind='episode', id=20, season=1, episode=1, auto=1)
            self.assertEqual([d for d in STATE['dialogs'] if d[0] == 'menu'], [])
        finally:
            STATE['answers'].pop('menu', None)
            database.progress_mark('episode', 20, 1, 1, False)

    def test_upnext_integration(self):
        import base64
        import json
        from resources.lib import upnext
        tracker = Tracker()
        STATE['addons'] = {'service.upnext'}
        try:
            call('play', _handle='-1', kind='episode', id=20, season=1, episode=1)
            tracker.onAVStarted()
            # Up Next dostal informace o hrajícím a následujícím dílu
            request = json.loads(STATE['jsonrpc'][-1])
            self.assertEqual(request['params']['message'], 'upnext_data')
            self.assertEqual(request['params']['sender'], 'plugin.video.mojekino.SIGNAL')
            data = json.loads(base64.b64decode(request['params']['data'][0]))
            self.assertEqual(data['current_episode']['episode'], 1)
            self.assertEqual(data['next_episode']['episode'], 2)
            self.assertEqual(data['next_episode']['showtitle'], 'Testovací seriál')
            self.assertEqual(data['play_info'], {'tmdb_id': 20, 'season': 1, 'episode': 2})
            # před koncem se další díl z playlistu odebere - o pokračování rozhoduje okénko Up Next
            STATE['player'].update(playing=True, time=2390.0, total=2400.0)
            tracker.poll()
            self.assertEqual(len(STATE['playlist']), 1)
            tracker.onPlayBackEnded()
            self.assertIsNone(tracker.pop_finished_episode())
            # Up Next žádá o přehrání -> služba spustí další díl sama
            encoded = base64.b64encode(json.dumps(data['play_info']).encode()).decode()
            wanted = upnext.play_request('Other.plugin.video.mojekino_play_action', json.dumps([encoded]))
            self.assertEqual(wanted, {'tmdb_id': 20, 'season': 1, 'episode': 2})
            self.assertIsNone(upnext.play_request('Other.jiny_doplnek_play_action', json.dumps([encoded])))
            self.assertIsNone(upnext.play_request('Other.plugin.video.mojekino_play_action', 'nesmysl'))
            monitor = runner.ServiceMonitor()
            monitor.onNotification('upnextprovider.SIGNAL', 'Other.plugin.video.mojekino_play_action',
                                   json.dumps([encoded]))
            kodistubs.reset()
            self.assertTrue(autoplay.play_now(monitor.pop_upnext_request()))
            self.assertEqual(STATE['direct'], 'https://example.invalid/stream/e2b')
            self.assertIsNone(monitor.pop_upnext_request())
            # vypnuté v nastavení -> Up Next se nepoužije
            STATE['settings']['use_upnext'] = 'false'
            self.assertFalse(upnext.active())
        finally:
            STATE['addons'] = set()
            for number in (1, 2):
                ctx.db().progress_mark('episode', 20, 1, number, False)

    def test_subtitles_offer_and_imdb(self):
        import json
        tracker = Tracker()
        STATE['answers']['select'] = 1                             # anglický stream bez titulků
        call('play', kind='movie', id=10)
        self.assertEqual(STATE['resolved_item'].tag.values.get('IMDBNumber'), 'tt1375666')
        self.assertTrue(json.loads(STATE['window']['mojekino.playing'])['subs'])
        tracker.onAVStarted()
        tracker.subs_due = 1                                       # jako by už uběhly 4 sekundy
        STATE['player'].update(playing=True, time=5.0, total=6000.0)
        kodistubs.reset()
        tracker.poll()
        self.assertEqual(STATE['builtins'], ['ActivateWindow(SubtitleSearch)'])
        tracker.poll()
        self.assertEqual(len(STATE['builtins']), 1)                # jen jednou
        tracker.onPlayBackStopped()
        STATE['answers']['select'] = 0                             # český stream - titulky se nenabízí
        call('play', kind='movie', id=10)
        self.assertFalse(json.loads(STATE['window']['mojekino.playing'])['subs'])
        STATE['settings']['subs_auto'] = 'false'
        STATE['answers']['select'] = 1
        call('play', kind='movie', id=10)
        self.assertFalse(json.loads(STATE['window']['mojekino.playing'])['subs'])
        ctx.db().progress_mark('movie', 10, 0, 0, False)

    def test_alphabetical_list(self):
        database = ctx.db()
        database.execute("DELETE FROM catalog")
        database.execute("DELETE FROM hidden")
        call('az', kind='movie')                                   # první otevření index sestaví
        self.assertTrue(STATE['ended'])
        self.assertIn('Titulů v seznamu: 9', labels()[0])
        self.assertEqual([l.split('  ')[0] for l in labels()[1:]], ['0–9', 'A', 'B', 'Z'])
        self.assertIn('(4)', labels()[2])                          # Avatar, Árie, Amélie, Anděl
        call('az_list', kind='movie', letter='a')
        self.assertEqual([l.split(' (')[0] for l in labels()],
                         ['Amélie z Montmartru', 'Anděl Páně', 'Árie', 'Avatar'])   # diakritika se řadí správně
        call('az_list', kind='movie', letter='z')
        self.assertEqual([l.split(' (')[0] for l in labels()], ['Zelená míle', 'Želvy Ninja'])
        call('az_list', kind='movie', letter='#')
        self.assertEqual(len(STATE['items']), 2)
        # stránkování a skok na stranu
        STATE['settings']['page_size'] = '0'
        for i in range(45):
            database.execute("INSERT INTO catalog (kind, tmdb_id, title, sort_key, letter) VALUES "
                             "('movie', ?, ?, ?, 'x')", (500 + i, 'X film %02d' % i, 'x film %02d' % i))
        call('az_list', kind='movie', letter='x')
        self.assertIn('Strana 1 z 3', labels()[0])
        self.assertEqual(len(STATE['items']), 22)                  # řádek se stranou + 20 titulů + další strana
        STATE['answers']['numeric'] = '3'
        call('az_nav', kind='movie', letter='x', page=1, pages=3)
        self.assertIn('page=3', STATE['builtins'][-1])
        call('az_list', kind='movie', letter='x', page=3)
        self.assertEqual(len(STATE['items']), 6)                   # řádek se stranou + posledních 5 titulů
        # ruční aktualizace index přepíše
        calls = self.tmdb.catalog_calls
        call('az_build', kind='movie')
        self.assertGreater(self.tmdb.catalog_calls, calls)
        self.assertEqual(database.catalog_count('movie'), 9)
        database.execute("DELETE FROM catalog")

    def test_hidden_titles(self):
        database = ctx.db()
        database.execute("DELETE FROM hidden")
        call('list', kind='movie', cat='popular')
        self.assertTrue(any('Skrýt' in label for label, _cmd in STATE['items'][1][1].context))
        call('hide', kind='movie', id=10, title='Počátek')
        self.assertIn('Počátek', STATE['notifications'][-1])
        call('list', kind='movie', cat='popular')
        self.assertFalse(any('Počátek' in label for label in labels()))
        call('my')
        self.assertTrue(any('Skryté tituly' in label for label in labels()))
        call('hidden')
        self.assertIn('Počátek', labels()[0])
        call('unhide', kind='movie', id=10)
        call('list', kind='movie', cat='popular')
        self.assertTrue(any('Počátek' in label for label in labels()))
        call('my')
        self.assertFalse(any('Skryté tituly' in label for label in labels()))

    def test_catalog_background_job(self):
        import xbmc
        monitor = xbmc.Monitor()
        database = ctx.db()
        database.execute("DELETE FROM catalog")
        self.assertTrue(jobs.catalog_refresh(monitor))
        self.assertEqual(database.catalog_count('movie'), 9)
        self.assertEqual(database.catalog_count('tv'), 9)
        calls = self.tmdb.catalog_calls
        self.assertTrue(jobs.catalog_refresh(monitor))            # čerstvý index se znovu nestahuje
        self.assertEqual(self.tmdb.catalog_calls, calls)
        database.meta_set('catalog_built_movie', 1)                # starší než týden -> obnoví se
        jobs.catalog_refresh(monitor)
        self.assertGreater(self.tmdb.catalog_calls, calls)
        STATE['player']['playing'] = True                          # během přehrávání se nespouští
        self.assertFalse(jobs.catalog_refresh(monitor))
        database.execute("DELETE FROM catalog")

    def test_similar_collection_and_people(self):
        ctx.db().execute("DELETE FROM hidden")
        call('list', kind='movie', cat='popular')
        entries = dict(STATE['items'][1][1].context)
        self.assertIn('cat=similar', entries['Podobné tituly'])
        self.assertIn('ref=10', entries['Podobné tituly'])
        self.assertIn('action=collection', entries['Celá série: Sny'])
        self.assertIn('action=people', entries['Herci a tvůrci'])
        call('list', kind='tv', cat='popular')
        entries = dict(STATE['items'][1][1].context)
        self.assertIn('Podobné tituly', entries)
        self.assertFalse(any('série' in label.lower() for label in entries))     # série jsou jen u filmů
        call('history')                                            # titul bez zjištěných údajů: obecná položka
        # podobné tituly jsou běžný seznam se stránkováním
        call('list', kind='movie', cat='similar', ref=10)
        self.assertEqual((self.tmdb.calls[-1]['cat'], self.tmdb.calls[-1]['ref']), ('similar', '10'))
        self.assertIn('Počátek', labels()[1])
        STATE['answers']['select'] = 1
        call('list_nav', kind='movie', cat='similar', ref=10, page=1, pages=3)
        self.assertEqual(self.tmdb.calls[-1]['ref'], '10')
        # série: podle čísla i podle filmu; krátký díl série se neskrývá
        call('collection', id=77)
        self.assertEqual(STATE['content'], 'movies')
        self.assertEqual(len(STATE['items']), 3)
        self.assertIn('Počátek 2 (2014)', labels()[1])
        call('collection', movie=10)
        self.assertEqual(len(STATE['items']), 3)
        call('collection', movie=999)
        self.assertEqual(STATE['ended'], False)
        self.assertIn('nepatří', STATE['notifications'][-1])
        # obsazení
        call('people', kind='movie', id=10)
        self.assertEqual(labels(), ['Christopher Nolan  [COLOR gray]režie[/COLOR]',
                                    'Leonardo DiCaprio  [COLOR gray]Cobb[/COLOR]'])
        self.assertIn('action=person', STATE['items'][0][0])
        self.assertEqual(STATE['items'][1][1].art['thumb'], 'leo.jpg')
        call('people', kind='movie', id=999)
        self.assertEqual(STATE['ended'], False)
        # tvorba osoby: odkaz na seriály, stránkování
        call('person', id=50)
        self.assertEqual(labels()[0], 'Seriály této osoby (1)')
        self.assertEqual(len(STATE['items']), 1 + 40 + 1)
        self.assertIn('2/2', labels()[-1])
        call('person', id=50, page=2)
        self.assertEqual(len(STATE['items']), 5)
        call('person', id=50, kind='tv')
        self.assertEqual(labels()[0], 'Filmy této osoby (45)')
        self.assertTrue(STATE['items'][1][2])

    def test_runtime_is_shown_only_once(self):
        media = {'tmdb_id': 10, 'title': 'Počátek', 'year': 2010, 'rating': 8.4, 'runtime': 148}
        ui._options.clear()
        _url, item, _folder = ui.movie_item(media)
        self.assertIn('148 min', item.label)
        self.assertNotIn('Duration', item.tag.values)             # vzhled Kodi by délku vypsal podruhé
        STATE['settings']['show_runtime'] = 'false'
        ui._options.clear()
        _url, item, _folder = ui.movie_item(media)
        self.assertNotIn('148 min', item.label)
        self.assertEqual(item.tag.values.get('Duration'), 148 * 60)
        ui._options.clear()

    def test_languages_in_lists(self):
        from resources.lib import availability
        database = ctx.db()
        database.langs_clear()
        STATE['settings']['show_langs'] = 'true'
        self.provider.add('m3', 'Pocatek.2010.2160p.EN.CZ.titulky.mkv')
        try:
            self.provider.queries = []
            call('list', kind='movie', cat='popular')
            self.assertEqual(labels()[1], 'Počátek (2010)  [COLOR gray]84 % · 148 min · CZ, EN · tit. CZ[/COLOR]')
            asked = len(self.provider.queries)
            self.assertTrue(asked)
            call('list', kind='movie', cat='popular')                 # podruhé už z paměti
            self.assertEqual(len(self.provider.queries), asked)
            self.assertIn('CZ, EN', labels()[1])
            # seriál jako celek a jednotlivé díly
            call('list', kind='tv', cat='popular')
            self.assertIn('2 řady · CZ[/COLOR]', labels()[1])        # podle prvního dílu seriálu
            call('episodes', id=20, season=1)
            self.assertEqual(labels()[0], '1. Díl 1  [COLOR gray]CZ[/COLOR]')
            self.assertEqual(labels()[1], '2. Díl 2  [COLOR gray]CZ, EN[/COLOR]')
            self.assertEqual(labels()[2], '3. Díl 3')                 # pro třetí díl stream není
            # výpadek poskytovatele se neukládá a seznam se zobrazí i tak
            database.langs_clear()
            original = self.provider.search

            def broken(query, limit=50, offset=0, sort=''):
                raise ProviderError(ProviderError.NETWORK)
            self.provider.search = broken
            call('list', kind='movie', cat='popular')
            self.assertEqual(labels()[1], 'Počátek (2010)  [COLOR gray]84 % · 148 min[/COLOR]')
            self.assertEqual(database.langs_get('movie', [10]), {})
            self.provider.search = original
            # časový limit: co se nestihne, zůstane na příště
            ticks = iter(range(0, 1000, 20))
            found = availability.lookup('movie', {(10, 0, 0): (['Počátek', 'Inception'], 2010),
                                                  (11, 0, 0): (['Počátek', 'Inception'], 2010)},
                                        self.provider, ctx.prefs(), database, budget=10, clock=lambda: next(ticks))
            self.assertEqual(found, {})
            # vypnuto v nastavení -> poskytovatele se na nic neptá
            STATE['settings']['show_langs'] = 'false'
            self.provider.queries = []
            call('list', kind='movie', cat='popular')
            self.assertEqual(self.provider.queries, [])
            call('clear_cache')
            self.assertEqual(database.langs_get('movie', [10]), {})
        finally:
            self.provider.files = [f for f in self.provider.files if f.ident != 'm3']
            database.langs_clear()

    def test_unknown_action_is_reported_not_raised(self):
        call('neexistuje')
        self.assertTrue(STATE['notifications'])

    def test_service_jobs(self):
        import xbmc
        monitor = xbmc.Monitor()
        database = ctx.db()
        for key in ('vip_notice_day', 'job_last_vip', 'job_last_watcher', 'job_last_cleanup'):
            database.meta_delete(key)
        self.provider.vip_days = 3
        kodistubs.reset()
        runner.tick(monitor)
        self.assertTrue(any('3' in n for n in STATE['notifications']))      # varování před koncem VIP
        self.assertTrue(database.meta_get('job_last_vip'))
        kodistubs.reset()
        database.meta_delete('job_last_vip')
        runner.tick(monitor)
        self.assertEqual(STATE['notifications'], [])                        # jen jednou denně
        database.meta_delete('vip_notice_day')
        self.provider.vip = False
        self.assertTrue(jobs.vip_check(monitor))
        self.assertIn('není aktivní', STATE['notifications'][-1])
        self.provider.vip, self.provider.vip_days = True, 100


class _MemoryStore(dict):
    def set(self, key, value):
        self[key] = value

    def delete(self, key):
        self.pop(key, None)


_STREAMUJ_PAGE = '''<script>
    plugins: { "x": {
vkey: "vid1",
res0: "http://www.streamuj.tv/video/vid1?streamuj=original,http://www.streamuj.tv/video/vid1?streamuj=hd",
sub0: "",
res1: "http://www.streamuj.tv/video/vid1?streamuj=original&l=1",
sub1: "cs>http://www.streamuj.tv/sub/vid1.srt",
langs: "cs>čeština,en>angličtina",
rn: "SD,HD"
}}</script>'''


class SourceTests(unittest.TestCase):
    """Další zdroje streamů nad uloženými ukázkami odpovědí (bez sítě)."""

    def _http(self, pages):
        import json
        from unittest import mock

        def fake(url, params=None, data=None, headers=None, timeout=15, retries=1):
            if params:
                url += '?' + '&'.join('%s=%s' % (k, v) for k, v in sorted(params.items()))
            for prefix, body in pages.items():
                if url.startswith(prefix):
                    if callable(body):
                        body = body(url)
                    if isinstance(body, Exception):
                        raise body
                    return (body if isinstance(body, str) else json.dumps(body)).encode('utf-8')
            raise http.HttpError('HTTP 404', status=404)
        from resources.lib import http
        return mock.patch.object(http, 'request', fake)

    def test_sosac_finds_movie_by_imdb_and_resolves_with_account(self):
        from unittest import mock
        from resources.lib.providers import sosac
        search = [
            {'q': 'hd', 'n': {'cs': 'Počátek', 'en': 'Inception'}, 'd': ['cs'], 'y': '2010', 'm': '1375666',
             'l': 'vid1'},
            {'q': 'sd', 'n': {'cs': 'Počátek', 'en': 'Beginning'}, 'd': ['cs'], 'y': '2010', 'm': '9999999',
             'l': 'other'},
        ]
        store = _MemoryStore()
        source = sosac.Sosac(store)
        self.assertFalse(source.is_logged_in())
        with self._http({sosac.WEB_API: {'result': 1, 'UID': 7, 'expiration': 0}}):
            source.login('tester', 'heslo')
        self.assertNotIn('heslo', store.values())                   # heslo se neukládá, jen otisk
        self.assertEqual(store['password_hash'], sosac.password_hash('heslo'))
        with self._http({sosac.SEARCH: search, sosac.STREAMUJ + 'vid1': _STREAMUJ_PAGE}):
            files = source.find('movie', ['Počátek', 'Inception'], 2010, imdb='tt1375666')
            self.assertEqual(len(files), 3)                          # CZ SD + CZ HD + EN s titulky
            self.assertTrue(all(f.ident.startswith('vid1:') for f in files))   # cizí film se stejným názvem ne
            found = streams.find_movie([FakeProvider(), source], ['Počátek', 'Inception'], 2010,
                                       streams.Prefs(min_size_mb=50), imdb='tt1375666')
        best = found[0]
        self.assertEqual(best.file.provider, 'sosac')
        self.assertEqual(best.info['quality'], 720)
        self.assertEqual(best.info['audio'], ['cz'])
        self.assertIn('Sosáč', best.label)
        english = [c for c in found if c.info['audio'] == ['en']][0]
        self.assertEqual(english.info['subs'], ['cz'])

        class Response(object):
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size=-1):
                return self.body

        opened = []

        class Opener(object):
            def open(self, request, timeout=0):
                opened.append(request.full_url)
                return Response(b'http://s24.streamuj.tv:8080/vid/abc/vid1_hd.mp4?pass=x\n')

        with self._http({sosac.STREAMUJ + 'vid1': _STREAMUJ_PAGE}), \
                mock.patch.object(sosac.urllib.request, 'build_opener', lambda *handlers: Opener()):
            link = source.resolve(best.file.ident)
        self.assertTrue(link.startswith('http://s24.streamuj.tv:8080/vid/abc/vid1_hd.mp4'))
        self.assertIn('|User-Agent=', link)
        self.assertTrue(opened[0].startswith('http://www.streamuj.tv/video/vid1?streamuj=hd&pass=tester:::'))
        source.logout()
        with self.assertRaises(ProviderError):
            source.resolve(best.file.ident)

    def test_sosac_finds_episode_in_show_list(self):
        from resources.lib.providers import sosac
        sosac._letters.clear()
        show_list = [{'n': {'cs': 'Jiný seriál', 'en': 'Other'}, 'y': '2020', 'm': '1', 'l': 'http://x/s1.json'},
                     {'n': {'cs': 'Testovací seriál', 'en': 'Test Show'}, 'y': '2020', 'm': '0000020',
                      'l': 'http://x/s20.json'}]
        episodes = [{'1': {'1': {'n': 'Pilot', 'l': 'ep1'}}}, {'1': {'2': {'n': 'Dva', 'l': 'vid1'}}}]
        source = sosac.Sosac(_MemoryStore(username='u', password_hash='h'))
        with self._http({sosac.SHOW_LETTER % 't': show_list, 'http://x/s20.json': episodes,
                         sosac.STREAMUJ + 'vid1': _STREAMUJ_PAGE}):
            files = source.find('tv', ['Testovací seriál', 'Test Show'], 2020, 1, 2, imdb='tt0000020')
            found = streams.find_episode([source], ['Testovací seriál', 'Test Show'], 1, 2, streams.Prefs(),
                                         imdb='tt0000020')
            self.assertEqual(source.find('tv', ['Neexistuje'], 2020, 1, 2), [])
        self.assertEqual(len(files), 3)
        self.assertEqual(found[0].info['episode'], (1, 2))
        self.assertEqual(found[0].info['audio'], ['cz'])

    def test_hellspy_search_and_resolve(self):
        from resources.lib.providers import hellspy
        result = {'items': [
            {'id': 18926451, 'fileHash': '909dda6ddf941df7', 'size': 3908541179, 'duration': 8887,
             'title': 'Pocatek - Inception (2010) - FullHD 1080p (H264) - CZ dabing'},
            {'id': 1, 'title': 'bez hashe'}]}
        detail = {'conversions': {'360': 'https://cdn/360.mp4', '720': 'https://cdn/720.mp4'}}
        source = hellspy.HellSpy()
        with self._http({hellspy.API + '/search': result, hellspy.API + '/video/18926451/909dda6ddf941df7': detail}):
            files, _total = source.search('Inception 2010')
            link = source.resolve(files[0].ident)
            found = streams.find_movie([source], ['Počátek', 'Inception'], 2010, streams.Prefs())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].ident, '18926451/909dda6ddf941df7')
        self.assertTrue(link.startswith('https://cdn/720.mp4|'))
        self.assertEqual(found[0].info['audio'], ['cz'])
        self.assertIn('HellSpy', found[0].label)
        # hraje se převod 720p - kvalita z názvu (1080p) ani velikost souboru se neukazují
        self.assertEqual(found[0].info['quality'], 720)
        self.assertNotIn('GB', found[0].label)
        # stejný soubor z Webshare (originál) má přednost před převodem
        main = FakeProvider()
        main.files.append(StreamFile('webshare', 'w1', 'Pocatek.2010.720p.CZ.mkv', 2 * GB))
        with self._http({hellspy.API + '/search': result}):
            mixed = streams.find_movie([main, source], ['Počátek', 'Inception'], 2010, streams.Prefs())
        self.assertEqual(mixed[0].file.ident, 'w1')
        with self._http({hellspy.API + '/video/1/x': {'conversions': {}}}):
            with self.assertRaises(ProviderError):
                source.resolve('1/x')

    def test_same_file_from_hellspy_and_prehrajto_is_listed_once(self):
        def provider(pid):
            fake = FakeProvider()
            fake.id = pid
            fake.files.append(StreamFile(pid, pid + '1', 'Pocatek.2010.1080p.CZ.mkv', 3 * GB))
            return fake
        found = streams.find_movie([provider('hellspy'), provider('prehrajto')], ['Počátek'], 2010, streams.Prefs())
        self.assertEqual([c.file.provider for c in found], ['prehrajto'])     # převod 1080p je lepší než 720p
        self.assertEqual(found[0].info['quality'], 1080)

    def test_prehrajto_pauses_after_rate_limit(self):
        from resources.lib import http
        from resources.lib.providers import prehrajto
        prehrajto._paused_until[0] = 0
        source = prehrajto.Prehrajto()
        with self._http({prehrajto.BASE: http.HttpError('HTTP 429', status=429)}):
            with self.assertRaises(ProviderError):
                source.search('Počátek')
        with self._http({prehrajto.BASE: http.HttpError('nemá se volat', status=500)}):
            self.assertEqual(source.search('Počátek'), ([], 0))     # pauza: na web se ani neptá
        prehrajto._paused_until[0] = 0

    def test_prehrajto_search_and_resolve(self):
        from resources.lib.providers import prehrajto
        results = '''
        <a class="video video--small video--link"
           href="/pocatek-cz-dabing/0581c94cd128be0d"
           title="Počátek (2010) CZ dabing &amp; titulky">
           <div class="video__tag video__tag--time">02:28:08</div>
           <div class="video__tag video__tag--size video__tag--size-alone">
               4.78 GB
           </div>
        </a>
        <a class="video video--small video--link" href="/jine/123" title="Jiné video"><div>700 MB</div></a>'''
        video = '''var sources = [
            { file: "https://pf-storage3.premiumcdn.net/a.mp4?token=1&amp;x=2", label: '720p' },
            { file: "https://pf-storage1.premiumcdn.net/b.mp4?token=1", label: '1080p' }
        ];'''
        source = prehrajto.Prehrajto()
        with self._http({prehrajto.BASE + '/hledej/': results, prehrajto.BASE + '/pocatek-cz-dabing/': video}):
            files, _total = source.search('Počátek 2010')
            link = source.resolve(files[0].ident)
            self.assertEqual(source.search('Počátek', offset=50), ([], 0))
        self.assertEqual(files[0].name, 'Počátek (2010) CZ dabing & titulky')
        self.assertEqual(files[0].size, int(4.78 * GB))
        self.assertEqual(files[1].size, 0)
        self.assertTrue(link.startswith('https://pf-storage1.premiumcdn.net/b.mp4'))
        with self._http({prehrajto.BASE: '<html>nic</html>'}):
            with self.assertRaises(ProviderError):
                source.resolve('/prazdne/1')

    def test_failing_extra_source_does_not_break_search(self):
        class Broken(object):
            id = 'broken'

            def detached(self):
                return self

            def search(self, *args, **kwargs):
                raise RuntimeError('výpadek')

        main = FakeProvider()
        main.add('m1', 'Pocatek.2010.1080p.CZ.mkv')
        found = streams.find_movie([main, Broken()], ['Počátek'], 2010, streams.Prefs())
        self.assertEqual([c.file.ident for c in found], ['m1'])

        class Offline(FakeProvider):
            def search(self, *args, **kwargs):
                raise ProviderError(ProviderError.NETWORK)

        extra = FakeProvider()
        extra.add('x1', 'Pocatek.2010.720p.CZ.mkv')
        found = streams.find_movie([Offline(), extra], ['Počátek'], 2010, streams.Prefs())
        self.assertEqual([c.file.ident for c in found], ['x1'])     # Webshare mimo provoz, ostatní hrají
        with self.assertRaises(ProviderError):
            streams.find_movie([Offline()], ['Počátek'], 2010, streams.Prefs())

    def test_streamuj_account_screen(self):
        import datetime
        from resources.lib.providers import sosac
        from resources.lib.service import jobs
        until = datetime.datetime.now() + datetime.timedelta(days=5, hours=3)
        expiration = until.strftime('%Y-%m-%d %H:%M:%S')

        def premium(url):          # check-user: 2 = účet s premium; check-premium-status: 1 = premium
            return {'result': 2 if 'check-user' in url else 1, 'UID': 7, 'expiration': expiration}

        def free(url):
            return {'result': 1 if 'check-user' in url else 0, 'UID': 7, 'expiration': 0}
        try:
            STATE['settings'] = {'tmdb_api_key': 'x'}
            STATE['answers'] = {'yesno': False, 'select': 0, 'input': ['tester', 'heslo'], 'numeric': '',
                                'cancel_progress': False}
            with self._http({sosac.WEB_API: premium}):
                call('account_sosac')
            self.assertTrue(ctx.sosac().is_logged_in())
            self.assertIn('Zbývá dní: 6', STATE['dialogs'][-1][1])         # 5 dní a kousek = 6. den
            self.assertIn('Premium: aktivní', STATE['dialogs'][-1][1])
            call('root')                                                   # dny premium v hlavním menu
            self.assertTrue(any('Streamuj.tv' in label and 'premium 6 dní' in label for label in labels()))
            # služba: premium končí do 7 dní -> jednou denně upozornění
            STATE['notifications'] = []
            with self._http({sosac.WEB_API: premium}):
                self.assertTrue(jobs.sosac_check(None))
                self.assertTrue(jobs.sosac_check(None))
            self.assertEqual(STATE['notifications'], ['Premium na Streamuj.tv končí za 6 dní.'])
            # bez premium
            with self._http({sosac.WEB_API: free}):
                call('account_sosac')
            self.assertIn('přehraje jen část videa', STATE['dialogs'][-1][1])
            # podruhé: „Odhlásit“
            STATE['answers']['yesno'] = True
            with self._http({sosac.WEB_API: premium}):
                call('account_sosac')
            self.assertFalse(ctx.sosac().is_logged_in())
            call('root')
            self.assertTrue(any('Streamuj.tv' in label and 'nepřihlášeno' in label for label in labels()))
        finally:
            ctx.sosac().logout()
            ctx.db().meta_delete('sosac_notice_day')

    def test_streamuj_login_like_website(self):
        import hashlib
        from resources.lib.providers import sosac
        single = hashlib.md5(b'heslo').hexdigest()
        asked = []

        def answer(url):
            asked.append(url)
            if 'check-user' in url:
                ok = 'password=%s' % single in url and 'passwordinmd5=1' in url and 'login=tester' in url
                return {'result': 2 if ok else 0, 'UID': 7 if ok else 0, 'cookie': 'x', 'expiration': 0}
            return {'result': 1 if 'UID=7' in url else 0, 'expiration': '2099-01-31 12:00:00'}
        store = _MemoryStore()
        source = sosac.Sosac(store)
        with self._http({sosac.WEB_API: answer}):
            info = source.login('tester', 'heslo')
            self.assertTrue(info.vip)
            self.assertIsNone(info.vip_days)                        # premium, ale bez data konce
            # kontrola premium jde přes UID a jméno, bez hesla
            status = source.account()
        self.assertEqual(store['uid'], '7')
        self.assertNotIn(single, store.values())                     # md5 hesla se neukládá
        self.assertEqual(status.vip_until, '31.01.2099')
        self.assertFalse(any('heslo' in url for url in asked))      # heslo samotné se nikam neposílá
        self.assertNotIn('password', asked[-1])
        # špatné heslo: bez potvrzení se účet neuloží, s potvrzením ano (jen bez stavu premium)
        source.logout()
        self.assertNotIn('uid', store)
        with self._http({sosac.WEB_API: answer}):
            with self.assertRaises(ProviderError):
                source.login('tester', 'spatne')
            self.assertFalse(source.is_logged_in())
            info = source.login('tester', 'spatne', force=True)
        self.assertTrue(source.is_logged_in())
        self.assertFalse(info.known)
        self.assertFalse(source.account().known)
        # účet bez premium
        source.logout()
        with self._http({sosac.WEB_API: {'result': 1, 'UID': 9, 'expiration': 0}}):
            info = source.login('tester', 'heslo')
        self.assertTrue(info.known)
        self.assertFalse(info.vip)
        # rozpoznání konce premium
        self.assertIsNone(sosac.parse_expiration(0))
        self.assertIsNone(sosac.parse_expiration('0000-00-00 00:00:00'))
        self.assertEqual(sosac.parse_expiration('15.03.2030').year, 2030)
        self.assertEqual(sosac.parse_expiration(1900000000000).year, 2030)    # milisekundy

    def test_premium_without_end_date_is_shown(self):
        from resources.lib.providers import sosac
        try:
            STATE['settings'] = {'tmdb_api_key': 'x'}
            STATE['answers'] = {'yesno': False, 'select': 0, 'input': ['tester', 'heslo'], 'numeric': '',
                                'cancel_progress': False}
            with self._http({sosac.WEB_API: lambda url: {'result': 2 if 'check-user' in url else 1, 'UID': 7,
                                                         'expiration': 0}}):
                call('account_sosac')
            self.assertIn('Premium: aktivní', STATE['dialogs'][-1][1])
            self.assertNotIn('Zbývá dní', STATE['dialogs'][-1][1])
            call('root')
            self.assertTrue(any('Streamuj.tv' in label and '[COLOR lime]premium[/COLOR]' in label
                                for label in labels()))
        finally:
            ctx.sosac().logout()

    def test_failing_source_is_reported(self):
        class Broken(FakeProvider):
            id = 'hellspy'

            def search(self, *args, **kwargs):
                raise ProviderError(ProviderError.NETWORK, 'výpadek')
        main = FakeProvider()
        main.add('m1', 'Pocatek.2010.1080p.CZ.mkv')
        errors = []
        found = streams.find_movie([main, Broken()], ['Počátek'], 2010, streams.Prefs(), errors=errors)
        self.assertEqual(len(found), 1)
        self.assertEqual([source for source, _e in errors], ['hellspy'])
        # hlavní zdroj vypadl, ostatní něco našly -> výpadek hlavního je v seznamu chyb
        errors = []
        offline = Broken()
        offline.id = 'webshare'
        extra = FakeProvider()
        extra.add('x1', 'Pocatek.2010.720p.CZ.mkv')
        streams.find_movie([offline, extra], ['Počátek'], 2010, streams.Prefs(), errors=errors)
        self.assertEqual([source for source, _e in errors], ['webshare'])
        # ve výběru je u každého streamu vidět zdroj, i u Webshare
        main.files[0] = StreamFile('webshare', 'w1', 'Pocatek.2010.1080p.CZ.mkv', 2 * GB)
        self.assertIn('Webshare', streams.find_movie([main], ['Počátek'], 2010, streams.Prefs())[0].label)

    def test_sources_follow_settings(self):
        extra = REAL_EXTRA_PROVIDERS
        try:
            STATE['settings'] = {}
            self.assertEqual([p.id for p in extra()], ['hellspy', 'prehrajto'])   # Sosáč bez účtu ne
            from resources.lib.providers import sosac
            with self._http({sosac.WEB_API: {'result': 1, 'UID': 7, 'expiration': 0}}):
                ctx.sosac().login('tester', 'heslo')
            self.assertEqual([p.id for p in extra()], ['sosac', 'hellspy', 'prehrajto'])
            STATE['settings'] = {'src_sosac': 'false', 'src_hellspy': 'false', 'src_prehrajto': 'false'}
            self.assertEqual(extra(), [])
        finally:
            ctx.sosac().logout()


if __name__ == '__main__':
    unittest.main(verbosity=1)
