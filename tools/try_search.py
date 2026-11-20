#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vyzkouší hledání streamů mimo Kodi (bez přihlášení).

Použití:
    python3 tools/try_search.py "Název filmu" 2010
    python3 tools/try_search.py "Název seriálu" 1 2      (sezóna 1, díl 2)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plugin.video.mojekino'))

from resources.lib import streams  # noqa: E402
from resources.lib.providers.webshare import Webshare  # noqa: E402


class _NoStore(object):
    def get(self, key, default=None):
        return default

    def set(self, key, value):
        pass

    def delete(self, key):
        pass


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    titles = [t.strip() for t in argv[1].split('|')]
    provider = Webshare(_NoStore())
    prefs = streams.Prefs()
    if len(argv) >= 4:
        found = streams.find_episode(provider, titles, int(argv[2]), int(argv[3]), prefs)
    else:
        found = streams.find_movie(provider, titles, int(argv[2]), prefs)
    print('Nalezeno: %d' % len(found))
    for c in found[:25]:
        print('%6.1f  %-45s %s' % (c.score, c.label, c.file.name))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
