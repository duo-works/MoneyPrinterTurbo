"""Malzeme tedariki KAREYE gore suzuyor ve siraliyor.

⚠️ OLCULDU (2026-08-15, DW-51). Bu modulun tamami 9:16'ya sabitlenmisti ve
uzun format da ondan besleniyordu. Kusur COKME URETMIYOR — sessiz kalite
kaybi uretiyor, ki daha kotusu: video cikardi, kanal sahibi bakardi, yarisi
yan bantli olurdu ve bir tur daha donerdik.

Sekizinci Herculaneum koşumunun sectigi 45 gorselin olculen dagilimi:

    portre (16:9'da yan bant) : 22  (%48)
    yatay  (16:9'a uygun)     : 20  (%44)
    kare                      :   3

Iki ayri mekanizma vardi:
  1. SUZGEC   — `dikey_karede_yeterli`, 9:16'da kullanilabilirlige bakiyor
  2. SIRALAMA — `orientation_score = 2.0 if height >= width else 1.0`,
                yani PORTRE her zaman ustte

⚠️ Ikincisi daha etkili: aday havuzu 100 gorsel, secilen 45. Suzgec biraz
gevsek olsa bile siralama neyin secildigini belirliyor.

⚠️ SHORTS YOLU BIREBIR AYNI KALMALI — kalibre edilmis bir hat. Bu dosyanin
yarisi onu kilitliyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402
import youtube_automation as ya  # noqa: E402

DIKEY = wm.SHORTS_ORANI
YATAY = wm.UZUN_ORANI


def _sayfa(ad: str, en: int, boy: int) -> dict:
    return {
        "title": f"File:{ad}.jpg",
        "imageinfo": [
            {
                "url": f"https://commons.example/{ad}.jpg",
                "width": en,
                "height": boy,
                "mime": "image/jpeg",
                "extmetadata": {"LicenseShortName": {"value": "Public domain"}},
            }
        ],
    }


# --- Kadraj: SHORTS davranisi degismedi ------------------------------------


def test_SHORTS_dikey_gorseli_tam_ekran_sayiyor():
    assert wm.tam_ekran_doluyor(1080, 1920)
    assert wm.tam_ekran_doluyor(1000, 2000)
    # ⚠️ KARE gorsel 9:16'da tam ekran DEGIL: %44 kirpma gerekiyor ve tavan
    # %35. Kaynaktaki "dikey ya da kare" yorumu gevsek yazilmis; olculen
    # davranis bu ve degistirilmedi.
    assert not wm.tam_ekran_doluyor(1000, 1000)


def test_SHORTS_panoramayi_eliyor():
    """Olculmus esikler: 2,22 → %25 doluluk, 5,00 → %11."""
    assert not wm.dikey_karede_yeterli(2220, 1000)
    assert not wm.dikey_karede_yeterli(5000, 1000)


def test_SHORTS_bulanik_bantli_gorseli_KABUL_ediyor():
    """Kanal sahibinin karari: bantli gercek fotograf > tam ekran AI."""
    assert wm.dikey_karede_yeterli(1600, 1200)  # 4:3
    assert wm.dikey_karede_yeterli(1920, 1080)  # 16:9


def test_dikey_sarmalayici_ESKI_fonksiyonla_ayni():
    for en, boy in ((1080, 1920), (1600, 1200), (2220, 1000), (0, 100)):
        assert wm.dikey_karede_yeterli(en, boy) == wm.karede_yeterli(en, boy, DIKEY)


# --- Kadraj: YATAY kare ----------------------------------------------------


def test_yatay_karede_16_9_TAM_EKRAN():
    assert wm.tam_ekran_doluyor(1920, 1080, YATAY)


def test_yatay_karede_PANORAMA_kabul_ediliyor():
    """⚠️ Dikey karede elenen panorama, yatay karede tam ekran doluyor."""
    assert not wm.dikey_karede_yeterli(2220, 1000)
    assert wm.tam_ekran_doluyor(2220, 1000, YATAY)


def test_yatay_karede_PORTRE_tam_ekran_DEGIL():
    """9:16 bir gorsel 16:9 karede yan bant demek."""
    assert not wm.tam_ekran_doluyor(1080, 1920, YATAY)


def test_yatay_karede_asiri_dik_gorsel_ELENIYOR():
    """Cok dar bir serit yatay karede izlenebilir bir sey vermiyor."""
    assert not wm.karede_yeterli(1000, 3000, YATAY)


def test_kural_SIMETRIK():
    """Karenin kendi yonunde uc olan gorsel her iki karede de serbest."""
    assert wm.tam_ekran_doluyor(1000, 3000, DIKEY)  # cok dik, dikey kare
    assert wm.tam_ekran_doluyor(3000, 1000, YATAY)  # cok genis, yatay kare


# --- Siralama --------------------------------------------------------------


def _secilen_adlar(sayfalar, hedef_oran):
    return [
        str(a["title"]).removeprefix("File:").removesuffix(".jpg")
        for a in wm._puanli_adaylar(sayfalar, set(), "", "", hedef_oran)
    ]


def test_SHORTS_portreyi_ustte_tutuyor():
    """⚠️ Kalibre edilmis davranis; degismemeli."""
    sayfalar = [_sayfa("yatay", 1920, 1080), _sayfa("portre", 1080, 1920)]

    assert _secilen_adlar(sayfalar, DIKEY)[0] == "portre"


def test_YATAY_karede_siralama_TERSINE_donuyor():
    """Asil kusur buydu: yatay belgesel icin portre gorseller ustte geliyordu."""
    sayfalar = [_sayfa("portre", 1080, 1920), _sayfa("yatay", 1920, 1080)]

    assert _secilen_adlar(sayfalar, YATAY)[0] == "yatay"


def test_yatay_karede_PANORAMA_portrenin_ustunde():
    sayfalar = [_sayfa("portre", 1080, 1920), _sayfa("panorama", 2400, 1080)]

    assert _secilen_adlar(sayfalar, YATAY)[0] == "panorama"


# --- Hatta baglanti --------------------------------------------------------


def test_kare_orani_KARE_OLCUSUNDEN_turetiliyor():
    """⚠️ Ayri bir sabit olsaydi retrieval kendi render'indan farkli bir kare
    varsayabilirdi — bu dosyada zaten olculmus bir kusur sinifi."""
    en, boy = ya.kare_olcusu(ya.UZUN_BICIMI)

    assert ya.kare_orani(ya.UZUN_BICIMI) == en / boy
    assert ya.kare_orani(ya.SHORTS_BICIMI) == ya.SHORTS_EN / ya.SHORTS_BOY


def test_kare_orani_varsayilani_DIKEY():
    assert ya.kare_orani() == ya.kare_orani(ya.SHORTS_BICIMI)


def test_MENU_orani_geciriyor():
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "hedef_oran=oran" in kaynak


def test_INDIRICI_orani_geciriyor():
    """Suzgec dogru olsa da indirici orani gecirmezse eski davranis surer."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert kaynak.count("hedef_oran=kare_orani(bicim)") == 2


