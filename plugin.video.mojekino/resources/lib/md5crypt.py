# -*- coding: utf-8 -*-
"""MD5-crypt ($1$) v čistém Pythonu.

Webshare při přihlášení chce heslo ve tvaru sha1(md5crypt(heslo, sůl)).
Modul `crypt` ze standardní knihovny není v Kodi všude dostupný, proto vlastní
implementace známého algoritmu.
"""
import hashlib

MAGIC = '$1$'
_ITOA64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'


def _to64(value, length):
    out = []
    for _ in range(length):
        out.append(_ITOA64[value & 0x3f])
        value >>= 6
    return ''.join(out)


def md5crypt(password, salt, magic=MAGIC):
    pw = password.encode('utf-8')
    if salt.startswith(magic):
        salt = salt[len(magic):]
    salt = salt.split('$')[0][:8]
    s = salt.encode('utf-8')
    m = magic.encode('utf-8')

    ctx = pw + m + s
    final = hashlib.md5(pw + s + pw).digest()
    remaining = len(pw)
    while remaining > 0:
        ctx += final[:min(16, remaining)]
        remaining -= 16

    i = len(pw)
    while i:
        ctx += b'\x00' if i & 1 else pw[:1]
        i >>= 1
    final = hashlib.md5(ctx).digest()

    for i in range(1000):
        step = pw if i & 1 else final
        if i % 3:
            step += s
        if i % 7:
            step += pw
        step += final if i & 1 else pw
        final = hashlib.md5(step).digest()

    out = ''
    for a, b, c in ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5)):
        out += _to64((final[a] << 16) | (final[b] << 8) | final[c], 4)
    out += _to64(final[11], 2)
    return magic + salt + '$' + out


def webshare_password_hash(password, salt):
    """Tvar hesla, který očekává Webshare API."""
    return hashlib.sha1(md5crypt(password, salt).encode('utf-8')).hexdigest()
