from __future__ import annotations

import html
import itertools
import json
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

import requests

import capa_eslesme
import gorsel_olcum
from europeana_materials import download_europeana_scene_material
from met_materials import download_met_scene_material

API_URL = "https://commons.wikimedia.org/w/api.php"
VIKIPEDI_API_URL = "https://en.wikipedia.org/w/api.php"
VIKIVERI_API_URL = "https://www.wikidata.org/w/api.php"
VIKIPEDI_OZET_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
"""Ingilizce Vikipedi ozet ucu — anahtarsiz, kotasiz."""

_VARSAYILAN_UA = (
    "MoneyPrinterTurbo-YouTubeAutomation/1.0 "
    "(+https://github.com/harry0703/MoneyPrinterTurbo)"
)
USER_AGENT = os.environ.get("WIKIMEDIA_USER_AGENT", "").strip() or _VARSAYILAN_UA
"""Wikimedia'nin User-Agent politikasina uyan tanitici dize.

⚠️ ILETISIM BILGISI SUS DEGIL, ZORUNLU (olculdu 2026-08-12). Dize eskiden
"MoneyPrinterTurbo-YouTubeAutomation/1.0" idi ve upload.wikimedia.org gorsel
indirmelerine 429 doneyip iki uretim kosumunu ust uste dusurdu.

Once sebebi kendi yukume bagladim (ayni anda arsiv arzi taramasi
yapiyordum) — YANLISTI. Kontrol olcumu, ayni URL, saniyeler arayla, tek
degisken UA:

    ShemzHistoryShorts/1.0                                    → 429
    MoneyPrinterTurbo/1.0 (https://example.org; bot@x)        → 200
    MoneyPrinterTurbo-YouTubeAutomation/1.0                   → 429

Yani engellenen sey ne IP'miz ne de "MoneyPrinterTurbo" adi: ILETISIM
BILGISI TASIMAYAN ciplak "Ad/Surum" bicimi. Isim iletisim bilgisiyle
birlikte gecince 200 donuyor. Sira ters cevrilerek de dogrulandi
(200/429/200), yani kova zamanlamasi degil.

`WIKIMEDIA_USER_AGENT` ile ezilebiliyor: politika "size ulasabilelim" diyor
ve buradaki adres yalnizca yazilimi tanitiyor, isleticiye ulastirmiyor.
Kanal sahibinin kendi e-postasini ya da kanal adresini disaridan koyabilmesi
icin — kimsenin kisisel adresi koda gomulmedi.
"""
SAFE_LICENSE_MARKERS = ("public domain", "pd-", "cc0")
"""Kosulsuz kullanilabilen lisanslar — atif bile gerekmiyor."""

ATIF_LISANS_ISARETLERI = ("cc by",)
"""Yalnizca ATIF isteyen lisanslar. Share-alike (BY-SA) BURAYA GIRMEZ.

⚠️ Olculdu (2026-08-06, DW-99): yalnizca PD/CC0 kabul edilirken ayakta duran
anitlarin gercek fotograflarinin **%78'i** reddediliyordu. Uc sorgu, 90 aday:

    20  Public domain + CC0    kabul
    30  CC BY                  RED  ← yalnizca atif istiyor, biz zaten yapiyoruz
    40  CC BY-SA               RED  ← share-alike, disarida birakildi

Sonucu somuttu: Machu Picchu videosunda 8 sahnenin 7'si AI oldu cunku arsiv
tek bir gorsel verebildi. Oysa Commons'ta binlerce Machu Picchu fotografi var.

**CC BY-SA bilerek disarida.** "Share-alike" turev eserin ayni lisansla
yayinlanmasini istiyor; bu, videonun tamamının CC BY-SA olmasi anlamina
gelebilir ve baskalarinin videoyu alip kullanmasina kapi acar. Bu bir is
karari; kullanici PD/CC0 + CC BY'de karar kildi.

⚠️ Metin eslesmesi TUZAKLI: "cc by-sa 4.0" metni "cc by" iceriyor. Naif bir
`in` kontrolu share-alike'i de gecirirdi — `atif_gerektiren` once SA'yi
disliyor, sonra BY'ye bakiyor. Bir test bu tuzagi kilitliyor.
"""
REQUEST_INTERVAL_SECONDS = 1.0
DELIVERY_PROXY_URL = "https://images.weserv.nl/"
GENERIC_SEARCH_WORDS = {
    "ancient",
    "archival",
    "historic",
    "historical",
    "illustration",
    "old",
    "traditional",
}
RELEVANCE_STOPWORDS = GENERIC_SEARCH_WORDS | {
    "building",
    "historic",
    "photo",
    "scene",
    "setting",
    "stone",
    "structure",
    "view",
}
ANCHOR_GENERIC_WORDS = {
    "ancient",
    "egyptian",
    "great",
    "historic",
    "medieval",
    "roman",
}


class MaterialsUnavailableError(RuntimeError):
    pass


def _get_with_retry(
    url: str,
    *,
    timeout: int,
    params: dict[str, str] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_attempts: int = 5,
) -> requests.Response:
    for attempt in range(max_attempts):
        sleep_fn(REQUEST_INTERVAL_SECONDS)
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
        except (requests.Timeout, requests.ConnectionError):
            # ⚠️ Gecici ag hatasi 429 ile ayni sekilde tekrar denenmeli.
            # Onceden yalnizca 429 tekrarlaniyordu ve tek bir ReadTimeout
            # butun koshumu olduruyordu: konu secimi, senaryo, TTS ve uretilmis
            # gorseller bosa gidiyor — yani gecici bir ag hatasinin bedeli
            # harcanan LLM/gorsel parasi oluyor.
            #
            # Olculdu (2026-08-05): images.weserv.nl bir kez 60 saniyede
            # yanit vermedi ve tam bir uretim koshumu coptu. Ayni URL 20 saniye
            # sonra 200 ve 473 KB dondu, yani hata gercekten geciciydi.
            if attempt == max_attempts - 1:
                raise
            sleep_fn(float(2 ** (attempt + 1)))
            continue
        # 429 VE 5xx tekrar denenir; ikisi de gecici.
        #
        # ⚠️ 5xx once atlanmisti ve ayni koshum bu kez "504 Gateway Timeout"
        # ile dustu — istemci zaman asimini yakalamak yetmiyor, teslim
        # proxy'si (weserv) hatayi kendi tarafinda da uretebiliyor. Bir onbellek
        # proxy'sinden gelen 502/503/504 tanimi geregi gecici; kalicilarsa
        # asagidaki son deneme zaten yukseltiyor.
        if response.status_code != 429 and not (500 <= response.status_code < 600):
            response.raise_for_status()
            return response
        if attempt == max_attempts - 1:
            response.raise_for_status()
        retry_after = response.headers.get("Retry-After", "")
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            delay = float(2 ** (attempt + 1))
        sleep_fn(max(delay, 0.0))
    raise RuntimeError("unreachable Wikimedia retry state")


def vikipedi_ozeti(konu: str, *, timeout: int = 15) -> str:
    """Konunun Ingilizce Vikipedi ozeti. Bulunamazsa BOS DONER, patlamaz.

    ⚠️ NEDEN VAR — olculdu (2026-08-09, DW-114): huniden gelen "Franziska
    Scanagatta" konusu icin model, senaryoyu ve etiketleri tamamen UYDURDU:
    "Italian opera", "19th century music", "opera history". Gercekte
    Scanagatta, 1794'te Theresian Askeri Akademisi'ne girmek icin erkek
    kiligina giren ve Habsburg ordusunda subay olarak gorev yapan bir kadin.
    Opera ile hicbir ilgisi yok.

    Kusur YAPISAL, tek bir konunun sanssizligi degil: `generate_content_plan`
    modele yalnizca konunun ADINI veriyordu. Unlu konularda (Kolezyum, Chaco
    Canyon) modelin kendi bilgisi yetiyor ve sorun gorunmuyor. Ama huninin
    VARLIK SEBEBI arzin az oldugu konulari bulmak — ve bir konu hakkinda az
    video olmasinin en yaygin sebebi, o konunun az bilinmesi. Yani huni tam
    da modelin bilmedigi konulari seciyor, model de bosluğu uydurmayla
    dolduruyor. Huni ne kadar iyi calisirsa uydurma riski o kadar artiyor.

    Cozum kaynagi modele vermek. Aday zaten bir Vikipedi maddesinden geliyor
    (huni okunma sayilarini oradan olcuyor), yani dogru metin elimizde.

    Bos donmek bilincli: ozet yoksa uretim durmamali, ama plan istemi de
    "kaynak yok" bilgisini gormeli ve modelden bildigini soylemesi degil,
    bilmedigini soylemesi istenmeli.
    """
    try:
        yanit = _get_with_retry(
            VIKIPEDI_OZET_URL + urllib.parse.quote(konu.replace(" ", "_"), safe=""),
            timeout=timeout,
            max_attempts=2,
        )
    except (requests.RequestException, RuntimeError):
        return ""
    try:
        veri = yanit.json()
    except ValueError:
        return ""
    # Belirsizlik sayfasi bir kaynak degil: "X birden fazla seye isaret
    # edebilir" metni modele hicbir olgu vermez, yanlis dala sapmasina yol acar.
    if veri.get("type") == "disambiguation":
        return ""
    return str(veri.get("extract") or "").strip()


