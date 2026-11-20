# -*- coding: utf-8 -*-
"""Sestavení společných objektů (databáze, poskytovatel, katalog) z nastavení.

Menu i služba na pozadí si vše berou odsud, takže výměna poskytovatele nebo
zdroje metadat znamená úpravu jen tohoto souboru.
"""
import os
import uuid

from resources.lib import kodi
from resources.lib.db import Database
from resources.lib.metadata.tmdb import Tmdb
from resources.lib.providers.hellspy import HellSpy
from resources.lib.providers.prehrajto import Prehrajto
from resources.lib.providers.sosac import Sosac
from resources.lib.providers.webshare import Webshare
from resources.lib.streams import Prefs

_db = None

TMDB_LANGUAGES = ('cs-CZ', 'sk-SK', 'en-US')
PREF_LANGUAGES = ('cz', 'en', 'any')
MAX_QUALITIES = (0, 2160, 1080, 720)
PAGE_BATCHES = (1, 2, 3, 5)       # 20 / 40 / 60 / 100 položek na stránku
CATALOG_PAGES = (100, 250, 500)   # abecední seznam: 2 000 / 5 000 / 10 000 titulů
SHORT_FILM_MINUTES = 40


class MetaStore(object):
    """Úložiště malých hodnot poskytovatele (token apod.) v tabulce meta."""

    def __init__(self, database, prefix):
        self._db = database
        self._prefix = prefix + '_'

    def get(self, key, default=None):
        return self._db.meta_get(self._prefix + key, default)

    def set(self, key, value):
        self._db.meta_set(self._prefix + key, value)

    def delete(self, key):
        self._db.meta_delete(self._prefix + key)


def db():
    global _db
    if _db is None:
        _db = Database(os.path.join(kodi.profile_dir(), 'data.db'))
    return _db


def device_uuid():
    value = db().meta_get('device_uuid')
    if not value:
        value = str(uuid.uuid4())
        db().meta_set('device_uuid', value)
    return value


def provider():
    """Hlavní poskytovatel (Webshare) - účet, hledání souborů, jazyky v seznamech."""
    return Webshare(MetaStore(db(), 'webshare'), device_uuid())


def sosac():
    return Sosac(MetaStore(db(), 'sosac'))


def extra_providers():
    """Další zdroje streamů zapnuté v nastavení (Účet → Další zdroje)."""
    result = []
    if kodi.setting_bool('src_sosac', True):
        source = sosac()
        if source.is_logged_in():
            result.append(source)
    if kodi.setting_bool('src_hellspy', True):
        result.append(HellSpy())
    if kodi.setting_bool('src_prehrajto', True):
        result.append(Prehrajto())
    return result


def stream_providers():
    """Všechny zdroje, ve kterých se při přehrání hledá. Webshare (je-li přihlášený) je první."""
    main = provider()
    return ([main] if main.is_logged_in() else []) + extra_providers()


def tmdb():
    index = kodi.setting_int('tmdb_language', 0)
    language = TMDB_LANGUAGES[index] if 0 <= index < len(TMDB_LANGUAGES) else TMDB_LANGUAGES[0]
    return Tmdb(kodi.setting('tmdb_api_key'), db(), language, include_adult=kodi.setting_bool('include_adult'),
                min_runtime=min_runtime())


def min_runtime():
    """Nejkratší film (v minutách), který se má v seznamech zobrazit; 0 = bez omezení."""
    return SHORT_FILM_MINUTES if kodi.setting_bool('hide_shorts', True) else 0


def catalog_pages():
    index = kodi.setting_int('catalog_size', 1)
    return CATALOG_PAGES[index] if 0 <= index < len(CATALOG_PAGES) else 250


def wants_langs():
    """Zjišťovat a ukazovat v seznamech jazyky zvuku a titulků?"""
    return kodi.setting_bool('show_langs', True)


def wants_extras():
    """Je potřeba ke každému titulu zjišťovat délku / počet řad?"""
    return kodi.setting_bool('show_runtime', True) or bool(min_runtime())


def page_batches():
    """Kolik dávek po 20 položkách tvoří jednu stránku seznamu (podle nastavení)."""
    index = kodi.setting_int('page_size', 1)
    return PAGE_BATCHES[index] if 0 <= index < len(PAGE_BATCHES) else 2


def prefs():
    lang = kodi.setting_int('pref_language', 0)
    quality = kodi.setting_int('max_quality', 0)
    return Prefs(
        language=PREF_LANGUAGES[lang] if 0 <= lang < len(PREF_LANGUAGES) else 'cz',
        max_quality=MAX_QUALITIES[quality] if 0 <= quality < len(MAX_QUALITIES) else 0,
        hide_cam=kodi.setting_bool('hide_cam', True),
        min_size_mb=kodi.setting_int('min_size_mb', 50),
    )
