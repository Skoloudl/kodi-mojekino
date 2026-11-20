# -*- coding: utf-8 -*-
"""Malá HTTP vrstva nad standardní knihovnou (bez závislosti na dalších doplňcích)."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = 'MojeKino/0.1 (Kodi addon)'
DEFAULT_TIMEOUT = 15


class HttpError(Exception):
    def __init__(self, message, status=None):
        super(HttpError, self).__init__(message)
        self.status = status


def request(url, params=None, data=None, headers=None, timeout=DEFAULT_TIMEOUT, retries=1):
    """Vrátí tělo odpovědi jako bytes. `data` (dict) znamená POST formulář."""
    if params:
        url = url + ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    body = None
    if data is not None:
        clean = dict((k, v) for k, v in data.items() if v is not None)
        body = urllib.parse.urlencode(clean).encode('utf-8')
    hdrs = {'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'}
    if headers:
        hdrs.update(headers)

    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            # 4xx nemá smysl opakovat (špatný klíč, neexistující stránka...)
            if 400 <= e.code < 500 and e.code != 429:
                raise HttpError('HTTP %s' % e.code, status=e.code)
            last = HttpError('HTTP %s' % e.code, status=e.code)
        except Exception as e:  # síť, timeout, DNS
            last = HttpError(str(e))
        if attempt < retries:
            time.sleep(1.5)
    raise last


def get_json(url, params=None, headers=None, timeout=DEFAULT_TIMEOUT):
    raw = request(url, params=params, headers=headers, timeout=timeout)
    try:
        return json.loads(raw.decode('utf-8'))
    except ValueError:
        raise HttpError('Neplatná odpověď serveru')
