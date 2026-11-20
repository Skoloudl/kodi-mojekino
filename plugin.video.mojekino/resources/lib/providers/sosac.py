# -*- coding: utf-8 -*-
"""Sosáč: veřejný katalog tv.sosac.to, streamy přes vlastní účet Streamuj.tv.

Sosáč nehledá podle názvů souborů jako Webshare. Má katalog filmů a seriálů s čísly
IMDb, takže titul z TMDB najdeme přesně. Video pak leží na Streamuj.tv - jeho stránka
prozradí jazyky a kvality a s účtem Streamuj.tv vydá odkaz na soubor.

Postup podle doplňku plugin.video.sosac.ph a script.module.stream.resolver
(oba GPL-2.0, kodi-czsk), kód je napsaný znovu.
"""
import datetime
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from resources.lib import http, parser
from resources.lib.providers import AccountInfo, ProviderError, StreamFile, StreamProvider

CATALOG = 'http://tv.sosac.to'
SEARCH = CATALOG + '/jsonsearchapi.php'
SHOW_LETTER = CATALOG + '/vystupy5981/tvpismena/%s.json'
STREAMUJ = 'http://www.streamuj.tv/video/'
WEB_API = 'https://www.streamuj.tv/json_api.php'
USER_AGENT = 'Mozilla/5.0 (X11; Linux armv7l) Kodi/21'
LETTER_TTL = 12 * 3600

_LANG_NAMES = {'cs': 'CZ', 'cz': 'CZ', 'sk': 'SK', 'en': 'EN'}
_RE_FIELD = r'%s\s*:\s*"([^"]*)"'

# abecední seznamy seriálů jsou velké - v rámci jednoho běhu Kodi je stačí stáhnout jednou
_letters = {}
_letters_lock = threading.Lock()


def password_hash(password):
    """Streamuj.tv chce md5(md5(heslo)) - heslo samotné se nikde neukládá."""
    first = hashlib.md5(password.encode('utf-8')).hexdigest()
    return hashlib.md5(first.encode('ascii')).hexdigest()


def parse_expiration(value):
    """Konec premium z odpovědi Streamuj.tv: unixový čas nebo datum; None = bez premium."""
    if value in (None, '', 0, '0', False):
        return None
    text = str(value).strip()
    if text.isdigit():
        number = int(text)
        if number > 10 ** 12:                    # milisekundy
            number //= 1000
        return datetime.datetime.fromtimestamp(number) if number > 10 ** 8 else None
    for pattern in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M',
                    '%d.%m.%Y'):
        try:
            return datetime.datetime.strptime(text[:19], pattern)
        except ValueError:
            continue
    return None


def _imdb_number(value):
    digits = re.sub(r'\D', '', str(value or ''))
    return int(digits) if digits else 0


def _name(names):
    if isinstance(names, dict):
        return names.get('cs') or names.get('en') or ''
    return names or ''


def _letter(title):
    norm = parser.normalize(title)
    if not norm:
        return None
    first = norm[0]
    if first.isdigit():
        return '0-9'
    return first if 'a' <= first <= 'z' else None


