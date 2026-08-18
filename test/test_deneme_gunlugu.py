"""Her REDDEDILEN deneme iz birakmali — yalnizca sonuncusu degil.

⚠️ OLCULDU (2026-08-15, sekizinci Herculaneum koşumu): koşum 8,6 dakika
surdu, bes deneme de reddedildi ve geriye TEK satir bilgi kaldi:

    "5 denemede gecerli plan uretilemedi; son kusur: ... 48 sahne"

Diger dort denemenin neye taktigi kayboldu. Uzun format koşumlari 10-50
dakika suruyor; teshis edilemeyen her koşum yeni bir koşum demek.

⚠️ YUMUSAK KAPILAR daha da korduler: `alinti_kusuru`, kanca/kapanis/baslik
tekrari ve capa tekrari `son_kusur`u HIC yazmiyordu. Bes deneme bunlardan
duserse nihai mesaj eski bir dogrulama kusurunu ya da "bilinmiyor"
gosteriyordu — yani teshisi YANLIS yone gonderiyordu.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _dongu_govdesi() -> str:
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def generate_content_plan(") :]
    return govde[: govde.index("\ndef ", 10)]


def test_dogrulama_kusuru_DENEME_NUMARASIYLA_yaziliyor():
    govde = _dongu_govdesi()

    assert 'f"⚠️ deneme {deneme}/5 reddedildi:' in govde


def test_dogrulama_kusuru_OLCULERI_de_yaziyor():
    """Sahne sayisi, kelime sayisi ve capa — bir sonraki adimi bunlar belirliyor."""
    govde = _dongu_govdesi()

    assert "len(plan.scenes)} sahne" in govde
    assert "len(plan.script.split())} kelime" in govde
    assert "plan.visual_anchor!r}" in govde


def test_HER_yumusak_kapi_son_kusuru_yaziyor():
    """⚠️ Genelleyen test: bir kapi unutulursa o kapinin reddi gorunmez olur.

    Dongudeki her `continue`den once ya `son_kusur` atanmali ya da o dal
    plani KABUL etmeli. Sayim, kapi eklendiginde bu testin de guncellenmesini
    zorunlu kilar.
    """
    govde = _dongu_govdesi()

    assert govde.count("son_kusur = ") >= 6


def test_yumusak_kapi_redleri_de_YAZDIRILIYOR():
    govde = _dongu_govdesi()

    assert govde.count("deneme {deneme}/5 reddedildi") >= 6


def test_son_kusur_NIHAI_mesaja_giriyor():
    """Kapilar `son_kusur` yazmasa nihai mesaj yaniltirdi."""
    govde = _dongu_govdesi()

    assert "son kusur: {son_kusur or 'bilinmiyor'}" in govde


def test_alinti_kapisi_kusuru_ETIKETLI():
    """Hangi kapinin reddettigi mesajdan anlasilmali."""
    govde = _dongu_govdesi()

    assert re.search(r'son_kusur = f?"alinti kapisi:', govde)


# --- Kabuk yarisi: yazdirilan satir KALICI oluyor mu -------------------------
#
# ⚠️ OLCULDU (2026-08-18, #41). Yukaridaki testlerin hepsi `print` edildigini
# dogruluyor — ama zamanlayici koşumlarinda o ciktinin GIDECEK YERI yoktu:
#
#     uret.sh:67   CIKTI_DOSYASI="$(mktemp)"
#     uret.sh:68   trap 'rm -f "$CIKTI_DOSYASI"' EXIT
#
# Kopya yalnizca BEKLENMEDIK cikis kodunda (`*)` dali) `hata-*.log`a
# aliniyordu; 0 (yayin) ve 2 (red) — koşumlarin neredeyse tamami — stdout'u
# cope atiyordu. Kalici `<slot>-rejected.json` de bosluğu kapatmiyor: oraya
# yalnizca bes denemenin HEPSI tukenirse tek bir "son kusur" yaziliyor.
#
# Yani 1. deneme 184 kelimede dusup 2. deneme gecerse geriye HIC iz kalmiyordu.
# `youtube_automation.py` tarafi 2026-08-15'te duzeltilmisti; duzeltme elle
# koşumlara ulasti, zamanlayiciya ulasmadi.

URET_BETIGI = Path(__file__).resolve().parent.parent / "scripts" / "uret.sh"


CAPA = 'grep "reddedildi"'


def _yakalama_blogu() -> str:
    """`uret.sh`ten yakalama blogunu ayikla — testin CALISTIRDIGI sey bu.

    ⚠️ Capa kaybolunca `ValueError: substring not found` ile dusmemeli;
    bozulan seyin NE oldugu mesajdan anlasilmali.
    """
    m = URET_BETIGI.read_text(encoding="utf-8")
    assert CAPA in m, f"{URET_BETIGI.name}: plan redi yakalama blogu ({CAPA}) YOK"
    bas = m.index(CAPA)
    return m[bas : m.index("\ncase", bas)]


def test_uret_betigi_plan_redlerini_KALICI_dosyaya_yaziyor():
    assert "plan-redleri.log" in URET_BETIGI.read_text(encoding="utf-8")


def test_yakalama_CASE_ten_once_yani_her_cikis_kodunda_calisiyor():
    """⚠️ Yayinlanan koşum da deneme yakmis olabilir; o da sinyaldir.

    Blok `case`in ICINDE olsaydi yalnizca tek bir cikis kodunu kapsardi.
    """
    m = URET_BETIGI.read_text(encoding="utf-8")

    assert CAPA in m, f"yakalama blogu ({CAPA}) YOK"
    assert m.index(CAPA) < m.index('case "$KOD" in'), (
        "yakalama blogu `case`ten SONRA — o halde yalnizca tek bir cikis "
        "kodunu kapsar, yayinlanan koşumun yaktigi denemeler kaybolur"
    )


def test_yakalama_blogu_GERCEKTEN_calisiyor(tmp_path):
    """⚠️ DIZE TESTI YETMEZ — bu blok iki kez calisma aninda patladi:

      · `sed` degistirme metninde ayrac karakteri (`|`) gecti,
      · tanimsiz bir slot degiskeni kullanildi ve betik `set -u` ile kosuyor.

    Ikisini de `bash -n` YAKALAMAZ. Bu yuzden test blogu gercekten kosturuyor.
    """
    import subprocess

    cikti = tmp_path / "cikti.log"
    # ⚠️ Iki BICIM birden: dogrulama kusuru ":" ile, yumusak kapilar "—" ile
    # yaziyor. Capa yalnizca birini tutarsa yarisi sessizce kaybolur.
    cikti.write_text(
        "⚠️ deneme 2/5 reddedildi: script must contain 80-150 words, got 184\n"
        "⚠️ deneme 3/5 reddedildi — baslik bicimi tekrari: 'X #Shorts'\n"
        "alakasiz satir\n",
        encoding="utf-8",
    )
    betik = tmp_path / "blok.sh"
    betik.write_text(
        "set -uo pipefail\n"
        'zaman() { echo "ZAMAN"; }\n'
        f'CIKTI_DOSYASI="{cikti}"\nLOG_DIZINI="{tmp_path}"\n' + _yakalama_blogu(),
        encoding="utf-8",
    )

    sonuc = subprocess.run(["bash", str(betik)], capture_output=True, text=True)

    assert sonuc.returncode == 0, sonuc.stderr
    satirlar = (tmp_path / "plan-redleri.log").read_text(encoding="utf-8").splitlines()
    assert len(satirlar) == 2, satirlar
    assert all(s.startswith("ZAMAN | ") for s in satirlar), satirlar
    assert "got 184" in satirlar[0]
    assert "baslik bicimi tekrari" in satirlar[1]


def test_yakalama_ESLESME_YOKKEN_kosumu_OLDURMUYOR(tmp_path):
    """⚠️ Asil risk buydu: eslesmeyen grep 1 donduruyor ve bu blok, ozet
    satirini (`YAYIN | ...`) yazan `case`ten ONCE calisiyor. Blok koşumu
    dusurseydi yayin kaydi hic yazilmazdi."""
    import subprocess

    cikti = tmp_path / "temiz.log"
    cikti.write_text("hicbir red yok\n", encoding="utf-8")
    betik = tmp_path / "blok.sh"
    betik.write_text(
        "set -uo pipefail\n"
        'zaman() { echo "ZAMAN"; }\n'
        f'CIKTI_DOSYASI="{cikti}"\nLOG_DIZINI="{tmp_path}"\n' + _yakalama_blogu(),
        encoding="utf-8",
    )

    sonuc = subprocess.run(["bash", str(betik)], capture_output=True, text=True)

    assert sonuc.returncode == 0, sonuc.stderr
