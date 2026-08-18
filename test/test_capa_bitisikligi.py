"""Capanin kelimeleri BITISIK gecmeli — adas ozel adlar arsive giriyordu.

⚠️ Olculdu (2026-08-18, "Operation Storm" koşumu). Capa kapisi kelimeleri
sirasiz ve bitisiksiz ariyordu:

    capa  "Operation Storm"          -> {"operation", "storm"}
    dosya "Operation DESERT Storm"   -> ikisini de iceriyor, GECIYORDU

Menuyu dokunce delik butun genisligiyle goruldu — 15 girdinin 13'u adas:

    Operation EASTERN Storm (Afganistan, ABD Deniz Piyadeleri)   7 dosya
    Operation DESERT Storm  (Kuveyt, 1991 Korfez Savasi)         4 dosya
    Tropical Storm Nalgae   (Filipinler tayfunu)                 1 dosya
    (+1 baska)

Geriye kalan 2 dosya konunun GERCEK arsiviydi: Oluja haritasi ve Martic'in
tahliye emri. Bedeli iki katliydi:

  * Hakem 50 / 0 / 53 verdi (kapi 70) — videoya Kuveyt'te yanan petrol
    kuyulari ve USAF ucaklari girmisti; bir uretim slotu yandi.
  * Menu 15 GORUNDUGU icin arz kapisi (6 sahne icin 6 gorsel) konuyu
    geciriyordu; model dogru davranip copu almiyor, iki iyi dosyayi tekrar
    ediyor ve alinti kapisindan dusuyordu. 21:07 koşumunda ayni red ust uste
    UC kez, kelimesi kelimesine ayni iki dosya adiyla yazildi.

Yani kural yalnizca kotu goruntuyu elemiyor, konunun arzini DURUST
gosteriyor: bitisiklikten sonra menu 2'ye duser ve konu daha plan asamasinda
reddedilir — render ve goru cagrisi harcanmadan.

Bu, deponun dorduncu kez olctugu kusur sinifi (`Nadia Murad`/`Murad III`,
`Herculaneum, Missouri`, `Getty Villa`): kapi ADI olcuyor, GORUNTUYU degil.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import capa_eslesme as ce  # noqa: E402
import wikimedia_materials as wm  # noqa: E402


# --- Kuralin kendisi -----------------------------------------------------


@pytest.mark.parametrize(
    "capa,kanit,beklenen",
    [
        # Olculen adaslar — hepsi ESKI kapiyi geciyordu.
        ("Operation Storm", "usaf f-16a f-15c f-15e desert storm edit2", False),
        ("Operation Storm", "cannons help gain territory in operation eastern storm", False),
        ("Operation Storm", "rescue operation tropical storm nalgae", False),
        (
            "Operation Storm",
            "french military forces that cleared the beach in kuwait city during "
            "operation desert storm",
            False,
        ),
        # Konunun GERCEK arsivi — gecmeye devam etmeli.
        ("Operation Storm", "map 49 croatia operation storm oluja 1995", True),
        # Aradaki KISA kelimeler masum: capanin kendisi elenirse kural yanlistir.
        (
            "Republic of Serbian Krajina",
            "flag of the republic of serbian krajina",
            True,
        ),
        # Alt dize deligi: "storm" artik "brainstorm"un icinde bulunmuyor.
        ("Storm", "a brainstorm session in the office", False),
        # On ek korunuyor: cogul/tamlama ekleri eskiden oldugu gibi geciyor.
        ("Pyramid", "the great pyramids of giza at sunrise", True),
        # Capasiz cagri her seyi gecirir (kapi degil, iyilestirme).
        ("", "herhangi bir dosya", True),
    ],
)
def test_bitisiklik_kurali(capa, kanit, beklenen):
    terimler = ce.sirali_terimler(capa)
    assert ce.bitisik_geciyor(kanit, terimler) is beklenen


def test_sirali_terimler_SIRAYI_koruyor():
    """Kume degil liste donmeli — bitisiklik sira olmadan olculemez."""
    assert ce.sirali_terimler("Republic of Serbian Krajina") == [
        "republic",
        "serbian",
        "krajina",
    ]


# --- Kapinin kendisi -----------------------------------------------------


def _sayfa(baslik: str, aciklama: str = "") -> dict:
    return {
        "title": baslik,
        "imageinfo": [
            {
                "url": "https://x/i.jpg",
                "mime": "image/jpeg",
                "width": 1200,
                "height": 1600,
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "ImageDescription": {"value": aciklama},
                    "Artist": {"value": "x"},
                },
                "descriptionurl": "https://commons/x",
            }
        ],
    }


def _gecenler(sayfalar, capa):
    return {
        str(aday.get("title") or "")
        for aday in wm._puanli_adaylar(sayfalar, set(), "", capa)
    }


def test_commons_kapisi_adas_operasyonu_eliyor():
    """Olculen vakanin birebir kendisi: menunun 13/15'i bu yoldan giriyordu."""
    sayfalar = [
        _sayfa("File:Map 49 - Croatia - Operation Storm Oluja 1995.jpg"),
        _sayfa("File:USAF F-16A F-15C F-15E Desert Storm edit2.jpg"),
        _sayfa("File:Cannons help gain territory in Operation Eastern Storm.jpg"),
        _sayfa("File:Rescue Operation - Tropical Storm Nalgae.jpg"),
    ]

    gecen = _gecenler(sayfalar, "Operation Storm")

    assert gecen == {"File:Map 49 - Croatia - Operation Storm Oluja 1995.jpg"}


