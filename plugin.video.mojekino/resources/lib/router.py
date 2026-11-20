# -*- coding: utf-8 -*-
"""Směrování: adresa plugin://…/?action=NAZEV&… zavolá funkci označenou @route('NAZEV').

Nová obrazovka = nová funkce s @route v některém souboru ve složce actions.
"""
from urllib.parse import parse_qsl

ROUTES = {}


def route(name):
    def decorator(func):
        ROUTES[name] = func
        return func
    return decorator


def parse(query):
    return dict(parse_qsl((query or '').lstrip('?'), keep_blank_values=True))


def dispatch(params):
    action = params.get('action', 'root')
    handler = ROUTES.get(action)
    if handler is None:
        raise KeyError('Neznámá akce: %s' % action)
    return handler(params)
