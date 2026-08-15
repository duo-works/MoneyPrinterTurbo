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
    assert "[bicim, SHORTS_BICIMI] if denecek_uzun else [bicim]" in govde


def test_kuyruk_adayi_yoksa_uzun_DENENMIYOR():
    """⚠️ `--uzun --yedek-konu` ile bos kuyrukta `aday` None kalir ve
    `generate_content_plan` `ValueError` atar — dongu onu yakalamiyordu,
    yani koşum izlenmeyen bir istisnayla olurdu."""
    govde = _run_cycle_govdesi()

    assert "if not bicim.dikey and etkin_konu is None:" in govde


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


# --- Ikincil gorsel: uzun kipte hic indirilmiyor ---------------------------


def test_uzun_kipte_IKINCIL_GORSEL_indirilmiyor():
    """⚠️ Kipten bagimsiz calisirken UC sey birden oluyordu:

    1. `bant_ister` DIKEY hedefe bakiyor, yani her 16:9 arsiv fotografi
       "bant ister" cikip 45 sahnenin hepsine yedek indiriliyordu.
    2. Gelen dosyalar `credits`e ekleniyor, yani ACIKLAMADA KAYNAK
       GOSTERILIYORDU.
    3. Uzun kipte `kare_yerlesimi` ikincil listeyi HIC KULLANMIYOR.

    Yani video hic gostermedigi fotograflara atif yapardi — yanlis atif
    sessiz ve yayinlandiktan sonra duzeltilmesi zor bir kusur.
    """
    i = KAYNAK.index("def run_generator(")
    govde = KAYNAK[i : KAYNAK.index("\ndef ", i + 10)]
    j = govde.index("ikincil_gorseller(")

    # Cagri bir kip kosulunun ICINDE olmali.
    onceki = govde[:j]
    assert "if bicim.kare_yuvasi >= 2:" in onceki
    assert onceki.rindex("if bicim.kare_yuvasi >= 2:") > onceki.rindex("\n    ikincil_dosyalar")


def test_uzun_kipte_kredi_LISTESI_buyumuyor():
    """`credits` uzatmasi da ayni kosulun icinde olmali."""
    i = KAYNAK.index("def run_generator(")
    govde = KAYNAK[i : KAYNAK.index("\ndef ", i + 10)]
    j = govde.index("credits = list(credits) + ikincil_krediler")

    # Sekiz bosluk girinti = `if` blogunun icinde (fonksiyon govdesi dort).
    satir_basi = govde.rindex("\n", 0, j) + 1
    assert govde[satir_basi:j] == " " * 8, "kredi uzatmasi kip kosulunun disinda"


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
    kelime basina degil kelime SAYISIYLA olcekleniyor (DW-114).

    ⚠️ Sart olan sey Notion DEGIL, konunun verilmis olmasi: `--konu` ayni
    kosulu birebir sagliyor (kaynak metin ve arsiv menusu isteme giriyor).
    """
    assert "if args.uzun and not (args.from_notion or args.konu):" in KAYNAK


def test_ACIK_KONU_kuyrugu_atliyor():
    """⚠️ Kullanim yeri olculmus: kanalin en cok izlenen videolari talebi
    KANITLANMIS konular ama huni onlari `benzeri uretilmis` diye yeniden
    onermiyor, yani uzun formatta yeniden ele almanin tek yolu bu."""
    govde = _run_cycle_govdesi()

    assert "if konu_override:" in govde
    assert 'kaynak = "acik-konu"' in govde
    assert "etkin_konu = konu_override or (aday.baslik if aday else None)" in govde


def test_acik_konuda_CAPA_TEKRARI_serbest():
    """⚠️ Kanitlanmis konuyu uzun formatta yeniden ele alirken AYNI capa
    isteniyor — amac o. Kapi acik kalsaydi uc denemenin ucu de reddedilir,
    her biri ~2.000 kelimelik bir cikarim koşumu yakardi.

    Tekrar politikasi ihlal edilmiyor: 40 saniyelik Short ile 10 dakikalik
    belgesel ayri eserler ("each video has a distinct storyline, focus, or
    concept").
    """
    govde = _run_cycle_govdesi()

    assert "capa_serbest = bool(konu_override)" in govde
    assert "capa_tekrari_serbest=capa_serbest" in govde


def test_acik_konu_ile_kuyruk_CAKISMIYOR():
    assert "if args.konu and args.from_notion:" in KAYNAK


def test_uzun_ile_sahne_deneyi_CAKISMIYOR():
    """`--sahne-sayisi` 6-10 dogruluyor; uzun bicim 24-45 istiyor. Ikisi
    birlikte verilirse her plan reddedilir ve bes deneme yanar."""
    assert "if args.uzun and args.sahne_sayisi is not None:" in KAYNAK


def test_run_cycle_cagrisi_bicimi_TASIYOR():
    i = KAYNAK.index("result = run_cycle(")
    cagri = KAYNAK[i : KAYNAK.index(")", i)]

    assert "bicim=bicim" in cagri
