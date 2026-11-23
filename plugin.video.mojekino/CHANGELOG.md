# Seznam změn

## 0.8.3
- **Filtr ve výběru streamu.** První řádek seznamu („Filtr: zdroj, zvuk, kvalita, titulky…“, pod ním počty
  streamů z jednotlivých zdrojů) otevře okno filtru. Každý řádek v něm ukazuje zvolenou hodnotu a po stisku
  nabídne jen hodnoty, které ve výsledcích opravdu jsou, s počty: **zdroj** (Webshare, Sosáč…), **zvuk**
  (CZ, SK, EN, neoznačeno), **kvalita** (4K, 1080p, 720p, SD) a **titulky** (CZ, SK, EN, bez titulků).
  Filtry se dají kombinovat – počty se přepočítávají podle ostatních zvolených filtrů. „Zobrazit streamy“
  vrátí zúžený seznam, „Zrušit filtr“ všechno zruší. U krátkých seznamů z jednoho zdroje se řádek nenabízí.
- **Titulky při přehrání** (Nastavení → Streamy → Titulky): „Podle nastavení Kodi“ (výchozí), „Zapnout
  české/slovenské, když zvuk není česky ani slovensky“ (použije stopu titulků ve streamu, je-li) a „Vždy
  vypnout“. Titulky vpálené přímo do obrazu se vypnout nedají.

## 0.8.2
- **Výběr streamu: filtr podle zdroje.** Streamy ze Sosáče nebyly vidět, protože u titulů s anglickým zvukem
  a českými titulky jsou v seřazeném seznamu hluboko pod dabovanými kopiemi z Webshare, Přehraj.to a HellSpy
  (u jednoho dílu to bylo 75 položek). Nahoře je teď řádek „Zdroj: všechny – zúžit na jeden…“ s počty
  streamů z každého zdroje; po výběru zdroje se v seznamu ukážou jen jeho streamy.

## 0.8.1
- Přihlášení ke Streamuj.tv zapisuje do logu Kodi (po zapnutí Nastavení → Pokročilé → Ladění), která cesta
  účet potvrdila a jestli se našlo datum konce premium. Hesla ani cookies se nezapisují.

## 0.8.0
- **Oprava: po skončení dílu se nespustil další.** S nainstalovaným doplňkem Up Next odebral doplněk
  další díl z playlistu a čekal na okénko Up Next – to se ale u playlistu neukáže, takže se nespustilo nic.
  Teď doplněk pošle Up Next adresu dalšího dílu a těsně před okénkem mu playlist uvolní; Up Next si díl
  zařadí sám (okénko „Další díl“ s odpočtem, „Zavřít“ pokračování zruší). Když se okénko neukáže,
  díl se před koncem vrátí do playlistu a spustí se v každém případě. Tlačítko „další“ (⏭) funguje dál.
- **Výběr streamu se štítky kvality:** místo obrázku promítačky je u každého streamu barevný štítek
  UHD 4K / FHD 1080 / HD 720 / SD (s HDR, CAM, 3D). Vedle něj jazyk zvuku (český a slovenský zeleně),
  velikost, kodek a zvuk; na druhém řádku barevně zdroj a název souboru.
- **Hlídané** – nová položka v hlavním menu. Nahoře jsou nové díly a filmy, které hlídač našel
  (dají se rovnou pustit), pod nimi hlídané seriály se stavem: „čeká na stream: S02E05“,
  „další díl S02E06 · 28.11.“ nebo „seriál skončil“. Seriál přidáte v kontextovém menu volbou
  „Hlídat nové díly“ (dříve „Sledovat seriál“).
- Hlídač hledá nové díly kromě Webshare i na Sosáči (je-li přihlášený účet Streamuj.tv).
- **Streamuj.tv: přihlášení a konec premium.** Když rozhraní přehrávače účet odmítne, přihlásí se doplněk
  stejně jako web (formulářem) a ze stránky účtu přečte „Premium účet máte aktivní do“. V hlavním menu
  je pak „premium do 21.12.2026 (28 dní)“. Heslo se dál neukládá; ukládá se cookie sezení a datum konce.

