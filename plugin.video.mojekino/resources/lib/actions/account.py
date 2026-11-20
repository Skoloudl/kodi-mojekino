# -*- coding: utf-8 -*-
"""Účet poskytovatele: přihlášení, test VIP, odhlášení."""
import datetime
import json

from resources.lib import context as ctx
from resources.lib import kodi
from resources.lib.kodi import t
from resources.lib.providers import ProviderError
from resources.lib.router import route


def save_vip_state(database, account):
    """Uloží výsledek poslední kontroly (zobrazuje se v hlavním menu)."""
    database.meta_set('vip_state', json.dumps({
        'vip': bool(account.vip), 'days': int(account.vip_days or 0), 'until': account.vip_until or '',
        'checked': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
    }))


def account_text(account):
    lines = [t('account_user', account.username)]
    if account.vip:
        lines.append(t('account_vip_active'))
        lines.append(t('account_vip_days', account.vip_days))
        if account.vip_until:
            lines.append(t('account_vip_until', account.vip_until))
        if account.vip_days <= kodi.setting_int('vip_warn_days', 7):
            lines.append('[COLOR orange]%s[/COLOR]' % t('vip_expiring', account.vip_days))
    else:
        lines.append('[COLOR red]%s[/COLOR]' % t('vip_inactive'))
    return '\n'.join(lines)


def _login(provider):
    username = kodi.keyboard(t('login_username')).strip()
    if not username:
        return None
    password = kodi.keyboard(t('login_password'), hidden=True)
    if not password:
        return None
    try:
        account = provider.login(username, password)
    except ProviderError as e:
        if e.code == ProviderError.BAD_CREDENTIALS:
            kodi.ok(t('err_bad_credentials'))
        else:
            kodi.ok(t('err_network'))
        return None
    return account


@route('account')
def account(params):
    provider = ctx.provider()
    database = ctx.db()
    if not provider.is_logged_in():
        info = _login(provider)
        if info is None:
            return
        save_vip_state(database, info)
        kodi.ok(account_text(info), t('login_ok'))
        kodi.refresh()
        return

    try:
        info = provider.account()
    except ProviderError as e:
        if e.code in (ProviderError.BAD_CREDENTIALS, ProviderError.NOT_LOGGED_IN):
            if kodi.yesno(t('err_session_expired'), yes=t('login_now'), no=t('close')):
                provider.logout()
                database.meta_delete('vip_state')
                kodi.execute('RunPlugin(%s)' % kodi.url_for('account'))
        else:
            kodi.ok(t('err_network'))
        return
    save_vip_state(database, info)
    # tlačítko „Odhlásit“ je záměrně to druhé, aby nešlo zmáčknout omylem
    if kodi.yesno(account_text(info), t('menu_account'), yes=t('logout'), no=t('close')):
        if kodi.yesno(t('logout_confirm')):
            provider.logout()
            database.meta_delete('vip_state')
            kodi.notify(t('logged_out'))
    kodi.refresh()


SOSAC_STATE = 'sosac_state'


def save_sosac_state(database, account):
    """Stav premium Streamuj.tv z poslední kontroly (zobrazuje se v hlavním menu)."""
    if not account.known:
        database.meta_set(SOSAC_STATE, json.dumps({'known': False}))
        return
    database.meta_set(SOSAC_STATE, json.dumps({
        'known': True, 'vip': bool(account.vip), 'until': account.vip_until or '',
        'days': None if account.vip_days is None else int(account.vip_days),
        'checked': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
    }))


def sosac_text(account):
    lines = [t('account_user', account.username)]
    if not account.known:
        lines.append(t('premium_unknown'))
    elif account.vip:
        lines.append(t('premium_active'))
        if account.vip_days is None:
            return '\n'.join(lines)                 # Streamuj.tv neposlal, do kdy premium platí
        lines.append(t('account_vip_days', account.vip_days))
        if account.vip_until:
            lines.append(t('account_vip_until', account.vip_until))
        if account.vip_days <= kodi.setting_int('vip_warn_days', 7):
            lines.append('[COLOR orange]%s[/COLOR]' % t('premium_expiring', account.vip_days))
    else:
        lines.append('[COLOR red]%s[/COLOR]' % t('premium_inactive'))
    return '\n'.join(lines)


@route('account_sosac')
def account_sosac(params):
    """Účet Streamuj.tv pro zdroj Sosáč: přihlášení se stavem premium, nebo odhlášení."""
    source = ctx.sosac()
    database = ctx.db()
    if source.is_logged_in():
        try:
            info = source.account()
        except ProviderError as e:
            if e.code == ProviderError.BAD_CREDENTIALS:
                if kodi.yesno(t('sosac_session_bad'), yes=t('login_now'), no=t('close')):
                    source.logout()
                    database.meta_delete(SOSAC_STATE)
                    kodi.execute('RunPlugin(%s)' % kodi.url_for('account_sosac'))
            else:
                kodi.ok(t('err_network'))
            return
        save_sosac_state(database, info)
        if kodi.yesno(sosac_text(info), t('menu_sosac_account'), yes=t('logout'), no=t('close')):
            source.logout()
            database.meta_delete(SOSAC_STATE)
            kodi.notify(t('sosac_logged_out'))
        kodi.refresh()
        return
    username = kodi.keyboard(t('sosac_username')).strip()
    if not username:
        return
    password = kodi.keyboard(t('sosac_password'), hidden=True)
    if not password:
        return
    try:
        info = source.login(username, password)
    except ProviderError as e:
        if e.code != ProviderError.BAD_CREDENTIALS:
            kodi.ok(t('err_network'))
            return
        # Streamuj.tv účet nepotvrdil - může jít o překlep, nebo o jiný tvar kontroly hesla
        if not kodi.yesno(t('sosac_not_verified'), yes=t('save_anyway'), no=t('close')):
            return
        info = source.login(username, password, force=True)
    save_sosac_state(database, info)
    kodi.ok(sosac_text(info), t('login_ok'))
    kodi.refresh()


@route('clear_cache')
def clear_cache(params):
    database = ctx.db()
    database.cache_clear()
    database.langs_clear()
    kodi.notify(t('cache_cleared'))

