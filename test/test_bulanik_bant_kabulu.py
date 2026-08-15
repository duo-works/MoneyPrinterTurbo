"""Yatay arsiv fotografi elenmemeli — bulanik bant kabul (DW-123).

⚠️ Karar kanal sahibinin (2026-08-11): "bulanık bantlı gerçek fotoğraf",
tam ekran AI gorseline tercih ediliyor.

Olculdu (2026-08-10), Wikidata ile cozulen 7 Commons kategorisi: lisans ve
cozunurluk bakimindan **80** kullanilabilir gorsel vardi, eski oran filtresini
gecen **24**. Elenen 56 gorselin yerine AI uretiliyordu.

⚠️ Asil celiski: `youtube_automation.dikeye_uydur` bu gorselleri ZATEN
basabiliyordu — kirpma `AZAMI_KIRPMA`'yi gecince bulanik arka plan yolunu
kullaniyor. Yani retrieval kendi render'indan kati davraniyordu.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402
import youtube_automation as ya  # noqa: E402


# --- Esik render'la ayni mi ----------------------------------------------


def test_kirpma_esigi_render_ile_ayni():
    """⚠️ Ayrisirlarsa retrieval yine kendi render'indan farkli dusunur.

    Kusurun kaynagi tam olarak buydu: arama bir esikle, render baskasiyla
    karar veriyordu.
    """
    assert wm.AZAMI_KIRPMA == ya.AZAMI_KIRPMA


def test_shorts_orani_render_ile_ayni():
    assert wm.SHORTS_ORANI == ya.SHORTS_EN / ya.SHORTS_BOY


# --- Kabul sinirlari ------------------------------------------------------


def test_yaygin_fotograf_oranlari_geciyor():
    """Arsivdeki tarihi fotograflarin neredeyse tamami bu oranlarda."""
    for en, boy, ad in [
        (1600, 1200, "4:3"),
        (1500, 1000, "3:2"),
        (1920, 1080, "16:9"),
    ]:
        assert wm.dikey_karede_yeterli(en, boy), ad


def test_panorama_hala_eleniyor():
    """Bulanik karenin ortasindaki ince serit izlenebilir bir kare degil."""
    assert not wm.dikey_karede_yeterli(2220, 1000)  # 2,22 → %25
    assert not wm.dikey_karede_yeterli(5000, 1000)  # 5,00 → %11


def test_dikey_ve_kare_gecmeye_devam_ediyor():
    assert wm.dikey_karede_yeterli(1080, 1920)
    assert wm.dikey_karede_yeterli(1000, 1000)


def test_gecersiz_olcu_hala_eleniyor():
    assert not wm.dikey_karede_yeterli(0, 100)
    assert not wm.dikey_karede_yeterli(100, 0)
    assert not wm.tam_ekran_doluyor(0, 0)


def test_esik_dolulukla_tutarli():
    """Kabul siniri gercekten `ASGARI_DIKEY_DOLULUK` — yuvarlak sayi degil."""
    hemen_ustu = wm.SHORTS_ORANI / (wm.ASGARI_DIKEY_DOLULUK + 0.01)
    hemen_alti = wm.SHORTS_ORANI / (wm.ASGARI_DIKEY_DOLULUK - 0.01)
    assert wm.dikey_karede_yeterli(round(hemen_ustu * 1000), 1000)
    assert not wm.dikey_karede_yeterli(round(hemen_alti * 1000), 1000)


# --- Tam ekran tercihi ----------------------------------------------------


def test_tam_ekran_ayrimi():
    """⚠️ Sinir `AZAMI_KIRPMA`'dan cikiyor: oran ~0,87'ye kadar kirp-doldur.

    Yani "hafif yatay" bile (1200x1300, oran 0,92) bulanik yola dusuyor —
    render boyle davraniyor, filtre de ona uymali.
    """
    assert wm.tam_ekran_doluyor(1080, 1920)  # dikey
    assert wm.tam_ekran_doluyor(1000, 1200)  # oran 0,83 → kirp-doldur
    assert not wm.tam_ekran_doluyor(1200, 1300)  # oran 0,92 → bulanik yol
    assert not wm.tam_ekran_doluyor(1920, 1080)  # 16:9 → bulanik yol


def _sayfa(ad, en, boy):
    return {
        "title": ad,
        "imageinfo": [
            {
                "mime": "image/jpeg",
                "url": f"https://upload.wikimedia.org/{ad}",
                "descriptionurl": "https://commons.wikimedia.org/wiki/x",
                "width": en,
                "height": boy,
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "ImageDescription": {"value": ""},
                },
            }
        ],
    }


def test_tam_ekran_buyuk_panoramayi_geciyor():
    """⚠️ Kabul etmek TERCIH etmek degil.

    Cozunurluk puani tavani 4,0; bonus ondan buyuk olmazsa buyuk bir yatay
    gorsel kucuk ama tam ekran bir dikeyi geceredi ve videolar bulanik
    bantla dolardi.
    """
    sayfalar = [
        _sayfa("File:genis.jpg", 4000, 2100),  # ~8,4 MP, bulanik yol
        _sayfa("File:dikey.jpg", 800, 1400),  # ~1,1 MP, tam ekran
    ]
    secilen = wm.select_candidate(sayfalar, set())
    assert secilen["title"] == "File:dikey.jpg"


def test_tam_ekran_yoksa_yatay_seciliyor():
    """Tek secenek bulanik bantsa AI'ya gitmek yerine o kullanilmali."""
    sayfalar = [_sayfa("File:genis.jpg", 1920, 1080)]
    secilen = wm.select_candidate(sayfalar, set())
    assert secilen is not None
    assert secilen["title"] == "File:genis.jpg"


def test_filtre_secime_bagli_kaliyor():
    """Fonksiyon dogru olsa bile aday secimi cagirmazsa kusur surer."""
    kaynak = Path(wm.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def _puanli_adaylar(") :]
    # ⚠️ Suzgec KAREYE BAGLANDI (2026-08-15): `karede_yeterli` hedef orani
    # da aliyor. Aranan sey degismedi — suzgecin aday seciminde CAGRILMASI.
    assert "karede_yeterli(width, height, hedef_oran)" in govde
    assert "tam_ekran_doluyor(width, height, hedef_oran)" in govde


def test_render_bulanik_yolu_gercekten_kullaniyor():
    """Kabul ettigimiz gorseli render'in basabildigi kilitlensin."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def dikeye_uydur(")
    govde = re.sub(r"\s+", " ", kaynak[i : i + 3000])
    assert "GaussianBlur" in govde
    assert "kirpma <= AZAMI_KIRPMA" in govde
