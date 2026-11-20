# -*- coding: utf-8 -*-
"""Lokální databáze doplňku (SQLite v profilu doplňku).

Schéma se mění jen přes seznam MIGRATIONS: nová verze doplňku přidá na konec
další krok a při prvním spuštění se databáze sama povýší. Stará data zůstávají.
"""
import json
import sqlite3
import time

MIGRATIONS = [
    # verze 1 - první vydání
    """
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE cache (key TEXT PRIMARY KEY, value TEXT, expires INTEGER);
    CREATE TABLE watchlist (
        kind TEXT NOT NULL,            -- 'movie' nebo 'tv'
        tmdb_id INTEGER NOT NULL,
        title TEXT, original_title TEXT, year INTEGER,
        poster TEXT, fanart TEXT, plot TEXT,
        added_at INTEGER, checked_at INTEGER,
        available_at INTEGER,          -- film: kdy se poprvé našel stream
        last_season INTEGER DEFAULT 0, -- seriál: poslední známý odvysílaný díl
        last_episode INTEGER DEFAULT 0,
        PRIMARY KEY (kind, tmdb_id)
    );
    CREATE TABLE pending (             -- odvysílané díly, ke kterým ještě není stream
        tmdb_id INTEGER NOT NULL, season INTEGER NOT NULL, episode INTEGER NOT NULL,
        name TEXT, air_date TEXT,
        PRIMARY KEY (tmdb_id, season, episode)
    );
    CREATE TABLE news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL, tmdb_id INTEGER NOT NULL,
        season INTEGER NOT NULL DEFAULT 0, episode INTEGER NOT NULL DEFAULT 0,
        title TEXT, subtitle TEXT, poster TEXT, fanart TEXT,
        found_at INTEGER, seen INTEGER DEFAULT 0,
        UNIQUE (kind, tmdb_id, season, episode)
    );
    CREATE TABLE history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL, tmdb_id INTEGER NOT NULL,
        season INTEGER NOT NULL DEFAULT 0, episode INTEGER NOT NULL DEFAULT 0,
        title TEXT, subtitle TEXT, poster TEXT, fanart TEXT,
        played_at INTEGER,
        UNIQUE (kind, tmdb_id, season, episode)
    );
    CREATE TABLE search_history (
        kind TEXT NOT NULL, query TEXT NOT NULL, used_at INTEGER,
        PRIMARY KEY (kind, query)
    );
    """,
    # verze 2 - zhlédnuto / rozkoukáno
    """
    CREATE TABLE progress (
        kind TEXT NOT NULL,            -- 'movie' nebo 'episode'
        tmdb_id INTEGER NOT NULL,
        season INTEGER NOT NULL DEFAULT 0, episode INTEGER NOT NULL DEFAULT 0,
        position REAL DEFAULT 0,       -- kde přehrávání skončilo (sekundy)
        duration REAL DEFAULT 0,
        watched INTEGER DEFAULT 0,
        updated_at INTEGER,
        PRIMARY KEY (kind, tmdb_id, season, episode)
    );
    """,
    # verze 3 - abecední seznam, skryté tituly, délka filmů / počet řad
    """
    CREATE TABLE catalog (
        kind TEXT NOT NULL, tmdb_id INTEGER NOT NULL,
        title TEXT, original_title TEXT, sort_key TEXT, letter TEXT,
        year INTEGER, premiered TEXT, plot TEXT, poster TEXT, fanart TEXT,
        rating REAL, votes INTEGER,
        PRIMARY KEY (kind, tmdb_id)
    );
    CREATE INDEX catalog_sort ON catalog (kind, letter, sort_key);
    CREATE TABLE hidden (
        kind TEXT NOT NULL, tmdb_id INTEGER NOT NULL, title TEXT, hidden_at INTEGER,
        PRIMARY KEY (kind, tmdb_id)
    );
    CREATE TABLE extras (
        kind TEXT NOT NULL, tmdb_id INTEGER NOT NULL,
        runtime INTEGER DEFAULT 0,     -- film: délka v minutách
        seasons INTEGER DEFAULT 0, episodes INTEGER DEFAULT 0,
        updated_at INTEGER,
        PRIMARY KEY (kind, tmdb_id)
    );
    """,
    # verze 4 - do které filmové série titul patří (NULL = zatím nezjištěno, 0 = do žádné)
    """
    ALTER TABLE extras ADD COLUMN collection_id INTEGER;
    ALTER TABLE extras ADD COLUMN collection_name TEXT;
    """,
    # verze 5 - v jakých jazycích má titul streamy (u filmu a seriálu jsou season i episode 0)
    """
    CREATE TABLE langs (
        kind TEXT NOT NULL, tmdb_id INTEGER NOT NULL, season INTEGER NOT NULL DEFAULT 0,
        episode INTEGER NOT NULL DEFAULT 0, audio TEXT, subs TEXT, streams INTEGER DEFAULT 0,
        updated_at INTEGER, PRIMARY KEY (kind, tmdb_id, season, episode));
    """,
]


