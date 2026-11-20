#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sestaví repozitář pro Kodi do složky docs/ (zveřejňuje ho GitHub Pages).

    python3 tools/build_repo.py

Co udělá:
  1. sestaví zip doplňku (tools/build.py),
  2. z repository.mojekino/addon.xml (šablona s {base} a {author}) a tools/repo.json
     sestaví zip repozitáře,
  3. do docs/ uloží addons.xml, addons.xml.md5, zipy obou doplňků a index.html,
     ze kterého jde zip repozitáře nainstalovat přímo v Kodi (Správce souborů → Přidat zdroj).

Kodi pak nové verze najde samo - stačí zvýšit verzi, spustit tento skript a změny nahrát na GitHub.
"""
import hashlib
import json
import os
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ElementTree

import build

ROOT = build.ROOT
DOCS = os.path.join(ROOT, 'docs')
REPO_ID = 'repository.mojekino'
REPO_DIR = os.path.join(ROOT, REPO_ID)


def config():
    with open(os.path.join(ROOT, 'tools', 'repo.json'), encoding='utf-8') as handle:
        data = json.load(handle)
    if not data.get('github_user') or not data.get('repo'):
        raise SystemExit('V tools/repo.json chybí github_user nebo repo.')
    data['base'] = 'https://%s.github.io/%s/' % (data['github_user'].lower(), data['repo'])
    return data


def repository_xml(settings):
    template = open(os.path.join(REPO_DIR, 'addon.xml'), encoding='utf-8').read()
    return template.replace('{base}', settings['base']).replace('{author}', settings['author'])


def make_repository_zip(settings):
    xml = repository_xml(settings)
    version = ElementTree.fromstring(xml.encode('utf-8')).get('version')
    folder = os.path.join(DOCS, REPO_ID)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, '%s-%s.zip' % (REPO_ID, version))
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('%s/addon.xml' % REPO_ID, xml)
        archive.write(os.path.join(REPO_DIR, 'icon.png'), '%s/icon.png' % REPO_ID)
    shutil.copy(os.path.join(REPO_DIR, 'icon.png'), os.path.join(folder, 'icon.png'))
    # stejný zip i v kořeni pod stálým jménem - na ten odkazuje návod
    shutil.copy(target, os.path.join(DOCS, '%s.zip' % REPO_ID))
    return xml, version


def addon_xml(path):
    with zipfile.ZipFile(path) as archive:
        name = [n for n in archive.namelist() if n.endswith('/addon.xml') and n.count('/') == 1][0]
        return archive.read(name).decode('utf-8')


def strip_declaration(xml):
    return xml.split('?>', 1)[1].strip() if xml.lstrip().startswith('<?xml') else xml.strip()


def main():
    settings = config()
    if build.main() != 0:
        return 1
    version = build.addon_version()
    plugin_zip = os.path.join(build.DIST_DIR, '%s-%s.zip' % (build.ADDON_ID, version))
    os.makedirs(DOCS, exist_ok=True)

    plugin_folder = os.path.join(DOCS, build.ADDON_ID)
    if os.path.isdir(plugin_folder):
        shutil.rmtree(plugin_folder)            # v repozitáři je jen poslední verze
    os.makedirs(plugin_folder)
    shutil.copy(plugin_zip, plugin_folder)
    shutil.copy(os.path.join(build.ADDON_DIR, 'resources', 'icon.png'), os.path.join(plugin_folder, 'icon.png'))

    repo_xml, repo_version = make_repository_zip(settings)
    addons = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n%s\n%s\n</addons>\n' % (
        strip_declaration(addon_xml(plugin_zip)), strip_declaration(repo_xml))
    with open(os.path.join(DOCS, 'addons.xml'), 'w', encoding='utf-8') as handle:
        handle.write(addons)
    with open(os.path.join(DOCS, 'addons.xml.md5'), 'w', encoding='utf-8') as handle:
        handle.write(hashlib.md5(addons.encode('utf-8')).hexdigest())

    index = ('<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>Moje Kino</title></head><body>\n'
             '<h1>Moje Kino – repozitář pro Kodi</h1>\n'
             '<p>Návod: <a href="https://github.com/%(user)s/%(repo)s">github.com/%(user)s/%(repo)s</a></p>\n'
             '<ul>\n<li><a href="%(repo_id)s.zip">%(repo_id)s.zip</a></li>\n'
             '<li><a href="%(addon)s/%(addon)s-%(version)s.zip">%(addon)s-%(version)s.zip</a></li>\n</ul>\n'
             '</body></html>\n') % {'user': settings['github_user'], 'repo': settings['repo'], 'repo_id': REPO_ID,
                                    'addon': build.ADDON_ID, 'version': version}
    with open(os.path.join(DOCS, 'index.html'), 'w', encoding='utf-8') as handle:
        handle.write(index)
    # GitHub Pages nemá složky s podtržítkem apod. zpracovávat jako Jekyll
    open(os.path.join(DOCS, '.nojekyll'), 'w').close()
    print('Repozitář: %s (doplněk %s, repozitář %s) -> %s' % (DOCS, version, repo_version, settings['base']))
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
