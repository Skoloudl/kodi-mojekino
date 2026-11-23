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
from http.cookiejar import CookieJar

from resources.lib import http, parser
from resources.lib.providers import AccountInfo, ProviderError, StreamFile, StreamProvider

CATALOG = 'http://tv.sosac.to'
SEARCH = CATALOG + '/jsonsearchapi.php'
SHOW_LETTER = CATALOG + '/vystupy5981/tvpismena/%s.json'
STREAMUJ = 'http://www.streamuj.tv/video/'
WEB_API = 'https://www.streamuj.tv/json_api.php'
WEB = 'https://www.streamuj.tv'
WEB_LOGIN = '/login'
WEB_ACCOUNT_PAGES = ('/', '/my_profile')     # kde web po přihlášení ukazuje „Premium účet máte aktivní do“
WEB_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
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


_RE_ACTIVE_UNTIL = re.compile(r'aktivn\w*\s+do\b(.{0,160})', re.I | re.S)
_RE_DATE = re.compile(r'(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?')
_RE_LOGGED = re.compile(r'logout|odhl[aá]sit|V[ií]tejte\s*,', re.I)
_RE_BAD_LOGIN = re.compile(r'errorbox[^>]*>[^<]*(jm[eé]no|heslo)', re.I)


def parse_premium_page(page):
    """Konec premium ze stránky účtu („Premium účet máte aktivní do: 21.12.2026 03:56:38“), jinak None."""
    found = _RE_ACTIVE_UNTIL.search(page or '')
    if not found:
        return None
    date = _RE_DATE.search(re.sub(r'<[^>]+>', ' ', found.group(1)))
    if not date:
        return None
    day, month, year, hour, minute, second = (int(part or 0) for part in date.groups())
    try:
        return datetime.datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def page_logged_in(page):
    """Je stránka webu zobrazená přihlášenému uživateli? True / False (odmítnuté údaje) / None (nejde poznat)."""
    if _RE_BAD_LOGIN.search(page or ''):
        return False
    if _RE_LOGGED.search(page or '') or parse_premium_page(page):
        return True
    return None


