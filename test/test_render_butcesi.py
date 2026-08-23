"""Render butcesi ve kilit suresi BIRLIKTE degisiyor.

⚠️ OLCULDU 2026-08-23, FAZ FAZ. Bu dosyanin eski hali iki butceyi de TEK bir
2026-08-15 SHORTS koşumundan cikan 3,4x oraniyla gerekcelendiriyordu ve
uzun format hic ffmpeg duzeyinde zamanlanmamisti. 2026-08-23 00:05 uzun
koşumu tam orada oldu (`subprocess.TimeoutExpired`, 5400 sn).

Olculen faz profili (saniye / saniye-video):

    faz 2  preprocess_video (zoom)   5,40x   <- darbogaz, %46'si Python/PIL
    faz 3  combine_videos            0,97x
    faz 4  generate_video + altyazi  3,15x
                                     -----
    TOPLAM                           9,52x

⚠️ Altyazi maliyeti KUS SAYISIYLA buyumuyor (17/34/68/136 kus: sekiz kat
kus, 1,12 kat sure), yani maliyet sureyle DOGRUSAL ve butce dogrusal
genisletmeyle yazilabiliyor. Karesel olsaydi bu dosyadaki hicbir sayi
gecerli olmazdi.

Iki sabit birbirine bagli ve ayri ayri degistirilemez: zaman asimini
yukseltip kilidi kisa birakmak, iki koşumun ayni `state.json` ve ayni
`storage/` uzerinde paralel calismasi demek.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


# --- Olculen en kotu yuk ----------------------------------------------------
#
# Ikisi de KELIME TAVANINDA ve AGIR rejimde, yani hattin uretebilecegi en
# uzun videonun en kotu gunu. Hedef degil TAVAN kullaniliyor: tavan modelin
# gercekten uretebildigi bir deger ve 5400 tam da hedefe bakilarak
# konuldugu icin patlamisti.

SHORTS_OLCULEN_EN_KOTU = 1505
"""53 sn ses (150 kelime tavani / 170) x 28,4.

Olcum: `logs/2026-08-22-20-attempt-1.log`, BASARILI koşum — 41,4 sn ses
19,6 dakikada render edildi.
"""

UZUN_OLCULEN_EN_KOTU = 10928
"""775 sn ses (2200 kelime tavani / 170) x 14,1.

14,1x, olculen 9,52x profilinin 00:05 gecesinin agir rejimine tasinmis
hali (faz 2 orada 8,0x, olcum aninda 5,4x -> 1,48 kat). Model o gecenin
GOZLENEN 79 dakikasini 76 dk olarak yeniden uretiyor.
"""


# --- Render siniri ---------------------------------------------------------


def test_SHORTS_butcesi_OLCULEN_yuku_kaldiriyor():
    assert ya.render_zaman_asimi(ya.SHORTS_BICIMI) >= SHORTS_OLCULEN_EN_KOTU


def test_bicimsiz_cagri_SHORTS_butcesini_veriyor():
    """⚠️ Varsayilan `None`: `render_zaman_asimi` `SHORTS_BICIMI`den once
    cagrilabiliyor ve varsayilanlar `def` aninda hesaplaniyor."""
    assert ya.render_zaman_asimi(None) == ya.render_zaman_asimi(ya.SHORTS_BICIMI)


def test_uzun_butce_OLCULEN_GECE_rejimini_kaldiriyor():
    """⚠️ Eski 5400 bunun YARISINDAN azdi — 00:05 koşumu burada oldu."""
    assert ya.render_zaman_asimi(ya.UZUN_BICIMI) >= UZUN_OLCULEN_EN_KOTU


def test_uzun_butce_SHORTS_tan_buyuk():
    assert ya.render_zaman_asimi(ya.UZUN_BICIMI) > ya.render_zaman_asimi(
        ya.SHORTS_BICIMI
    )


# --- Butceler slot penceresine sigiyor mu ----------------------------------
#
# ⚠️ Butce yalnizca "yeterince buyuk" olamaz: asiri buyuk bir butce, asmis
# bir koşumun SONRAKI slotu da yakmasi demek. Ust sinirlar da olculuyor.


def test_SHORTS_butcesi_SLOT_penceresine_sigiyor():
    """Shorts slotlari 3 saat arayla ve slot basina EN FAZLA 2 koşum var."""
    assert 2 * ya.render_zaman_asimi(ya.SHORTS_BICIMI) < 3 * 3600


def test_uzun_butce_SLOT_penceresine_PLANLA_BIRLIKTE_sigiyor():
    """00:05 -> 05:05 = 300 dk, ve plan asamasi (~38 dk, olculdu) ayni
    pencerede. Butce tek basina degil, planla BIRLIKTE sigmali."""
    plan_asamasi = 38 * 60

    assert ya.render_zaman_asimi(ya.UZUN_BICIMI) + plan_asamasi < 300 * 60


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

    ⚠️ OLCULDU 2026-08-23: bu bayragin HIZ kazanci SIFIR cikti (0,97x).
    Faz 2 (`preprocess_video`) `write_videofile`i ciplak cagiriyor, yani
    bayrak koşumun EN PAHALI fazina hic ulasmiyor — ama ulassaydi da fark
    etmeyecekti, cunku darbogaz kodlayici degil kare kare PIL zoom'u.
    Bayrak faz 3 ve faz 4'e ulasiyor ve testin olctugu sey o.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert '"--n-threads",' in kaynak
    assert "str(ffmpeg_is_parcaciklari())" in kaynak


# ⚠️ `test_render_siniri_KAYNAKTA_sabit_degil` BURADAN TASINDI.
#
# O test kaynak METNINDE `"timeout=render_zaman_asimi(bicim)"` ariyordu ve
# 2026-08-23'te davranis DOGRUYKEN dustu: ifade
# `butce = render_zaman_asimi(bicim)` + `timeout=butce` haline gelmisti.
# Metne cakili test gercek bir kusur bildirmedi, yalnizca yeniden yazimi
# engelledi — bu oturumda ayni sey dorduncu kez oldu.
#
# Yerine `test_render_zaman_asimi.py` icindeki
# `test_render_butcesi_CAGRI_YERINDE_sabit_degil` geldi: cagrinin ICINI
# ayristiriyor, yani `timeout` bir sabit olmasin yeter.