def _field(page, name):
    found = re.search(_RE_FIELD % name, page)
    return found.group(1) if found else ''


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Sosac(StreamProvider):
    id = 'sosac'
    name = 'Sosáč'

    def __init__(self, store):
        self._store = store

    # ---- účet Streamuj.tv ----
    def is_logged_in(self):
        return bool(self._store.get('username')) and bool(self._store.get('password_hash'))

    def _api(self, params):
        """Rozhraní webu Streamuj.tv (json_api.php) - to samé, které používá jeho přehrávač."""
        try:
            raw = http.request(WEB_API, params=params, headers={'User-Agent': USER_AGENT}, timeout=10)
            data = json.loads(raw.decode('utf-8'))
        except http.HttpError as e:
            raise ProviderError(ProviderError.NETWORK, str(e))
        except ValueError:
            raise ProviderError(ProviderError.UNKNOWN, 'neplatná odpověď Streamuj.tv')
        return data if isinstance(data, dict) else {}

    def login(self, username, password, force=False):
        """Ověří účet u Streamuj.tv a uloží ho. Heslo se neukládá.

        Ověření dělá stejně jako přihlášení na webu Streamuj.tv: check-user s md5(heslo)
        a passwordinmd5=1. Odpověď: result 0 = špatné jméno nebo heslo, 1 = účet bez premium,
        2 = účet s premium; UID = číslo účtu. Pro přehrávání se uloží md5(md5(heslo)),
        pro pozdější kontrolu premium stačí UID a jméno (bez hesla).
        Špatné údaje vyvolají BAD_CREDENTIALS; s `force` se účet uloží i tak (bez stavu premium).
        """
        data = self._api({'action': 'check-user', 'login': username, 'passwordinmd5': 1,
                          'password': hashlib.md5(password.encode('utf-8')).hexdigest()})
        result = _int(data.get('result'))
        if result not in (1, 2) and not force:
            raise ProviderError(ProviderError.BAD_CREDENTIALS)
        self._store.set('username', username)
        self._store.set('password_hash', password_hash(password))
        self._store.delete('check_secret')               # úložiště z verze 0.7.1 - už se nepoužívá
        uid = _int(data.get('UID'))
        if result in (1, 2) and uid > 0:
            self._store.set('uid', str(uid))
        else:
            self._store.delete('uid')
        if result not in (1, 2):
            return AccountInfo(logged_in=True, username=username, known=False)
        return self._info(username, result == 2, parse_expiration(data.get('expiration')))

    def logout(self):
        for key in ('username', 'password_hash', 'uid', 'check_secret'):
            self._store.delete(key)

    @staticmethod
    def _info(username, premium, expiration):
        """Stav účtu. Premium bez čitelného data konce má vip_days None (dny nejsou známé)."""
        now = datetime.datetime.now()
        if expiration and expiration > now:
            days = (expiration - now).days + (1 if (expiration - now).seconds else 0)
            return AccountInfo(logged_in=True, username=username, vip=True, vip_days=days,
                               vip_until=expiration.strftime('%d.%m.%Y'))
        if premium:
            return AccountInfo(logged_in=True, username=username, vip=True, vip_days=None)
        return AccountInfo(logged_in=True, username=username, vip=False)

    def account(self):
        """Stav premium podle UID z přihlášení (check-premium-status, heslo není potřeba)."""
        if not self.is_logged_in():
            return AccountInfo(logged_in=False)
        username = self._store.get('username', '') or ''
        uid = self._store.get('uid')
        if not uid:
            return AccountInfo(logged_in=True, username=username, known=False)
        data = self._api({'action': 'check-premium-status', 'UID': uid, 'login': username})
        return self._info(username, _int(data.get('result')) == 1, parse_expiration(data.get('expiration')))

    # ---- síť ----
    @staticmethod
    def _get(url, params=None):
        try:
            return http.request(url, params=params, headers={'User-Agent': USER_AGENT}, timeout=10)
        except http.HttpError as e:
            raise ProviderError(ProviderError.NETWORK, str(e))

    def _json(self, url, params=None):
        try:
            return json.loads(self._get(url, params).decode('utf-8'))
        except ValueError:
            raise ProviderError(ProviderError.UNKNOWN, 'neplatná odpověď Sosáče')

    def _page(self, video_id):
        page = self._get(STREAMUJ + video_id).decode('utf-8', 'replace')
        if 'Toto video neexistuje' in page:
            raise ProviderError(ProviderError.NOT_FOUND)
        return page

    def _show_list(self, letter):
        now = time.time()
        with _letters_lock:
            cached = _letters.get(letter)
            if cached and now - cached[0] < LETTER_TTL:
                return cached[1]
        data = self._json(SHOW_LETTER % letter)
        with _letters_lock:
            _letters[letter] = (now, data)
        return data

    # ---- hledání ----
    def search(self, query, limit=50, offset=0, sort=''):
        """Sosáč se prochází přes find() - volné hledání souborů nenabízí."""
        return [], 0

    def find(self, kind, titles, year=0, season=0, episode=0, imdb=''):
        titles = [title for title in titles if title]
        if not titles:
            return []
        if kind == 'movie':
            return self._find_movie(titles, year, _imdb_number(imdb))
        return self._find_episode(titles, year, season, episode, _imdb_number(imdb))

    @staticmethod
    def _same(item, titles, year, imdb):
        if imdb and _imdb_number(item.get('m')):
            return _imdb_number(item.get('m')) == imdb
        raw = item.get('n')
        names = set(parser.normalize(n) for n in (raw.values() if isinstance(raw, dict) else [raw or '']))
        if not names & set(parser.normalize(t) for t in titles):
            return False
        try:
            return not year or abs(int(item.get('y') or 0) - int(year)) <= 1
        except ValueError:
            return False

    def _find_movie(self, titles, year, imdb):
        seen, files = set(), []
        for title in titles[:2]:
            if len(title) < 3:
                continue
            for item in self._json(SEARCH, {'q': title}) or []:
                video_id = item.get('l')
                if not video_id or video_id in seen or not self._same(item, titles, year, imdb):
                    continue
                seen.add(video_id)
                files += self._streams(video_id, titles[0], '%s' % (year or item.get('y') or ''))
            if files:
                break
        return files

    def _find_show(self, titles, year, imdb):
        letters = []
        for title in titles:
            letter = _letter(title)
            if letter and letter not in letters:
                letters.append(letter)
        for letter in letters:
            try:
                shows = self._show_list(letter) or []
            except ProviderError:
                continue                 # seznam pro toto písmeno chybí nebo nejde načíst
            for show in shows:
                if self._same(show, titles, year, imdb):
                    return show
        return None

    def _find_episode(self, titles, year, season, episode, imdb):
        show = self._find_show(titles, year, imdb)
        if not show or not show.get('l'):
            return []
        data = self._json(show['l'])
        for entry in data if isinstance(data, list) else [data]:
            for season_key, episodes in (entry or {}).items():
                if not isinstance(episodes, dict) or _int(season_key) != season:
                    continue
                for episode_key, video in episodes.items():
                    if _int(episode_key) == episode and video.get('l'):
                        return self._streams(video['l'], titles[0], 'S%02dE%02d' % (season, episode))
        return []

    def _streams(self, video_id, title, label):
        """Jazyky a kvality ze stránky Streamuj.tv jako „soubory“ s názvem, kterému rozumí parser."""
        try:
            page = self._page(video_id)
        except ProviderError:
            return []
        langs = [part.split('>')[0].strip().lower() for part in _field(page, 'langs').split(',') if part.strip()]
        qualities = [q.strip().upper() for q in _field(page, 'rn').split(',') if q.strip()]
        files = []
        for lang_index in range(max(len(langs), 1)):
            links = [link for link in _field(page, 'res%d' % lang_index).split(',') if link]
            subs = _field(page, 'sub%d' % lang_index)
            lang = langs[lang_index] if lang_index < len(langs) else ''
            for quality_index in range(len(links)):
                quality = qualities[quality_index] if quality_index < len(qualities) else ''
                words = [title, label, '720p' if quality == 'HD' else 'SD']
                if lang:
                    words.append(_LANG_NAMES.get(lang, lang.upper()))
                if subs:
                    words.append('CZ titulky')
                files.append(StreamFile(self.id, '%s:%d:%d' % (video_id, lang_index, quality_index),
                                        ' '.join(w for w in words if w)))
        return files

    # ---- přehrání ----
    def resolve(self, ident):
        if not self.is_logged_in():
            raise ProviderError(ProviderError.NOT_LOGGED_IN)
        try:
            video_id, lang_index, quality_index = ident.split(':')
            links = [link for link in _field(self._page(video_id), 'res%d' % int(lang_index)).split(',') if link]
            link = links[int(quality_index)]
        except (ValueError, IndexError):
            raise ProviderError(ProviderError.NOT_FOUND)
        link += '&pass=%s:::%s' % (urllib.parse.quote(self._store.get('username', ''), safe=''),
                                   self._store.get('password_hash', ''))
        # odpověď je adresa souboru v těle, případně přesměrování - samotné video se nestahuje
        opener = urllib.request.build_opener(_NoRedirect())
        request = urllib.request.Request(link, headers={'User-Agent': USER_AGENT,
                                                        'Referer': 'http://www.streamuj.tv/mediaplayer/player.swf'})
        try:
            with opener.open(request, timeout=15) as response:
                body = response.read(4096).decode('utf-8', 'replace').strip()
        except urllib.error.HTTPError as e:
            target = e.headers.get('Location', '') if 300 <= e.code < 400 else ''
            if not target:
                raise ProviderError(ProviderError.UNAVAILABLE, 'HTTP %s' % e.code)
            body = target
        except Exception as e:
            raise ProviderError(ProviderError.NETWORK, str(e))
        if not body.startswith('http'):
            raise ProviderError(ProviderError.BAD_CREDENTIALS if 'pass' in body.lower() else ProviderError.UNAVAILABLE,
                                body[:80])
        return body + '|User-Agent=' + urllib.parse.quote(USER_AGENT)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1
