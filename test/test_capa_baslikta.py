"""Uzun formatta capa BASLIKTA aranir, aciklamada degil.

⚠️ OLCULDU (2026-08-16, uc Herculaneum videosu: 72, 72, 52 — kapi 80).
Kelimenin aciklamada gecmesi, gorselin onu GOSTERDIGI anlamina gelmiyor.
Videoya giren uc dosya ve Commons aciklamalarindaki ilgili cumle:

    1846 Missouri serif ilani → "Louis to Herculaneum, by Catalang's ford"
    Getty Villa, Kaliforniya  → "1974 tasarimi Villa dei Papiri'den alindi"
    Kolezyum, Roma            → "MS 79 ... Herculaneum ve Pompeii'yi yok etti"

Uc ayri gecis bicimi: ADAS YER (Herculaneum, Missouri gercek bir kasaba),
MODERN KOPYA, GECERKEN ANMA. Hicbiri konuya ozgu degil — adasi, muze
replikasi ya da meshur bir baglam cumlesi olan her konu ayni kapidan gecer.

⚠️ KAPININ NEDEN COKTUGU ayri olculdu: `build_search_queries` terimi ikili
parcalara boluyor ("Herculaneum decorative elements Pompeii comparison" →
10 sorgu) ve iki terimlik sorguda asgari eslesme 1'e dusuyor. Yani tam terim
tutmayinca ilgi kapisi 3'ten 1'e iniyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402


def _sayfa(baslik: str, aciklama: str = "", genislik: int = 4000, yukseklik: int = 2400) -> dict:
    return {
        "title": baslik,
        "imageinfo": [
            {
                "mime": "image/jpeg",
                "url": "https://example.invalid/o.jpg",
                "width": genislik,
                "height": yukseklik,
                "extmetadata": {
                    "LicenseShortName": {"value": "CC0"},
                    "ImageDescription": {"value": aciklama},
                },
            }
        ],
    }


# Videoya gercekten girmis uc dosya, gercek aciklamalariyla.
KOLEZYUM = _sayfa(
    "File:Colosseum, Rome (44601875200).jpg",
    "The eruption of AD 79, which destroyed the towns of Herculaneum and Pompeii",
)
GETTY = _sayfa(
    "File:Getty Villa - 17985 Pacific Coast Highway - Pacific Palisades, California1.jpg",
    "Hatch &amp; Faulkner's original 1974 design borrowed wholesale from the "
    "Villa dei Papiri at Herculaneum",
)
MISSOURI = _sayfa(
    "File:Announcement-John Hammond, sheriff of Jefferson County, 1846.jpg",
    "the road from St. Louis to Herculaneum, by Catalang's ford",
)
GERCEK = _sayfa(
    "File:Deux hangars à bateaux Herculaneum.jpg",
    "Boat houses at Herculaneum where skeletons were found",
    4470,
    2758,
)


def _sec(sayfalar, capa_baslikta):
    return wm.select_candidate(
        sayfalar,
        set(),
        query="Herculaneum Pompeii",
        required_anchor="Herculaneum",
        hedef_oran=wm.UZUN_ORANI,
        capa_baslikta=capa_baslikta,
    )


def test_ADAS_KASABA_eleniyor():
    assert _sec([MISSOURI], True) is None


def test_MODERN_KOPYA_eleniyor():
    assert _sec([GETTY], True) is None


def test_GECERKEN_ANMA_eleniyor():
    assert _sec([KOLEZYUM], True) is None


def test_GERCEK_dosya_geciyor():
    """⚠️ Kural fazla sikiysa arz kurur — asil risk bu."""
    assert _sec([GERCEK], True) is not None


def test_kotuler_iyiyi_ARTIK_gecemiyor():
    """Asil senaryo: buyuk ve iyi kadrajli alakasiz fotograf, puanlamada
    yon (+5) ve cozunurluk (+4) bonuslariyla one geciyordu."""
    secilen = _sec([KOLEZYUM, GETTY, MISSOURI, GERCEK], True)

    assert secilen is not None
    assert "Herculaneum" in secilen["title"]


def test_SHORTS_yolu_DEGISMEDI():
    """⚠️ En kritik olcut. Shorts'ta capa bilerek DAR olabiliyor ve dar capa
    cogu zaman baslikta gecmez; o yol 96 puan aliyor, bozulmamali."""
    assert _sec([KOLEZYUM], False) is not None


def test_varsayilan_KAPALI():
    """Yeni kapi opt-in olmali — cagrisi olmayan her yol eski davranista."""
    assert (
        wm.select_candidate(
            [KOLEZYUM], set(), query="Herculaneum Pompeii", required_anchor="Herculaneum"
        )
        is not None
    )


def test_uretim_cagrisi_BICIME_bagli():
    """⚠️ Kapi dogru olsa da cagri gecirmezse hic calismaz — bu sinif kusur
    bu oturumda iki koşum oldurdu."""
    kaynak = Path(
        Path(wm.__file__).parent / "youtube_automation.py"
    ).read_text(encoding="utf-8")

    assert "capa_baslikta=not bicim.dikey" in kaynak


def test_sorgu_parcalanmasi_KAPIYI_dusuruyor():
    """Kusurun mekanizmasi — duzelirse bu test bunu haber verir."""
    parcalar = wm.build_search_queries(
        "Herculaneum", "Herculaneum decorative elements Pompeii comparison"
    )
    tek_eslesmelik = [s for s in parcalar if len(wm._relevance_terms(s)) < 3]

    assert len(tek_eslesmelik) >= 8, "parcalanma kapiyi 1'e dusuruyordu"
