"""Uzun format UCTAN UCA — `run_cycle` bicimi butun kapilara tasiyor mu.

⚠️ NEDEN BAGLANTI TESTI: bu hattaki kusurlarin cogu fonksiyonlarin
kendisinde degil, CAGRILMAMALARINDA cikti. `bicim` bir yerde gecirilmezse
hicbir sey patlamaz — video sessizce dikey render edilir, YouTube onu Shorts
sayar ve uzun formatin varlik sebebi olan izlenme saati YAZILMAZ.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def _bosluksuz(metin: str) -> str:
    return re.sub(r"\s+", "", metin)


def _run_cycle_govdesi() -> str:
    i = KAYNAK.index("def run_cycle(")
    return KAYNAK[i : KAYNAK.index("\ndef ", i + 10)]


# --- Bicim butun kapilara gidiyor mu --------------------------------------


def test_run_cycle_bicim_aliyor():
    assert "bicim: VideoBicimi = SHORTS_BICIMI" in _run_cycle_govdesi()


def test_bicim_URETICIYE_geciyor():
    """⚠️ Gecmezse video 9:16 render edilir ve YouTube onu Shorts sayar."""
    assert "run_generator(plan, attempt, bicim=bicim)" in _run_cycle_govdesi()


def test_bicim_HAKEME_geciyor():
    govde = _bosluksuz(_run_cycle_govdesi())

    assert "review_video(plan,montage,bicim=bicim)" in govde
    assert "len(plan.scenes)*bicim.kare_yuvasi,bicim=bicim" in govde


def test_bicim_PLANLAYICIYA_geciyor():
    assert _bosluksuz("bicim=aday_bicim") in _bosluksuz(_run_cycle_govdesi())


def test_ONARIMA_orneklem_geciyor():
    """⚠️ En sinsi tel: gecirilmezse hakemin "kare 7" dedigi sey orneklemin
    7. elemani yerine videonun 7. karesi sayilir ve onarim YANLIS sahneye
    gider. Hicbir sey patlamaz."""
    govde = _bosluksuz(_run_cycle_govdesi())

    assert "ornekler=hakem_kareleri(" in govde
    assert "bicim=bicim" in govde


# --- Ince arsivde Shorts'a dusus ------------------------------------------


def test_ince_arsivde_SHORTS_A_dusuyor():
    """⚠️ Durmak, kuyruktan kapilmis adayi ve uretim slotunu birlikte
    yakmak olurdu. Uzun format bir IYILESTIRME, uretimin on kosulu degil."""
    govde = _run_cycle_govdesi()

    assert "except UzunFormatUygunDegilError" in govde
    assert "[bicim] if bicim.dikey else [bicim, SHORTS_BICIMI]" in govde


def test_planlama_hatasi_DONGUDE_yakalaniyor():
    """⚠️ Ilk yazimda yedek cagri `except` govdesinin ICINDEYDI ve oradan
    cikan `DistinctTopicUnavailableError` kardes `except`e ugramadan disari
    kacardi — nazikce reddedilecek koşum izlenmeyen istisnayla olurdu."""
    govde = _run_cycle_govdesi()
    i = govde.index("for aday_bicim in denenecek:")
    dongu = govde[i : govde.index("if plan is None:", i)]

    assert "except DistinctTopicUnavailableError" in dongu
    assert "planlama_hatasi = exc" in dongu


def test_konu_sorununda_DIGER_bicim_denenmiyor():
    """Konu sorunu bicim degistirerek cozulmez; denemek bes cikarim koşumunu
    daha yakmak olurdu."""
    govde = _run_cycle_govdesi()
    i = govde.index("planlama_hatasi = exc")

    assert "break" in govde[i : i + 60]


# --- Telemetri -------------------------------------------------------------


def test_kayitta_BICIM_alani_var():
    """⚠️ Yazilmazsa izlenme saati raporunda uzun videoyla Short'u ayirt
    etmek imkansiz olur — ve uzun formatin varlik sebebi tam olarak o
    saatler."""
    govde = _bosluksuz(_run_cycle_govdesi())

    assert '"bicim":bicim.ad' in govde


def test_kare_duzeni_SABIT_degil():
    govde = _bosluksuz(_run_cycle_govdesi())

    assert '"kare_duzeni":bicim.kare_yuvasi' in govde
    assert '"kare_duzeni":KARE_YUVASI' not in govde


# --- CLI -------------------------------------------------------------------


def test_uzun_bayragi_var():
    assert '"--uzun"' in KAYNAK
    assert "bicim = UZUN_BICIMI if args.uzun else SHORTS_BICIMI" in KAYNAK


def test_uzun_KONU_zorunlu_kiliyor():
    """⚠️ Konusuz uzun plan 2.000 kelimeyi hafizadan yazar; uydurma riski
    kelime basina degil kelime SAYISIYLA olcekleniyor (DW-114)."""
    assert "if args.uzun and not args.from_notion:" in KAYNAK


def test_uzun_ile_sahne_deneyi_CAKISMIYOR():
    """`--sahne-sayisi` 6-10 dogruluyor; uzun bicim 24-45 istiyor. Ikisi
    birlikte verilirse her plan reddedilir ve bes deneme yanar."""
    assert "if args.uzun and args.sahne_sayisi is not None:" in KAYNAK


def test_run_cycle_cagrisi_bicimi_TASIYOR():
    i = KAYNAK.index("result = run_cycle(")
    cagri = KAYNAK[i : KAYNAK.index(")", i)]

    assert "bicim=bicim" in cagri