def test_ONBELLEK_ORANA_gore_ayrisiyor(monkeypatch):
    """⚠️ Anahtar orani icermeseydi once calisan Shorts koşumu DIKEY suzulmus
    menuyu onbellege koyar, uzun koşum onu alirdi — kapinin modele
    gosterilenden baska bir listeye bakmasi ("Jock Willis") kusurunun aynisi.
    """
    ya._ENVANTER_ONBELLEGI.clear()
    cagrilar: list[float] = []

    def sahte(konu, sinir, hedef_oran=DIKEY):
        cagrilar.append(hedef_oran)
        return [{"title": "File:D.jpg", "aciklama": "x", "tarih": ""}]

    monkeypatch.setattr(wm, "arsiv_menusu", sahte)

    ya.arsiv_envanteri("Konu", sinir=40, bicim=ya.SHORTS_BICIMI)
    ya.arsiv_envanteri("Konu", sinir=40, bicim=ya.UZUN_BICIMI)

    assert cagrilar == [DIKEY, YATAY], "her bicim kendi menusunu cekmeli"


def test_ikincil_gorseller_DIKEY_kaliyor():
    """⚠️ Ikinci gorsel yalnizca Shorts'ta var (`kare_yuvasi >= 2`); o yol
    dikey kalmali, yoksa kalibre edilmis bir hat degisir."""
    kaynak = Path(wm.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def ikincil_gorseller(") :]
    govde = govde[: govde.index("\ndef ", 10)]

    assert "hedef_oran" not in govde
