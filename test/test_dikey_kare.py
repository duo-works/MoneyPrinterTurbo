"""Shorts karesi — kaynak gorseller 1080x1920'ye getirilir, siyah bant kalmaz.

Ayri dosya: bu is kendi sozlesmesine sahip ve testler saf goruntu islemi,
ag yok.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _gorsel(yol: Path, en: int, boy: int, renk=(180, 140, 90)) -> Path:
    Image.new("RGB", (en, boy), renk).save(yol, format="PNG")
    return yol


def test_ciktinin_olcusu_her_zaman_shorts_karesi(tmp_path):
    """Hangi kaynak gelirse gelsin cikti 1080x1920 olmali."""
    for en, boy in ((1024, 1536), (1280, 738), (900, 900), (600, 2000)):
        kaynak = _gorsel(tmp_path / f"k-{en}x{boy}.png", en, boy)
        hedef = ya.dikeye_uydur(kaynak, tmp_path / f"h-{en}x{boy}.jpg")
        with Image.open(hedef) as im:
            assert im.size == (ya.SHORTS_EN, ya.SHORTS_BOY), f"{en}x{boy} icin"


def test_dikey_ai_gorseli_kirpilarak_dolduruluyor(tmp_path):
    """2:3 AI gorseli (1024x1536) — %16 kirpma kabul edilebilir.

    Uretilen videolarda ustte/altta 150'ser piksel siyah bant vardi
    (`cropdetect` → `crop=1080:1620:0:150`), yani ekranin %15,6'si bostu.
    """
    kaynak = _gorsel(tmp_path / "ai.png", 1024, 1536)

    hedef = ya.dikeye_uydur(kaynak, tmp_path / "cikti.jpg")

    with Image.open(hedef) as im:
        # Kirp-doldur uygulandiysa her kose kaynak rengini tasir; bulanik
        # arka plan yolunda ust ve alt seritler bulanik kopyadan gelir ama
        # yine dolu olur. Ayirt edici olan: hicbir yerde siyah bant yok.
        for nokta in ((5, 5), (1075, 5), (5, 1915), (1075, 1915), (540, 960)):
            assert im.getpixel(nokta) != (0, 0, 0), f"{nokta} siyah"


def test_yatay_arsiv_fotografi_bulanik_arka_planla_dolduruluyor(tmp_path):
    """16:9 fotografi kirpmak konuyu kadraj disinda birakirdi.

    1280x738 bir akvedukt fotografini 9:16'ya kirpmak genisligin %68'ini
    atardi — geriye tek bir kemer kalirdi. Bulanik arka plan konuyu butun
    halinde koruyor.
    """
    kaynak = _gorsel(tmp_path / "arsiv.png", 1280, 738)

    hedef = ya.dikeye_uydur(kaynak, tmp_path / "cikti.jpg")

    with Image.open(hedef) as im:
        assert im.size == (ya.SHORTS_EN, ya.SHORTS_BOY)
        # Ust serit siyah degil — bulanik kopya oraya konmus olmali.
        assert im.getpixel((540, 40)) != (0, 0, 0)
        assert im.getpixel((540, 1880)) != (0, 0, 0)


def test_kirpma_esigi_iki_yolu_ayiriyor():
    """Esik sabiti kaybolursa iki yol ayirt edilemez hale gelir."""
    assert 0 < ya.AZAMI_KIRPMA < 1
    # 2:3 gorseli kirp-doldur tarafinda kalmali (%16 kirpma).
    assert (1 - (1536 * (1080 / 1920)) / 1024) < ya.AZAMI_KIRPMA
    # 16:9 gorseli bulanik arka plan tarafina dusmeli (%68 kirpma).
    assert (1 - (738 * (1080 / 1920)) / 1280) > ya.AZAMI_KIRPMA


def test_sahne_sirasi_korunuyor(tmp_path):
    """Sira bozulursa anlatim yanlis gorselle eslesir — sessiz ve pahali."""
    kaynaklar = [
        _gorsel(tmp_path / f"s{i}.png", 1024, 1536, renk=(i * 30, 60, 60))
        for i in range(1, 4)
    ]

    ciktilar = ya.dikeye_uydur_hepsi(kaynaklar, tmp_path / "dikey")

    assert [y.name for y in ciktilar] == ["sahne-01.jpg", "sahne-02.jpg", "sahne-03.jpg"]
    for sira, cikti in enumerate(ciktilar, 1):
        with Image.open(cikti) as im:
            kirmizi = im.getpixel((540, 960))[0]
        assert abs(kirmizi - sira * 30) < 12, f"sahne {sira} yanlis gorselden"


@pytest.mark.parametrize("bayrak,beklenen", [("--custom-position", "78"), ("--font-size", "56")])
def test_altyazi_ayarlari_alt_ucte_biri_hedefliyor(bayrak, beklenen):
    """Olculdu: 82 karakterlik blok 72px fontta 4-5 satira cikip gorselin
    ana oznesini kapatiyordu. 56px'te 3 satira iniyor, %78 konumla alt ucte
    birde kaliyor."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index(f'"{bayrak}"')
    sonraki = kaynak[i : i + 200]

    assert f'"{beklenen}"' in sonraki, f"{bayrak} degeri {beklenen} olmali"
