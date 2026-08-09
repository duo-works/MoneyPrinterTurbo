"""Karanlik kare tabani (DW-112).

⚠️ Olculdu (2026-08-09, Chaco Canyon): acilis karesinin ortalama parlakligi
37/255 idi ve telefonda gunduz isiginda ilk saniye okunmuyordu. Shorts'un ilk
karesi izlenme kararinin verildigi yer.

Prompt bunu ZATEN istiyor ("readable at small size on a phone screen — no
crushed shadows") ve tutmuyor; ayrica sorun yalnizca AI'da degil, arsivden
inen karanlik bir fotograf da ayni sonucu verir. Bu yuzden dilek degil, olcum
ve duzeltme — ve duzeltme dikeye cevirme adiminda, yani her iki kaynak da
oradan geciyor.
"""

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gorsel_olcum  # noqa: E402
import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def _kare(parlaklik: int, *, doku: bool = True) -> Image.Image:
    """Verilen ORTALAMA parlaklikta, dokulu bir dikey kare.

    Duz renk yetmez: gama egrisinin dokuyu ezip ezmedigi ancak degisim
    varken olculebilir.

    ⚠️ Doku ortalamayi KAYDIRMAMALI, yoksa test 37 istedigini sanip 49 ile
    calisir ve esik testleri sessizce anlamsizlasir. Bu yuzden acilan ve
    koyulan seritler esit sayida ve esit miktarda.
    """
    dizi = np.full((96, 64, 3), parlaklik, dtype=np.int16)
    if doku:
        delta = min(25, parlaklik, 255 - parlaklik)
        for y in range(0, 96, 6):
            dizi[y : y + 3, :, :] += delta
            dizi[y + 3 : y + 6, :, :] -= delta
    return Image.fromarray(np.clip(dizi, 0, 255).astype(np.uint8))


# --- Olcum ----------------------------------------------------------------


def test_parlaklik_yoldan_ve_goruntuden_ayni():
    """Iki giris yolu da ayni sayiyi vermeli, yoksa esik anlamini yitirir."""
    gorsel = _kare(40)
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as gecici:
        yol = Path(gecici) / "k.png"
        gorsel.save(yol)

        assert gorsel_olcum.parlaklik(yol) == pytest.approx(
            gorsel_olcum.parlaklik(gorsel), abs=0.5
        )


def test_esik_iki_kume_arasindaki_bosluga_dusuyor():
    """⚠️ Esik veriden secildi: sorunlu kume 29,6-42,0, saglikli kume 51,1'den
    baslıyor. Esik aradaki boslukta olmali ki bir kumeyi ikiye bolmesin.
    """
    assert 42.0 < gorsel_olcum.PARLAKLIK_TABANI < 51.1


def test_hedef_tabanin_ustunde_ortancanin_altinda():
    """Tam tabana cikarmak kareyi sinirda birakir; ortancaya (70,7) cikarmak
    gecesi olan sahneyi gunduze cevirirdi.
    """
    assert gorsel_olcum.PARLAKLIK_TABANI < gorsel_olcum.PARLAKLIK_HEDEFI < 70.7


# --- Duzeltme -------------------------------------------------------------


def test_aydinlik_kareye_DOKUNULMUYOR():
    """⚠️ En onemli sart: duzeltme sessizce her kareyi degistirmemeli.

    Aksi halde yonetmenin bilincli karanlik sahnesi de acilirdi ve videonun
    ton araligi duzlesirdi.
    """
    gorsel = _kare(120)

    sonuc, gama = gorsel_olcum.karanligi_ac(gorsel)

    assert gama is None
    assert sonuc is gorsel, "aydinlik kare kopyalanmadan aynen donmeli"


def test_sinirin_hemen_ustundeki_kare_de_gecer():
    gorsel = _kare(int(gorsel_olcum.PARLAKLIK_TABANI) + 3)

    _, gama = gorsel_olcum.karanligi_ac(gorsel)

    assert gama is None


def test_karanlik_kare_hedefe_cikariliyor():
    gorsel = _kare(37)  # Chaco acilis karesinin olculen degeri

    sonuc, gama = gorsel_olcum.karanligi_ac(gorsel)

    assert gama is not None and gama > 1.0
    assert gorsel_olcum.parlaklik(sonuc) >= gorsel_olcum.PARLAKLIK_HEDEFI


def test_duzeltme_beyaza_yapistirmiyor():
    """⚠️ Gama normalize degerler uzerinde calisiyor, yani KIRPMA olamaz.

    Parlatmanin "yanik" degil "acilmis" gorunmesinin sebebi bu; test bunu
    en parlak pikselden dogruluyor.
    """
    gorsel = _kare(30)

    sonuc, _ = gorsel_olcum.karanligi_ac(gorsel)

    assert np.asarray(sonuc.convert("L")).max() < 255


def test_duzeltme_dokuyu_korumali():
    """Parlaklik kazanip dokuyu kaybetmek kotu bir takas olurdu."""
    gorsel = _kare(35)
    onceki = float(np.asarray(gorsel.convert("L"), dtype=float).std())

    sonuc, _ = gorsel_olcum.karanligi_ac(gorsel)
    sonraki = float(np.asarray(sonuc.convert("L"), dtype=float).std())

    assert sonraki > onceki * 0.9, "doku ezilmis"


def test_kurtarilamaz_kare_uretimi_durdurmuyor():
    """Neredeyse siyah kare hedefe cikmayabilir ve CIKMAMALI.

    ⚠️ Uydurma bir parlaklik, karanlik bir kareden daha yaniltici olurdu:
    sonuc gurultuden ibaret gri bir yuzey olurdu. Duzeltme azami gamada durur,
    patlamaz.
    """
    gorsel = _kare(2, doku=False)

    sonuc, gama = gorsel_olcum.karanligi_ac(gorsel)

    assert gama == gorsel_olcum.AZAMI_GAMA
    assert sonuc is not None


# --- Hatta baglanti -------------------------------------------------------


def test_taban_hatta_bagli():
    """⚠️ Baglanti testi — fonksiyon dogru olsa bile cagrilmazsa kusur surer.

    Kanca `dikeye_uydur` icinde olmali: her sahne karesi, AI uretimi de arsiv
    fotografi da oradan geciyor. Uretim tarafina konsaydi arsivden gelen
    karanlik kare kacardi.
    """
    i = KAYNAK.index("def dikeye_uydur(")
    govde = KAYNAK[i : KAYNAK.index("def dikeye_uydur_hepsi(")]

    assert "karanligi_ac(" in govde


def test_dikeye_uydur_karanlik_kareyi_aciyor(tmp_path):
    """Uctan uca: karanlik bir dosya girdi, aydinlik bir dosya cikti."""
    kaynak = tmp_path / "karanlik.png"
    _kare(30).resize((1080, 1620)).save(kaynak)

    hedef = ya.dikeye_uydur(kaynak, tmp_path / "dikey" / "sahne-01.jpg")

    assert gorsel_olcum.parlaklik(hedef) >= gorsel_olcum.PARLAKLIK_TABANI


def test_dikeye_uydur_aydinlik_kareyi_bozmuyor(tmp_path):
    kaynak = tmp_path / "aydinlik.png"
    _kare(120).resize((1080, 1620)).save(kaynak)

    hedef = ya.dikeye_uydur(kaynak, tmp_path / "dikey" / "sahne-01.jpg")

    assert gorsel_olcum.parlaklik(hedef) == pytest.approx(120, abs=12)
