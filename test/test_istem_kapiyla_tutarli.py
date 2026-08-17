"""Modele SOYLENEN sayi ile KAPININ olctugu sayi ayni olmali (#41).

⚠️ NEDEN VAR — olculdu (2026-08-18), iki gun uretim yiyen kusur:

    istem  (`EDITORYAL_YONERGE`)  "80-120 spoken English words"
    kapi   (`SHORTS_BICIMI.kelime_araligi`)  (80, 150)
    red mesaji                     "must contain 80-150 words"

16 Agustos'ta tavan 120'den 150'ye cikarildi (`6d409ed`) ama istemdeki SABIT
METIN guncellenmedi. Uzun kip `_yonerge_degistir` ile sayiyi enjekte ettigi
icin dogruydu; SHORTS dali sozlesmeyi hic degistirmiyordu — ve hat yalnizca
Shorts uretiyor.

Sonucu loglarda gorunuyor: 14 kelime reddinin 10'u tavanin USTUNDE (157, 159,
165, 184, 186, 188, 196, 198, 219) ve bir uretim koşumunda 12 plan denemesi
yandi. 18 Agu 00:06 zamanlayici koşumu "skor 0" ile bitti — yani video degil
PLAN uretilemedi.

⚠️ Bu dosya bir DEGERI degil bir TUTARLILIGI koruyor. Tavan yarin 170 olursa
testler yine gecmeli; gecmemesi gereken tek sey istemle kapinin ayrilmasi.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

BICIMLER = [
    pytest.param(ya.SHORTS_BICIMI, id="shorts"),
    pytest.param(ya.UZUN_BICIMI, id="uzun"),
]


def _istemdeki_aralik(bicim) -> tuple[int, int]:
    yonerge = ya.editoryal_sistem_yonergesi(bicim)
    eslesme = re.search(r"script must be (\d+)-(\d+) spoken English words", yonerge)
    assert eslesme, f"{bicim.ad}: istemde kelime araligi cumlesi bulunamadi"
    return int(eslesme.group(1)), int(eslesme.group(2))


@pytest.mark.parametrize("bicim", BICIMLER)
def test_istemdeki_kelime_araligi_KAPIYLA_ayni(bicim):
    """⚠️ Asil kosul. Ikisi ayrilirsa model tutturamayacagi bir hedef kovalar."""
    assert _istemdeki_aralik(bicim) == bicim.kelime_araligi, (
        f"{bicim.ad}: modele {_istemdeki_aralik(bicim)} deniyor ama kapi "
        f"{bicim.kelime_araligi} olcuyor"
    )


@pytest.mark.parametrize("bicim", BICIMLER)
def test_istemde_kelime_araligi_TEK_KEZ_geciyor(bicim):
    """Iki farkli sayi kalirsa istem kendi kendisiyle celisir.

    ⚠️ Ilk tasarim eski cumleyi yerinde birakip sonuna gecersiz kilma blogu
    eklemekti; gerekce `editoryal_sistem_yonergesi` docstring'inde.
    """
    yonerge = ya.editoryal_sistem_yonergesi(bicim)
    assert len(re.findall(r"script must be \d+-\d+ spoken English words", yonerge)) == 1


def test_SHORTS_istemi_artik_capa_dizeyi_TASIMIYOR():
    """Capa dize (`80-120`) degistirilmeden kalirsa kusur geri gelmis demektir.

    ⚠️ Shorts araligi bir gun gercekten 80-120 olursa bu test yaniltici
    sekilde duser; o zaman silinmeli, cunku `test_istemdeki_kelime_araligi_
    KAPIYLA_ayni` zaten dogru kosulu tutuyor.
    """
    if ya.SHORTS_BICIMI.kelime_araligi == (80, 120):
        pytest.skip("aralik gercekten 80-120; capa kontrolu anlamsiz")
    assert ya.KELIME_CUMLESI not in ya.editoryal_sistem_yonergesi(ya.SHORTS_BICIMI)


def test_capa_dize_EDITORYAL_YONERGEDE_duruyor():
    """`_yonerge_degistir` capayi bulamazsa PATLIYOR; capa kaybolursa iki kip
    birden coker. Bu test o coküşü teste tasiyor."""
    assert ya.KELIME_CUMLESI in ya.EDITORYAL_YONERGE


# --- Resmedilemez anlatim: istemdeki ORNEKLER kapiyla ayni tarafta mi -------
#
# ⚠️ NEDEN — olculdu (2026-08-17). Bir uretim koşumunda 12 plan denemesi yandi
# ve EN SIK sebep kelime sayisi degil resmedilemez anlatimdi (5 red). Modelin
# gercek ihlalleri hep ayni bicimdeydi:
#
#     "Photographs show"  ·  "portraits from the same era shows"
#     "images do not show"  ·  "portraits from 1912 to 1917 show"
#
# Istem ise yalnizca SOYUT ornekler veriyordu ("the record here does not name
# each turning point"). Model somut bir kaynak adi yazinca ("photographs")
# ayni kurali cignedigini anlamiyordu. Ornekler olculen bicimlerle
# guncellendi; asagisi ikisinin ayrilmasini engelliyor.


@pytest.mark.parametrize(
    "cumle",
    [
        "Photographs show the fortress walls.",
        "Portraits from the same era show him in uniform.",
        "The images do not show the roof.",
    ],
)
def test_istemin_YASAKLADIGI_ornek_kapida_da_DUSUYOR(cumle):
    """Istemde ornek verilip kapida gecen bir kalip, sahte bir kuraldir."""
    assert ya.resmedilemez_kusuru(cumle), f"{cumle!r} istemde yasak ama kapi geciriyor"


@pytest.mark.parametrize(
    "cumle",
    [
        # ⚠️ Bunlari KANAL_SESI acikca ISTIYOR ("Say what is NOT known, out
        # loud, at least once"). Kapi bunlari reddederse istem kendi kendisiyle
        # celisir ve model her denemede iki zit talimat arasinda kalir.
        "locals still claim the hill is hollow.",
        "His body was never found.",
        "No one has found the tomb.",
        "The record stops here.",
    ],
)
def test_kanal_sesinin_ISTEDIGI_cumle_kapidan_GECIYOR(cumle):
    assert not ya.resmedilemez_kusuru(cumle), (
        f"{cumle!r} kanal sesinin istedigi bicim ama kapi reddediyor"
    )


@pytest.mark.parametrize("bicim", BICIMLER)
def test_istem_ORTAYI_hedeflemeyi_soyluyor(bicim):
    """⚠️ NEDEN — olculdu (2026-08-18), tavan-ustu redlerin sayisal imzasi:

        gozlenen  153, 154, 153 kelime / 6 sahne = 25,5 kelime/sahne
        tavan     150 kelime / 6 sahne          = 25,0 kelime/sahne

    Model sahne basina yarim kelime sapiyor ve alti sahnede bu 3-4 kelimelik
    asima donusuyor. Yani model TAVANI hedefliyor ve dogal olarak biraz
    asiyor; geri bildirim alinca 194'ten 153'e iniyor ama esigin ustunde
    takiliyor.

    ⚠️ Cozum ARALIGI GENISLETMEK DEGIL — 150 kelime = 52,9 sn ve Shorts
    siniri 60 sn, yani pay neredeyse bitti; ustelik tavan 120'den 150'ye
    cikarildiginda model de yukari kaydi (122-151'den 153-194'e). Aralik
    ayni kaliyor, degisen sey modele verilen HEDEF.
    """
    yonerge = ya.editoryal_sistem_yonergesi(bicim)
    assert "AIM FOR THE MIDDLE OF THAT RANGE, NOT ITS CEILING" in yonerge


def test_istem_resmedilemez_kuralini_SOMUT_ornekle_anlatiyor():
    """Soyut ornek yetmedi — olculdu, 5 red hep somut kaynak adiyla geldi."""
    yonerge = ya.editoryal_sistem_yonergesi()
    assert "photographs show the walls" in yonerge
    assert "portraits from the same era show him" in yonerge


@pytest.mark.parametrize("bicim", BICIMLER)
def test_dogrulama_mesaji_ISTEMLE_ayni_sayiyi_soyluyor(bicim):
    """Model uc ayri sayi gormemeli: istem, kapi ve RED MESAJI.

    Red mesaji modele geri besleniyor (`generate_content_plan` dislama
    dongusu), yani o da sozlesmenin bir parcasi.
    """
    en_az, en_cok = bicim.kelime_araligi
    plan = ya.ContentPlan(
        topic="konu",
        visual_anchor="capa",
        title="baslik #Shorts",
        script="kelime " * (en_cok + 40),
        scenes=[{"narration": "x", "search_term": "y"} for _ in range(6)],
        description="aciklama",
        tags=["a", "b", "c"],
    )
    with pytest.raises(ValueError) as hata:
        ya.validate_content_plan(plan, bicim=bicim)
    assert f"{en_az}-{en_cok} words" in str(hata.value)
