# -*- coding: utf-8 -*-
"""Poskytovatelé streamů.

Každý poskytovatel (úložiště) je třída odvozená od StreamProvider. Další úložiště
se přidá jako nový soubor v této složce, zapojí se v `context.py` (stream_providers)
a jeho název se doplní do NAMES - zbytek doplňku se měnit nemusí.
"""

# zobrazované názvy poskytovatelů podle id (u streamu ve výběru)
NAMES = {'webshare': 'Webshare', 'sosac': 'Sosáč', 'hellspy': 'HellSpy', 'prehrajto': 'Přehraj.to'}

# Poskytovatelé, kteří nepouští původní soubor, ale video převedené serverem (H.264, nejvýš
# uvedená kvalita). Kvalita z názvu souboru i jeho velikost tu o streamu nic neříkají.
TRANSCODED = {'hellspy': 720, 'prehrajto': 1080}


class ProviderError(Exception):
    """Chyba poskytovatele s kódem, podle kterého UI vybere hlášku."""
    NOT_LOGGED_IN = 'not_logged_in'
    BAD_CREDENTIALS = 'bad_credentials'
    NOT_FOUND = 'not_found'
    UNAVAILABLE = 'unavailable'
    TOO_MANY = 'too_many'
    PASSWORD = 'password'
    NETWORK = 'network'
    UNKNOWN = 'unknown'

    def __init__(self, code, detail=''):
        super(ProviderError, self).__init__('%s %s' % (code, detail))
        self.code = code
        self.detail = detail


class StreamFile(object):
    """Jeden soubor nalezený u poskytovatele."""
    __slots__ = ('provider', 'ident', 'name', 'size', 'positive', 'negative', 'protected')

    def __init__(self, provider, ident, name, size=0, positive=0, negative=0, protected=False):
        self.provider = provider
        self.ident = ident
        self.name = name
        self.size = size
        self.positive = positive
        self.negative = negative
        self.protected = protected

    def to_dict(self):
        return dict((k, getattr(self, k)) for k in self.__slots__)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


class AccountInfo(object):
    def __init__(self, logged_in=False, username='', vip=False, vip_days=0, vip_until='', known=True):
        self.logged_in = logged_in
        self.username = username
        self.vip = vip
        self.vip_days = vip_days
        self.vip_until = vip_until
        self.known = known           # False = stav předplatného nejde zjistit


class StreamProvider(object):
    id = 'base'
    name = 'Base'

    def is_logged_in(self):
        raise NotImplementedError

    def login(self, username, password):
        raise NotImplementedError

    def logout(self):
        raise NotImplementedError

    def account(self):
        """Vrátí AccountInfo (ověří přihlášení a stav předplatného)."""
        raise NotImplementedError

    def search(self, query, limit=50, offset=0, sort=''):
        """Vrátí (seznam StreamFile, celkový počet)."""
        raise NotImplementedError

    def find(self, kind, titles, year=0, season=0, episode=0, imdb=''):
        """Poskytovatel s vlastním katalogem (např. Sosáč) tu vrátí soubory k titulu přímo.

        None = poskytovatel katalog nemá a streamy se hledají podle názvů souborů (search).
        """
        return None

    def resolve(self, ident):
        """Vrátí přímou adresu pro přehrání souboru."""
        raise NotImplementedError

    def detached(self):
        """Objekt se stejnou metodou search(), který smí běžet ve vedlejších vláknech
        (nesmí sahat do databáze doplňku). Výchozí: poskytovatel sám."""
        return self
