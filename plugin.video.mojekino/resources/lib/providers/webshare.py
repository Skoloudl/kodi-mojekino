# -*- coding: utf-8 -*-
"""Klient pro veřejné API Webshare (přihlášení, stav účtu, hledání, odkaz na soubor)."""
import xml.etree.ElementTree as ElementTree

from resources.lib import http
from resources.lib.md5crypt import webshare_password_hash
from resources.lib.providers import AccountInfo, ProviderError, StreamFile, StreamProvider

API = 'https://webshare.cz/api'

_LINK_ERRORS = {
    'FILE_LINK_FATAL_1': ProviderError.NOT_FOUND,
    'FILE_LINK_FATAL_3': ProviderError.PASSWORD,
    'FILE_LINK_FATAL_4': ProviderError.UNAVAILABLE,
    'FILE_LINK_FATAL_5': ProviderError.TOO_MANY,
}


def _int(text, default=0):
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


class _MemoryStore(object):
    """Úložiště jen v paměti - pro hledání z vedlejších vláken, kam databáze nesmí."""

    def __init__(self, values=None):
        self._values = dict(values or {})

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value

    def delete(self, key):
        self._values.pop(key, None)


class Webshare(StreamProvider):
    id = 'webshare'
    name = 'Webshare'

    def __init__(self, store, device_uuid=''):
        """`store` je úložiště malých hodnot s metodami get/set/delete (viz storage.MetaStore).

        Ukládá se jen uživatelské jméno, otisk hesla a token - heslo v čitelné podobě nikdy.
        """
        self._store = store
        self._uuid = device_uuid
        self._http = {}              # případné zkrácení čekání na odpověď (viz detached)

    # ---- nízká úroveň ----
    def _post(self, path, data=None, token=True):
        payload = dict(data or {})
        if token:
            payload['wst'] = self._store.get('token', '')
        try:
            raw = http.request(API + path, data=payload, headers={'Referer': 'https://webshare.cz/'}, **self._http)
        except http.HttpError as e:
            raise ProviderError(ProviderError.NETWORK, str(e))
        try:
            return ElementTree.fromstring(raw)
        except ElementTree.ParseError:
            raise ProviderError(ProviderError.UNKNOWN, 'neplatná odpověď')

    @staticmethod
    def _ok(root):
        return root.findtext('status', '') == 'OK'

    # ---- přihlášení ----
    def is_logged_in(self):
        return bool(self._store.get('token')) and bool(self._store.get('username'))

    def _token_for(self, username, password_hash):
        root = self._post('/login/', {'username_or_email': username, 'password': password_hash,
                                      'keep_logged_in': 1}, token=False)
        if not self._ok(root):
            raise ProviderError(ProviderError.BAD_CREDENTIALS, root.findtext('code', ''))
        return root.findtext('token', '')

    def login(self, username, password):
        root = self._post('/salt/', {'username_or_email': username}, token=False)
        if not self._ok(root):
            raise ProviderError(ProviderError.BAD_CREDENTIALS, root.findtext('code', ''))
        password_hash = webshare_password_hash(password, root.findtext('salt', ''))
        token = self._token_for(username, password_hash)
        self._store.set('username', username)
        self._store.set('password_hash', password_hash)
        self._store.set('token', token)
        return self.account()

    def relogin(self):
        """Obnoví token z uloženého otisku hesla (token časem vyprší)."""
        username = self._store.get('username')
        password_hash = self._store.get('password_hash')
        if not username or not password_hash:
            raise ProviderError(ProviderError.NOT_LOGGED_IN)
        self._store.set('token', self._token_for(username, password_hash))

    def logout(self):
        for key in ('username', 'password_hash', 'token'):
            self._store.delete(key)

    def account(self):
        if not self.is_logged_in():
            return AccountInfo(logged_in=False)
        root = self._post('/user_data/')
        if not self._ok(root):
            self.relogin()
            root = self._post('/user_data/')
            if not self._ok(root):
                raise ProviderError(ProviderError.BAD_CREDENTIALS, root.findtext('code', ''))
        return AccountInfo(
            logged_in=True,
            username=root.findtext('username', '') or self._store.get('username', ''),
            vip=root.findtext('vip', '0') == '1',
            vip_days=_int(root.findtext('vip_days', '')),
            vip_until=root.findtext('vip_until', '') or '',
        )

    # ---- hledání a přehrání ----
    def search(self, query, limit=50, offset=0, sort=''):
        root = self._post('/search/', {'what': query, 'category': 'video', 'sort': sort,
                                       'limit': limit, 'offset': offset})
        if not self._ok(root):
            raise ProviderError(ProviderError.UNKNOWN, root.findtext('code', ''))
        files = []
        for node in root.iter('file'):
            ident = node.findtext('ident', '')
            name = node.findtext('name', '')
            if not ident or not name:
                continue
            files.append(StreamFile(
                provider=self.id, ident=ident, name=name,
                size=_int(node.findtext('size', '')),
                positive=_int(node.findtext('positive_votes', '')),
                negative=_int(node.findtext('negative_votes', '')),
                protected=node.findtext('password', '0') == '1',
            ))
        return files, _int(root.findtext('total', ''), len(files))

    def detached(self, timeout=6):
        """Nepřihlášená kopie jen pro hledání: nesahá do databáze a na odpověď čeká kratší dobu."""
        copy = Webshare(_MemoryStore(), self._uuid)
        copy._http = {'timeout': timeout, 'retries': 0}
        return copy

    def resolve(self, ident, _retry=True):
        if not self.is_logged_in():
            raise ProviderError(ProviderError.NOT_LOGGED_IN)
        root = self._post('/file_link/', {'ident': ident, 'download_type': 'video_stream',
                                          'device_uuid': self._uuid})
        link = root.findtext('link', '')
        if self._ok(root) and link:
            return link
        code = root.findtext('code', '')
        if code in _LINK_ERRORS:
            raise ProviderError(_LINK_ERRORS[code], code)
        if _retry:
            # nejčastější důvod neznámé chyby je vypršený token
            self.relogin()
            return self.resolve(ident, _retry=False)
        raise ProviderError(ProviderError.UNKNOWN, code)