TAM_METIN_AZAMI_KELIME = 6000
"""Modele verilen kaynak metnin tavani.

15 dakikalik bir video ~2.000 kelime konusuyor; kaynagin ondan belirgin
genis olmasi gerekiyor ki model SECEBILSIN, ama sinirsiz da olmamali —
uzun makaleler (Roman aqueduct 7.539 kelime) baglami ve maliyeti bosuna
sisirir.
"""

# Makalenin GOVDESI disindaki bolumler: modele olgu vermiyorlar, yer
# kapliyorlar ve kaynakca satirlari senaryoya sizabiliyor.
_ATILACAK_BOLUMLER = (
    "references",
    "external links",
    "see also",
    "further reading",
    "bibliography",
    "notes",
    "citations",
    "sources",
)


def vikipedi_tam_metin(
    konu: str, *, azami_kelime: int = TAM_METIN_AZAMI_KELIME, timeout: int = 20
) -> str:
    """Konunun Vikipedi makalesinin TAM govdesi. Bulunamazsa BOS DONER.

    ⚠️ NEDEN OZET YETMIYOR — olculdu (2026-08-15):

        konu                ozet      tam makale
        Roman aqueduct        39        7.539     (193x)
        Herculaneum           32        3.207     (100x)
        Egyptian pyramids     56        3.208      (57x)
        Bayeux Tapestry      102        6.456      (63x)

    `vikipedi_ozeti` yalnizca giris paragrafini veriyor: 32-102 kelime.
    80-120 kelimelik bir Shorts senaryosuna yetiyor, ama uzun format
    ~2.000 kelime konusuyor ve model 56 kelimelik bir ozetten 2.000
    kelime yazmak zorunda kalirsa aradaki farki UYDURUR.

    Uydurma riski bu hatta olculmus ve belgelenmis bir kusur
    (`vikipedi_ozeti` docstring'i, DW-114: Scanagatta "Italian opera"
    diye anlatildi). Uzun formatta ayni risk kelime basina degil, kelime
    SAYISIYLA olcekleniyor.

    ⚠️ Kaynakca/dis baglanti bolumleri ATILIYOR: modele olgu vermiyorlar
    ve "Retrieved 12 March 2019" gibi satirlarin anlatima sizmasi, bu
    hatta zaten olculmus bir kusur sinifinin (kaynagin kendisini
    anlatmak) besleyicisi olurdu.
    """
    ad = (konu or "").strip()
    if not ad:
        return ""
    try:
        yanit = _get_with_retry(
            VIKIPEDI_API_URL,
            timeout=timeout,
            max_attempts=2,
            params={
                "action": "query",
                "prop": "extracts",
                "explaintext": "1",
                "redirects": "1",
                "titles": ad,
                "format": "json",
            },
        )
    except (requests.RequestException, RuntimeError):
        return ""
    try:
        sayfalar = yanit.json()["query"]["pages"]
    except (ValueError, KeyError, TypeError):
        return ""
    metin = ""
    for sayfa in sayfalar.values():
        if isinstance(sayfa, dict) and sayfa.get("extract"):
            metin = str(sayfa["extract"])
            break
    if not metin.strip():
        return ""

    # `explaintext` bolum basliklarini "== Baslik ==" biciminde birakiyor.
    govde: list[str] = []
    atlaniyor = False
    for satir in metin.splitlines():
        if baslik := re.fullmatch(r"\s*=+\s*(.+?)\s*=+\s*", satir):
            atlaniyor = baslik.group(1).strip().lower() in _ATILACAK_BOLUMLER
            continue
        if not atlaniyor:
            govde.append(satir)

    kelimeler = " ".join(govde).split()
    return " ".join(kelimeler[:azami_kelime]).strip()


def is_safe_license(value: str) -> bool:
    """Kosulsuz kullanilabilir mi — PD ya da CC0."""
    normalized = (value or "").strip().lower()
    return any(marker in normalized for marker in SAFE_LICENSE_MARKERS)


def paylasimli_lisans(value: str) -> bool:
    """Share-alike (BY-SA) mi — turev eseri ayni lisansa zorlar, kabul edilmiyor."""
    normalized = (value or "").strip().lower()
    return "sa" in normalized.replace("-", " ").split() or "share" in normalized


def atif_gerektiren(value: str) -> bool:
    """Yalnizca ATIF isteyen bir lisans mi — CC BY, ama CC BY-SA DEGIL.

    ⚠️ Sira onemli: "cc by-sa 4.0" metni "cc by" iceriyor. Once share-alike
    elenmezse naif eslesme onu da gecirirdi (DW-99).
    """
    normalized = (value or "").strip().lower()
    if paylasimli_lisans(normalized):
        return False
    return any(marker in normalized for marker in ATIF_LISANS_ISARETLERI)


def kullanilabilir_lisans(value: str) -> bool:
    """Videoda kullanilabilir mi — PD/CC0 ya da yalnizca atif isteyen CC BY."""
    return is_safe_license(value) or atif_gerektiren(value)


BELGE_ISARETLERI = (
    "letter of",
    "letter from",
    "letter to",
    "manuscript",
    "folio",
    "title page",
    "frontispiece",
    "diary",
    "journal of",
    "page from",
    "codex",
    "charter",
    "deed of",
    "handwritten",
    "signature of",
    "postcard",
    "stamp of",
    "map of",
    "plan of",
    # ⚠️ Bilimsel yayin plakalari — 2026-08-07'de olculdu. "Pottery found at
    # the Pueblo Hungo Pavie" bir kitap sayfasiydi: ustunde "Senate Ex. doc."
    # ve "Pl. 32" yazili, beyaz zeminde cizim panelleri. Baslikta belge
    # kelimesi gecmedigi icin filtre kacirdi. Bunlar arkeolojik olarak degerli
    # ama dikey videoda izleyiciye hicbir sey anlatmiyor.
    "plate ",
    "pl. ",
    "fig. ",
    "figure ",
    "engraving of",
    "lithograph",
    "diagram",
    "cross-section",
    "cross section",
    "table of",
    "chart of",
    "inscription",
    "specimen",
    # ⚠️ Kitaptan taranmis sayfalar — 2026-08-08'de olculdu. Ustteki filtre
    # bunlari kacirdi cunku basliktaki isaret "lithograph" degil KISALTMA:
    # "R. H. Kern delt. P.S. Duval's Lith. Steam Press."
    #
    # "(IA " Commons'ta Internet Archive kitap tarama kimligi; dosyanin bir
    # kitap sayfasindan cikarildigi anlamina geliyor. Gecmise karsi olculdu:
    # kullanilmis 45 arsiv gorselinin 3'unde geciyor ve UCU DE kitap sayfasi
    # (Chaco videosunun 1., 5. ve 7. sahneleri). Yanlis pozitif yok.
    "(ia ",
    "delt.",
    "lith.",
    "steam press",
    "(to accompany)",
)
"""Basligi bunlari iceren Commons dosyasi bir BELGE taramasidir, resim degil.

⚠️ Olculdu (2026-08-06, DW-98): "Lighthouse of Alexandria" videosunda arsiv
5 sahne besledi ve ikisi belge cikti — 1869 tarihli el yazisi bir mektup
sayfasi ve iki kucuk panelli bir kitap sayfasi. Ikisi de ekrani tam
dolduruyor ama izleyiciye hicbir sey gostermiyor: birinde okunamayan el
yazisi, digerinde kitabin kenar bosluklari.

Arama metin alakasina bakiyor; "Pharos" kelimesi gecen bir gunluk sayfasi
sorguyla mukemmel eslesiyor ama fener kulesinin resmi degil. Kalite kapisi da
bunu yakalayamadi (85 verdi) cunku o "gorsel anlatimla uyumlu mu" diye
soruyor, "bu bir belge mi" diye degil.
"""

