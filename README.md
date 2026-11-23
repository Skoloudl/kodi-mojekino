# Moje Kino – doplněk pro Kodi

Osobní katalog filmů a seriálů s vlastními seznamy a hlídáním novinek. Přehrává přes
váš vlastní účet Webshare a volitelně ze Sosáče (účet Streamuj.tv), HellSpy a Přehraj.to.
Doplněk nemá žádný server – vše běží přímo v Kodi.

Určeno pro Kodi 20/21 (LibreELEC 11/12), Python 3.

## Instalace (s automatickými aktualizacemi)

Všechno se dělá přímo v Kodi, ovladačem:

1. **Nastavení → Systém → Doplňky** → zapněte **Neznámé zdroje**.
2. **Nastavení → Správce souborů → Přidat zdroj** → do adresy napište
   `https://skoloudl.github.io/kodi-mojekino/` a zdroj pojmenujte `mojekino`.
3. **Doplňky → Instalovat ze souboru zip** → `mojekino` → `repository.mojekino.zip`.
4. **Doplňky → Instalovat z repozitáře → Moje Kino – repozitář → Video doplňky → Moje Kino** → Instalovat.
5. V doplňku otevřete **Nastavení → Obecné** a vložte **TMDB API klíč**
   (zdarma na themoviedb.org → Nastavení účtu → API).
6. V hlavním menu doplňku se přihlaste k **Účtu Webshare**, případně k **Účtu Streamuj.tv** pro Sosáč.
   HellSpy a Přehraj.to účet nepotřebují.

Nové verze pak Kodi stáhne samo (kontroluje jednou denně; hned: dlouhý stisk na repozitáři →
Zkontrolovat aktualizace). Nastavení, seznamy i přihlášení zůstanou zachovány.

Každý používá **vlastní** účty a vlastní TMDB klíč – doplněk žádné nesdílí ani nikam neposílá.

## Právní upozornění

Moje Kino je jen přehrávač a vyhledávač. Samo žádný obsah nehostuje ani nešíří; soubory leží
na službách třetích stran a přehrávají se přímo odtud přes účty uživatele. Doplněk neověřuje,
zda je soubor legální. Používejte ho jen k obsahu, ke kterému máte právo – za to, co přehráváte,
odpovídáte vy.

## Co doplněk umí

- **Filmy / Seriály** – novinky, populární, trendy, žánry, hledání.
- **Přehrání** – po výběru titulu najde soubory ve všech zapnutých zdrojích najednou, seřadí je podle jazyka
  a kvality a nabídne výběr (nebo vybere sám, je-li to zapnuto v nastavení). Každý stream má barevný štítek
  kvality (UHD 4K, FHD 1080, HD 720, SD, případně HDR / CAM / 3D), jazyk zvuku (český a slovenský zeleně),
  velikost, kodek a zvuk; na druhém řádku je barevně zdroj a název souboru.
- **Filtr streamů** – první řádek výběru („Filtr: zdroj, zvuk, kvalita, titulky…“, s počty streamů podle zdrojů)
  otevře okno filtru. Zúžit lze podle zdroje, zvuku (CZ, SK, EN), kvality (4K až SD) a titulků; filtry se kombinují
  a nabízejí jen hodnoty, které ve výsledcích opravdu jsou, s počty.
- **Moje seznamy** – přes kontextové menu (dlouhý stisk OK / klávesa C) přidáte film
  do „Filmy ke zhlédnutí“ nebo u seriálu zvolíte „Hlídat nové díly“.
- **Hlídané** – na pozadí kontroluje, zda vyšel nový díl hlídaného seriálu nebo zda se k filmu
  ze seznamu objevil stream. Položka „Hlídané“ v hlavním menu ukazuje nové díly (jdou rovnou pustit)
  a u každého seriálu stav: čeká na stream / kdy vyjde další díl.
- **Účet** – test přihlášení a VIP, upozornění na končící předplatné (počet dní lze nastavit).
- **Stránkování** – 20 až 100 položek na stránku (Nastavení → Obecné → Seznamy). Řádek
  „Strana X z Y · načteno HH:MM“ nahoře v seznamu umí skočit na libovolnou stranu nebo seznam načíst znovu.
- **Zhlédnuto a rozkoukané** – služba na pozadí ukládá, kde jste skončili. Zhlédnuté tituly jsou
  označené, rozkoukané najdete v hlavním menu a Kodi u nich nabídne pokračování.

- **Seriály** – po dokoukání dílu se sám spustí další ve stejném jazyce a kvalitě (dotaz předem lze zapnout).
  Díly se pouští jako playlist, takže v přehrávači funguje přeskočení na další / předchozí díl.
  S doplňkem **Up Next** se ke konci dílu ukáže jeho okénko „Další díl“ s odpočtem (Zavřít pokračování zruší).
  U sezón a sledovaných seriálů je ukazatel zhlédnutých dílů, „Rozkoukané“ nabízí další díl k přehrání.
- **Další zdroje** – Nastavení → Účet → Další zdroje streamů: Sosáč (účet Streamuj.tv, titul se páruje
  podle IMDb), HellSpy a Přehraj.to (bez účtu, video převedené serverem). Hledá se ve všech zapnutých
  zdrojích najednou, u streamu je vidět, odkud je. Účet Streamuj.tv je v hlavním menu se stavem a datem konce
  premium („premium do 21.12.2026 (28 dní)“), služba upozorní na končící premium. Hlídač novinek hledá
  na Webshare a Sosáči, jazyky v seznamech zatím používají jen Webshare.