## 0.7.2
- **Oprava:** přihlášení ke Streamuj.tv (Sosáč) hlásilo chybné jméno nebo heslo i u správného účtu.
  Doplněk se ptal jiného rozhraní, než používá web Streamuj.tv. Teď ověřuje účet stejně jako přihlášení
  na webu (check-user s md5 hesla) a stav premium zjišťuje podle čísla účtu – bez hesla.
- Když Streamuj.tv potvrdí premium, ale nepošle datum konce, ukáže se „premium“ bez počtu dní.

## 0.7.1
- **Oprava:** po spuštění dílu ze seznamu se místo něj za pár sekund pustil hned další díl. Kodi
  odmítnutý odkaz připsalo prvnímu dílu playlistu a přeskočilo ho. Díly se teď spouští tak, že Kodi
  na odkaz nečeká a playlist pustí doplněk sám.
- U rozkoukaného dílu se doplněk sám zeptá „Pokračovat od 12:34 / Přehrát od začátku“; pozice je
  v seznamu dílů i v Rozkoukaných vidět jako ▶ 12:34.
- Při hledání streamů dílu je vpravo dole vidět „Hledám streamy…“.
- Ve výběru streamu je u každého streamu napsané, odkud je – i u Webshare.
- Když některý zdroj neodpoví (Webshare, HellSpy…), objeví se upozornění „Neodpověděl zdroj: …“
  místo tichého vynechání jeho streamů.
- **Účet Streamuj.tv** (Sosáč) je v hlavním menu se stavem premium („premium 23 dní“). Při přihlášení
  doplněk účet ověří u Streamuj.tv a ukáže, do kdy platí premium; služba jednou denně upozorní
  na končící nebo neaktivní premium (stejné nastavení jako u VIP Webshare).

## 0.7.0
- **Přeskočení na další díl:** díl seriálu se pouští jako playlist, takže v přehrávači funguje tlačítko
  „další“ (⏭) i „předchozí“ (⏮). Stream dalšího dílu se hledá až po přeskočení, ve stejném jazyce a kvalitě.
- Na konci dílu přejde Kodi na další díl samo (jako dřív). Když je zapnutý dotaz předem nebo automatické
  přehrání vypnuté, další díl se z playlistu 20 sekund před koncem odebere.
- **Up Next:** je-li nainstalovaný doplněk Up Next, ukáže ke konci dílu své okénko „Další díl“ s obrázkem
  a odpočtem. Lze vypnout: Nastavení → Streamy → Okénko dalšího dílu přes Up Next.
- Volba „Pokračovat od …“ v okně Kodi platí i pro díly pouštěné jako playlist.
- **Další zdroje streamů** (Nastavení → Účet → Další zdroje streamů), hledá se ve všech najednou:
  - **Sosáč** – katalog tv.sosac.to, titul se páruje přesně podle čísla IMDb; přehrává přes účet
    Streamuj.tv (Nastavení → Účet → Účet Streamuj.tv). Heslo se neukládá, jen jeho otisk.
  - **HellSpy** – bez účtu, video převedené serverem do 720p.
  - **Přehraj.to** – bez účtu, video převedené do 1080p, jen první strana výsledků. Když web odmítne
    příliš mnoho dotazů, zdroj se na 10 minut vynechá.
- Ve výběru streamu je u streamů z dalších zdrojů vidět jejich název. U převáděného videa se ukazuje
  skutečná kvalita přehrávání, ne kvalita z názvu souboru. Stejný soubor z HellSpy a Přehraj.to je
  ve výběru jen jednou a původní soubor z Webshare má přednost před převodem.
- Výpadek jednoho zdroje hledání v ostatních nezastaví.

## 0.6.0
- V seznamech filmů, seriálů i dílů jsou vidět dostupné jazyky zvuku a titulků, např. „CZ, EN · tit. CZ“.
  Doplněk se na ně ptá Webshare při prvním otevření seznamu (nejvýš 10 sekund) a pamatuje si je 3 dny.
  Lze vypnout: Nastavení → Obecné → Zobrazovat jazyky zvuku a titulků.
- Další díl se po dokoukání spustí rovnou, bez potvrzování. Dotaz s 10 sekundami na zrušení lze zapnout
  v Nastavení → Streamy → Před dalším dílem se zeptat.