SHORTS_ORANI = 1080 / 1920
"""Dikey Shorts karesinin en/boy orani — `youtube_automation` ile ayni kare."""

AZAMI_KIRPMA = 0.35
"""Bu kadar kirpma tam ekran sayiliyor; fazlasi bulanik arka plan yoluna duser.

⚠️ `youtube_automation.AZAMI_KIRPMA` ile AYNI sayi olmak ZORUNDA: orada
render hangi yolu secegini bu esikle belirliyor. Burasi ayrisirsa retrieval
yine kendi render'indan farkli dusunmeye baslar. Bir test ikisini
karsilastiriyor.
"""

# Bulanik arka plan yoluna dusen gorselin net kisminin kaplamasi gereken en az
# dikey oran.
#
# ⚠️ Bu esik 2026-08-11'de 0,55'ten 0,28'e INDIRILDI — kanal sahibinin karari:
# "bulanik bantli gercek fotograf" tam ekran AI gorseline tercih ediliyor.
#
# Onceki 0,55, en/boy orani ~1,02'den genis HER gorseli eliyordu, yani
# Commons'taki tarihi fotograflarin neredeyse tamamini. Olculdu (2026-08-10),
# Wikidata ile cozulen 7 kategori: lisans ve cozunurluk bakimindan **80**
# kullanilabilir gorsel vardi, oran filtresini gecen **24**. Elenen 56 gorselin
# yerine AI uretiliyordu.
#
# ⚠️ Asil celiski suydu: `youtube_automation.dikeye_uydur` bu gorselleri ZATEN
# basabiliyor — kirpma `AZAMI_KIRPMA`'yi gecince buyutulmus bulanik kopyayi
# arka plana koyup neti ortada gosteriyor. Yani retrieval, kendi render'indan
# kati davraniyordu: basabildigimiz gorseli aramada atiyorduk.
#
# Yeni esik render'in URETECEGI kareden turetildi. Bulanik yolda net gorselin
# kapladigi dikey oran tam olarak `SHORTS_ORANI / oran`:
#
#     4:3   (1,33) → %42 doluluk   geciyor
#     3:2   (1,50) → %38 doluluk   geciyor
#     16:9  (1,78) → %32 doluluk   geciyor
#     2,00           %28 doluluk   sinirda, geciyor
#     panorama(2,22) → %25 doluluk  eleniyor
#     panorama(5,00) → %11 doluluk  eleniyor
#
# Panoramalar disarida kaliyor cunku bulanik bir karenin ortasindaki ince bir
# serit gercekten izlenebilir bir kare vermiyor; takas orada AI lehine donuyor.
ASGARI_DIKEY_DOLULUK = 0.28


def belge_taramasi(baslik: str) -> bool:
    """Bu Commons dosyasi bir belge/el yazmasi taramasi mi — bkz. `BELGE_ISARETLERI`."""
    normal = (baslik or "").lower()
    return any(isaret in normal for isaret in BELGE_ISARETLERI)


def tam_ekran_doluyor(width: int, height: int) -> bool:
    """Render bu gorseli kirp-doldur ile TAM EKRAN basabilir mi.

    Bulanik arka plan yoluna dusenler `False` doner. Aday puanlamasi bunu
    kullaniyor: bulanik bantli gercek fotograf kabul ediliyor ama tam ekran
    olan her zaman tercih ediliyor.
    """
    if width <= 0 or height <= 0:
        return False
    oran = width / height
    if oran <= SHORTS_ORANI:
        return True  # dikey ya da kare — kirp-doldur tam ekran verir
    return 1 - (SHORTS_ORANI / oran) <= AZAMI_KIRPMA


def dikey_karede_yeterli(width: int, height: int) -> bool:
    """Gorsel 9:16 karede kullanilabilir bir kare veriyor mu.

    Iki yol var ve ikisi de kabul ediliyor:

    - **Kirp-doldur** — tam ekran (`tam_ekran_doluyor`).
    - **Bulanik arka plan** — net gorsel ortada, kalani bulanik bant. Net
      kismin kapladigi dikey oran `ASGARI_DIKEY_DOLULUK`'un altina duserse
      eleniyor.
    """
    if width <= 0 or height <= 0:
        return False
    if tam_ekran_doluyor(width, height):
        return True
    # Bulanik yolda net gorselin kapladigi dikey oran — `dikeye_uydur`
    # `ImageOps.contain` ile ayni sonucu veriyor.
    return SHORTS_ORANI / (width / height) >= ASGARI_DIKEY_DOLULUK


def delivery_url(source_url: str) -> str:
    """Map an allowlisted Wikimedia upload URL to a cache-backed delivery URL."""
    parsed = urllib.parse.urlsplit(source_url)
    if parsed.scheme != "https" or parsed.hostname != "upload.wikimedia.org":
        raise ValueError("Commons media URL must use https://upload.wikimedia.org")
    host_and_path = f"{parsed.hostname}{parsed.path}"
    query = urllib.parse.urlencode({"url": host_and_path, "w": "1280", "fit": "inside"})
    return f"{DELIVERY_PROXY_URL}?{query}"


def dogrudan_url(source_url: str) -> str:
    """Wikimedia'nin kendi sunucusundaki URL — teslim proxy'si atlanarak.

    `delivery_url` ile AYNI izin listesi uygulaniyor: yalnizca
    `upload.wikimedia.org`. Commons bugun URL'lere izleme parametreleri
    ekliyor (`?utm_source=...`); bunlar atiliyor.
    """
    parsed = urllib.parse.urlsplit(source_url)
    if parsed.scheme != "https" or parsed.hostname != "upload.wikimedia.org":
        raise ValueError("Commons media URL must use https://upload.wikimedia.org")
    return urllib.parse.urlunsplit(("https", parsed.hostname, parsed.path, "", ""))


def build_search_queries(topic: str, term: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9'-]+", term)
    meaningful = [word for word in words if word.lower() not in GENERIC_SEARCH_WORDS]
    candidates = [term.strip()]
    if meaningful != words:
        candidates.append(" ".join(meaningful))
    if len(meaningful) > 2:
        candidates.extend(" ".join(pair) for pair in itertools.combinations(meaningful, 2))

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = " ".join(candidate.split())
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique[:10]


def _metadata_value(image: dict[str, Any], key: str) -> str:
    metadata = image.get("extmetadata", {})
    value = metadata.get(key, {})
    if isinstance(value, dict):
        return str(value.get("value", ""))
    return str(value or "")


def _plain_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(value).split())


def _relevance_terms(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(word) >= 4 and word not in RELEVANCE_STOPWORDS
    }


def select_candidate(
    pages: list[dict[str, Any]],
    used_titles: set[str],
    query: str = "",
    required_anchor: str = "",
) -> dict[str, Any] | None:
    adaylar = _puanli_adaylar(pages, used_titles, query, required_anchor)
    return adaylar[0] if adaylar else None


def _kategori_adaylari(
    pages: list[dict[str, Any]], used_titles: set[str]
) -> list[dict[str, Any]]:
    """Kategori havuzunu puana gore siralar — capa ve sorgu kontrolu olmadan.

    Cagiran taraf listeyi bastan gezebilsin diye TEK aday degil LISTE
    donuyor: indirme dusebilir ya da aday tekrar cikabilir, o zaman
    sonrakine gecilmeli.
    """
    return _puanli_adaylar(pages, used_titles, "", "")