def test_capa_ACIKLAMADA_bitisik_geciyorsa_kabul():
    """Shorts yolunda kanit baslik + aciklama; kural ikisinde de ayni."""
    sayfalar = [
        _sayfa("File:IMG_2231.jpg", "The Republic of Serbian Krajina parliament, 1993"),
        _sayfa("File:IMG_2232.jpg", "The Serbian army in the republic, Krajina region"),
    ]

    gecen = _gecenler(sayfalar, "Republic of Serbian Krajina")

    # Ikincisinde capa kelimeleri dagilmis: ayri bir konudan soz ediyor olabilir.
    assert gecen == {"File:IMG_2231.jpg"}


def test_GENEL_kelime_bitisikligi_bolmuyor():
    """⚠️ "Great Pyramid" capasi "Pyramid of Djoser"i ELEMEMELI.

    Genel kelimeler capadan da kanittan da AYNI anda dusuruluyor. Yalnizca
    capadan dusurulseydi kanit akisinda kalir ve obegi bolerdi; yalnizca
    kanittan dusurulseydi capa hicbir zaman eslesmezdi. Iki tarafi ayri
    suzmek, bu deponun iki kez olctugu "kapi baska bir listeyi olcuyor"
    kusurunun ta kendisi olurdu.
    """
    sayfalar = [
        _sayfa("File:Pyramid of Djoser at Saqqara.jpg"),
        _sayfa("File:Great Pyramid of Giza.jpg"),
        _sayfa("File:Great cathedral of Cologne.jpg"),
    ]

    gecen = _gecenler(sayfalar, "Great Pyramid")

    assert gecen == {
        "File:Pyramid of Djoser at Saqqara.jpg",
        "File:Great Pyramid of Giza.jpg",
    }


def test_kanittaki_GENEL_kelime_obegi_BOLMUYOR():
    """⚠️ Simetrinin asil sinavi: genel kelime capa kelimelerinin ARASINDA.

    "Hadrian Wall" capasi ile "Hadrian's Roman Wall" dosyasi. Genel kelimeler
    yalnizca capadan dusurulseydi "roman" kanit akisinda kalir, obegi boler ve
    kapi DOGRU dosyayi elerdi. Tek terimli capalar bu kusuru gosteremez —
    orada bitisiklik zaten aranmaz.
    """
    sayfalar = [
        _sayfa("File:Hadrian's Roman Wall at Housesteads.jpg"),
        _sayfa("File:Roman wall of Lugo, Spain.jpg"),
    ]

    gecen = _gecenler(sayfalar, "Hadrian Wall")

    assert gecen == {"File:Hadrian's Roman Wall at Housesteads.jpg"}


def test_capasi_TAMAMEN_genel_kelimelerden_olusan_konu_calismaya_devam_ediyor():
    """⚠️ Genel kelimeler yalnizca AYIRT EDICI terim varken dusuruluyor.

    Kosulsuz dusurulseydi "Ancient Egypt" gibi bir capadan geriye hicbir
    terim kalmaz ve kapi butun arsivi gecirirdi — sessizce acilan bir kapi,
    kapali kapidan daha kotudur.
    """
    sayfalar = [
        _sayfa("File:Ancient Egypt temple.jpg"),
        _sayfa("File:Modern Paris street.jpg"),
    ]

    gecen = _gecenler(sayfalar, "Ancient Egypt")

    assert gecen == {"File:Ancient Egypt temple.jpg"}