def now():
    return int(time.time())


class Database(object):
    def __init__(self, path):
        self.path = path
        self._conn = sqlite3.connect(path, timeout=15)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def _migrate(self):
        version = self._conn.execute('PRAGMA user_version').fetchone()[0]
        for index in range(version, len(MIGRATIONS)):
            self._conn.executescript(MIGRATIONS[index])
            self._conn.execute('PRAGMA user_version = %d' % (index + 1))
            self._conn.commit()

    def execute(self, sql, args=()):
        cur = self._conn.execute(sql, args)
        self._conn.commit()
        return cur

    def query(self, sql, args=()):
        return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        row = self._conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    # ---- meta (malé trvalé hodnoty: token, časy posledních kontrol...) ----
    def meta_get(self, key, default=None):
        row = self.one('SELECT value FROM meta WHERE key=?', (key,))
        return row['value'] if row else default

    def meta_set(self, key, value):
        self.execute('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', (key, str(value)))

    def meta_delete(self, key):
        self.execute('DELETE FROM meta WHERE key=?', (key,))

    # ---- cache (odpovědi z TMDB a hledání, s dobou platnosti) ----
    def cache_info(self, key):
        """Vrátí (hodnota, čas vypršení) nebo None, když záznam chybí či vypršel."""
        row = self.one('SELECT value, expires FROM cache WHERE key=?', (key,))
        if not row or row['expires'] < now():
            return None
        try:
            return json.loads(row['value']), row['expires']
        except ValueError:
            return None

    def cache_get(self, key):
        info = self.cache_info(key)
        return info[0] if info else None

    def cache_set(self, key, value, ttl):
        self.execute('INSERT OR REPLACE INTO cache (key, value, expires) VALUES (?, ?, ?)',
                     (key, json.dumps(value), now() + int(ttl)))

    def cache_cleanup(self):
        self.execute('DELETE FROM cache WHERE expires < ?', (now(),))

    def cache_clear(self):
        self.execute('DELETE FROM cache')

    # ---- seznamy (watchlist filmů, sledované seriály) ----
    def watch_add(self, media, last_season=0, last_episode=0):
        self.execute(
            'INSERT OR IGNORE INTO watchlist (kind, tmdb_id, title, original_title, year, poster, '
            'fanart, plot, added_at, last_season, last_episode) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (media['kind'], media['tmdb_id'], media.get('title'), media.get('original_title'),
             media.get('year') or 0, media.get('poster'), media.get('fanart'), media.get('plot'),
             now(), last_season, last_episode))

    def watch_remove(self, kind, tmdb_id):
        self.execute('DELETE FROM watchlist WHERE kind=? AND tmdb_id=?', (kind, tmdb_id))
        if kind == 'tv':
            self.execute('DELETE FROM pending WHERE tmdb_id=?', (tmdb_id,))

    def watch_has(self, kind, tmdb_id):
        return self.one('SELECT 1 AS x FROM watchlist WHERE kind=? AND tmdb_id=?', (kind, tmdb_id)) is not None

    def watch_list(self, kind):
        return self.query('SELECT * FROM watchlist WHERE kind=? ORDER BY added_at DESC', (kind,))

    def watch_ids(self, kind):
        return set(r['tmdb_id'] for r in self.query('SELECT tmdb_id FROM watchlist WHERE kind=?', (kind,)))

    def watch_update(self, kind, tmdb_id, **fields):
        if not fields:
            return
        cols = ', '.join('%s=?' % k for k in fields)
        self.execute('UPDATE watchlist SET %s WHERE kind=? AND tmdb_id=?' % cols,
                     tuple(fields.values()) + (kind, tmdb_id))

    # ---- čekající díly ----
    def pending_add(self, tmdb_id, season, episode, name, air_date):
        self.execute('INSERT OR IGNORE INTO pending (tmdb_id, season, episode, name, air_date) VALUES (?,?,?,?,?)',
                     (tmdb_id, season, episode, name, air_date))

    def pending_list(self, tmdb_id):
        return self.query('SELECT * FROM pending WHERE tmdb_id=? ORDER BY season, episode', (tmdb_id,))

    def pending_remove(self, tmdb_id, season, episode):
        self.execute('DELETE FROM pending WHERE tmdb_id=? AND season=? AND episode=?', (tmdb_id, season, episode))

    # ---- novinky nalezené hlídačem ----
    def news_add(self, kind, tmdb_id, title, subtitle='', poster=None, fanart=None, season=0, episode=0):
        cur = self.execute(
            'INSERT OR IGNORE INTO news (kind, tmdb_id, season, episode, title, subtitle, poster, fanart, found_at) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (kind, tmdb_id, season, episode, title, subtitle, poster, fanart, now()))
        return cur.rowcount > 0

    def news_list(self, limit=200):
        return self.query('SELECT * FROM news ORDER BY found_at DESC, id DESC LIMIT ?', (limit,))

    def news_unseen_count(self):
        return self.one('SELECT COUNT(*) AS c FROM news WHERE seen=0')['c']

    def news_mark_seen(self):
        self.execute('UPDATE news SET seen=1 WHERE seen=0')

    def news_remove(self, news_id=None):
        if news_id is None:
            self.execute('DELETE FROM news')
        else:
            self.execute('DELETE FROM news WHERE id=?', (news_id,))

    # ---- historie přehrávání ----
    def history_add(self, kind, tmdb_id, title, subtitle='', poster=None, fanart=None, season=0, episode=0):
        self.execute('DELETE FROM history WHERE kind=? AND tmdb_id=? AND season=? AND episode=?',
                     (kind, tmdb_id, season, episode))
        self.execute('INSERT INTO history (kind, tmdb_id, season, episode, title, subtitle, poster, fanart, played_at) '
                     'VALUES (?,?,?,?,?,?,?,?,?)',
                     (kind, tmdb_id, season, episode, title, subtitle, poster, fanart, now()))
        # držíme jen posledních 200 záznamů
        self.execute('DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY played_at DESC LIMIT 200)')

    def history_list(self, limit=100):
        return self.query('SELECT * FROM history ORDER BY played_at DESC, id DESC LIMIT ?', (limit,))

    def history_remove(self, history_id=None):
        if history_id is None:
            self.execute('DELETE FROM history')
        else:
            self.execute('DELETE FROM history WHERE id=?', (history_id,))

    # ---- průběh sledování (zhlédnuto, rozkoukáno) ----
    def progress_get(self, kind, tmdb_id, season=0, episode=0):
        return self.one('SELECT * FROM progress WHERE kind=? AND tmdb_id=? AND season=? AND episode=?',
                        (kind, tmdb_id, season, episode))

    def progress_set(self, kind, tmdb_id, season, episode, position, duration, watched):
        self.execute('INSERT OR REPLACE INTO progress (kind, tmdb_id, season, episode, position, duration, '
                     'watched, updated_at) VALUES (?,?,?,?,?,?,?,?)',
                     (kind, tmdb_id, season, episode, float(position), float(duration), int(bool(watched)), now()))

    def progress_mark(self, kind, tmdb_id, season, episode, watched):
        """Ruční označení: zhlédnuté = bez pozice, nezhlédnuté = záznam se smaže."""
        if watched:
            self.progress_set(kind, tmdb_id, season, episode, 0, 0, True)
        else:
            self.execute('DELETE FROM progress WHERE kind=? AND tmdb_id=? AND season=? AND episode=?',
                         (kind, tmdb_id, season, episode))

    def progress_movies(self):
        return dict((r['tmdb_id'], r) for r in self.query("SELECT * FROM progress WHERE kind='movie'"))

    def progress_episodes(self, tmdb_id):
        rows = self.query("SELECT * FROM progress WHERE kind='episode' AND tmdb_id=?", (tmdb_id,))
        return dict(((r['season'], r['episode']), r) for r in rows)

    def progress_shows(self, limit=15):
        """Seriály, u kterých je něco zhlédnuto, naposledy sledované první."""
        rows = self.query("SELECT tmdb_id, MAX(updated_at) AS last FROM progress WHERE kind='episode' AND watched=1 "
                          "GROUP BY tmdb_id ORDER BY last DESC LIMIT ?", (limit,))
        return [r['tmdb_id'] for r in rows]

    def progress_show_counts(self):
        """Počet zhlédnutých dílů podle seriálu."""
        rows = self.query("SELECT tmdb_id, COUNT(*) AS c FROM progress WHERE kind='episode' AND watched=1 "
                          "GROUP BY tmdb_id")
        return dict((r['tmdb_id'], r['c']) for r in rows)

    def progress_continue(self, limit=50):
        """Rozkoukané tituly (s názvem a obrázky z historie), nejnovější první."""
        return self.query(
            'SELECT h.*, p.position, p.duration, p.watched, p.updated_at FROM progress p '
            'JOIN history h ON h.kind=p.kind AND h.tmdb_id=p.tmdb_id AND h.season=p.season AND h.episode=p.episode '
            'WHERE p.watched=0 AND p.position>0 ORDER BY p.updated_at DESC LIMIT ?', (limit,))

    # ---- abecední index ----
    _VISIBLE = ' AND tmdb_id NOT IN (SELECT tmdb_id FROM hidden WHERE hidden.kind = catalog.kind)'

    def catalog_replace(self, kind, rows):
        self._conn.execute('DELETE FROM catalog WHERE kind=?', (kind,))
        self._conn.executemany(
            'INSERT OR REPLACE INTO catalog (kind, tmdb_id, title, original_title, sort_key, letter, year, '
            'premiered, plot, poster, fanart, rating, votes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            [(kind, r['tmdb_id'], r.get('title'), r.get('original_title'), r['sort_key'], r['letter'],
              r.get('year') or 0, r.get('premiered') or '', r.get('plot') or '', r.get('poster'), r.get('fanart'),
              r.get('rating') or 0, r.get('votes') or 0) for r in rows])
        self._conn.commit()

    def catalog_count(self, kind, letter=None, include_hidden=False):
        sql = 'SELECT COUNT(*) AS c FROM catalog WHERE kind=?' + ('' if include_hidden else self._VISIBLE)
        args = [kind]
        if letter is not None:
            sql += ' AND letter=?'
            args.append(letter)
        return self.one(sql, args)['c']

    def catalog_letters(self, kind):
        """Seznam (písmeno, počet titulů); '#' (číslice a znaky) je první."""
        rows = self.query('SELECT letter, COUNT(*) AS c FROM catalog WHERE kind=?' + self._VISIBLE +
                          ' GROUP BY letter ORDER BY letter', (kind,))
        return [(r['letter'], r['c']) for r in rows]

    def catalog_page(self, kind, letter, limit, offset):
        rows = self.query('SELECT * FROM catalog WHERE kind=? AND letter=?' + self._VISIBLE +
                          ' ORDER BY sort_key, year LIMIT ? OFFSET ?', (kind, letter, limit, offset))
        for row in rows:
            row['language'] = ''
        return rows

    # ---- skryté tituly ----
    def hidden_add(self, kind, tmdb_id, title=''):
        self.execute('INSERT OR REPLACE INTO hidden (kind, tmdb_id, title, hidden_at) VALUES (?,?,?,?)',
                     (kind, tmdb_id, title, now()))

    def hidden_remove(self, kind, tmdb_id):
        self.execute('DELETE FROM hidden WHERE kind=? AND tmdb_id=?', (kind, tmdb_id))

    def hidden_ids(self, kind):
        return set(r['tmdb_id'] for r in self.query('SELECT tmdb_id FROM hidden WHERE kind=?', (kind,)))

    def hidden_list(self):
        return self.query('SELECT * FROM hidden ORDER BY hidden_at DESC')

    # ---- doplňující údaje (délka filmu, počet řad) ----
    def extras_get(self, kind, ids):
        result = {}
        ids = list(ids)
        for start in range(0, len(ids), 200):
            chunk = ids[start:start + 200]
            marks = ','.join('?' * len(chunk))
            for row in self.query('SELECT * FROM extras WHERE kind=? AND tmdb_id IN (%s)' % marks, [kind] + chunk):
                result[row['tmdb_id']] = row
        return result

    def extras_set(self, kind, rows):
        """`rows` = seznam (tmdb_id, délka v minutách, počet řad, počet dílů, číslo série, název série)."""
        self._conn.executemany(
            'INSERT OR REPLACE INTO extras (kind, tmdb_id, runtime, seasons, episodes, collection_id, '
            'collection_name, updated_at) VALUES (?,?,?,?,?,?,?,?)',
            [(kind, r[0], r[1], r[2], r[3], r[4], r[5], now()) for r in rows])
        self._conn.commit()

    # ---- dostupné jazyky streamů ----
    def langs_get(self, kind, ids):
        """Vrátí {(tmdb_id, řada, díl): řádek} pro zadané tituly."""
        result = {}
        ids = list(ids)
        for start in range(0, len(ids), 200):
            chunk = ids[start:start + 200]
            marks = ','.join('?' * len(chunk))
            for row in self.query('SELECT * FROM langs WHERE kind=? AND tmdb_id IN (%s)' % marks, [kind] + chunk):
                result[(row['tmdb_id'], row['season'], row['episode'])] = row
        return result

    def langs_set(self, kind, rows):
        """`rows` = seznam (tmdb_id, řada, díl, jazyky zvuku, jazyky titulků, počet streamů)."""
        self._conn.executemany(
            'INSERT OR REPLACE INTO langs (kind, tmdb_id, season, episode, audio, subs, streams, updated_at) '
            'VALUES (?,?,?,?,?,?,?,?)',
            [(kind, r[0], r[1], r[2], r[3], r[4], r[5], now()) for r in rows])
        self._conn.commit()

    def langs_clear(self):
        self.execute('DELETE FROM langs')

    # ---- historie hledání ----
    def search_add(self, kind, query):
        self.execute('INSERT OR REPLACE INTO search_history (kind, query, used_at) VALUES (?,?,?)',
                     (kind, query, now()))

    def search_list(self, limit=30):
        return self.query('SELECT * FROM search_history ORDER BY used_at DESC LIMIT ?', (limit,))

    def search_clear(self):
        self.execute('DELETE FROM search_history')