def _puanli_adaylar(
    pages: list[dict[str, Any]],
    used_titles: set[str],
    query: str = "",
    required_anchor: str = "",
) -> list[dict[str, Any]]:
    candidates: list[tuple[float, dict[str, Any]]] = []
    query_terms = _relevance_terms(query)
    anchor_terms = _relevance_terms(required_anchor)
    distinctive_anchor_terms = anchor_terms - ANCHOR_GENERIC_WORDS
    required_anchor_terms = distinctive_anchor_terms or anchor_terms
    # ⚠️ Sira sayilari AYRI: `_relevance_terms` 4 harften kisa kelimeleri
    # atiyor, yani "Murad III" yalnizca {"murad"} veriyordu ve
    # `File:Nadia Murad Nobel Peace Prize 2018.jpg` kapiyi GECIYORDU
    # (olculdu 2026-08-13). Tam sozcuk eslesmesinin sebebi `capa_eslesme`de.
    gerekli_sira_sayilari = capa_eslesme.sira_sayilari(required_anchor)
    for order, page in enumerate(pages):
        title = str(page.get("title", ""))
        if not title or title in used_titles:
            continue
        image_infos = page.get("imageinfo") or []
        if not image_infos:
            continue
        image = image_infos[0]
        evidence = " ".join(
            [title, _plain_text(_metadata_value(image, "ImageDescription"))]
        ).lower()
        if required_anchor_terms and not all(
            term in evidence for term in required_anchor_terms
        ):
            continue
        if not capa_eslesme.sira_sayisi_uyuyor(
            set(re.findall(r"[a-z]+", evidence)), gerekli_sira_sayilari
        ):
            continue
        matched_terms = {term for term in query_terms if term in evidence}
        if len(query_terms) >= 5:
            minimum_matches = 3
        elif len(query_terms) >= 3:
            minimum_matches = 2
        else:
            minimum_matches = 1
        if query_terms and len(matched_terms) < minimum_matches:
            continue
        mime = str(image.get("mime", "")).lower()
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        license_name = _metadata_value(image, "LicenseShortName")
        if not kullanilabilir_lisans(license_name):
            continue
        url = image.get("url")
        if not url:
            continue
        if belge_taramasi(title):
            continue
        width = int(image.get("width") or image.get("thumbwidth") or 0)
        height = int(image.get("height") or image.get("thumbheight") or 0)
        if width < 720 or height < 720:
            continue
        if not dikey_karede_yeterli(width, height):
            continue
        # ⚠️ Bulanik bantli gorsel artik KABUL ediliyor (bkz.
        # `ASGARI_DIKEY_DOLULUK`) ama tam ekran olan her zaman ONCE gelmeli.
        # Bonus cozunurluk puaninin tavanindan (4,0) buyuk secildi: yoksa
        # buyuk bir panorama, kucuk ama tam ekran bir dikey fotografi
        # geceredi ve videolar bulanik bantla dolardi.
        orientation_score = 2.0 if height >= width else 1.0
        if tam_ekran_doluyor(width, height):
            orientation_score += 5.0
        resolution_score = min(width * height / 1_000_000, 4.0)
        search_order_score = max(0.0, 2.0 - order * 0.1)
        candidate = {
            "title": title,
            "url": str(url),
            "source_url": str(image.get("descriptionurl", "")),
            "license": license_name,
            "artist": _plain_text(_metadata_value(image, "Artist")),
            "credit": _plain_text(_metadata_value(image, "Credit")),
            "width": width,
            "height": height,
            "mime": mime,
            # ⚠️ Aciklama ve tarih, dosya adinin soylemedigini soyluyor.
            # Olculdu (2026-08-14): Borobudur kategorisinin ilk dosyalari
            # `20190415 151806b.jpg`, `500px photo (50204564).jpeg`,
            # `Ujung.jpg` — bir modelin bunlardan ne gorecegini bilmesi
            # imkansiz. Ayni dosyalarin `ImageDescription` alani ise
            # "Boroboedoer bij Magelang, KITLV 99831" ya da "The clipper
            # CUTTY SARK in full sails" gibi gercekten kullanilabilir bir
            # bilgi tasiyor. `arsiv_menusu` bunun uzerine kuruluyor.
            "aciklama": (
                _plain_text(_metadata_value(image, "ImageDescription"))
                or _plain_text(_metadata_value(image, "ObjectName"))
            ),
            "tarih": (
                _plain_text(_metadata_value(image, "DateTimeOriginal"))
                or _plain_text(_metadata_value(image, "DateTime"))
            ),
        }
        relevance_score = len(matched_terms) * 2.0
        candidates.append(
            (
                orientation_score
                + resolution_score
                + search_order_score
                + relevance_score,
                candidate,
            )
        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [aday for _, aday in candidates]


_KATEGORI_ONBELLEGI: dict[str, str | None] = {}
_QID_ONBELLEGI: dict[str, str | None] = {}
_KISI_ONBELLEGI: dict[str, bool | None] = {}


def vikiveri_kimligi(konu: str) -> str | None:
    """Konunun Wikidata ogesi (QID). Bulunamazsa None.

    `commons_kategorisi` ve `kisi_mi` ayni ilk adimi paylasiyor; tek yerde
    tutuluyor ki iki cagri arasinda sapma olmasin ve onbellek ortak olsun.
    """
    anahtar = konu.strip().casefold()
    if anahtar in _QID_ONBELLEGI:
        return _QID_ONBELLEGI[anahtar]
    sonuc: str | None = None
    try:
        yanit = _get_with_retry(
            VIKIPEDI_API_URL,
            params={
                "action": "query",
                "titles": konu.strip(),
                "prop": "pageprops",
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            },
            timeout=15,
        )
        sayfalar = yanit.json().get("query", {}).get("pages", [])
        if sayfalar:
            kimlik = str(sayfalar[0].get("pageprops", {}).get("wikibase_item", "")).strip()
            sonuc = kimlik or None
    except (requests.RequestException, ValueError, KeyError, IndexError):
        sonuc = None
    _QID_ONBELLEGI[anahtar] = sonuc
    return sonuc


def kisi_mi(konu: str) -> bool | None:
    """Konu bir INSAN mi (Wikidata P31 = Q5). Cozulemezse None.

    ⚠️ NEDEN VAR — olculdu (2026-08-13). Yayinlanan 12 videonun kaydinda
    konu sinifi ile kusur sayisi arasinda temiz bir ayrim var:

        anit / yer / nesne   skor 70-90, hakem kusuru  0-3
        kisi biyografisi     skor 68-84, hakem kusuru 9-11

    Sebep kisinin kendisi degil ARSIVI: kisi kategorileri portre yigini,
    yer kategorileri dogal olarak cesitli (genel gorunum, detay, plan).
    Hakem her kisi koşumunda ayni cumleyi yaziyor ("static portraits",
    "repeated portrait format").

    ⚠️ Ucuz olcutlerle bu ayrim YAPILAMADI, ucu de olculup elendi:
      · dosya adi turu   → Kolezyum'un adlari anlamsiz ("Colosseum (46202669405).jpg")
      · algisal benzerlik → kaybeden 0,50-0,54 / kazanan 0,51-0,63, ayrismiyor
      · ton yayilimi      → Dholavira (85 puan, 0 kusur) 0,004 ile en dusugu
    Geriye kalan tek guvenilir sinyal konu sinifi; Wikidata bunu kesin
    veriyor (10/10 dogru olculdu).

    ⚠️ Vekil oldugu unutulmamali: asil sebep portre agirligi. Treaty of
    Breda bir OLAY ama imza sahiplerinin portreleriyle dolu oldugu icin 9
    kusur aldi. Yani `False` donmesi iyi arsiv GARANTISI degil.

    None donmek "kisi degil" DEMEK DEGIL: cagiran taraf bilinmeyeni kendi
    politikasina gore ele almali.
    """
    anahtar = konu.strip().casefold()
    if anahtar in _KISI_ONBELLEGI:
        return _KISI_ONBELLEGI[anahtar]
    sonuc: bool | None = None
    kimlik = vikiveri_kimligi(konu)
    if kimlik:
        try:
            iddia = _get_with_retry(
                VIKIVERI_API_URL,
                params={
                    "action": "wbgetclaims",
                    "entity": kimlik,
                    "property": "P31",
                    "format": "json",
                },
                timeout=15,
            )
            kayitlar = iddia.json().get("claims", {}).get("P31", [])
            if kayitlar:
                sonuc = any(
                    (kayit.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("id")
                    == "Q5"
                    for kayit in kayitlar
                )
        except (requests.RequestException, ValueError, KeyError, IndexError):
            sonuc = None
    _KISI_ONBELLEGI[anahtar] = sonuc
    return sonuc


def commons_kategorisi(konu: str) -> str | None:
    """Konunun Commons KATEGORISINI Wikidata uzerinden cozer (DW-122).

    Wikipedia basligi → Wikidata ogesi (QID) → P373 (Commons kategorisi).

    ⚠️ Neden tahmin degil de Wikidata: arsiv konuyu bizim yazdigimiz adla
    saklamiyor. Olculdu (2026-08-10):

        "Franziska Scanagatta"       → Category:Francesca Scanagatta
        "Theresian Military Academy" → Category:Theresianische Militärakademie
        "Chaco Canyon"               → Category:Chaco Culture National Historical Park

    Ilk satir Scanagatta videosunun 6/6 sahnesinin neden AI ile uretildigini
    tek basina acikliyor: gorsel arsivde VARDI, biz **Franziska** diye
    aradik, Commons **Francesca** diye sakliyor. Yazim ve dil farkini
    normalize eden sey Wikidata'nin kendisi; `Category:{konu}` tahmini bunu
    yapamaz.

    Bulunamazsa `None` doner — cagiran taraf tam metin aramasiyla devam eder.
    """
    anahtar = konu.strip().casefold()
    if anahtar in _KATEGORI_ONBELLEGI:
        return _KATEGORI_ONBELLEGI[anahtar]
    sonuc: str | None = None
    try:
        # Wikipedia basligi → QID adimi `vikiveri_kimligi`de; `kisi_mi` de
        # ayni adimi kullaniyor, onbellek ortak.
        kimlik = vikiveri_kimligi(konu)
        if kimlik:
            iddia = _get_with_retry(
                VIKIVERI_API_URL,
                params={
                    "action": "wbgetclaims",
                    "entity": kimlik,
                    "property": "P373",
                    "format": "json",
                },
                timeout=15,
            )
            kayitlar = iddia.json().get("claims", {}).get("P373", [])
            if kayitlar:
                deger = kayitlar[0].get("mainsnak", {}).get("datavalue", {}).get("value")
                if isinstance(deger, str) and deger.strip():
                    sonuc = deger.strip()
    except (requests.RequestException, ValueError, KeyError, IndexError):
        # ⚠️ Kategori cozumu bir IYILESTIRME; basarisiz olursa uretim
        # durmamali. Tam metin aramasi zaten calisiyor.
        sonuc = None
    _KATEGORI_ONBELLEGI[anahtar] = sonuc
    return sonuc


def kategori_gorselleri(kategori: str, limit: int = 100) -> list[dict[str, Any]]:
    """Bir Commons kategorisindeki dosyalari `search_commons` bicimiyle dondurur."""
    try:
        yanit = _get_with_retry(
            API_URL,
            params={
                "action": "query",
                "generator": "categorymembers",
                "gcmtitle": f"Category:{kategori}",
                "gcmtype": "file",
                "gcmlimit": str(limit),
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "iiurlwidth": "1080",
                "format": "json",
                "formatversion": "2",
            },
            timeout=30,
        )
        return yanit.json().get("query", {}).get("pages", [])
    except (requests.RequestException, ValueError):
        return []


def dosya_sayfasi(baslik: str) -> dict[str, Any] | None:
    """TEK bir Commons dosyasini adiyla getirir — `search_commons` biciminde.

    Sahne artik envanterden bir dosya SECIYOR (bkz. `arsiv_menusu`); secilen
    dosya cogu zaman zaten indirilmis kategori havuzunda bulunuyor ve bu
    fonksiyon cagrilmiyor. Havuz sinirinin disinda kalan bir secim icin tek
    istekle dosyayi getirmek, secimi bosa dusurmekten iyidir.
    """
    ad = baslik.strip().removeprefix("File:").strip()
    if not ad:
        return None
    try:
        yanit = _get_with_retry(
            API_URL,
            params={
                "action": "query",
                "titles": f"File:{ad}",
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "iiurlwidth": "1080",
                "format": "json",
                "formatversion": "2",
            },
            timeout=30,
        )
        sayfalar = yanit.json().get("query", {}).get("pages", [])
    except (requests.RequestException, ValueError):
        return None
    for sayfa in sayfalar:
        if sayfa.get("missing"):
            continue
        if sayfa.get("imageinfo"):
            return sayfa
    return None


MENU_KATEGORI_SINIRI = 500


def arsiv_menusu(konu: str, *, sinir: int = 40) -> list[dict[str, Any]]:
    """Konu icin GERCEKTEN kullanilabilir arsiv gorsellerinin menusu.

    ⚠️ NEDEN VAR — olculdu (2026-08-14). Hat, plani yazan modele kategorinin
    ILK 45 dosya ADINI veriyordu. Commons kategori listesi baslik sirasina
    gore geliyor, yani listenin basi rakamla baslayan modern telefon
    fotograflari ve `500px photo (...)` aktarimlari oluyor. Model bu isimsiz
    slaytlardan ne gosterebilecegini bilemeyince anlatiyi TAHMINLE yaziyor ve
    arsivde bulunmayan anlari istiyordu: "1974'te kuyu kazan koyluler",
    "denizde dumenini kaybeden gemi", "Ay'in agiz acma toreni". Son 12
    kosumun kaynak skoru 0-63 (kapi 70) ve hakemin gerekcesi hep ayniydi:
    "dogru konu, YANLIS an".

    Menu farki olculdu: ayni kategori lisans + kadraj suzgecinden gecirilip
    aciklama ve tarihle sunuldugunda Cutty Sark icin "The clipper CUTTY SARK
    in full sails (1916 oncesi)", "waiting in Sydney Harbour for the new
    season's wool (1885-1894)", "re-conditioned at anchor at Falmouth (1922
    sonrasi)" cikiyor — bunlardan senaryo yazilabilir.

    Suzgec `_kategori_adaylari`: yani menude gorunen her dosyayi indirici de
    kabul eder. Menunun "var" dedigi seyin indirilememesi, menuyu yeniden
    yalana cevirirdi.

    ⚠️ HAVUZ IKI KAYNAKTAN: kategori VE tam metin aramasi. Yalnizca kategori
    yetmiyor cunku Commons kategorileri hiyerarsik — olculdu (2026-08-14):
    `Category:Terracotta Army` dogrudan uyeliginde suzgecten gecen 4 dosya
    var, gerisi alt kategorilerde. Indiricinin asil yolu zaten arama; menu
    onun goremedigi bir arsivi anlatirsa yine yalan soyler, yalnizca ters
    yone dogru.
    """
    havuz: list[dict[str, Any]] = []
    kategori = commons_kategorisi(konu)
    if kategori:
        havuz = kategori_gorselleri(kategori, limit=MENU_KATEGORI_SINIRI)
    adaylar = _kategori_adaylari(havuz, set()) if havuz else []
    gorulen = {str(aday.get("title") or "") for aday in adaylar}
    try:
        aramadan = search_commons(konu, limit=50)
    except requests.RequestException:
        aramadan = []
    # Aramada capa zorunlu: kategori uyeligi konuya aitligi zaten garanti
    # ediyor, arama etmiyor ("Cutty Sark" sorgusu DLR istasyonunu da
    # getiriyor — bu oturumda bir videoya modern ulasim haritasi bu yoldan
    # girdi).
    for aday in _puanli_adaylar(aramadan, set(), "", konu):
        baslik = str(aday.get("title") or "")
        if baslik and baslik not in gorulen:
            gorulen.add(baslik)
            adaylar.append(aday)
    return _aciklamayi_seyrelt(adaylar)[:sinir]


AYNI_ACIKLAMA_TAVANI = 2


def _aciklamayi_seyrelt(adaylar: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ayni aciklamayi tasiyan dosyalari en fazla `AYNI_ACIKLAMA_TAVANI` tutar.

    ⚠️ Olculdu (2026-08-14, Cutty Sark): menunun 40 girdisinin 38'i
    `Cutty Sark 26-06-2012 (...).jpg` idi ve HEPSININ aciklamasi ayni tek
    cumleydi ("Cutty Sark, King William Walk, Greenwich... badly damaged by
    fire on 21 May 2007"). Bir yukleyicinin ayni gun cektigi 38 kare
    siralamanin tepesini kapliyor (buyuk, dikey, yuksek cozunurluklu) ve
    tarihsel SLV fotograflarini menunun disina itiyordu.

    Menunun isi SECENEK sunmak. Ayni cumleyi 38 kez gostermek modele hicbir
    sey soylemiyor, yalnizca gercekten farkli olan dosyalari gizliyor.
    """
    sayac: dict[str, int] = {}
    seyrek: list[dict[str, Any]] = []
    for aday in adaylar:
        # Aciklamasi olmayanlar gruplanmiyor: ortak bosluk bir benzerlik
        # kaniti degil.
        anahtar = " ".join(str(aday.get("aciklama") or "").lower().split())[:60]
        if anahtar:
            sayac[anahtar] = sayac.get(anahtar, 0) + 1
            if sayac[anahtar] > AYNI_ACIKLAMA_TAVANI:
                continue
        seyrek.append(aday)
    return seyrek


def search_commons(query: str, limit: int = 20) -> list[dict[str, Any]]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "1080",
        "format": "json",
        "formatversion": "2",
        "origin": "*",
    }
    response = _get_with_retry(
        API_URL,
        params=params,
        timeout=30,
    )
    payload = response.json()
    return payload.get("query", {}).get("pages", [])


def _download(
    url: str,
    destination: Path,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    try:
        response = _get_with_retry(delivery_url(url), timeout=60, sleep_fn=sleep_fn)
    except requests.HTTPError as exc:
        # ⚠️ Teslim proxy'si (weserv) BELLI dosyalarda kalici 404 donuyor,
        # gecici degil. Olculdu (2026-08-10): 15 arsiv dosyasinin 13'u
        # proxy'den geldi, 2'si israrla 404 verdi — ve o ikisi Wikimedia'nin
        # kendi sunucusunda 200 ve 652 KB olarak duruyordu.
        #
        # Bedeli dogrudan "AI gorsel cok" sikayetine yaziliyor: proxy
        # dusunce gecerli bir arsiv gorseli atiliyor ve sahne AI'ya gidiyor.
        # Kaynak yerinde dururken bunu yapmanin sebebi yok.
        #
        # 5xx BURAYA GIRMIYOR: `_get_with_retry` onlari zaten geri cekilmeyle
        # 5 kez deniyor ve gecici olduklari icin proxy'yi atlamaya gerek yok.
        durum = exc.response.status_code if exc.response is not None else 0
        if durum not in {403, 404}:
            raise
        response = _get_with_retry(dogrudan_url(url), timeout=60, sleep_fn=sleep_fn)
    destination.write_bytes(response.content)
    if destination.stat().st_size < 10_000:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded Commons image is unexpectedly small: {url}")


def _izi_ekle(yol: Path, izler: list[Any]) -> None:
    """Secilen sahnenin parmak izini listeye ekler.

    Okunamayan dosya olcumu degil URETIMI ilgilendirir; burada sessizce
    geciliyor cunku dosya zaten indirilmis ve kullanilacak.
    """
    try:
        izler.append(gorsel_olcum.parmak_izi(yol))
    except OSError:
        pass


def _tekrar_mi(yol: Path, izler: list[Any]) -> bool:
    """Aday, secilmis sahnelerden birinin kopyasi mi.

    ⚠️ Olcum basarisiz olursa `False` doner — okunamayan bir dosya yuzunden
    mesru bir adayi elemek, tekrari kacirmaktan daha kotu.
    """
    if not izler:
        return False
    try:
        iz = gorsel_olcum.parmak_izi(yol)
    except OSError:
        return False
    return any(
        gorsel_olcum.benzerlik(iz, onceki) >= gorsel_olcum.ARSIV_TEKRAR_ESIGI
        for onceki in izler
    )


_UZANTI = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def kategori_havuzunu_coz(visual_anchor: str, topic: str) -> list[dict[str, Any]]:
    """Konunun Commons KATEGORISINDEKI dosyalar.

    Tam metin aramasi bir sahneyi bulamayinca AI'ya gitmeden once buraya
    bakiliyor (DW-122). Kategori bir kez cozuluyor; sahne basina istek yok.

    ⚠️ Ayri fonksiyon oldu cunku ikinci gorsel gecisi (`ikincil_gorseller`)
    ayni havuzu istiyor. Her gecis kendi cozseydi ayni video icin iki kez
    kategori sorgusu atilirdi.
    """
    for aday_konu in (visual_anchor.strip(), topic.strip()):
        if not aday_konu:
            continue
        kategori = commons_kategorisi(aday_konu)
        if not kategori:
            continue
        havuz = kategori_gorselleri(kategori)
        if havuz:
            print(
                f"ℹ️ Commons kategorisi: {kategori} ({len(havuz)} dosya) — {aday_konu}",
                flush=True,
            )
            return havuz
    return []


def ikincil_gorseller(
    scenes: list[dict[str, str]],
    target_dir: Path,
    kategori_havuzu: list[dict[str, Any]],
    used_titles: set[str] | None = None,
    esleme_gerekli: list[bool] | None = None,
) -> tuple[list[Path | None], list[dict[str, Any]]]:
    """Sahnelerin IKINCI alintisini indirir; bulunamayan sahne icin None.

    ⚠️ YEDEK ZINCIRI YOK, bilincli. Birincil gorselin zincirinde (Met →
    Commons arama → kategori → Europeana) her adim "sahne bos kalmasin"
    icin var. Ikincil gorsel ise bir IYILESTIRME: bulunamazsa o sahne
    birincil kareyi iki yuvada gosterir ve bugunku haliyle birebir ayni
    durur. Yedek aramak, ikinci gorseli anlatimla ilgisiz bir kareye
    dondurme riskini bedava kabul etmek olurdu.

    ⚠️ `used_titles` birincil gecisin kullandigi basliklari tasimali —
    yoksa ayni gorsel bir sahnenin iki yuvasinda birden cikar ve tam da
    sikayet edilen tekrari uretiriz ("cok fazla benzer gorseller").
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    kullanilan = set(used_titles or set())
    dosyalar: list[Path | None] = []
    krediler: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, 1):
        aday = None
        if alinti := str(scene.get("kaynak_dosya_2", "")).strip():
            aday = _alinti_adayi(alinti, kategori_havuzu, kullanilan)
        # ⚠️ ESLESTIRME YEDEGI — yalnizca birincil gorsel BANT ISTIYORSA.
        #
        # Olculdu (2026-08-14, son 4 koşumun 24 gorseli): **%54'u** tam
        # kareye kirpilamiyor, yani plan ikinci dosya vermediginde o sahne
        # bulanik bant yoluna dusuyor — kanal sahibinin "ekrani kaplamayan
        # gorseller olmamali, cok kalitesiz duruyor" dedigi sey. Lycurgus
        # Cup koşumunda 12 karenin 2'si boyle cikti ve hakem de yazdi.
        #
        # Kategori havuzundan esleme guvenli: uyeligi Commons'in kendi
        # kuratoryasi belirliyor, yani OZNE garantili. Kirpilabilen bir
        # birincil icin bu yapilmiyor — o kare zaten tam ekran ve iyi
        # duruyor, ikiye bolmek onu kucultmek olurdu.
        if aday is None and kategori_havuzu and (esleme_gerekli or [])[index - 1 : index] == [True]:
            adaylar = _kategori_adaylari(kategori_havuzu, kullanilan)
            aday = adaylar[0] if adaylar else None
        if aday is None:
            dosyalar.append(None)
            continue
        hedef = target_dir / f"scene-{index:02d}b{_UZANTI[aday['mime']]}"
        try:
            _download(aday["url"], hedef)
        except requests.HTTPError:
            dosyalar.append(None)
            continue
        kullanilan.add(aday["title"])
        dosyalar.append(hedef)
        # ⚠️ Kredi ZORUNLU: CC BY gorsellerinde atif hukuki yukumluluk.
        # Ikincil gorsel de videoda gorunuyor, yani birincilden farki yok.
        krediler.append(
            {
                "scene": index,
                "title": aday["title"],
                "source_url": aday["source_url"],
                "license": aday["license"],
                "artist": aday["artist"],
            }
        )
    return dosyalar, krediler


def _alinti_adayi(
    baslik: str,
    kategori_havuzu: list[dict[str, Any]],
    used_titles: set[str],
) -> dict[str, Any] | None:
    """Planin alintiladigi dosyayi indiricinin kendi suzgecinden gecirir.

    Menu zaten `_kategori_adaylari` ile suzuldugu icin buradan cogu zaman
    aday cikar; kontrol yine de yapiliyor cunku menu onbellekten gelebilir ve
    ayni sahnede daha once kullanilmis bir dosya elenmeli.

    ⚠️ HAVUZDAKI KAYIT EKSIK OLABILIR, DOSYA EKSIK DEMEK DEGIL. Olculdu
    (2026-08-14): MediaWiki `generator=categorymembers` istegi `imageinfo`yu
    sayfa basina degil ISTEK BASINA sinirliyor ve yaklasik ilk 50 dosyadan
    sonrasini BOS donduruyor (mime yok, boyut yok, url yok). Kategori
    buyuklugune gore: Machu Picchu 31 uye → %0 bos, Rosetta Stone 94 → %47,
    Great Zimbabwe 102 → %51, Angkor Wat 500 → %90.

    Sonucu dogrudan olculdu: alintilarin yalnizca %39'u teslim edilebildi.
    Havuzdaki bos kayit suzgecten eleniyor, sahne aramaya dusuyor ve baska
    bir gorsel geliyordu — hakemin sikayet ettigi 11 sahnenin 10'u tam da
    bunlardi. Yani menu, indiricinin getiremeyecegi dosyayi vaat ediyordu.

    Bu yuzden eleme SESSIZ KABUL EDILMIYOR: havuz kaydi aday vermezse dosya
    tek istekle yeniden isteniyor. Ancak ondan sonra "bu dosya kullanilamaz"
    denir.
    """
    ad = baslik.strip().removeprefix("File:").strip()
    if not ad:
        return None
    tam_ad = f"File:{ad}"
    sayfalar = [
        sayfa for sayfa in kategori_havuzu if str(sayfa.get("title", "")) == tam_ad
    ]
    if sayfalar:
        adaylar = _puanli_adaylar(sayfalar, used_titles, "", "")
        if adaylar:
            return adaylar[0]
    # Havuzda yok, ya da havuzdaki kayit eksik: tek istekle dosyanin kendisi.
    # Menu kategoriden VE aramadan beslendigi icin aramadan gelen bir secim
    # zaten burada cozuluyor.
    sayfa = dosya_sayfasi(ad)
    if sayfa is None:
        return None
    adaylar = _puanli_adaylar([sayfa], used_titles, "", "")
    return adaylar[0] if adaylar else None


def download_scene_materials(
    topic: str,
    scenes: list[dict[str, str]],
    target_dir: Path,
    *,
    visual_anchor: str = "",
    excluded_titles: set[str] | None = None,
    excluded_met_ids: set[int] | None = None,
    kismi: bool = False,
    kategori_havuzu: list[dict[str, Any]] | None = None,
) -> tuple[list[Path], list[dict[str, Any]]]:
    """Sahne gorsellerini arsivlerden indirir.

    `kismi=False` (varsayilan): bir sahne bile bulunamazsa
    `MaterialsUnavailableError`. Cagiran taraf AI yedegi kullanmiyorsa dogru
    davranis bu — delikli bir video yapilamaz.

    `kismi=True`: bulunamayan sahnenin yerine `None` konur ve digerleri
    korunur. Cagiran taraf yalnizca delikleri AI ile doldurur.

    ⚠️ Olculdu (2026-08-06, DW-97): "hep ya da hic" davranisi kanalin gorsel
    kimligini bozuyordu. 8 sahnenin 7'sinde gercek arsiv fotografi bulunmus
    olsa bile, 8'inci bulunamayinca hepsi cope gidiyor ve butun video AI ile
    uretiliyordu. Sonuc: uretilen 161 gorselin **96'si AI** ve bunlarin
    **76'si** tam da bu yoldan geldi. AI gorselleri tek bir estetikte
    olduklari icin videolar birbirinin kopyasi gibi duruyordu.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    eksik: list[int] = []
    used_titles: set[str] = set(excluded_titles or set())
    used_met_ids: set[int] = set(excluded_met_ids or set())
    # ⚠️ Europeana kimlikleri METIN ("/2020903/KMS1"), Met'inkiler gibi sayi
    # degil. Cagiran taraf `excluded_met_ids` gonderirken `int()` uyguluyor,
    # bu yuzden Europeana kimligi oraya KARISTIRILMIYOR. Sahneler arasi
    # tekrar yine engelleniyor: `used_titles` ve parmak izi kontrolu
    # Europeana adaylarini da kapsiyor.
    used_europeana_ids: set[str] = set()
    files: list[Path] = []
    credits: list[dict[str, Any]] = []
    # ⚠️ Secilmis sahnelerin parmak izleri — AYNI GORSELIN iki sahnede
    # kullanilmasini engellemek icin. `used_titles` bunu yakalayamiyor:
    # olculdu (2026-08-09, Library of Alexandria) "The Great Library of
    # Alexandria - Colorized.jpg" ile "Ancientlibraryalex.jpg" AYNI gravurdu
    # ama dosya adlari tamamen farkli. Kullanici sikayeti birebir buydu:
    # "bir resmi birden fazla kez kullanmissin".
    secilmis_izler: list[Any] = []
    # Konunun Commons KATEGORISI — tam metin aramasi bir sahneyi bulamayinca
    # AI'ya gitmeden once buraya bakiliyor (DW-122). Kategori bir kez
    # cozuluyor; sahne basina istek yok.
    if kategori_havuzu is None:
        kategori_havuzu = kategori_havuzunu_coz(visual_anchor, topic)
    for index, scene in enumerate(scenes, 1):
        term = scene.get("search_term", "").strip()
        queries = build_search_queries(topic, term)
        selected = None
        destination = None
        failed_titles: set[str] = set()
        # Tekrar diye elenen ilk aday: baska hicbir sey bulunamazsa buna
        # donulur. Delik birakmaktansa benzer bir gorsel iyidir.
        yedek: tuple[dict[str, Any], Path] | None = None
        # Met/Europeana'nin kredisi zaten hazir gelir; Commons yedeginden
        # ayri tutuluyor cunku son carede krediyi yeniden kurmak gerekmiyor.
        hazir_yedek: tuple[Path, dict[str, Any]] | None = None

        # ⚠️ ALINTILANAN DOSYA HER SEYDEN ONCE. Plan artik arsiv menusunden
        # secim yapiyor (`youtube_automation.alinti_kusuru`) ve sahnenin
        # anlatisi TAM DA bu dosyanin gosterdigi seyin uzerine yazildi. Baska
        # bir gorsel "yakin" degil, yanlis olur.
        #
        # Olculdu (2026-08-14): senaryo once yazilip arsiv sonra arandiginda
        # hakem 12 kosumun 12'sinde ayni gerekceyi yazdi — "dogru konu,
        # yanlis an": Terracotta Army'nin kazi salonu geldi, anlatim boyali
        # rekonstruksiyon istiyordu; Cutty Sark'in gemi portresi geldi,
        # anlatim 1872 yarisini istiyordu. Kaynak skorlari 0-63 (kapi 70).
        #
        # Alinti bir GARANTI degil ILK TERCIH: dosya silinmis olabilir,
        # teslim dusebilir ya da ayni gorsel baska sahnede kullanilmis
        # olabilir. Bu durumlarda asagidaki zincir eskisi gibi calisiyor.
        if alinti := str(scene.get("kaynak_dosya", "")).strip():
            alinti_adayi = _alinti_adayi(alinti, kategori_havuzu, used_titles)
            if alinti_adayi is not None:
                alinti_hedefi = target_dir / f"scene-{index:02d}{_UZANTI[alinti_adayi['mime']]}"
                try:
                    _download(alinti_adayi["url"], alinti_hedefi)
                except requests.HTTPError:
                    failed_titles.add(alinti_adayi["title"])
                else:
                    if _tekrar_mi(alinti_hedefi, secilmis_izler):
                        yedek = (alinti_adayi, alinti_hedefi)
                        failed_titles.add(alinti_adayi["title"])
                    else:
                        selected, destination = alinti_adayi, alinti_hedefi

        # ⚠️ ONCE MET denendi (2026-08-12'ye kadar Commons ilkti). Canli
        # olculdu: Commons'in 720px tabani gecen adaylari bile konuya gore
        # 720-4000px arasi dalgalaniyor (orn. "Ferdinand Magellan" 494-1045px
        # ham, tabandan sonra hala dusuk), Met ise 720px tabaniyla BIRLIKTE
        # tutarli 2400-4000px veriyor (Magellan 2458-3999, Cleopatra
        # 2778-4000). Bedeli Met'in kucuk katalogu: ayni olcumde "Tycho
        # Brahe" icin 0 aday dondu. Bu yuzden sirada KALDI — Met bulamazsa
        # asagidaki Commons mantigi degismeden calisir, kapsam kaybolmuyor,
        # yalnizca Met'in kapsadigi sahnelerde kalite yukseliyor.
        met_result = (
            None
            if selected is not None
            else download_met_scene_material(
                queries,
                scene_number=index,
                target_dir=target_dir,
                used_ids=used_met_ids,
                required_anchor=visual_anchor,
            )
        )

        if met_result is not None:
            met_path, met_credit = met_result
            used_met_ids.add(int(met_credit["object_id"]))
            # ⚠️ Bu kontrol 2026-08-13'e kadar YOKTU: Met parmak izini
            # kaydediyor (`_izi_ekle`) ama hic SORGULAMIYORDU. Met her
            # sahnede ILK denenen kaynak oldugu icin (f271e27) kusur her
            # sahneyi etkiliyordu — kucuk katalogunda ayni oznenin birkac
            # benzer nesnesi var ve hepsi ayri `object_id` tasidigi icin
            # `used_met_ids` de yakalamiyordu.
            #
            # Olculdu (2026-08-13, Mehmed II): sahne 1 ve 4 benzerlik 0,887
            # (esik 0,70) ve hakem "dort madalya karesi" diye yazdi.
            if _tekrar_mi(met_path, secilmis_izler):
                hazir_yedek = (met_path, met_credit)
            else:
                _izi_ekle(met_path, secilmis_izler)
                files.append(met_path)
                credits.append(met_credit)
                continue
        # Alinti tuttuysa arama zinciri hic calismiyor: sahnenin gorseli
        # zaten SECILMIS durumda, aramak onu degistirmek olurdu.
        for query in [] if selected is not None else queries:
            pages = search_commons(query)
            while True:
                candidate = select_candidate(
                    pages,
                    used_titles | failed_titles,
                    query=query,
                    required_anchor=visual_anchor,
                )
                if not candidate:
                    break
                suffix = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                }[candidate["mime"]]
                candidate_destination = target_dir / f"scene-{index:02d}{suffix}"
                try:
                    _download(candidate["url"], candidate_destination)
                except requests.HTTPError as exc:
                    status = exc.response.status_code if exc.response is not None else 0
                    # 403/404 → bu aday teslim edilemiyor.
                    # 5xx → `_get_with_retry` zaten geri cekilmeyle 5 kez denedi;
                    # buraya ulastiysa proxy O GORSEL icin kalici olarak
                    # basarisiz. Ikisi de ayni anlama geliyor: bu adayi birak,
                    # SONRAKINE gec.
                    #
                    # ⚠️ Onceden 5xx `raise` ediyordu ve tek bir sorunlu gorsel
                    # butun uretim koshumunu olduruyordu — oysa elde baska
                    # aday var. Olculdu (2026-08-05): weserv, Louvre'daki Tanis
                    # sfenksinin uzun adli dosyasinda israrla 504 dondu; ayni
                    # arama icin calisan baska adaylar mevcuttu.
                    if status not in {403, 404} and not (500 <= status < 600):
                        raise
                    failed_titles.add(candidate["title"])
                    continue
                # ⚠️ Indirdikten SONRA bakiliyor: benzerlik pikselden olculuyor,
                # baslikla ya da URL'yle bilinemez.
                if _tekrar_mi(candidate_destination, secilmis_izler):
                    if yedek is None:
                        yedek = (candidate, candidate_destination)
                    failed_titles.add(candidate["title"])
                    continue
                selected = candidate
                destination = candidate_destination
                break
            if selected:
                break
        if (not selected or destination is None) and kategori_havuzu:
            # ⚠️ Kategori havuzunda capa ve sorgu kontrolu KAPALI (`query=""`,
            # `required_anchor=""`) ve bu kasitli: kategoriye uyeligi
            # Commons'in kendi kuratoryasi belirliyor, yani ozne zaten
            # garantili. Dosya adinda capa kelimelerini aramak tam da
            # duzeltmeye calistigimiz kusuru geri getirirdi —
            # `Category:Francesca Scanagatta` icindeki dosyalar "Franziska"
            # yazmiyor.
            #
            # ⚠️ Gevsetme YALNIZCA burada. Ayni gevsetmeyi tam metin
            # aramasinda yapmak isabeti bozuyor: olculdu (2026-08-10), capa
            # "Victoria Cross" iken "herhangi bir capa kelimesi" kurali
            # "Medal, campaign", "Medal, miniature" gibi 13 adsiz madalyayi
            # iceri aliyordu — DW-116'daki yanlis ozne kusurunun ta kendisi.
            for aday in _kategori_adaylari(kategori_havuzu, used_titles | failed_titles):
                suffix = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                }[aday["mime"]]
                aday_hedefi = target_dir / f"scene-{index:02d}{suffix}"
                try:
                    _download(aday["url"], aday_hedefi)
                except requests.HTTPError:
                    failed_titles.add(aday["title"])
                    continue
                if _tekrar_mi(aday_hedefi, secilmis_izler):
                    if yedek is None:
                        yedek = (aday, aday_hedefi)
                    failed_titles.add(aday["title"])
                    continue
                selected, destination = aday, aday_hedefi
                break
        if not selected or destination is None:
            # ⚠️ IKINCI KAPI: Met (yukarida) ve Commons bos dondu. AI'ya
            # gitmeden ya da sahneyi bos birakmadan once Europeana'ya
            # bakiliyor — yuzlerce Avrupa kurumunu tek uctan tariyor
            # (DW-130). Met burada TEKRAR denenmiyor: sahne basina zaten
            # yukarida bir kez denendi, ayni queries ile ikinci deneme ayni
            # sonucu verir.
            #
            # Olculdu (2026-08-12): capa ve lisans kapilarindan gecen
            # aday sayisi Tycho Brahe 38, Hayek 39, Augustus 10,
            # Anglo-Dutch 7. Ama Harald Rose'da 1 — kaynak eklemek her
            # konuyu kurtarmiyor.
            #
            # Anahtar yoksa modul sessizce None doner; kaynak bagli
            # degilse hat eskisi gibi calisir.
            europeana_result = download_europeana_scene_material(
                queries,
                scene_number=index,
                target_dir=target_dir,
                used_ids=used_europeana_ids,
                required_anchor=visual_anchor,
            )
            if europeana_result is not None:
                eu_path, eu_credit = europeana_result
                used_europeana_ids.add(str(eu_credit["europeana_id"]))
                # ⚠️ Met'teki kusurun ikizi — burada da parmak izi
                # kaydediliyor ama sorgulanmiyordu (2026-08-13'e kadar).
                if _tekrar_mi(eu_path, secilmis_izler):
                    if hazir_yedek is None:
                        hazir_yedek = (eu_path, eu_credit)
                else:
                    used_titles.add(str(eu_credit["title"]))
                    _izi_ekle(eu_path, secilmis_izler)
                    files.append(eu_path)
                    credits.append(eu_credit)
                    continue
        if (not selected or destination is None) and yedek is not None:
            # SON CARE: butun adaylar tekrar cikti ve Europeana da bos dondu.
            # Yine de bir gorsel koymak, sahneyi bos birakmaktan iyi.
            #
            # ⚠️ Bu blok 2026-08-13'e kadar Europeana'dan ONCE geliyordu ve
            # bu yanlisti: `yedek` YALNIZCA `_tekrar_mi` dallarinda atanir,
            # yani TANIMI GEREGI bilinen bir kopya. Once calistiginda
            # `selected`i doldurup Europeana kapisini hic actirmiyordu —
            # bilinen kopya, hic denenmemis kaynaga tercih ediliyordu.
            #
            # Olculdu (2026-08-13, Mehmed II): hakem "kare 2 ve 3 ayni, kare
            # 6 ve 7 ayni" yazdi ve gorsel skoru 56'ya dustu; tekrar, o
            # koşumda kalan tek baskin kusurdu.
            selected, destination = yedek
        if (not selected or destination is None) and hazir_yedek is not None:
            # Commons yedegi de yoksa Met/Europeana'nin kopyasina donuluyor.
            # Kredisi hazir geldigi icin asagidaki kurulum atlaniyor.
            yol, kredi = hazir_yedek
            _izi_ekle(yol, secilmis_izler)
            files.append(yol)
            credits.append(kredi)
            continue
        if not selected or destination is None:
            if not kismi:
                raise MaterialsUnavailableError(
                    f"no public-domain or CC0 archive image found for scene {index}: {term}"
                )
            # Kismi kip: bu sahne bos birakilir, bulunanlar korunur.
            files.append(None)
            eksik.append(index)
            continue
        used_titles.add(selected["title"])
        _izi_ekle(destination, secilmis_izler)
        files.append(destination)
        credits.append(
            {
                "scene": index,
                "title": selected["title"],
                "source_url": selected["source_url"],
                "license": selected["license"],
                "artist": selected["artist"],
            }
        )
    if kismi and len(eksik) == len(scenes):
        # Hicbir sahne bulunamadi — kismi kipte bile bu bir basarisizlik.
        raise MaterialsUnavailableError(
            f"no archive image found for any of the {len(scenes)} scenes"
        )
    (target_dir / "credits.json").write_text(
        json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return files, credits
