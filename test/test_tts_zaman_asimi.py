"""TTS zaman asimi METNE gore olceklenmeli — 30 sn Shorts olcusu.

⚠️ OLCULDU (2026-08-15, DW-51, YEDINCI Herculaneum koşumu). Koşum 51,5
dakika calisti, plan uretildi, 38 gorsel indi, render'a ulasti — sonra
1.210 kelimelik senaryo UC KEZ 30 saniyede zaman asimina ugradi ve video
uretilmedi.

Sinir ILK PAKETI degil BUTUN sentezi kapsiyor (`stream_edge_tts_chunks`
belgesi: "单次流式请求总超时"), yani metin uzadikca zorunlu olarak asiliyor.
Ust akis varsayilani da kendi belgesinde "覆盖常见短视频脚本" diyor —
kisa video senaryolarina gore ayarlanmis.

Olcum: 2.200 kelime -> 147 saniye (0,067 sn/kelime).

⚠️ Bu, ayni ailenin YEDINCI uyesi ve hepsi tek cumleyle ozetleniyor: uzun
format Shorts varsayilanlarina carpiyor. Sirasiyla kelime kapisi, terim
kapisi, yeniden dogrulama, cikarim zaman asimi, capa genisligi, sahne
basina kelime, simdi TTS zaman asimi.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import voice  # noqa: E402


def _kelimeler(n: int) -> str:
    return "word " * n


def test_SHORTS_metninde_davranis_DEGISMIYOR():
    """⚠️ Taban korunmali: asilma tespiti kisa metinlerde yasamali.

    100 kelime x 0,2 = 20 sn, yani tabanin (30) altinda kaliyor.
    """
    assert voice.get_edge_tts_timeout_seconds(_kelimeler(100)) == 30.0


def test_UZUN_metin_sinirI_buyutuyor():
    """Yedinci koşumun birebir durumu: 1.210 kelime."""
    sinir = voice.get_edge_tts_timeout_seconds(_kelimeler(1210))

    assert sinir == 242.0
    assert sinir > 147, "olculen 2.200 kelimelik sentez suresinden kucuk olamaz"


def test_EN_UZUN_senaryo_da_sigiyor():
    """Sozlesmenin tavani 2.200 kelime; olculen sentez suresi 147 sn."""
    sinir = voice.get_edge_tts_timeout_seconds(_kelimeler(2200))

    assert sinir >= 147 * 2, "yavas ag payi kalmali"


def test_metin_verilmezse_ESKI_davranis():
    """⚠️ Geriye donuk uyum: fonksiyonu metinsiz cagiran yerler bozulmamali."""
    assert voice.get_edge_tts_timeout_seconds() == 30.0


def test_SIFIR_hala_zaman_asimini_KAPATIYOR(monkeypatch):
    """Ust akisin acik sozlesmesi: 0 veya negatif = sinir yok."""
    monkeypatch.setitem(voice.config.app, "edge_tts_timeout", 0)

    assert voice.get_edge_tts_timeout_seconds(_kelimeler(2000)) is None


def test_yapilandirmadaki_deger_TABAN_olarak_kaliyor(monkeypatch):
    """Kullanici yavas agda 600 yazdiysa kisa metinde de 600 gecerli."""
    monkeypatch.setitem(voice.config.app, "edge_tts_timeout", 600)

    assert voice.get_edge_tts_timeout_seconds(_kelimeler(100)) == 600.0


def test_CAGRI_YERI_metni_geciriyor():
    """⚠️ Fonksiyon dogru olsa da cagri metni gecirmezse HIC calismaz.

    Ayni sinif kusur bu oturumda iki koşum oldurdu (`refine_search_terms`
    `bicim` almiyordu; `validate_content_plan` `konu` almiyordu).
    """
    kaynak = Path(voice.__file__).read_text(encoding="utf-8")

    assert "get_edge_tts_timeout_seconds(text)" in kaynak
