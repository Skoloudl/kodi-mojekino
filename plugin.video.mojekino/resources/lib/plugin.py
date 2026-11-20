# -*- coding: utf-8 -*-
"""Spuštění doplňku: zpracuje adresu, zavolá příslušnou obrazovku a ošetří chyby."""
import traceback

from resources.lib import kodi, router, ui
from resources.lib.kodi import t
from resources.lib.metadata import MetadataError
from resources.lib.providers import ProviderError

# Import registruje obrazovky (@route). Nový soubor s obrazovkami přidejte sem.
from resources.lib.actions import account, browse, discover, lists, play, search  # noqa: F401

# akce, které Kodi volá jako seznam (při chybě je potřeba seznam korektně ukončit)
_FOLDER_ACTIONS = ('root', 'movies', 'shows', 'genres', 'list', 'seasons', 'episodes', 'my', 'my_list',
                   'news', 'history', 'continue', 'search', 'ws_search', 'az', 'az_list', 'hidden',
                   'collection', 'people', 'person')
_PLAY_ACTIONS = ('play', 'play_file', 'play_next')


def _abort(action):
    if action in _FOLDER_ACTIONS:
        ui.fail()
    elif action in _PLAY_ACTIONS:
        play._cancel()


def run(argv):
    params = router.parse(argv[2] if len(argv) > 2 else '')
    action = params.get('action', 'root')
    kodi.debug('akce %s %s' % (action, dict((k, v) for k, v in params.items() if k != 'action')))
    try:
        router.dispatch(params)
    except MetadataError as e:
        _abort(action)
        if e.code == MetadataError.NO_KEY:
            kodi.ok(t('tmdb_help_text'), t('menu_setup_tmdb'))
            kodi.open_settings()
        elif e.code == MetadataError.BAD_KEY:
            kodi.ok(t('err_tmdb_key'))
        else:
            kodi.notify(t('err_tmdb_network'), is_error=True)
    except ProviderError as e:
        _abort(action)
        kodi.notify(play.provider_error_text(e), is_error=True)
    except Exception:
        _abort(action)
        kodi.error(traceback.format_exc())
        kodi.notify(t('err_unexpected'), is_error=True)
