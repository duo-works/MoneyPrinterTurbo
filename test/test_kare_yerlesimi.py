"""Sahne basina IKI kare — gorsel hizi ve ekranin tam dolmasi.

⚠️ NEDEN — kanal sahibinin sesli notu (2026-08-14), videolari izleyerek:

  * "Fotograflar cok uzun sure kaliyor ekranda, yazi degistikce fotografla
    degismesi gerekiyor"
  * "Kesinlikle gorsel sayisi artirilmali"
  * "Ekrani kaplamayan gorseller olmamali, cok kalitesiz duruyor"
  * "Oyle fotograflarda alt alta iki tane koyalim ekrana"

Olculdu: sahne basina 1 gorsel, suresi `ses ÷ sahne` (~5 sn); altyazi ~2
sn'de bir degisiyor. Yani gorsel altyazinin 2,5 kati yavasti.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _gorsel(yol: Path, en: int, boy: int, renk=(120, 90, 60)) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (en, boy), renk).save(yol, format="JPEG", quality=92)
    return yol


# --- Kirpma olcusu --------------------------------------------------------


def test_shorts_orani_hic_kirpilmiyor():
    assert ya.kirpma_orani(ya.SHORTS_EN, ya.SHORTS_BOY) == pytest.approx(0.0)


def test_yatay_fotograf_tam_kareye_sigmiyor():
    """16:9 bir fotograf 1080x1920'ye kirpilinca %60'tan fazlasi gider."""
    assert ya.kirpma_orani(1920, 1080) > ya.AZAMI_KIRPMA


def test_ayni_fotograf_YARIM_kareye_sigiyor():
    """⚠️ `dikeye_yapistir`in butun gerekcesi bu sayi.

    Tek basina kirpilamayan 16:9 fotograf, yarim kareye (1080x960)
    yalnizca ~%37 kirpmayla giriyor — yani IKISI alt alta ekrani bant
    birakmadan dolduruyor.
    """
    yarim = ya.kirpma_orani(1920, 1080, ya.SHORTS_EN, ya.SHORTS_BOY // 2)

    assert yarim < 0.4
    assert yarim < ya.kirpma_orani(1920, 1080)


def test_bant_ister_yatayda_dogru(tmp_path):
    assert ya.bant_ister(_gorsel(tmp_path / "yatay.jpg", 1920, 1080))


def test_bant_ister_dikeyde_yanlis(tmp_path):
    assert not ya.bant_ister(_gorsel(tmp_path / "dikey.jpg", 1080, 1920))


# --- Dikey yapistirma -----------------------------------------------------


def test_yapistirma_tam_kare_uretiyor(tmp_path):
    ust = _gorsel(tmp_path / "a.jpg", 1920, 1080, (200, 40, 40))
    alt = _gorsel(tmp_path / "b.jpg", 1600, 900, (40, 40, 200))

    sonuc = ya.dikeye_yapistir(ust, alt, tmp_path / "birlesik.jpg")

    with Image.open(sonuc) as g:
        assert g.size == (ya.SHORTS_EN, ya.SHORTS_BOY)


def test_yapistirmada_IKI_gorsel_de_gorunuyor(tmp_path):
    """Ust yari birinciyi, alt yari ikinciyi gostermeli."""
    ust = _gorsel(tmp_path / "a.jpg", 1920, 1080, (220, 20, 20))
    alt = _gorsel(tmp_path / "b.jpg", 1920, 1080, (20, 20, 220))

    sonuc = ya.dikeye_yapistir(ust, alt, tmp_path / "birlesik.jpg")

    with Image.open(sonuc) as g:
        ust_piksel = g.getpixel((ya.SHORTS_EN // 2, ya.SHORTS_BOY // 4))
        alt_piksel = g.getpixel((ya.SHORTS_EN // 2, ya.SHORTS_BOY * 3 // 4))
    assert ust_piksel[0] > ust_piksel[2], "ust yari KIRMIZI gorseli gostermeli"
    assert alt_piksel[2] > alt_piksel[0], "alt yari MAVI gorseli gostermeli"


def test_yapistirmada_SIYAH_BANT_kalmiyor(tmp_path):
    """Sikayetin ta kendisi: ekranin bos kalmasi."""
    ust = _gorsel(tmp_path / "a.jpg", 1920, 1080, (200, 180, 160))
    alt = _gorsel(tmp_path / "b.jpg", 1920, 1080, (190, 170, 150))

    sonuc = ya.dikeye_yapistir(ust, alt, tmp_path / "birlesik.jpg")

    with Image.open(sonuc) as g:
        for y in (5, ya.SHORTS_BOY // 2, ya.SHORTS_BOY - 5):
            piksel = g.getpixel((ya.SHORTS_EN // 2, y))
            assert sum(piksel) > 90, f"y={y} bant gibi karanlik: {piksel}"


# --- Yerlesim -------------------------------------------------------------


def test_her_sahne_IKI_kare_aliyor(tmp_path):
    """⚠️ Sabit iki yuva: MPT her materyale ESIT sure veriyor.

    Sahne basina degisken sayi, iki yuvali sahneye ayni ses icin iki kat
    ekran suresi verir ve gorsel anlatimdan kayar.
    """
    birincil = [_gorsel(tmp_path / f"p{i}.jpg", 1080, 1920) for i in range(3)]
    ikincil = [_gorsel(tmp_path / f"s{i}.jpg", 1080, 1920) for i in range(3)]

    kareler, tam = ya.kare_yerlesimi(birincil, ikincil, tmp_path / "cikti")

    assert len(kareler) == 6
    assert tam == 3


def test_ikinci_gorsel_yoksa_BIRINCISI_iki_yuvaya(tmp_path):
    """⚠️ Videonun tamamini 1 kareye dusurmek yerine sahne bazinda telafi.

    Boylece zamanlama tekdüze kalir ve o sahne bugunku haliyle birebir
    ayni gorunur — hicbir sey kotulesmiyor.
    """
    birincil = [_gorsel(tmp_path / "p.jpg", 1080, 1920)]

    kareler, tam = ya.kare_yerlesimi(birincil, [None], tmp_path / "cikti")

    assert len(kareler) == 2
    assert kareler[0] == kareler[1], "ayni kare iki yuvada olmali"
    assert tam == 0


def test_iki_yatay_gorsel_YAPISTIRILIYOR(tmp_path):
    birincil = [_gorsel(tmp_path / "p.jpg", 1920, 1080, (210, 30, 30))]
    ikincil = [_gorsel(tmp_path / "s.jpg", 1920, 1080, (30, 30, 210))]

    kareler, _ = ya.kare_yerlesimi(birincil, ikincil, tmp_path / "cikti")

    assert kareler[0] == kareler[1], "yapistirilmis kare iki yuvada durmali"
    with Image.open(kareler[0]) as g:
        ust = g.getpixel((ya.SHORTS_EN // 2, ya.SHORTS_BOY // 4))
        alt = g.getpixel((ya.SHORTS_EN // 2, ya.SHORTS_BOY * 3 // 4))
    assert ust[0] > ust[2] and alt[2] > alt[0], "iki gorsel de karede olmali"


def test_kirpilabilen_ikili_ARDISIK_gosteriliyor(tmp_path):
    """Dikey gorseller zaten tam ekran; yapistirmak onlari kucultmek olurdu."""
    birincil = [_gorsel(tmp_path / "p.jpg", 1080, 1920)]
    ikincil = [_gorsel(tmp_path / "s.jpg", 1080, 1920)]

    kareler, _ = ya.kare_yerlesimi(birincil, ikincil, tmp_path / "cikti")

    assert kareler[0] != kareler[1], "iki AYRI kare olmali"


def test_karisik_cift_yapistirilmiyor(tmp_path):
    """Biri kirpilir digeri bant isterse yapistirma YAPILMAZ.

    Yapistirmak, kirpilabilen gorseli gereksiz yere yariya indirirdi.
    """
    birincil = [_gorsel(tmp_path / "p.jpg", 1080, 1920)]  # kirpilir
    ikincil = [_gorsel(tmp_path / "s.jpg", 1920, 1080)]  # bant ister

    kareler, _ = ya.kare_yerlesimi(birincil, ikincil, tmp_path / "cikti")

    assert kareler[0] != kareler[1]


def test_sahne_yuvasi_sabiti_iki():
    assert ya.KARE_YUVASI == 2
