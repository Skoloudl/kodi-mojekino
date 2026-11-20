# -*- coding: utf-8 -*-
"""Smyčka služby: průběžně sleduje přehrávání a jednou za minutu spouští pravidelné úlohy."""
import time
import traceback

import xbmc

from resources.lib import context as ctx
from resources.lib import kodi, upnext
from resources.lib.service import autoplay
from resources.lib.service.jobs import JOBS
from resources.lib.service.tracker import Tracker

START_DELAY = 25      # po startu Kodi chvíli počkáme s úlohami (síť, ostatní doplňky)
TICK = 60             # jak často kontrolovat pravidelné úlohy
POLL = 2              # jak často se ptát přehrávače na pozici a na konec dílu


def _due(database, name, interval):
    if not interval:
        return False
    try:
        last = int(database.meta_get('job_last_' + name, 0) or 0)
    except ValueError:
        last = 0
    return time.time() - last >= interval


def tick(monitor):
    database = ctx.db()
    for name, interval, func in JOBS:
        if monitor.abortRequested():
            return
        if not _due(database, name, interval()):
            continue
        try:
            if func(monitor):
                database.meta_set('job_last_' + name, int(time.time()))
        except Exception:
            kodi.error('úloha %s selhala:\n%s' % (name, traceback.format_exc()))
            # po chybě počkáme celý interval, ať se chyba neopakuje každou minutu
            database.meta_set('job_last_' + name, int(time.time()))


class ServiceMonitor(xbmc.Monitor):
    """Monitor Kodi, který navíc zachytí žádost Up Next o přehrání dalšího dílu."""

    def __init__(self):
        super(ServiceMonitor, self).__init__()
        self.upnext_request = None

    def onNotification(self, sender, method, data):
        request = upnext.play_request(method, data)
        if request:
            self.upnext_request = request

    def pop_upnext_request(self):
        request, self.upnext_request = self.upnext_request, None
        return request


def run():
    monitor = ServiceMonitor()
    kodi.log('služba spuštěna, verze %s' % kodi.version())
    tracker = Tracker()
    next_tick = time.time() + START_DELAY
    while not monitor.abortRequested():
        try:
            tracker.poll()
            request = monitor.pop_upnext_request()
            if request:
                autoplay.play_now(request)
            finished = tracker.pop_finished_episode()
            if finished:
                autoplay.offer(finished, monitor)
            if time.time() >= next_tick:
                next_tick = time.time() + TICK
                tick(monitor)
        except Exception:
            kodi.error(traceback.format_exc())
        if monitor.waitForAbort(POLL):
            break
    kodi.log('služba ukončena')
