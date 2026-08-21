"""Slot penceresinde ikinci koşum karari (§C, 2026-08-21).

⚠️ OLCULDU — `zamanlayici.log`un 70 koşumu:

    YAYIN 11 · red 44 · HATA 15   ->  koşum basina yayin p = 0,16
    koşum medyan suresi           :  25 dk
    3 saatlik pencerede kalan bos : 156 dk
    denenen koşum                 :   1

Hat %84 ihtimalle dusuyor ve sonra 2,5 saat hicbir sey yapmiyor. 15:05
koşumu 14 dakikada dustu, 18:05'e kadar bos beklendi.

⚠️ Bu testler kabugu GERCEKTEN CALISTIRIYOR, kaynak metnini sabitlemiyor.
Bu depoda metin sabitleyen testler ayni oturumda UC KEZ kirildi ve hicbiri
gercek bir kusur bildirmedi.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
KARAR = KOK / "scripts" / "slot_karari.sh"
URET = KOK / "scripts" / "uret.sh"


def _karar(kod, kalan, yayin, kilit) -> bool:
    """`ikinci_kosum_gerekli_mi` kabukta calistirilir; cikis kodu dondurulur."""
    sonuc = subprocess.run(
        [
            "bash",
            "-c",
            f'. "{KARAR}"; ikinci_kosum_gerekli_mi {kod} {kalan} {yayin} {kilit}',
        ],
        capture_output=True,
        text=True,
    )
    return sonuc.returncode == 0


def _kalan(saat, dakika) -> int:
    sonuc = subprocess.run(
        ["bash", "-c", f'. "{KARAR}"; sonraki_tetige_kalan_dk {saat} {dakika}'],
        capture_output=True,
        text=True,
    )
    return int(sonuc.stdout.strip())


# --- Karar tablosu ----------------------------------------------------------


def test_KALITE_REDDINDE_ikinci_kosum_deneniyor():
    """Asil kazanc: bugun bu durumda hat 2,5 saat bos bekliyordu."""
    assert _karar(kod=2, kalan=150, yayin=1, kilit=0) is True


def test_YAYINLANDIYSA_ikinci_kosum_YOK():
    """Slot dolu; ikinci video ayni saatte zaten `completed_slots`a takilir."""
    assert _karar(kod=0, kalan=150, yayin=1, kilit=0) is False


def test_ADAY_YOKSA_ikinci_kosum_YOK():
    """Hemen yeniden denemek ayni bos kuyruga bakar."""
    assert _karar(kod=3, kalan=150, yayin=1, kilit=0) is False


def test_YAPISAL_HATADA_ikinci_kosum_YOK():
    """⚠️ Olculdu 21 Agu: uc koşum da DISK DOLU ile dustu (cikis 1).
    Yeniden denemek uc kez bosa render ederdi."""
    assert _karar(kod=1, kalan=150, yayin=1, kilit=0) is False


def test_KILIT_DOLUYSA_ikinci_kosum_YOK():
    """Baska bir koşum suruyor; ikincisi zaten kilide takilirdi."""
    assert _karar(kod=2, kalan=150, yayin=1, kilit=1) is False


@pytest.mark.parametrize("kalan", [34, 20, 0])
def test_PENCERE_DARSA_ikinci_kosum_YOK(kalan):
    """⚠️ Koşum medyani 25 dk. Tetik aninda kilit doluysa zamanlayici
    'atlandi | onceki kosum suruyor' yazar, yani bir SONRAKI slot yanar."""
    assert _karar(kod=2, kalan=kalan, yayin=1, kilit=0) is False


@pytest.mark.parametrize("kalan", [35, 60, 150])
def test_PENCERE_YETIYORSA_deneniyor(kalan):
    assert _karar(kod=2, kalan=kalan, yayin=1, kilit=0) is True


@pytest.mark.parametrize("yayin", [6, 7, 12])
def test_GUNLUK_TAVANDA_ikinci_kosum_YOK(yayin):
    """⚠️ `videos.insert` 1600 birim, gunluk kota 10.000 -> gunde 6 yukleme.
    Bugune kadar hat tavana TEPKISEL carpiyordu; ikinci koşum acilinca gunluk
    yayin sayisi artacagi icin tavan ONCEDEN sayiliyor."""
    assert _karar(kod=2, kalan=150, yayin=yayin, kilit=0) is False


@pytest.mark.parametrize("yayin", [0, 3, 5])
def test_TAVANIN_ALTINDA_deneniyor(yayin):
    assert _karar(kod=2, kalan=150, yayin=yayin, kilit=0) is True


# --- Pencere hesabi ---------------------------------------------------------


@pytest.mark.parametrize(
    "saat,dakika,beklenen",
    [
        (12, 5, 180),  # koşum yeni basladi
        (13, 0, 125),  # 55 dk sonra
        (15, 19, 166),  # bugunku gercek vaka: 14 dk'da dusen koşum
        (8, 30, 35),  # 09:05'e tam esik
        (8, 35, 30),  # esigin altina duser
    ],
)
def test_sonraki_tetige_kalan_dogru(saat, dakika, beklenen):
    """Zamanlayici 3 saatte bir :05'te atesliyor (com.shemz.uretim.plist)."""
    assert _kalan(saat, dakika) == beklenen


def test_SEKIZLIK_tuzagi_yok():
    """⚠️ `date +%H` saat 08/09'da '08'/'09' veriyor ve bash bunu sekizlik
    sanip hata verir. Ayni tuzak `uret.sh`te bir kez yasandi."""
    assert _kalan("08", "09") == 56


