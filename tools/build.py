#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sestaví instalační zip doplňku.

    python3 tools/build.py

Co udělá:
  1. z tabulky textů (resources/lib/strings.py) vygeneruje jazykové soubory,
  2. zkontroluje, že všechny použité texty existují a čísla se neopakují,
  3. zabalí doplněk do dist/plugin.video.mojekino-<verze>.zip.

Verze se bere z addon.xml - před vydáním nové verze ji tam zvyšte a doplňte CHANGELOG.md.
"""
import importlib.util
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ElementTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_ID = 'plugin.video.mojekino'
ADDON_DIR = os.path.join(ROOT, ADDON_ID)
DIST_DIR = os.path.join(ROOT, 'dist')
SKIP_DIRS = ('__pycache__',)
SKIP_FILES = ('.DS_Store',)


def load_strings():
    path = os.path.join(ADDON_DIR, 'resources', 'lib', 'strings.py')
    spec = importlib.util.spec_from_file_location('mojekino_strings', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STRINGS


def _po_escape(text):
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def write_po(strings, language, translated):
    folder = os.path.join(ADDON_DIR, 'resources', 'language', 'resource.language.' + language)
    os.makedirs(folder, exist_ok=True)
    lines = [
        '# Kodi Media Center language file',
        '# Addon id: ' + ADDON_ID,
        '# Generováno nástrojem tools/build.py z resources/lib/strings.py - neupravovat ručně.',
        'msgid ""',
        'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        '"Language: %s\\n"' % language,
        '',
    ]
    for _key, (number, czech, english) in sorted(strings.items(), key=lambda item: item[1][0]):
        lines.append('msgctxt "#%d"' % number)
        lines.append('msgid "%s"' % _po_escape(english))
        lines.append('msgstr "%s"' % (_po_escape(czech) if translated else ''))
        lines.append('')
    with open(os.path.join(folder, 'strings.po'), 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))


def check(strings):
    problems = []
    numbers = {}
    for key, (number, czech, english) in strings.items():
        if number in numbers:
            problems.append('číslo %d je použito dvakrát: %s a %s' % (number, numbers[number], key))
        numbers[number] = key
        if not czech or not english:
            problems.append('text %s nemá oba jazyky' % key)

    used, routes = set(), set()
    for folder, _dirs, files in os.walk(os.path.join(ADDON_DIR, 'resources', 'lib')):
        for name in files:
            if name.endswith('.py') and name != 'strings.py':
                source = open(os.path.join(folder, name), encoding='utf-8').read()
                used.update(re.findall(r"\bt\('([a-z0-9_]+)'", source))
                # klíče předávané nepřímo (tabulky chyb, kategorií a druhů hledání)
                used.update(re.findall(r"'((?:err|cat|search)_[a-z0-9_]+)'", source))
                routes.update(re.findall(r"@route\('([a-z0-9_]+)'\)", source))
    for key in sorted(used - routes):
        if key not in strings and not key.endswith('_'):
            problems.append('v kódu je použit neexistující text: %s' % key)

    settings = open(os.path.join(ADDON_DIR, 'resources', 'settings.xml'), encoding='utf-8').read()
    for number in set(re.findall(r'(?:label="|<heading>)(\d{5})', settings)):
        if int(number) not in numbers:
            problems.append('settings.xml odkazuje na neexistující text %s' % number)
    return problems


def addon_version():
    return ElementTree.parse(os.path.join(ADDON_DIR, 'addon.xml')).getroot().get('version')


def make_zip(version):
    os.makedirs(DIST_DIR, exist_ok=True)
    target = os.path.join(DIST_DIR, '%s-%s.zip' % (ADDON_ID, version))
    count = 0
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for folder, dirs, files in os.walk(ADDON_DIR):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(files):
                if name in SKIP_FILES or name.endswith('.pyc'):
                    continue
                full = os.path.join(folder, name)
                archive.write(full, os.path.relpath(full, ROOT))
                count += 1
    return target, count


def main():
    strings = load_strings()
    problems = check(strings)
    if problems:
        print('Sestavení zastaveno:')
        for problem in problems:
            print('  - ' + problem)
        return 1
    write_po(strings, 'en_gb', translated=False)
    write_po(strings, 'cs_cz', translated=True)
    target, count = make_zip(addon_version())
    print('Hotovo: %s (%d souborů, %d kB)' % (target, count, os.path.getsize(target) // 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
