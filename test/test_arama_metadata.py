"""Baslik/aciklama/etiket ARAMA icin yaziliyor mu (DW-104).

Kanal Ingilizce izleyiciye acildi. Bir Short'u bulunur kilan sey baslik ve
aciklamanin, insanin arama kutusuna YAZDIGI ifadeye benzemesi. Eski yonerge
yalnizca bicim soyluyordu ("iki cumlelik ozet, 3-5 hashtag") ve arama niyeti
hakkinda tek kelime etmiyordu; sonuc ansiklopedi basligiydi.

Sozlesme prompt metninde yasadigi icin testler metne bakiyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def _sistem_yonergesi() -> str:
    """Modele giden metnin kendisi — kaynak dilimleme degil (bkz. DW-105)."""
    return ya.editoryal_sistem_yonergesi()


def test_baslik_arama_ifadesi_olarak_isteniyor():
    """Olculdu (2026-08-07): uretilen basliklar manset, sorgu degildi.

        "The Disappearance of the Ancestral Puebloans"

    Kimse bunu aramiyor; aranan ifade "what happened to the Anasazi".
    """
    yonerge = _sistem_yonergesi()

    assert "WRITE THE TITLE AS A SEARCH QUERY, NOT AS A HEADLINE" in yonerge
    assert "first three words" in yonerge, "aranan ozel ad basa gelmeli"


def test_populer_ad_bilimsel_adin_onune_geciyor():
    """"Ancestral Puebloans" dogru terim ama arama hacmi "Anasazi"de.

    Baslik populer adi alir (bulunurluk), aciklama bilimsel adi tasir
    (dogruluk) — ikisi de kaybedilmiyor.
    """
    yonerge = _sistem_yonergesi()

    assert "popular name" in yonerge
    assert "the description carries the scholarly one" in yonerge


def test_aciklamanin_ilk_cumlesi_arama_ifadesini_tekrarliyor():
    """Arama sonuclarinda gorunen ve indekslenen kisim ilk cumle."""
    yonerge = _sistem_yonergesi()

    assert "FIRST sentence" in yonerge
    assert "restate the title's search phrase" in yonerge


def test_aciklama_soruyu_cevapsiz_birakmiyor():
    """Basligin sordugu seyi aciklamada da cevaplamak izlenmeyi degil
    tiklamayi degil, ARAMA eslesmesini artiriyor: cevabin kelimeleri de
    indeksleniyor."""
    assert "never leave the question unanswered" in _sistem_yonergesi()


def test_etiketler_arama_terimi_olarak_isteniyor():
    yonerge = _sistem_yonergesi()

    assert "alternative and popular spellings" in yonerge
    assert "never write a phrase nobody would type" in yonerge


def test_shorts_ve_uzunluk_kisiti_korunuyor():
    """Yeni kural eskisinin yerini aliyor, onu SILMIYOR."""
    yonerge = _sistem_yonergesi()

    assert "#Shorts" in yonerge
    assert "65 characters" in yonerge
    assert "3-5 hashtags" in yonerge
    assert "6-10 concise strings" in yonerge


def test_dogrulama_hala_uc_etiket_istiyor():
    """Prompt sozlesmesi degisti; KOD kapisi yerinde durmali."""
    assert "at least three tags are required" in KAYNAK
