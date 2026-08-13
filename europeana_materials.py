"""Europeana — Commons ve Met bos dondugunde bakilan ucuncu arsiv.

NEDEN
-----
Kanal sahibinin karari (2026-08-12): videolarda AI uretimi fotograf
bulunmayacak. Arsiv arzi tek kaynaga bagli kalamaz.

Europeana bir TOPLAYICI: yuzlerce Avrupa kurumunun kataloglarini tek arama
ucunda birlestiriyor. Rijksmuseum'un aksine gercek bir arama ucu var, yani
yerel indeks gerekmiyor.

OLCULDU (2026-08-12, canli uctan). Sayilar sirasiyla: gorseli olan sonuc →
https olan → lisansi gecen → capa kapisindan gecen:

    Tycho Brahe        49 → 38 → 38 → 38
    Friedrich Hayek    50 → 50 → 42 → 39
    Augustus Caesar    50 → 10 → 10 → 10
    Anglo-Dutch War     9 →  9 →  9 →  7
    Harald Rose        50 → 46 → 11 →  1

⚠️ Son satir onemli: Harald Rose Commons'ta LISANS kapisinda dusuyordu ve
"Europeana bunu cozer" diye dusunulmustu. COZMUYOR — 11 uygun gorselin
10'u capa kapisinda eleniyor, kalan tek kayit alakasiz. Kaynak eklemek her
konuyu kurtarmiyor; arama isabeti secilebilir aday DEMEK DEGIL.

LISANS
------
Filtre BEYAZ LISTE ve SUNUCUDA yapiliyor (`qf=RIGHTS:...`). Olculdu: Harald
Rose'da suzgecsiz 50 sonucun 35'i CC BY-SA idi, sunucu suzgeciyle 0.

⚠️ Europeana'nin kendi `reusability=open` filtresi CC BY-SA'yi DA iceriyor —
bizim reddettigimiz lisans. Yani `open` tek basina yetmez, hak alani
ayrica suzulmeli. Pay-benzer sarti videonun TAMAMINI baglar (DW-99, ayni
politika wikimedia_materials.py'de).

⚠️ GUVENLIK — SABIT HOST BEYAZ LISTESI BURADA UYGULANAMIYOR
------------------------------------------------------------
Depo, teslim adreslerinde sabit beyaz liste kullaniyor
(`upload.wikimedia.org`, `images.metmuseum.org`). Europeana bir toplayici
oldugu icin gorsel HER KURUMUN KENDI sunucusunda duruyor. Olculdu: 12
konuluk ornekte 1108 gorsel URL, **105 FARKLI HOST**, ve uzun kuyruk — ilk
50 host ancak %92'yi kapsiyor. Yeni her konu yeni kurumlar getiriyor.

Bu yuzden beyaz liste yerine TELAFI EDICI DENETIMLER kondu:

  * yalnizca https  (olculdu: URL'lerin %19'u duz http; http→https cevirisi
    40 denemede yalnizca 6 kez calisti, 34'u 502 verdi — kurtarmaya
    calismak yerine eleniyor)
  * hostname COZULUYOR ve ozel/yerel/ayrilmis IP'ler REDDEDILIYOR (SSRF)
  * yonlendirmeler elle, en fazla 3 adim, HER ADIM yeniden dogrulaniyor
  * indirme bayt tavanli — sonsuz govde bellegi doldurmasin
  * gelen sey goruntu olarak ACILIYOR; acilmazsa reddediliyor

Bu, sabit beyaz listeden daha zayif bir sinir. Bilerek ve olcerek verilmis
bir karar; kaynagin toplayici olmasinin dogal sonucu.
"""

from __future__ import annotations

import io
import ipaddress
import os
import re
import socket
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests
from PIL import Image

import capa_eslesme

ARAMA_UCU = "https://api.europeana.eu/record/v2/search.json"
KAYIT_SAYFASI = "https://www.europeana.eu/item"
USER_AGENT = "MoneyPrinterTurbo-YouTubeAutomation/1.0"