## 0.5.1
- Oprava: po odpočtu na další díl mohlo Kodi zamrznout. Další díl teď spouští služba přímo přehrávačem
  (už ne přes PlayMedia a čekací okno Kodi) a místo okna s odpočtem je běžný dotaz „Přehrát hned / Zrušit“,
  který se po 10 sekundách potvrdí sám. Když Kodi právě něco spouští nebo má otevřené jiné okno,
  služba se do toho neplete.
- Na konec dílu služba reaguje rychleji (do 2 sekund místo 5).
- Délka filmu je v seznamu jen jednou – v názvu. Po vypnutí „Zobrazit délku“ ji vypisuje vzhled Kodi (2:28).

## 0.5.0
- Kontextové menu „Podobné tituly“ u filmů i seriálů (doporučení z TMDB).
- „Celá série“ u filmů, které patří do filmové série – všechny díly v pořadí uvedení.
- „Herci a tvůrci“ – obsazení titulu s fotkami; stiskem se otevřou další filmy a seriály dané osoby.

## 0.4.0
- Abecední seznam filmů a seriálů (Filmy / Seriály → Abecedně): vlastní index nejznámějších titulů
  (2 000 / 5 000 / 10 000), řazený podle písmen; obnovuje se sám jednou týdně.
- V názvu je kromě hodnocení i rok a délka filmu, u seriálů počet řad.
- Krátké filmy pod 40 minut se v seznamech nezobrazují (bonusy a epizody vedené jako film); lze vypnout.
- Kontextové menu „Skrýt titul v seznamech“ a seznam skrytých titulů v Moje seznamy.

## 0.3.0
- Po dokoukání dílu se s odpočtem (10 s, lze zrušit) spustí další díl ve stejném jazyce a kvalitě.
- Další díly téhož seriálu se i při ručním výběru řadí podle naposledy přehraného streamu.
- Ukazatel zhlédnutých dílů u sezón a sledovaných seriálů, např. [3/10].
- „Rozkoukané“ nabízí u každého sledovaného seriálu další díl k přehrání; v kontextovém menu
  seriálu je „Přehrát další díl“.
- Titulky: u streamů bez českého zvuku se po spuštění otevře hledání titulků Kodi
  (vyžaduje nainstalovaný doplněk pro titulky, např. OpenSubtitles.com).
- Hodnocení (TMDB) v procentech přímo v názvu v seznamech.
- Skok na stranu je výraznější (nahoře i dole v seznamu), v hlavním menu je vidět verze doplňku.
- Kontextové menu: vlastní položky jsou nahoře, „Odebrat z rozkoukaných“.

## 0.2.0
- Seznamy: volitelně 20 / 40 / 60 / 100 položek na stránku (výchozí 40).
- Řádek „Strana X z Y · načteno HH:MM“ nahoře v seznamu: skok na libovolnou stranu,
  nové načtení seznamu, návrat na první stranu.
- Zhlédnuté tituly a díly jsou označené, rozkoukané si pamatují pozici a Kodi nabídne pokračování.
- Nová položka „Rozkoukané“ v hlavním menu; ruční označení zhlédnuto / nezhlédnuto v kontextovém menu.
- U „Zkontrolovat nyní“ je vidět čas poslední kontroly hlídače.
- Volba „Zobrazovat i obsah pro dospělé“ (hledání a žánry), výchozí vypnuto.

## 0.1.0
První verze.

- Katalog filmů a seriálů z TMDB: novinky, populární, trendy, nejlépe hodnocené, žánry, hledání.
- Přehrávání přes vlastní účet Webshare, výběr streamu s rozpoznanou kvalitou a jazykem,
  volitelně automatický výběr nejlepšího streamu.
- Moje seznamy: filmy ke zhlédnutí a sledované seriály.
- Hlídač novinek na pozadí: nové díly sledovaných seriálů a filmy ze seznamu, ke kterým se objevil stream.
- Kontrola účtu: test přihlášení a VIP, upozornění na končící předplatné.
- Historie přehrávání a hledání, ruční hledání souborů.
