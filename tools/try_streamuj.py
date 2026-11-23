#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zkouška přihlášení ke Streamuj.tv mimo Kodi - stejným kódem, jaký používá doplněk.

    python3 tools/try_streamuj.py

Zeptá se na jméno a heslo (heslo se při psaní nezobrazuje a nikam se neukládá) a vypíše, co která
cesta vrátila a jestli se našlo datum konce premium. Heslo ani cookies se nevypisují.
Když se datum nenajde, ukáže se kousek stránky kolem slova „Premium“ - ten pošlete dál.
"""
import getpass
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'plugin.video.mojekino'))
if os.path.exists('/etc/ssl/cert.pem'):
    os.environ.setdefault('SSL_CERT_FILE', '/etc/ssl/cert.pem')      # python.org na Macu nemá certifikáty

from resources.lib.providers import ProviderError, sosac  # noqa: E402


def snippet(page):
    text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', page))
    for word in ('aktivn', 'Premium', 'premium'):
        found = text.find(word)
        if found >= 0:
            return text[max(0, found - 80):found + 160]
    return ''


def main():
    username = input('Streamuj.tv uživatelské jméno: ').strip()
    password = getpass.getpass('Heslo (nezobrazuje se): ')
    print()
    print('1) Rozhraní přehrávače (json_api.php?action=check-user)')
    try:
        data = sosac.Sosac(None)._api({'action': 'check-user', 'login': username, 'passwordinmd5': 1,
                                       'password': hashlib.md5(password.encode('utf-8')).hexdigest()})
        print('   result=%r UID=%r expiration=%r' % (data.get('result'), data.get('UID'), data.get('expiration')))
        print('   přečtené datum: %s' % sosac.parse_expiration(data.get('expiration')))
    except ProviderError as e:
        print('   chyba: %s' % e)
    print('2) Přihlašovací formulář webu (POST /login)')
    try:
        page, cookie = sosac.web_fetch(sosac.WEB_LOGIN, {'username': username, 'password': password,
                                                         'login_remember': 'on', 'action_login': 'Přihlásit se'})
    except ProviderError as e:
        print('   chyba: %s' % e)
        return
    print('   přihlášen: %s, cookie sezení: %s' % (sosac.page_logged_in(page), 'ano' if cookie else 'ne'))
    until = sosac.parse_premium_page(page)
    print('   datum na odpovědi formuláře: %s' % until)
    for path in sosac.WEB_ACCOUNT_PAGES:
        if until or not cookie:
            break
        page, cookie = sosac.web_fetch(path, cookie=cookie)
        until = sosac.parse_premium_page(page)
        print('   stránka %-12s přihlášen: %s, datum: %s' % (path, sosac.page_logged_in(page), until))
        if not until:
            print('   kousek stránky: %r' % snippet(page))
    print()
    print('3) Celý postup doplňku (login + pozdější kontrola bez hesla)')
    store = type('Store', (dict,), {'set': dict.__setitem__, 'delete': lambda s, k: s.pop(k, None)})()
    source = sosac.Sosac(store, log=lambda message: print('   ' + message))
    try:
        info = source.login(username, password)
        print('   login: známo=%s premium=%s do=%s zbývá dní=%s' % (info.known, info.vip, info.vip_until, info.vip_days))
        info = source.account()
        print('   account (bez hesla): známo=%s premium=%s do=%s zbývá dní=%s' % (
            info.known, info.vip, info.vip_until, info.vip_days))
    except ProviderError as e:
        print('   chyba: %s %s' % (e.code, e.detail))


if __name__ == '__main__':
    main()