AZAMI_BAYT = 40 * 1024 * 1024
ASGARI_KENAR = 720
AZAMI_YONLENDIRME = 3
# Bir sorgu icinde kac aday denenir. Tek adayla yetinmek sahneyi tek bir
# kurumun sunucu arizasina baglar (bkz. select_europeana_candidates).
AZAMI_ADAY_DENEMESI = 6

# Okunabilir lisans adi — `format_commons_credits` bu METNE bakiyor:
# `is_safe_license` "public domain"/"cc0" gorurse atif zorunlu degil sayiyor,
# gormezse baglanti + lisans adi yaziyor. Yani buradaki ad, atifin dogru
# yapilip yapilmadigini belirliyor.
HAK_ADLARI = {
    "creativecommons.org/publicdomain/mark": "Public Domain Mark 1.0",
    "creativecommons.org/publicdomain/zero": "CC0 1.0",
    "creativecommons.org/licenses/by/3.0": "CC BY 3.0",
    "creativecommons.org/licenses/by/4.0": "CC BY 4.0",
}
# Sunucu tarafi suzgeci — kabul edilen hak adresleri.
IZINLI_HAKLAR = (
    "http://creativecommons.org/publicdomain/mark/1.0/",
    "http://creativecommons.org/publicdomain/zero/1.0/",
    "http://creativecommons.org/licenses/by/4.0/",
    "http://creativecommons.org/licenses/by/3.0/",
)
YASAKLI_IZLER = ("-sa", "-nc", "-nd")

# met_materials ile ayni kelime kurallari — iki kaynagin secim davranisi
# birbirinden sapmasin.
RELEVANCE_STOPWORDS = {
    "ancient", "archival", "artifact", "historical", "history",
    "image", "museum", "object", "scene", "view",
}
ANCHOR_GENERIC_WORDS = {
    "ancient", "egyptian", "great", "historic", "medieval", "roman",
}


_ANAHTAR_UYARISI_VERILDI = False


class EuropeanaKapali(RuntimeError):
    """Anahtar tanimli degil — kaynak devre disi."""


def _anahtar() -> str:
    """Anahtari config.toml'dan, yoksa ortamdan okur. DEGER ASLA YAZDIRILMAZ.

    ⚠️ Once config.toml'a bakiliyor cunku deponun BUTUN anahtarlari orada
    (`config.app.get(...)`). Yalnizca ortama bakan bir okuma, uretim
    kosumunda anahtari BULAMAZ ve kaynak sessizce devre disi kalirdi —
    hic hata vermeden, yalnizca "aday yok" diyerek.

    ⚠️ .env'deki ad `EUROPEAN_API_KEY` (yazim eksik, dogrusu EUROPEANA).
    Duzgun ad once deneniyor ki ad duzeltilince kod degismesin.
    """
    try:
        from app.config import config

        for ad in ("europeana_api_key", "european_api_key"):
            if deger := str(config.app.get(ad, "") or "").strip():
                return deger
    except Exception:  # noqa: BLE001 - config yoksa ortam denenir
        pass
    for ad in ("EUROPEANA_API_KEY", "EUROPEAN_API_KEY"):
        if deger := (os.environ.get(ad) or "").strip():
            return deger
    raise EuropeanaKapali(
        "europeana_api_key ne config.toml'da ne ortamda tanimli"
    )


def _terms(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(word) >= 4 and word not in RELEVANCE_STOPWORDS
    }


def lisans_adi(hak_url: str) -> str:
    h = (hak_url or "").lower()
    for iz, ad in HAK_ADLARI.items():
        if iz in h:
            return ad
    return ""


def lisans_uygun(hak_url: str) -> bool:
    """Beyaz liste. Kara liste bilerek kullanilmiyor: yeni bir hak turu
    eklendiginde kara liste sessizce ACILIR, beyaz liste acilmaz."""
    h = (hak_url or "").lower()
    if any(k in h for k in YASAKLI_IZLER):
        return False
    return bool(lisans_adi(h))


