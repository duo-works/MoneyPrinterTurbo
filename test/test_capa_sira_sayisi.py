"""Hukumdar sira sayisi capanin PARCASI — kapi onu dusuruyordu.

⚠️ Olculdu (2026-08-13, Murad III koşumu). Capa kapisi 4 harften kisa
kelimeleri atiyordu, yani sira sayisi sessizce dusuyordu:

    "Murad III" -> {"murad"}     "Mehmed II" -> {"mehmed"}

Sonucu somut: `File:Nadia Murad Nobel Peace Prize 2018.jpg` "Murad III"
capasini GECIYORDU. Hakem uc ayri koşumda yakaladi — Nadia Murad, Murad V
ve Fatih'in profili "Murad III" videosuna girdi.

Kanal icin yapisal: kuyruk sira sayili hukumdar adlariyla dolu (Mehmed
II/III, Selim I/II, Murad III, Mahmud II).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import capa_eslesme as ce  # noqa: E402
import europeana_materials as em  # noqa: E402
import met_materials as mm  # noqa: E402
import wikimedia_materials as wm  # noqa: E402


# --- Sira sayisi tanima --------------------------------------------------


@pytest.mark.parametrize(
    "capa,beklenen",
    [
        ("Murad III", {"iii"}),
        ("Mehmed II", {"ii"}),
        ("Selim I", {"i"}),
        ("Louis XIV", {"xiv"}),
        ("Ibn Saud", set()),
        ("Otto the Great", set()),
    ],
)
def test_sira_sayisi_ayikliniyor(capa, beklenen):
    assert ce.sira_sayilari(capa) == beklenen


def test_ingilizce_kelime_sira_sayisi_sayilmiyor():
    """⚠️ "mix" (M-I-X = 1009) gecerli bir roma rakami AMA gercek bir kelime.

    Capa metni modelden serbest geliyor; genel bir roma-rakami duzenli
    ifadesi kullanilsaydi "Mix Master" capasi sira sayili sayilirdi.
    """
    assert ce.sira_sayilari("Mix Master") == set()
    assert ce.sira_sayilari("Civil War") == set()
    assert "mix" not in ce.SIRA_SAYILARI


# --- Eslesme -------------------------------------------------------------


def _uyuyor(capa: str, kanit: str) -> bool:
    return ce.capa_uyuyor(
        kanit,
        kelimeler=ce.kelime_terimleri(capa),
        rakamlar=ce.sira_sayilari(capa),
    )


def test_ayni_soyadli_baska_kisi_eleniyor():
    """Gercek vakanin ozu."""
    assert not _uyuyor("Murad III", "file:nadia murad nobel peace prize 2018.jpg")


def test_ayni_hanedanin_baska_hukumdari_eleniyor():
    assert not _uyuyor("Murad III", "file:sultan murad v 1876.jpg")
    assert not _uyuyor("Mehmed II", "file:mehmed vi last sultan.jpg")


def test_dogru_hukumdar_geciyor():
    assert _uyuyor("Murad III", "file:sultan murad iii.jpg")
    assert _uyuyor("Murad III", "file:tughra of murad iii.jpg")


def test_sira_sayisi_alt_dize_olarak_aranmiyor():
    """⚠️ Duzeltmeye calistigimiz kusurun bir tik incesi.

    Alt dize kullanilsaydi "iii" kanittaki "xiii" ve "viii" icinde de
    bulunurdu, yani "Louis III" capasi "Louis XIII" gorselini gecirirdi.
    """
    assert not _uyuyor("Louis III", "file:louis xiii portrait.jpg")
    assert not _uyuyor("Louis III", "file:louis viii of france.jpg")
    assert _uyuyor("Louis III", "file:louis iii of france.jpg")


def test_sira_sayisiz_capa_davranisi_degismiyor():
    """Sira sayisi olmayan konularda eski davranis aynen surmeli."""
    assert _uyuyor("Ibn Saud", "file:ibn saud 1945.jpg")
    assert not _uyuyor("Ibn Saud", "file:winston churchill portrait.jpg")


# --- Uc kaynagin da bagli oldugu ------------------------------------------


def _sayfa(baslik: str) -> dict:
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
                    "ImageDescription": {"value": ""},
                    "Artist": {"value": "x"},
                },
                "descriptionurl": "https://commons/x",
            }
        ],
    }


def test_commons_kapisi_sira_sayisini_uyguluyor():
    adaylar = wm._puanli_adaylar(
        [
            _sayfa("File:Nadia Murad Nobel Peace Prize 2018.jpg"),
            _sayfa("File:Sultan Murad III portrait.jpg"),
        ],
        set(),
        "Murad III portrait",
        "Murad III",
    )

    basliklar = [a["title"] for a in adaylar]
    assert "File:Nadia Murad Nobel Peace Prize 2018.jpg" not in basliklar
    assert "File:Sultan Murad III portrait.jpg" in basliklar


def test_met_kapisi_sira_sayisini_uyguluyor(monkeypatch):
    nesneler = [
        {
            "objectID": 1,
            "title": "Portrait of Nadia Murad",
            "isPublicDomain": True,
            "primaryImage": "https://x/a.jpg",
            "objectURL": "https://metmuseum.org/1",
            "objectDate": "2018",
        },
        {
            "objectID": 2,
            "title": "Sultan Murad III enthroned",
            "isPublicDomain": True,
            "primaryImage": "https://x/b.jpg",
            "objectURL": "https://metmuseum.org/2",
            "objectDate": "1580",
        },
    ]

    secilen = mm.select_met_candidate(nesneler, set(), "Murad III", required_anchor="Murad III")

    assert secilen is not None
    assert secilen["id"] == 2, "sira sayisi tutmayan aday gecmemeli"


def test_europeana_kapisi_sira_sayisini_uyguluyor(monkeypatch):
    # ⚠️ `guvenli_url` adresi GERCEKTEN cozuyor (SSRF korumasi); sahte bir
    # ana bilgisayar DNS'te bulunamayip aday elenirdi. Kontrol edilen sey
    # sira sayisi kapisi oldugu icin bu adim yamaniyor.
    monkeypatch.setattr(em, "guvenli_url", lambda url: url)
    ogeler = [
        {
            "id": "/1/a",
            "rights": ["http://creativecommons.org/publicdomain/mark/1.0/"],
            "edmIsShownBy": ["https://example.org/a.jpg"],
            "title": ["Nadia Murad at the United Nations"],
        },
        {
            "id": "/1/b",
            "rights": ["http://creativecommons.org/publicdomain/mark/1.0/"],
            "edmIsShownBy": ["https://example.org/b.jpg"],
            "title": ["Sultan Murad III of the Ottoman Empire"],
        },
    ]

    secilenler = em.select_europeana_candidates(
        ogeler, set(), "Murad III", required_anchor="Murad III"
    )

    assert [a["id"] for a in secilenler] == ["/1/b"]


def test_dairesel_import_yok():
    """`capa_eslesme` notr kalmali — hicbir kaynak modulunu import etmemeli."""
    kaynak = Path(ce.__file__).read_text(encoding="utf-8")

    for modul in ("wikimedia_materials", "met_materials", "europeana_materials"):
        assert f"import {modul}" not in kaynak
