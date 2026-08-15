"""Ses olculemedigINDE klip suresi SENARYODAN tahmin ediliyor.

⚠️ Kusur calisma zamaninda degil KOD DENETIMINDE bulundu ve hic hata
firlatmiyor — tam da bu yuzden tehlikeli. `anlatim_suresi` agdan TTS cekip
sureyi olcuyor; hata olursa yutup 0.0 donuyor (uretimi durdurmamak icin,
bilincli bir karar). O noktada `klip_suresi` sabit 5 saniyeye dusuyordu:

    Shorts    8 kare × 5 sn =  40 sn gorsel · ses  33 sn   → zararsiz
    uzun     45 kare × 5 sn = 225 sn gorsel · ses 775 sn   → 3,4 KAT tekrar

MPT acigi `itertools.cycle` ile kapatiyor, yani izleyici ayni 45 goruntuyu
uc kez daha gorur. Log temiz, cikis kodu 0, kalite kapilari render ONCESI
plani okudugu icin bunu goremez.

⚠️ Sabiti yukseltmek COZUM DEGIL: dogru sure bicime degil senaryonun
uzunluguna bagli ve o bilgi zaten elde.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def test_ses_olculemezse_SENARYODAN_tahmin():
    """1.360 kelime / 170 = 480 sn ses; 38 karede ~12,6 sn/kare."""
    senaryo = "word " * 1360

    klip = ya.klip_suresi(0.0, 38, senaryo)

    assert klip > ya.VARSAYILAN_KLIP_SURESI
    assert 12 < klip < 14


def test_tahmin_TEKRARI_onluyor():
    """Asil olcut: kare sayisi × klip suresi, sesin suresini KARSILAMALI."""
    kelime = 1360
    senaryo = "word " * kelime
    kare = 38
    ses = kelime / ya.KELIME_HIZI * 60

    toplam = ya.klip_suresi(0.0, kare, senaryo) * kare

    assert toplam >= ses, "gorsel sesten kisa — cycle tekrar eder"
    assert toplam < ses * 1.1, "gorsel sesten cok uzun — son kare asili kalir"


def test_SHORTS_yedegi_de_dogru_calisiyor():
    """⚠️ Shorts'ta eski davranis zararsizdi ama YANLISTI; duzelme oraya da
    sizmali ve videoyu bozmamali."""
    senaryo = "word " * 100

    toplam = ya.klip_suresi(0.0, 8, senaryo) * 8
    ses = 100 / ya.KELIME_HIZI * 60

    assert toplam >= ses


def test_SENARYOSUZ_cagri_eski_sabite_dusuyor():
    """Tahmin edecek hicbir sey yoksa davranis degismemeli."""
    assert ya.klip_suresi(0.0, 7) == ya.VARSAYILAN_KLIP_SURESI
    assert ya.klip_suresi(0.0, 7, "   ") == ya.VARSAYILAN_KLIP_SURESI


def test_SIFIR_kare_hala_sabit():
    """Bolme hatasi korumasi — senaryo verilse bile."""
    assert ya.klip_suresi(35.88, 0, "word " * 500) == ya.VARSAYILAN_KLIP_SURESI


def test_ses_OLCULDUYSE_tahmine_bakilmiyor():
    """Gercek olcum her zaman ustun; senaryo yalnizca yedek."""
    senaryo = "word " * 5000

    assert ya.klip_suresi(35.88, 7, senaryo) == ya.klip_suresi(35.88, 7)


def test_KELIME_HIZI_olculen_deger():
    """⚠️ Kod icinde uc yerde yorum olarak geciyordu, sabit olarak hicbir
    yerde; degistiginde sessizce ayrisirlardi."""
    assert ya.KELIME_HIZI == 170


def test_uretim_cagrisi_SENARYOYU_geciriyor():
    """⚠️ Bu oturumda ayni sinif kusur iki koşum oldurdu: fonksiyon dogruydu
    ama cagri parametreyi gecirmiyordu (`refine_search_terms`/`bicim`).
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "klip_suresi(ses_saniye, len(material_files), plan.script)" in kaynak
