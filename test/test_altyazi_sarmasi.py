"""Altyazi sarma genisligi KAREYE gore.

⚠️ OLCULDU (2026-08-15, ilk 16:9 render'in kare goruntusu): metin cerceveyi
UCTAN UCA kapliyor ve son kelime sag kenara dayaniyor.

Sabit %90 dikey kareye gore kalibre edilmisti:

    dikey  1080 x 0,90 =  972 piksel   → alt ucte derli toplu blok
    yatay  1920 x 0,90 = 1728 piksel   → uctan uca metin

⚠️ FONT BOYUTU KUCULTMEK COZMEZ ve bu, ilk denedigim yoldu: sarma her
halukarda mevcut genisligi dolduruyor, yani kucuk font yalnizca satira daha
cok kelime sigdirir. Degismesi gereken sey GENISLIGIN KENDISI.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

KAYNAK = Path(__file__).resolve().parent.parent / "app/services/video.py"


def _oran_ifadesi() -> str:
    metin = KAYNAK.read_text(encoding="utf-8")
    i = metin.index("def create_text_clip(")
    return metin[i : metin.index("max_width = video_width", i) + 120]


def test_sarma_orani_KAREYE_bagli():
    govde = _oran_ifadesi()

    assert "video_height >= video_width" in govde, "oran kareye gore secilmeli"
    assert "max_width = video_width * oran" in govde


def test_DIKEY_oran_degismedi():
    """⚠️ Shorts altyazisi olculerek kalibre edildi (DW-93); dokunulmamali."""
    govde = _oran_ifadesi()
    oranlar = re.findall(r"0\.\d+", govde)

    assert "0.9" in oranlar, "dikey kare eski oranini korumali"


def test_YATAY_oran_daha_dar():
    govde = _oran_ifadesi()
    eslesme = re.search(r"oran = (0\.\d+) if video_height >= video_width else (0\.\d+)", govde)

    assert eslesme, "oran ifadesi bulunamadi"
    dikey, yatay = float(eslesme.group(1)), float(eslesme.group(2))
    assert yatay < dikey


def test_yatay_satir_DIKEYE_YAKIN_uzunlukta():
    """Yatay satir, kalibre edilmis dikey satirdan cok uzun olmamali.

    Dikey: 1080 x 0,90 =  972 piksel (olculerek ayarlandi)
    Yatay: 1920 x oran
    """
    govde = _oran_ifadesi()
    eslesme = re.search(r"oran = (0\.\d+) if video_height >= video_width else (0\.\d+)", govde)
    yatay_oran = float(eslesme.group(2))

    dikey_piksel = 1080 * 0.9
    yatay_piksel = 1920 * yatay_oran

    assert yatay_piksel <= dikey_piksel * 1.4, "satir hala fazla uzun"
    assert yatay_piksel >= dikey_piksel, "gereksiz daraltma — metin kucuk kalir"
