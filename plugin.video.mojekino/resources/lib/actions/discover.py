# -*- coding: utf-8 -*-
"""Objevování: filmové série, obsazení titulu a tvorba jednotlivých osob."""
import xbmcgui

from resources.lib import context as ctx
from resources.lib import kodi, ui
from resources.lib.actions.browse import add_media, prepare
from resources.lib.kodi import t
from resources.lib.router import route

_JOB_LABEL = {'director': 'people_director', 'writer': 'people_writer', 'creator': 'people_creator'}


@route('collection')
def collection(params):
    """Všechny filmy série v pořadí uvedení. Lze zadat číslo série, nebo film, který do ní patří."""
    tmdb = ctx.tmdb()
    collection_id = int(params.get('id', 0) or 0)
    if not collection_id:
        collection_id, _name = tmdb.collection_of(int(params['movie']))
    if not collection_id:
        ui.fail()
        kodi.notify(t('no_collection'))
        return
    _name, movies = tmdb.collection(collection_id)
    database = ctx.db()
    listing = ui.Listing('movies')
    # krátké filmy tady neschováváme - v sérii je chce člověk vidět všechny
    add_media(listing, 'movie', prepare('movie', movies, tmdb, database, hide_shorts=False), database)
    listing.finish(cache=False)


@route('people')
def people(params):
    """Tvůrci a herci titulu; stiskem se otevře další tvorba dané osoby."""
    kind = params.get('kind', 'movie')
    persons = ctx.tmdb().people(kind, int(params['id']))
    if not persons:
        ui.fail()
        kodi.notify(t('no_people'))
        return
    listing = ui.Listing()
    for person in persons:
        note = t(_JOB_LABEL[person['job']]) if person['job'] in _JOB_LABEL else person['role']
        label = person['name']
        if note:
            label += '  [COLOR gray]%s[/COLOR]' % note
        item = xbmcgui.ListItem(label)
        photo = person['photo'] or ui.ICON_USER
        item.setArt({'icon': photo, 'thumb': photo})
        listing.add(kodi.url_for('person', id=person['id']), item, True)
    listing.finish()


@route('person')
def person(params):
    """Filmy nebo seriály jedné osoby, známější první."""
    person_id = int(params['id'])
    kind = params.get('kind', 'movie')
    page = max(1, int(params.get('page', 1)))
    tmdb = ctx.tmdb()
    _name, movies, shows = tmdb.person(person_id)
    if kind == 'movie' and not movies and shows:
        kind = 'tv'                       # osoba, která točí jen seriály
    titles = movies if kind == 'movie' else shows
    other_kind, other = ('tv', shows) if kind == 'movie' else ('movie', movies)

    size = ctx.page_batches() * 20
    pages = max(1, (len(titles) + size - 1) // size)
    database = ctx.db()
    listing = ui.Listing('movies' if kind == 'movie' else 'tvshows')
    if other and page == 1:
        label = t('person_shows', len(other)) if other_kind == 'tv' else t('person_movies', len(other))
        listing.folder(label, 'person', ui.ICON_SHOWS if other_kind == 'tv' else ui.ICON_MOVIES,
                       id=person_id, kind=other_kind)
    chunk = titles[(page - 1) * size:page * size]
    add_media(listing, kind, prepare(kind, chunk, tmdb, database), database)
    if page < pages:
        listing.folder(t('next_page', page + 1, pages), 'person', ui.ICON_NEXT, id=person_id, kind=kind,
                       page=page + 1)
    if not titles:
        kodi.notify(t('nothing_found'))
    listing.finish(cache=False)
