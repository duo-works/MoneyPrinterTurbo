"""Render butcesi ve kilit suresi BIRLIKTE degisiyor.

⚠️ OLCULDU (2026-08-15, DW-51 denetimi). Iki sabit birbirine bagli ve ayri
ayri degistirilemez:

  `RENDER_ZAMAN_ASIMI = 1800`  — Shorts olcusu. Olcum: 33,4 sn'lik bir
      Short 115 saniyede render ediliyor (GERCEK ZAMANIN 3,4 KATI), yani
      1800 sn 15 kat paydi. Uzun formatta ses 775 sn'ye cikiyor, kodlama
      ~2.635 sn ediyor ve TTS de (en kotu 3 x 660 sn) AYNI surecin icinde.
      Yani bugunku TTS duzeltmesi tek basina eski 1800'u tasiriyordu.

  `KILIT_BAYATLAMA` (eski 4 saat) — kilit `expired or pid_is_dead` ile
      siliniyordu, yani sure dolunca sahibi CALISIYOR OLSA BILE. Slotlar da
      tam 4 saat arayla (`macos_zamanlama.py`). Shorts dakikalar surdugu
      icin bu erisilemez bir tavandi; uzun formatta degil.

⚠️ Zaman asimini yukseltip kilidi 4 saatte birakmak, iki koşumun ayni
`state.json` ve ayni `storage/` uzerinde paralel calismasi demekti. Bu
dosya iliskiyi kilitliyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


# --- Render siniri ---------------------------------------------------------


def test_SHORTS_render_siniri_DEGISMEDI():
    assert ya.render_zaman_asimi(ya.SHORTS_BICIMI) == 1800
    assert ya.render_zaman_asimi(None) == 1800


def test_uzun_render_siniri_OLCULEN_yuku_kaldiriyor():
    """Kodlama ~2.635 sn + TTS en kotu 1.980 sn, ikisi ayni surecte."""
    assert ya.render_zaman_asimi(ya.UZUN_BICIMI) >= 2635 + 1980


def test_render_siniri_KAYNAKTA_sabit_degil():
    """⚠️ 1800 gomulu kalsaydi bicim dallanmasi hic calismazdi."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "timeout=render_zaman_asimi(bicim)" in kaynak
    assert "timeout=1800" not in kaynak


# --- Kilit ------------------------------------------------------------------


def test_kilit_UZUN_KOSUMU_asamiyor():
    """⚠️ Asil kusur buydu: kilit gercek bir koşumun surebilecegi surede
    bayatliyordu ve canli sahibinden calin(a)biliyordu."""
    en_kotu_render = ya.render_zaman_asimi(ya.UZUN_BICIMI) * 3

    assert ya.KILIT_BAYATLAMA > en_kotu_render


def test_kilit_ZAMANLAYICI_araliginin_ustunde():
    """Slotlar 4 saat arayla; kilit bundan kisa olursa paralel koşum olur."""
    assert ya.KILIT_BAYATLAMA > 4 * 3600


def test_kilit_suresi_SABITTEN_okunuyor():
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "> KILIT_BAYATLAMA" in kaynak
    assert "> 4 * 3600" not in kaynak


# --- Is parcaciklari -------------------------------------------------------


def test_is_parcacigi_MPT_varsayilanindan_fazla():
    """MPT varsayilani 2 ve hat bunu hic gecmiyordu."""
    assert ya.ffmpeg_is_parcaciklari() > 2


def test_bir_cekirdek_BIRAKILIYOR():
    """Koşum arka planda calisiyor; makineyi doldurmak kullaniciyi yavaslatir."""
    import os

    cekirdek = os.cpu_count() or 2
    assert ya.ffmpeg_is_parcaciklari() <= max(cekirdek - 1, 2)


def test_bayrak_GERCEKTEN_geciriliyor():
    """⚠️ Sabit dogru olsa da bayrak gecirilmezse MPT yine 2 kullanir.

    Ayni sinif kusur bu oturumda iki koşum oldurdu (dogru fonksiyon, eksik
    argüman).
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert '"--n-threads",' in kaynak
    assert "str(ffmpeg_is_parcaciklari())" in kaynak
