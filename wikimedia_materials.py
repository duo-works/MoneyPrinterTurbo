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
        kimlik = ""
        if sayfalar:
            kimlik = str(sayfalar[0].get("pageprops", {}).get("wikibase_item", ""))
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


def download_scene_materials(
    topic: str,
    scenes: list[dict[str, str]],
    target_dir: Path,
    *,
    visual_anchor: str = "",
    excluded_titles: set[str] | None = None,
    excluded_met_ids: set[int] | None = None,
    kismi: bool = False,
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
    kategori_havuzu: list[dict[str, Any]] = []
    for aday_konu in (visual_anchor.strip(), topic.strip()):
        if not aday_konu:
            continue
        kategori = commons_kategorisi(aday_konu)
        if not kategori:
            continue
        kategori_havuzu = kategori_gorselleri(kategori)
        if kategori_havuzu:
            print(
                f"ℹ️ Commons kategorisi: {kategori} "
                f"({len(kategori_havuzu)} dosya) — {aday_konu}",
                flush=True,
            )
            break
    for index, scene in enumerate(scenes, 1):
        term = scene.get("search_term", "").strip()
        queries = build_search_queries(topic, term)
        selected = None
        destination = None
        failed_titles: set[str] = set()

        # ⚠️ ONCE MET denendi (2026-08-12'ye kadar Commons ilkti). Canli
        # olculdu: Commons'in 720px tabani gecen adaylari bile konuya gore
        # 720-4000px arasi dalgalaniyor (orn. "Ferdinand Magellan" 494-1045px
        # ham, tabandan sonra hala dusuk), Met ise 720px tabaniyla BIRLIKTE
        # tutarli 2400-4000px veriyor (Magellan 2458-3999, Cleopatra
        # 2778-4000). Bedeli Met'in kucuk katalogu: ayni olcumde "Tycho
        # Brahe" icin 0 aday dondu. Bu yuzden sirada KALDI — Met bulamazsa
        # asagidaki Commons mantigi degismeden calisir, kapsam kaybolmuyor,
        # yalnizca Met'in kapsadigi sahnelerde kalite yukseliyor.
        met_result = download_met_scene_material(
            queries,
            scene_number=index,
            target_dir=target_dir,
            used_ids=used_met_ids,
            required_anchor=visual_anchor,
        )
        # Tekrar diye elenen ilk aday: baska hicbir sey bulunamazsa buna
        # donulur. Delik birakmaktansa benzer bir gorsel iyidir.
        yedek: tuple[dict[str, Any], Path] | None = None
        # Met/Europeana'nin kredisi zaten hazir gelir; Commons yedeginden
        # ayri tutuluyor cunku son carede krediyi yeniden kurmak gerekmiyor.
        hazir_yedek: tuple[Path, dict[str, Any]] | None = None

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
        for query in queries:
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
