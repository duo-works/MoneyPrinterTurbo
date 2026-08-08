"""Editoryal kimlik ve kanca denetimi (DW-105).

Iki sozlesme: kanalin sabit sesi (prompt metni) ve acilis cumlesi kapisi
(kod). Ikincisi bir DAVRANIS, o yuzden fonksiyon dogrudan cagriliyor.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def _plan(script: str) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Chaco Canyon",
        visual_anchor="Chaco Canyon",
        title="t",
        script=script,
        scenes=[
            {"narration": f"n{i}", "search_term": f"Chaco Canyon view {i}"} for i in range(1, 7)
        ],
        description="d",
        tags=["a", "b", "c"],
    )


def _senaryo(acilis: str) -> str:
    """Acilis + gecerli kelime sayisina tamamlayan govde."""
    dolgu = " ".join(["word"] * 95)
    return f"{acilis} {dolgu}."


# --- Kanca kapisi --------------------------------------------------------


@pytest.mark.parametrize(
    "acilis",
    [
        "In the 12th century, Chaco Canyon was a thriving hub.",
        "By 1850, the lighthouse was gone.",
        "Around 1200 the rain stopped.",
        "During the 1800s the site was looted.",
        "1130 was the year the rain stopped.",
    ],
)
def test_tarihle_acilis_reddediliyor(acilis):
    """⚠️ Prompt bunu ZATEN yasakliyordu ve model yine de yapti.

    Olculdu (2026-08-07): yonerge acikca "do not begin with ... dates" diyor,
    uretilen senaryo "In the 12th century, Chaco Canyon was a thriving hub..."
    diye basladi ve YAYINA CIKTI.

    Esik hikayesinin (DW-87) aynisi: modele kurali soylemek yetmiyor.
    """
    assert ya.kanca_kusuru(acilis)


@pytest.mark.parametrize(
    "acilis",
    [
        "Did you know the Colosseum could seat 50,000 spectators?",
        "Have you ever wondered who built it?",
        "Imagine a world without running water.",
        "Welcome back to the channel.",
        "In this video we look at Chaco Canyon.",
    ],
)
def test_kalip_acilis_reddediliyor(acilis):
    """Olculdu (DW-94): 6 videonun 4'u birebir "Did you know" ile basladi."""
    assert ya.kanca_kusuru(acilis)


@pytest.mark.parametrize(
    "acilis",
    [
        # ⚠️ Filtre fazla agresif olmamali — bunlar iyi acilislar.
        "In the Andes, a staircase leads to nothing.",
        "Spanish soldiers searched Peru for a city that was never lost.",
        "No one has ever found the grave of Genghis Khan.",
        "The stones fit so tightly that a knife blade will not pass between them.",
        "By the time the rescuers arrived, the village had moved.",
    ],
)
def test_iyi_acilislar_geciyor(acilis):
    assert not ya.kanca_kusuru(acilis)


def test_kapi_dogrulamaya_bagli():
    """Baglanti testi — fonksiyon dogru olsa bile `validate_content_plan`
    cagirmazsa kusur geri gelir (DW-97 dersi).
    """
    with pytest.raises(ValueError, match="date or century"):
        ya.validate_content_plan(_plan(_senaryo("In the 12th century, Chaco Canyon fell.")))


def test_gecerli_plan_hala_geciyor():
    ya.validate_content_plan(_plan(_senaryo("No one has found where they went.")))


def test_bos_senaryo_anlasilir_hata_veriyor():
    assert ya.kanca_kusuru("")


# --- Editoryal kimlik ----------------------------------------------------


def test_sabit_bir_arastirma_acisi_var():
    """Kanal sahibinin istegi: sabit bir ses ve arastirma acisi.

    Aci "yaygin inanis ↔ kanit" — her videoya ayni bakisi veriyor ve kanali
    bir sey SAVUNAN hale getiriyor. Jenerik "bir yer hakkinda 5 bilgi"
    uretiminden ayrisan sey bu.
    """
    assert "ONE FIXED EDITORIAL ANGLE" in ya.KANAL_SESI
    assert "what the surviving evidence actually shows" in ya.KANAL_SESI


def test_bilginin_siniri_soyleniyor():
    """Her seye kesin cevap veren metin sig oldugunun isaretidir."""
    assert "Say what is NOT known" in ya.KANAL_SESI
    assert "where the knowledge stops" in ya.KANAL_SESI


def test_son_cumle_bir_pozisyon_aliyor():
    """Ortasini ozetleyerek biten metnin yazari yoktur."""
    assert "Take a position in the final line" in ya.KANAL_SESI


def test_yapi_videodan_videoya_degisiyor():
    """⚠️ Ayni iskeletle uretilen 20 video, tam olarak "toplu uretim" gibi
    gorunen seydir. Ses sabit, kalip degil."""
    assert "Vary the structure between videos" in ya.KANAL_SESI


def test_kimlik_modele_giden_metinde():
    """Sabitin var olmasi yetmiyor — modele gercekten gidiyor mu.

    Davranisa bakiliyor: birlesmis yonerge hem kimligi hem sozlesmeyi
    tasimali. Kaynak metnini dilimleyen eski yaklasim tam da bu testi
    kirilgan yapan seydi.
    """
    yonerge = ya.editoryal_sistem_yonergesi()

    assert ya.KANAL_SESI in yonerge, "kimlik dusmus"
    assert "JSON keys:" in yonerge, "sozlesme dusmus"
    assert yonerge.startswith("You are the editorial producer"), "kimlik basta olmali"


def test_uretim_akisi_bu_yonergeyi_kullaniyor():
    """Baglanti testi — birlesme dogru olsa bile `plan_content` onu
    cagirmazsa kimlik modele hic gitmez (DW-97 dersi).
    """
    i = KAYNAK.index("    system = ")
    assert "editoryal_sistem_yonergesi()" in KAYNAK[i : i + 120]


def test_insan_yazdi_iddiasi_yok():
    """⚠️ Kimlik ICERIKLE kuruluyor, iddiayla degil.

    "Bunu bir insan yazdi" cumlesi hem yalan olurdu hem de izleyicinin
    gordugu sey zaten metnin kendisi. Dogruluk kisiti da (`truthful about
    what is known`) bu yonde.
    """
    metin = ya.KANAL_SESI.lower()
    for iddia in ("written by a human", "not ai", "human-written", "pretend"):
        assert iddia not in metin
