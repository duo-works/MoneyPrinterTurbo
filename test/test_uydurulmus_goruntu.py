"""Goruntusu SONRADAN URETILMIS dosyalar videoya girmemeli.

⚠️ NEDEN VAR — kanal kurali acik: videoda AI uretimi fotograf olmayacak.
Olculdu (2026-08-18, Cemal Pasha — YAYINLANMIS video): alti birincil
gorselinin IKISI spekulatif renklendirilmis turevdi, biri AYRICA AI ile
buyutulmustu. Commons'in kendi uyarilari:

    "This image has been colorized. The coloring is speculative and may
     differ significantly from the real colors."
    "This image has been digitally upscaled using AI software. This process
     may have introduced inaccurate, speculative details not present in the
     original picture."

Yani yayinlanmis bir videoda, ORIJINALDE BULUNMAYAN ayrintilar tasidigi
Commons'ta YAZILI bir fotograf var.

⚠️ Isaret zaten cekiliyordu (`extmetadata.Categories`, `iiprop`e dahil); yeni
bir ag istegi gerekmedi. Canli Commons ile dogrulandi (2026-08-18): iki kirli
dosya elendi, uc temiz dosya gecti, yanlis alarm yok.

⚠️ ARZ OLCULDU, cunku kalite ugruna arzi oldurmek kusuru kusurla degistirmek
olurdu (`capa-havuzu-tukeniyor` bu depoda olculmus bir kusur):

    Cemal Pasha   menu 32 -> 29   (esik 6)
    Gobekli Tepe  15 · Ellora 40 · Palmyra 40 · Herculaneum 39 — degismedi

Hicbiri esigin altina inmedi.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402

KAYNAK = Path(wm.__file__).read_text(encoding="utf-8")


# --- Elenmesi gerekenler ----------------------------------------------------


@pytest.mark.parametrize(
    "kategoriler",
    [
        # ⚠️ Ikisi de CANLI Commons verisinden; uydurulmadi.
        "Djemal Pasha|Author died more than 70 years ago public domain images|"
        "Template Unknown (author)|CC-PD-Mark|AI upscaler software unknown|Colorized images",
        "PD US|Djemal Pasha|Retouched pictures|Colorized images|Ottoman Empire (LoC)",
        "Colorized images",
        "Colourized images",
        "Images upscaled with AI",
    ],
)
def test_UYDURULMUS_goruntu_yakalaniyor(kategoriler):
    assert wm.uydurulmus_goruntu(kategoriler)


def test_AI_BUYUTME_tek_basina_yeterli():
    """⚠️ Asil kural ihlali bu: "orijinalde bulunmayan spekulatif ayrintilar"."""
    assert wm.uydurulmus_goruntu("Djemal Pasha|AI upscaler software unknown")


def test_BUYUK_KUCUK_harf_farketmiyor():
    assert wm.uydurulmus_goruntu("COLORIZED IMAGES")


# --- Gecmesi gerekenler -----------------------------------------------------


@pytest.mark.parametrize(
    "kategoriler",
    [
        # Canli ciktidan gelen TEMIZ dosyalar.
        "Djemal Pasha|PD Old|PD Tr|PD US expired|PD-Ottoman|CC-PD-Mark",
        "Göbekli Tepe|Turkey photographs taken on 2022-07-21|Self-published work",
        "",
    ],
)
def test_TEMIZ_dosya_geciyor(kategoriler):
    assert not wm.uydurulmus_goruntu(kategoriler)


@pytest.mark.parametrize(
    "kategoriler",
    ["Sinai (Egypt)|Photographs", "Mountains of Sinai|Ottoman Empire", "Sinai Peninsula"],
)
def test_SINAI_yanlis_alarmi_YOK(kategoriler):
    """⚠️ NEDEN VAR — "ai " ALT DIZESI "Sinai" icinde geciyor. Bunu olcerken
    kendi tarama betigim tam bu yanlis alarmi verdi; eslesme bu yuzden kategori
    adinin TAMAMINA yapiliyor. Alt dize aramasi Sina Yarimadasi
    fotograflarinin tamamini elerdi."""
    assert not wm.uydurulmus_goruntu(kategoriler)


def test_RETOUCHED_tek_basina_ELEMIYOR():
    """⚠️ BILINCLI: "Retouched pictures" kirpma ve toz temizligini de kapsiyor,
    yani dogru bir arsiv taramasini da elerdi. Listede yalnizca goruntuyu
    UYDURAN islemler var."""
    assert not wm.uydurulmus_goruntu("Retouched pictures|Djemal Pasha")


def test_KISMI_ad_eslesmiyor():
    """"colorized images collection" ayri bir kategori; tam ad eslesmeli."""
    assert not wm.uydurulmus_goruntu("Colorized images collection")


# --- Sinir durumlari --------------------------------------------------------


def test_BOSLUK_ve_BOS_parcalar_PATLAMIYOR():
    assert not wm.uydurulmus_goruntu("||  ||")


def test_None_PATLAMIYOR():
    assert not wm.uydurulmus_goruntu(None)


# --- Baglanti ---------------------------------------------------------------


def test_suzgec_LISANSIN_YANINDA():
    """⚠️ Nokta bilincli: `kullanilabilir_lisans` butun depoda TEK yerde
    cagriliyor ve `_puanli_adaylar`in BES cagirani var (menu, arama,
    `_kategori_adaylari`, tekil sayfa yolu). Tek suzgec her yolu kapatiyor.
    Yalnizca menuye konsaydi kategori havuzundan gelen ikincil gorseller
    acikta kalirdi."""
    assert "if not kullanilabilir_lisans(license_name):" in KAYNAK
    assert "uydurulmus_goruntu(_metadata_value(image, \"Categories\"))" in KAYNAK

    lisans = KAYNAK.index("if not kullanilabilir_lisans(license_name):")
    suzgec = KAYNAK.index('uydurulmus_goruntu(_metadata_value(image, "Categories"))')
    assert 0 < suzgec - lisans < 1400, "suzgec lisans kontrolunden uzaklasmis"


def test_ELEME_loglaniyor():
    """⚠️ Sessiz eleme bu depoda olculmus bir kusur: 0 uygun capa = uretim
    durur ama log "red" der (`capa-havuzu-tukeniyor`)."""
    assert 'print(f"ℹ️ elendi ({uydurulmus}): {title}"' in KAYNAK


def test_kategoriler_ZATEN_cekiliyor():
    """Yeni bir ag istegi eklenmedi — `extmetadata` zaten isteniyordu."""
    assert "extmetadata" in KAYNAK
    assert "iiprop" in KAYNAK