# --- Gunluk yayin sayaci ----------------------------------------------------


def _bugunku(durum_yolu: Path) -> str:
    sonuc = subprocess.run(
        [
            "bash",
            "-c",
            f'. "{KARAR}"; bugunku_yayin_sayisi "{sys.executable}" "{durum_yolu}"',
        ],
        capture_output=True,
        text=True,
    )
    return sonuc.stdout.strip()


def test_gunluk_sayac_BUGUNU_sayiyor(tmp_path):
    from datetime import date, timedelta

    bugun = date.today().isoformat()
    dun = (date.today() - timedelta(days=1)).isoformat()
    d = tmp_path / "state.json"
    d.write_text(
        json.dumps(
            {
                "published": [
                    {"published_at": f"{bugun}T09:00:00"},
                    {"published_at": f"{bugun}T12:00:00"},
                    {"published_at": f"{dun}T23:00:00"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _bugunku(d) == "2", "dunku yayin bugune sayilmis"


def test_gunluk_sayac_BOZUK_dosyada_SIFIR(tmp_path):
    """⚠️ Okunamayan durum dosyasi yuzunden uretimi durdurmak, tavani bir kez
    asmaktan kotu — kota hatasi zaten `uret.sh` tarafinda yakalaniyor."""
    d = tmp_path / "state.json"
    d.write_text("{bozuk json", encoding="utf-8")
    assert _bugunku(d) == "0"


def test_gunluk_sayac_DOSYA_YOKSA_SIFIR(tmp_path):
    assert _bugunku(tmp_path / "olmayan.json") == "0"


def test_gunluk_sayac_PYTHON_CALISMAZSA_SIFIR(tmp_path):
    """⚠️ MUTASYON M8 BURADAN KACTI (2026-08-21).

    Kabuktaki `|| echo 0` yedegini silmek hicbir testi dusurmuyordu, cunku
    BOZUK JSON durumunu python'un kendi `try/except`i zaten karsiliyor. Kabuk
    yedegi BASKA bir seyi koruyor: python'un hic calismamasi.

    ⚠️ Bu gercek bir risk: `uret.sh` launchd altinda DAR bir PATH ile
    calisiyor (kabuk profili okunmuyor) ve ayni dosya bunun bir kez
    yasandigini yaziyor — `hermes` ciplak adla bulunamamisti. Yedek olmazsa
    fonksiyon bos dizge dondururdu ve `[ "" -lt 6 ]` kabukta HATA verip
    ikinci koşumu sessizce oldururdu.
    """
    d = tmp_path / "state.json"
    d.write_text("{}", encoding="utf-8")
    sonuc = subprocess.run(
        [
            "bash",
            "-c",
            f'. "{KARAR}"; bugunku_yayin_sayisi /olmayan/python "{d}"',
        ],
        capture_output=True,
        text=True,
    )
    assert sonuc.stdout.strip() == "0", (
        f"python yokken sayac bos dondu: {sonuc.stdout!r}"
    )


# --- Baglanti: uret.sh gercekten cagiriyor mu ------------------------------
# ⚠️ M9/M8 DERSI (bu oturum): "deger dogru" olcmek yetmiyor, hattin onu
# KULLANDIGI da olculmeli. Iki mutasyon tam bu bosluktan kacti.


def test_uret_sh_karari_YUKLUYOR_ve_CAGIRIYOR():
    govde = URET.read_text(encoding="utf-8")

    assert "slot_karari.sh" in govde, "karar dosyasi yuklenmiyor"
    assert "ikinci_kosum_gerekli_mi" in govde, "karar cagrilmiyor"


def test_IKINCI_kosum_FROM_NOTION_gecmiyor():
    """⚠️ Kanal sahibinin karari: ikinci deneme kanitlanmis capa havuzundan.

    Bayrak davranisi kodda dogrulandi: `--from-notion` yokken `aday` None
    kalir, `--yedek-konu` `no-candidate` donusunu engeller ve akis
    `kaynak = "yedek"` daline duser."""
    govde = URET.read_text(encoding="utf-8")
    bas = govde.index("ikinci_kosum_gerekli_mi")
    kuyruk = govde[bas:]

    assert "uretim_kosumu --yedek-konu" in kuyruk, "ikinci koşum yedek kipte degil"
    ikinci = kuyruk[kuyruk.index("uretim_kosumu --yedek-konu") :][:60]
    assert "--from-notion" not in ikinci, (
        f"ikinci koşum kuyruga bakiyor, havuza degil: {ikinci!r}"
    )


def test_ILK_kosum_DAVRANISI_degismedi():
    """⚠️ Regresyon kilidi: birinci koşum bugunku bayraklarla kalmali."""
    govde = URET.read_text(encoding="utf-8")

    assert "uretim_kosumu --from-notion --yedek-konu" in govde


def test_PLAN_REDLERI_her_kosumdan_sonra_yaziliyor():
    """⚠️ Ikinci koşumun denemeleri de butce yakiyor; #41'in olcmek istedigi
    sinyal tam olarak o. Tek seferlik cikarim ikinci koşumu kacirirdi."""
    govde = URET.read_text(encoding="utf-8")

    assert govde.count("plan_redlerini_yaz") >= 3, (
        "plan reddi cikarimi her koşumdan sonra cagrilmiyor"
    )


def test_KABUK_sozdizimi_saglam():
    for betik in (URET, KARAR):
        sonuc = subprocess.run(["bash", "-n", str(betik)], capture_output=True)
        assert sonuc.returncode == 0, f"{betik.name}: {sonuc.stderr.decode()}"