def web_fetch(path, data=None, cookie=''):
    """Stránka webu Streamuj.tv jako text + cookies sezení. `data` (dict) = odeslání formuláře."""
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = {'User-Agent': WEB_USER_AGENT, 'Referer': WEB + '/'}
    if cookie:
        headers['Cookie'] = cookie
    body = urllib.parse.urlencode(data).encode('utf-8') if data is not None else None
    try:
        with opener.open(urllib.request.Request(WEB + path, data=body, headers=headers), timeout=15) as response:
            page = response.read(400000).decode('utf-8', 'replace')
    except Exception as e:       # síť, timeout, HTTP chyba
        raise ProviderError(ProviderError.NETWORK, str(e))
    fresh = '; '.join('%s=%s' % (c.name, c.value) for c in jar)
    return page, fresh or cookie


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

    def __init__(self, store, log=None):
        self._store = store
        self._log = log or (lambda message: None)     # ladicí zpráva do logu Kodi (bez hesel a cookies)

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

        Dvě cesty, stejné jako na webu Streamuj.tv:
          1. rozhraní přehrávače: check-user s md5(heslo) a passwordinmd5=1. Odpověď: result 0 =
             odmítnuto, 1 = účet bez premium, 2 = účet s premium; UID = číslo účtu.
          2. přihlašovací formulář webu - použije se, když rozhraní účet nepotvrdí nebo nepošle datum
             konce premium (některé účty odmítá, i když na webu fungují). Stránka účtu po přihlášení
             ukazuje „Premium účet máte aktivní do: …“. Heslo jde jen na streamuj.tv přes HTTPS.
        Pro přehrávání se uloží md5(md5(heslo)); pro pozdější kontrolu premium UID, cookie sezení
        a naposledy zjištěné datum konce. Odmítnuté údaje vyvolají BAD_CREDENTIALS; s `force` se
        účet uloží i tak (bez stavu premium).
        """
        data, failure = {}, None
        try:
            data = self._api({'action': 'check-user', 'login': username, 'passwordinmd5': 1,
                              'password': hashlib.md5(password.encode('utf-8')).hexdigest()})
        except ProviderError as e:
            failure = e
        result = _int(data.get('result'))
        expiration = parse_expiration(data.get('expiration'))
        self._log('Streamuj.tv rozhraní: result=%s, expiration=%r -> datum %s' % (
            result, data.get('expiration'), expiration))
        web_ok, cookie = None, ''
        if result not in (1, 2) or expiration is None:
            web_ok, web_until, cookie = self._web_login(username, password)
            expiration = web_until or expiration
        verified = result in (1, 2) or web_ok is True
        self._log('Streamuj.tv výsledek přihlášení: ověřeno=%s, web=%s, konec premium=%s' % (
            verified, web_ok, expiration))
        if not verified and not force:
            if failure is not None and web_ok is None:
                raise failure                            # nešlo ověřit ani jednou cestou (síť)
            raise ProviderError(ProviderError.BAD_CREDENTIALS)
        self._store.set('username', username)
        self._store.set('password_hash', password_hash(password))
        self._store.delete('check_secret')               # úložiště z verze 0.7.1 - už se nepoužívá
        uid = _int(data.get('UID'))
        if result in (1, 2) and uid > 0:
            self._store.set('uid', str(uid))
        else:
            self._store.delete('uid')
        if web_ok is True and cookie:
            self._store.set('web_cookie', cookie)
        else:
            self._store.delete('web_cookie')
        self._remember_until(expiration if verified else None)
        if not verified or (expiration is None and result not in (1, 2)):
            return AccountInfo(logged_in=True, username=username, known=False)
        return self._info(username, result == 2, expiration)

    def _web_login(self, username, password):
        """Přihlášení formulářem webu. Vrací (přihlášeno True/False/None, konec premium, cookie)."""
        try:
            page, cookie = web_fetch(WEB_LOGIN, {'username': username, 'password': password,
                                                 'login_remember': 'on', 'action_login': 'Přihlásit se'})
        except ProviderError:
            return None, None, ''
        logged = page_logged_in(page)
        self._log('Streamuj.tv web: po odeslání formuláře přihlášen=%s, cookie=%s, premium text=%s' % (
            logged, bool(cookie), 'aktivn' in page))
        if logged is False:
            return False, None, ''
        until = parse_premium_page(page)
        for path in WEB_ACCOUNT_PAGES:
            if until is not None or not cookie:
                break
            try:
                page, cookie = web_fetch(path, cookie=cookie)
            except ProviderError:
                continue
            if logged is None:
                logged = page_logged_in(page) or None    # nepřihlášená stránka tu ještě nic nedokazuje
            until = parse_premium_page(page)
            self._log('Streamuj.tv web: stránka %s přihlášen=%s, datum=%s' % (path, logged, until))
        return logged, until, cookie

    def _remember_until(self, expiration):
        if expiration:
            self._store.set('premium_until', str(int(time.mktime(expiration.timetuple()))))
        else:
            self._store.delete('premium_until')

    def _stored_until(self):
        try:
            stamp = int(self._store.get('premium_until') or 0)
            return datetime.datetime.fromtimestamp(stamp) if stamp > 0 else None
        except (TypeError, ValueError, OverflowError, OSError):
            return None

    def logout(self):
        for key in ('username', 'password_hash', 'uid', 'check_secret', 'web_cookie', 'premium_until'):
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
        """Stav premium bez hesla: podle UID (check-premium-status), ze stránky účtu přes uloženou
        cookie sezení, a když neodpoví ani jedno, podle data konce zjištěného při přihlášení."""
        if not self.is_logged_in():
            return AccountInfo(logged_in=False)
        username = self._store.get('username', '') or ''
        uid, cookie = self._store.get('uid'), self._store.get('web_cookie')
        premium, expiration, known, failure = False, None, False, None
        if uid:
            try:
                data = self._api({'action': 'check-premium-status', 'UID': uid, 'login': username})
                premium, known = _int(data.get('result')) == 1, True
                expiration = parse_expiration(data.get('expiration'))
            except ProviderError as e:
                failure = e
        if known and not premium and expiration is None:
            # rozhraní zná účet a hlásí, že premium nemá - starší uložené datum už neplatí
            self._remember_until(None)
            return self._info(username, False, None)
        if cookie and expiration is None:
            for path in WEB_ACCOUNT_PAGES:
                try:
                    expiration = parse_premium_page(web_fetch(path, cookie=cookie)[0])
                except ProviderError:
                    break
                if expiration is not None:
                    break
        if expiration is not None:
            self._remember_until(expiration)
        else:
            expiration = self._stored_until()
        if expiration is None and not known:
            if failure is not None:
                raise failure
            return AccountInfo(logged_in=True, username=username, known=False)
        return self._info(username, premium, expiration)

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
