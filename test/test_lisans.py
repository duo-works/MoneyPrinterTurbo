"""Lisans kabulu — PD/CC0 ve CC BY evet, CC BY-SA hayir.

Bu bir hukuki sinir; testler o sinirin kodda tuttugunu dogrular.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402
from youtube_automation import format_commons_credits  # noqa: E402


@pytest.mark.parametrize(
    "lisans",
    ["Public domain", "PD-old-70", "CC0", "cc0 1.0", "PUBLIC DOMAIN"],
)
def test_kosulsuz_lisanslar_kabul(lisans):
    assert wm.is_safe_license(lisans)
    assert wm.kullanilabilir_lisans(lisans)


@pytest.mark.parametrize("lisans", ["CC BY 2.0", "CC BY 4.0", "cc by 3.0"])
def test_atif_lisanslari_kabul(lisans):
    """Olculdu: bunlar reddedilirken gercek fotograflarin %78'i eleniyordu."""
    assert wm.atif_gerektiren(lisans)
    assert wm.kullanilabilir_lisans(lisans)
    assert not wm.is_safe_license(lisans), "kosulsuz degil, atif istiyor"


@pytest.mark.parametrize(
    "lisans",
    ["CC BY-SA 4.0", "CC BY-SA 2.0", "cc by-sa 3.0", "CC BY-SA", "Share Alike 1.0"],
)
def test_share_alike_reddediliyor(lisans):
    """⚠️ Metin tuzagi: "cc by-sa 4.0" metni "cc by" ICERIYOR.

    Naif bir `in` kontrolu share-alike'i de gecirirdi. Share-alike turev eseri
    ayni lisansa zorluyor; bu videonun tamaminin CC BY-SA olmasi anlamina
    gelebilir ve baskalarinin videoyu alip kullanmasina kapi acar. Kullanici
    kararı: PD/CC0 + CC BY.
    """
    assert wm.paylasimli_lisans(lisans)
    assert not wm.atif_gerektiren(lisans), f"{lisans} atif lisansi sayilmamali"
    assert not wm.kullanilabilir_lisans(lisans), f"{lisans} KABUL EDILMEMELI"


@pytest.mark.parametrize("lisans", ["", "Fair use", "All rights reserved", "GFDL"])
def test_bilinmeyen_lisans_reddediliyor(lisans):
    assert not wm.kullanilabilir_lisans(lisans)


def test_lisans_kontrolu_secime_bagli():
    """Fonksiyon dogru olsa bile secim onu cagirmazsa sinir tutmaz."""
    kaynak = Path(wm.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def select_candidate(")
    govde = kaynak[i : i + 3000]

    assert "kullanilabilir_lisans(license_name)" in govde


# --- Atif metni ----------------------------------------------------------


def test_atif_sanatci_ve_lisansi_yaziyor():
    """CC BY icin atif hukuki zorunluluk — ad ve lisans gorunmeli."""
    metin = format_commons_credits(
        [
            {
                "source_url": "https://commons.wikimedia.org/wiki/File:A.jpg",
                "artist": "Jane Doe",
                "license": "CC BY 4.0",
            }
        ]
    )

    assert "Jane Doe" in metin
    assert "CC BY 4.0" in metin
    assert "https://commons.wikimedia.org/wiki/File:A.jpg" in metin


def test_baslik_artik_yaniltici_degil():
    """Eski baslik "Public-domain / CC0" diyordu; CC BY eklenince yanlis olur."""
    metin = format_commons_credits(
        [{"source_url": "https://x/A.jpg", "artist": "", "license": "CC BY 2.0"}]
    )

    assert "CC BY" in metin.splitlines()[0]


def test_ayni_kaynak_bir_kez_yaziliyor():
    metin = format_commons_credits(
        [
            {"source_url": "https://x/A.jpg", "artist": "A", "license": "CC0"},
            {"source_url": "https://x/A.jpg", "artist": "A", "license": "CC0"},
        ]
    )

    assert metin.count("https://x/A.jpg") == 1


def test_kaynak_yoksa_bos_doner():
    assert format_commons_credits([]) == ""
    assert format_commons_credits([{"source_url": ""}]) == ""


def test_sanatci_bilinmiyorsa_baglanti_yine_yaziliyor():
    metin = format_commons_credits(
        [{"source_url": "https://x/B.jpg", "artist": "", "license": ""}]
    )

    assert "https://x/B.jpg" in metin