def guvenli_url(url: str) -> str:
    """https + genel IP dogrulamasi. Gecmezse ValueError.

    Sabit host beyaz listesinin yerine gecen denetim (modul basligindaki
    gerekceye bakin). Amac SSRF: kaynak listesinden gelen bir adres, ic
    aglara veya yerel servislere istek attirmasin.
    """
    ayrisik = urllib.parse.urlsplit(url)
    if ayrisik.scheme != "https":
        raise ValueError(f"yalnizca https kabul ediliyor: {ayrisik.scheme}")
    if not ayrisik.hostname:
        raise ValueError("adreste host yok")
    if ayrisik.port not in (None, 443):
        raise ValueError(f"beklenmeyen port: {ayrisik.port}")
    try:
        bilgiler = socket.getaddrinfo(ayrisik.hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as hata:
        raise ValueError(f"host cozulemedi: {ayrisik.hostname}") from hata
    for bilgi in bilgiler:
        adres = ipaddress.ip_address(bilgi[4][0])
        # `is_global` ozel, yerel, baglanti-yerel, loopback ve ayrilmis
        # bloklarin HEPSINI birden eliyor.
        if not adres.is_global:
            raise ValueError(f"genel olmayan adres: {adres}")
    return url


def _indir_goruntu(url: str, destination: Path) -> None:
    """Goruntuyu indirir; her yonlendirme adimini yeniden dogrular."""
    su_anki = guvenli_url(url)
    for _ in range(AZAMI_YONLENDIRME + 1):
        yanit = requests.get(
            su_anki,
            headers={"User-Agent": USER_AGENT},
            timeout=60,
            stream=True,
            allow_redirects=False,
        )
        if yanit.status_code in (301, 302, 303, 307, 308):
            hedef = yanit.headers.get("Location") or ""
            yanit.close()
            if not hedef:
                raise RuntimeError("yonlendirme adresi bos")
            # Goreli yonlendirme mutlaklastirilip YENIDEN dogrulaniyor.
            su_anki = guvenli_url(urllib.parse.urljoin(su_anki, hedef))
            continue
        yanit.raise_for_status()

        ham = bytearray()
        for parca in yanit.iter_content(64 * 1024):
            ham.extend(parca)
            if len(ham) > AZAMI_BAYT:
                yanit.close()
                raise RuntimeError("goruntu bayt tavanini asti")
        yanit.close()

        # Icerik turune GUVENILMIYOR; dosya gercekten aciliyor mu, ona bakiliyor.
        with Image.open(io.BytesIO(bytes(ham))) as goruntu:
            if goruntu.width < ASGARI_KENAR or goruntu.height < ASGARI_KENAR:
                raise RuntimeError(
                    f"Europeana gorseli cok kucuk: {goruntu.width}x{goruntu.height}"
                )
            goruntu.convert("RGB").save(destination, format="JPEG", quality=92)
        return
    raise RuntimeError("cok fazla yonlendirme")


def _metin_parcalari(oge: dict[str, Any], alan: str) -> list[str]:
    """Europeana alanlari kimi zaman liste, kimi zaman dile gore sozluk."""
    deger = oge.get(alan)
    if deger is None:
        return []
    if isinstance(deger, list):
        return [str(x) for x in deger]
    if isinstance(deger, dict):
        parcalar: list[str] = []
        for ic in deger.values():
            parcalar += [str(x) for x in (ic if isinstance(ic, list) else [ic])]
        return parcalar
    return [str(deger)]


def _sanatci_adi_mi(deger: str) -> bool:
    """Cozulmemis ic kimlikleri sanatci adi saymaz.

    ⚠️ Olculdu (2026-08-12, Tycho Brahe): dcCreator alani "22711_person"
    dondurdu — kurumun ic kimligi, insan adi degil. Bu deger video
    ACIKLAMASINA atif olarak basiliyor, yani gorunen bir kusur. Ayni sey
    URI'ler ve numaralar icin de gecerli.
    """
    ad = (deger or "").strip()
    if not ad or len(ad) < 3:
        return False
    if ad.startswith("http://") or ad.startswith("https://"):
        return False
    if re.fullmatch(r"[\d_\W]+", ad):
        return False
    # "22711_person", "person_4471" gibi kaliplar: rakam + alt cizgi agirlikli.
    if "_" in ad and re.search(r"\d", ad):
        return False
    return True


def _baslik(oge: dict[str, Any]) -> str:
    for parca in _metin_parcalari(oge, "title"):
        if parca.strip():
            return parca.strip()
    return "Europeana kaydi"


def search_europeana(query: str, limit: int = 40) -> list[dict[str, Any]]:
    """Hak suzgeci SUNUCUDA uygulanmis arama sonuclari."""
    qf = "RIGHTS:(" + " OR ".join(f'"{h}"' for h in IZINLI_HAKLAR) + ")"
    yanit = requests.get(
        ARAMA_UCU,
        params={
            "wskey": _anahtar(),
            "query": query,
            "rows": limit,
            "media": "true",
            # Sunucu suzgeci varken bu gereksiz gorunuyor ama duruyor:
            # iki kapi bir kapidan iyi, ve `open` kumesi daralirsa
            # davranis daha kisitlayici olur, daha genis degil.
            "reusability": "open",
            "profile": "rich",
            "qf": qf,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=45,
    )
    yanit.raise_for_status()
    veri = yanit.json()
    if not veri.get("success", False):
        # ⚠️ Europeana hata durumunda da HTTP 200 dondurebiliyor; govdedeki
        # `success` alanina bakilmazsa hata sessizce "sonuc yok" gibi gecer.
        return []
    return veri.get("items", []) or []


def select_europeana_candidates(
    items: list[dict[str, Any]],
    used_ids: set[str],
    query: str,
    required_anchor: str = "",
) -> list[dict[str, Any]]:
    """Uygun adaylarin TAMAMINI puana gore sirali dondurur.

    ⚠️ Neden liste, neden tek aday degil: olculdu (2026-08-12, Tycho Brahe)
    — kapilardan 30 aday geciyordu, ama en yuksek puanli adayin sunucusu
    SSL hatasi verince sahne komple bos kaldi ve "aday yok" gibi gorundu.
    Oysa sonraki adaylarin 4'te 3'u sorunsuz iniyordu.

    Europeana bir toplayici oldugu icin gorseller yuzlerce farkli kurumun
    sunucusunda; tek bir sunucunun cokmesi normal. Commons tarafi da bu
    yuzden aday aday geziyor.
    """
    query_terms = _terms(query)
    anchor_terms = _terms(required_anchor)
    distinctive_anchor_terms = anchor_terms - ANCHOR_GENERIC_WORDS
    required_anchor_terms = distinctive_anchor_terms or anchor_terms
    # ⚠️ Sira sayilari AYRI — `_terms` 4 harften kisalari atiyor, yani
    # "Murad III" yalnizca {"murad"} veriyordu. Gerekcesi `capa_eslesme`de.
    gerekli_sira_sayilari = capa_eslesme.sira_sayilari(required_anchor)

    adaylar: list[tuple[int, dict[str, Any]]] = []
    for oge in items:
        kimlik = str(oge.get("id") or "").strip()
        if not kimlik or kimlik in used_ids:
            continue

        hak = ""
        for h in _metin_parcalari(oge, "rights"):
            if h.strip():
                hak = h.strip()
                break
        if not lisans_uygun(hak):
            continue

        gorsel = ""
        for u in _metin_parcalari(oge, "edmIsShownBy"):
            if u.strip():
                gorsel = u.strip()
                break
        if not gorsel:
            continue
        try:
            guvenli_url(gorsel)
        except ValueError:
            # https degil ya da genel olmayan adres — bu aday atlanir.
            continue

        kanit_parcalari: list[str] = []
        for alan in (
            "title", "dcCreator", "dcDescription", "dcType",
            "dataProvider", "edmConceptPrefLabel", "dcSubject",
        ):
            kanit_parcalari += _metin_parcalari(oge, alan)
        kanit_metni = " ".join(kanit_parcalari).lower()
        kanit = _terms(kanit_metni)

        if required_anchor_terms and not all(
            any(gerekli in terim or terim in gerekli for terim in kanit)
            for gerekli in required_anchor_terms
        ):
            continue
        if not capa_eslesme.sira_sayisi_uyuyor(
            set(re.findall(r"[a-z]+", kanit_metni)), gerekli_sira_sayilari
        ):
            continue
        eslesen = query_terms & kanit
        if query_terms and not eslesen:
            continue

        sanatci = ""
        for a in _metin_parcalari(oge, "dcCreator"):
            if _sanatci_adi_mi(a):
                sanatci = a.strip()
                break

        aday = {
            "id": kimlik,
            "title": _baslik(oge),
            "url": gorsel,
            "source_url": f"{KAYIT_SAYFASI}{kimlik}",
            "license": lisans_adi(hak),
            "artist": sanatci or (
                (_metin_parcalari(oge, "dataProvider") or ["Europeana"])[0]
            ),
        }
        adaylar.append((len(eslesen), aday))

    adaylar.sort(key=lambda oge: oge[0], reverse=True)
    return [aday for _, aday in adaylar]


def select_europeana_candidate(
    items: list[dict[str, Any]],
    used_ids: set[str],
    query: str,
    required_anchor: str = "",
) -> dict[str, Any] | None:
    """En yuksek puanli tek aday (yoksa None)."""
    adaylar = select_europeana_candidates(
        items, used_ids, query, required_anchor=required_anchor
    )
    return adaylar[0] if adaylar else None


def download_europeana_scene_material(
    queries: list[str],
    *,
    scene_number: int,
    target_dir: Path,
    used_ids: set[str],
    required_anchor: str = "",
) -> tuple[Path, dict[str, Any]] | None:
    """Sahne icin Europeana'dan bir gorsel indirir; bulamazsa None.

    ⚠️ Bu modul YARDIMCI bir yol. Anahtar yoksa, ag dusukse veya aday
    bulunamazsa None doner — uretimi DUSURMEZ. Ayni ders DW-95'te Met
    tarafinda ogrenildi: tek bir eksik nesne butun kosumu oldurmustu.
    """
    try:
        _anahtar()
    except EuropeanaKapali:
        # ⚠️ Sessiz devre disilik, calisan bir hattan ayirt edilemiyor:
        # kaynak yokmus gibi degil, "aday bulunamadi" gibi gorunur. Bu
        # yuzden kosum basina BIR KEZ soyleniyor — sahne basina tekrar
        # etmesi gunlugu doldururdu.
        global _ANAHTAR_UYARISI_VERILDI
        if not _ANAHTAR_UYARISI_VERILDI:
            _ANAHTAR_UYARISI_VERILDI = True
            print(
                "ℹ️ Europeana devre disi: europeana_api_key tanimli degil "
                "(config.toml ya da ortam degiskeni).",
                flush=True,
            )
        return None

    for query in queries[:2]:
        try:
            sonuclar = search_europeana(query)
        except (requests.RequestException, ValueError):
            continue
        adaylar = select_europeana_candidates(
            sonuclar, used_ids, query, required_anchor=required_anchor
        )
        hedef = target_dir / f"scene-{scene_number:02d}-europeana.jpg"
        aday = None
        for sirali_aday in adaylar[:AZAMI_ADAY_DENEMESI]:
            try:
                _indir_goruntu(sirali_aday["url"], hedef)
            except (requests.RequestException, ValueError, RuntimeError, OSError):
                # Tek bir kurumun sunucusu cokebilir (SSL, 404, cok kucuk
                # goruntu). Sahneyi birakmadan once SONRAKI adaya bakiliyor.
                time.sleep(0.2)
                continue
            aday = sirali_aday
            break
        if aday is None:
            continue
        # ⚠️ Kimlik `object_id` DEGIL `europeana_id` olarak yaziliyor.
        # youtube_automation.py yeniden deneme yolunda
        # `int(credit["object_id"])` yapiyor; Europeana kimligi metin
        # ("/2020903/KMS1") oldugu icin `object_id` kullanmak o yolu
        # ValueError ile dusururdu.
        kunye = {
            "scene": scene_number,
            "title": aday["title"],
            "source_url": aday["source_url"],
            "license": aday["license"],
            "artist": aday["artist"],
            "provider": "Europeana",
            "europeana_id": aday["id"],
        }
        time.sleep(0.2)
        return hedef, kunye
    return None
