# -*- coding: utf-8 -*-
"""Rozpoznání vlastností videa z názvu souboru (kvalita, jazyk, kodek...).

Čistý Python bez závislosti na Kodi, takže se dá testovat i mimo něj.
"""
import re
import unicodedata

VIDEO_EXTENSIONS = ('mkv', 'mp4', 'avi', 'm4v', 'mov', 'ts', 'm2ts', 'mpg', 'mpeg', 'wmv', 'webm', 'flv', 'divx')

_LANG_WORDS = {
    'cz': 'cz', 'cze': 'cz', 'czech': 'cz', 'cesky': 'cz', 'cestina': 'cz', 'ces': 'cz',
    'sk': 'sk', 'svk': 'sk', 'slo': 'sk', 'slovak': 'sk', 'slovensky': 'sk', 'slovencina': 'sk',
    'en': 'en', 'eng': 'en', 'english': 'en',
}
_SUB_WORDS = ('tit', 'titulky', 'titulkami', 'sub', 'subs', 'subtitles', 'forced')
_DUB_WORDS = ('dabing', 'dab', 'dub', 'dubbing', 'dubbed', 'dabovany', 'dabovane')

_RE_YEAR = re.compile(r'\b(19[2-9]\d|20[0-4]\d)\b')
_RE_EPISODE = re.compile(r'\bs(\d{1,2}) ?e(\d{1,3})\b')
_RE_EPISODE_X = re.compile(r'\b(\d{1,2})x(\d{2,3})\b')
_RE_RESOLUTION = re.compile(r'\b\d{3,4}x(\d{3,4})\b')
_RE_CHANNELS = re.compile(r'(?<!\d)([257])\.([01])(?!\d)')

_QUALITY = (
    (2160, re.compile(r'(?<!\d)2160(?!\d)|\b(4k|uhd[a-z]*)\b')),
    (1080, re.compile(r'(?<!\d)1080(?!\d)|\b(fullhd|fhd)\b')),
    (720, re.compile(r'(?<!\d)720(?!\d)')),
    (480, re.compile(r'\b(480p?|576p?|dvdrip|dvd|xvid|divx|sd)\b')),
)
_SOURCE = (
    ('cam', re.compile(r'\b(cam|camrip|hdcam|telesync|hdts|ts|tc|telecine)\b')),
    ('bluray', re.compile(r'\b(bluray|blu ray|bdrip|brrip|bdremux|remux)\b')),
    ('web', re.compile(r'\b(web ?dl|webrip|web)\b')),
    ('hdtv', re.compile(r'\b(hdtv|tvrip)\b')),
    ('dvd', re.compile(r'\b(dvdrip|dvd)\b')),
)
_CODEC = (
    ('HEVC', re.compile(r'\b(hevc|x265|h ?265)\b')),
    ('AV1', re.compile(r'\bav1\b')),
    ('H264', re.compile(r'\b(x264|h ?264|avc)\b')),
    ('XviD', re.compile(r'\b(xvid|divx)\b')),
)
_RE_HDR = re.compile(r'(\b|u)hdr(10|10plus|dv)?\b|\b(dovi|dolby vision)\b')
_RE_3D = re.compile(r'\b3d\b')
_RE_ATMOS = re.compile(r'\batmos\b')


def normalize(text):
    """Malá písmena, bez diakritiky, vše kromě písmen a číslic jako mezera."""
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def split_extension(name):
    if '.' in name:
        base, ext = name.rsplit('.', 1)
        if ext.lower() in VIDEO_EXTENSIONS:
            return base, ext.lower()
    return name, ''


def _languages(tokens):
    """Rozdělí jazyky v názvu na zvuk a titulky."""
    audio, subs = [], []

    def add(target, lang):
        if lang not in target:
            target.append(lang)

    for i, token in enumerate(tokens):
        prev_token = tokens[i - 1] if i else ''
        next_token = tokens[i + 1] if i + 1 < len(tokens) else ''
        # slepené tvary: cztit, cztitulky, czsub, czdab, czdabing
        glued = re.match(r'^(cz|sk|en|eng)(tit|titulky|sub|subs|dab|dabing|dub)$', token)
        if glued:
            lang = _LANG_WORDS[glued.group(1)]
            add(subs if glued.group(2) in _SUB_WORDS else audio, lang)
            continue
        lang = _LANG_WORDS.get(token)
        if not lang:
            continue
        if next_token in _SUB_WORDS or prev_token in _SUB_WORDS:
            add(subs, lang)
        else:
            add(audio, lang)

    has_dub = any(t in _DUB_WORDS for t in tokens)
    has_sub = any(t in _SUB_WORDS[:3] for t in tokens)
    if has_dub and not audio:
        add(audio, 'cz')       # „dabing“ bez jazyka bývá český
    if has_sub and not subs:
        add(subs, 'cz')        # „titulky“ bez jazyka bývají české
    return audio, subs


def parse(name):
    """Vrátí slovník vlastností rozpoznaných z názvu souboru."""
    base, ext = split_extension(name)
    norm = normalize(base)
    tokens = norm.split()

    years = [int(y) for y in _RE_YEAR.findall(norm)]
    episode = None
    m = _RE_EPISODE.search(norm) or _RE_EPISODE_X.search(norm)
    if m:
        episode = (int(m.group(1)), int(m.group(2)))

    quality = 0
    res = _RE_RESOLUTION.search(norm)
    if res:
        height = int(res.group(1))
        quality = 2160 if height >= 1600 else 1080 if height >= 800 else 720 if height >= 600 else 480
    else:
        for value, rx in _QUALITY:
            if rx.search(norm):
                quality = value
                break

    source = ''
    for value, rx in _SOURCE:
        if rx.search(norm):
            source = value
            break
    codec = ''
    for value, rx in _CODEC:
        if rx.search(norm):
            codec = value
            break

    channels = ''
    ch = _RE_CHANNELS.search(base)
    if ch:
        channels = '%s.%s' % ch.groups()

    # Jazyk hledáme až za rokem / označením dílu / kvalitou, aby se slova
    # z názvu filmu (např. „En“) nepletla s jazykem.
    start = len(norm)
    for rx in (_RE_YEAR, _RE_EPISODE, _RE_EPISODE_X) + tuple(q[1] for q in _QUALITY):
        found = rx.search(norm)
        if found:
            start = min(start, found.start())
    tail = norm[start:].split() if start < len(norm) else tokens
    audio, subs = _languages(tail)

    return {
        'name': name, 'normalized': norm, 'extension': ext,
        'years': years, 'episode': episode,
        'quality': quality, 'source': source, 'codec': codec,
        'hdr': bool(_RE_HDR.search(norm)), '3d': bool(_RE_3D.search(norm)),
        'channels': channels, 'atmos': bool(_RE_ATMOS.search(norm)),
        'audio': audio, 'subs': subs,
    }