- **Titulky** – u streamů bez českého zvuku se otevře hledání titulků Kodi. Je k tomu potřeba
  doplněk pro titulky (Doplňky → Instalovat z repozitáře → Titulky → OpenSubtitles.com) a účet u něj.
  V Nastavení → Streamy → Titulky lze zvolit, co se stane při spuštění: nechat na Kodi, zapnout české/slovenské
  titulky ze streamu (když zvuk není česky ani slovensky), nebo titulky vždy vypnout. Titulky vpálené přímo
  do obrazu se vypnout nedají; ostatní se přepínají v přehrávači (klávesa T).
- **Objevování** – v kontextovém menu titulu: „Podobné tituly“, „Celá série“ (filmové série v pořadí
  uvedení) a „Herci a tvůrci“ s proklikem na další tvorbu dané osoby.
- **Abecedně** – Filmy / Seriály → Abecedně. Doplněk si sám udržuje index nejznámějších titulů
  (velikost v nastavení) a řadí je podle písmen; obnovuje ho jednou týdně na pozadí.
- **Skrytí titulů** – krátké filmy pod 40 minut se nezobrazují (lze vypnout); cokoli dalšího
  skryjete přes kontextové menu a vrátíte v Moje seznamy → Skryté tituly.
- **Jazyky** – v seznamech je u titulu vidět, v jakém zvuku a s jakými titulky má streamy
  (zjišťuje se u Webshare při prvním otevření seznamu, pamatuje se 3 dny; lze vypnout).
- **Hodnocení** – v názvu je rok, hodnocení z TMDB v procentech a délka filmu nebo počet řad. Hodnocení z ČSFD přidat nejde,
  web ČSFD je chráněn proti automatickému čtení.

## Struktura projektu

```
plugin.video.mojekino/        samotný doplněk (tohle se balí do zipu)
  addon.xml                   název, verze, závislosti
  main.py, service.py         vstupní body (menu / služba na pozadí)
  resources/settings.xml      stránka nastavení
  resources/lib/
    strings.py                všechny texty (česky + anglicky)
    plugin.py, router.py      spuštění a směrování akcí
    actions/                  obrazovky: browse, discover, play, lists, search, account
    ui.py, kodi.py            stavba položek, dialogy, nastavení
    context.py                sestavení databáze, poskytovatele a katalogu
    providers/                zdroje streamů (webshare, sosac, hellspy, prehrajto)
    upnext.py                 spolupráce s doplňkem Up Next
    metadata/                 zdroje informací o titulech (tmdb.py)
    streams.py, parser.py     hledání, rozpoznání a řazení streamů
    availability.py           dostupné jazyky streamů do seznamů
    watcher.py                hlídač novinek
    service/                  smyčka služby a pravidelné úlohy
    db.py                     databáze a její migrace
repository.mojekino/          šablona repozitáře pro Kodi (adresu doplní tools/build_repo.py)
docs/                         zveřejněný repozitář pro Kodi (GitHub Pages) - generuje se, neupravovat
tools/build.py                sestavení zipu (generuje i jazykové soubory)
tools/build_repo.py           sestavení repozitáře do docs/ (nastavení v tools/repo.json)
tools/try_search.py           vyzkoušení hledání streamů mimo Kodi
tools/make_icon.py            vygenerování ikony
tools/make_badges.swift       vygenerování štítků kvality (resources/media; jen macOS)
tools/try_streamuj.py         vyzkoušení přihlášení ke Streamuj.tv mimo Kodi (heslo se zeptá, nikam se neukládá)
tests/test_all.py             testy (běží bez Kodi a bez sítě)
```

## Vývoj

```bash
python3 tests/test_all.py     # testy
python3 tools/build.py        # zip do složky dist/
```

Vydání nové verze: zvyšte `version` v `addon.xml`, doplňte `CHANGELOG.md`, spusťte testy
a `python3 tools/build_repo.py`, pak změny (včetně `docs/`) nahrajte na GitHub. Kodi si novou verzi stáhne samo.

### Jak doplněk rozšířit

| Chci přidat | Kde |
|---|---|
| novou obrazovku nebo akci | funkce s `@route('nazev')` v `resources/lib/actions/`; nový soubor doplnit do importu v `plugin.py` |
| nový text | `resources/lib/strings.py` s dalším volným číslem (stará čísla neměnit), pak `tools/build.py` |
| novou volbu v nastavení | `resources/settings.xml` + popisek ve `strings.py` (čísla 30000–30099) |
| změnu databáze | nový krok na konec `MIGRATIONS` v `db.py` (existující kroky neupravovat) |
| pravidelnou úlohu na pozadí | funkce v `service/jobs.py` a řádek v seznamu `JOBS` |
| další úložiště | třída odvozená od `StreamProvider` v `providers/`, zapojit v `context.py` (`extra_providers`), název do `NAMES` v `providers/__init__.py`; zdroj s vlastním katalogem implementuje `find()` |
| jiný zdroj informací o titulech | modul v `metadata/` vracející stejné slovníky jako `tmdb.py`, zapojit v `context.py` |
| lepší rozpoznání názvů souborů | `parser.py` (vlastnosti) a `streams.py` (shoda a bodování) + test |

### Náměty na další verze

- synchronizace zhlédnutého a seznamů mezi více Kodi (přes Home Assistant),
- titulky (stažení k přehrávanému titulu),
- propojení s Trakt (synchronizace seznamů a zhlédnutého).

## Soukromí

Hesla k Webshare ani Streamuj.tv se neukládají. V profilu doplňku (`userdata/addon_data/plugin.video.mojekino/data.db`)
jsou uložené jen otisky hesel a přihlašovací token – tento soubor nikomu neposílejte.

## Licence

GPL-2.0-or-later. Doplněk nehostuje ani nešíří žádný obsah.
