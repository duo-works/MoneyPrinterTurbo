"""Sahne anlatimlari esit uzunlukta olmali — klip suresi ESIT cunku.

⚠️ NEDEN VAR — `klip_suresi` toplam sesi kare sayisina boluyor, yani her sahne
ekranda AYNI kadar kaliyor. Cumleler esit degilse gorsel, anlattigi cumleden
kayiyor ve kayma video boyunca birikiyor.

⚠️ OLCULDU (2026-08-18, Cemal Pasha — YAYINLANMIS video, gorsel 75/100).
`subtitle.srt` ile klip sinirlari ust uste konuldu:

    sahne   gorsel ekranda   cumlesi soyleniyor   kayma
    s2       6,4-12,8         7,9-16,3            cumle 3,5 sn tasiyor
    s3      12,8-19,2        16,6-24,2            gorsel 3,8 sn ONCE
    s4      19,2-25,6        24,5-27,4            gorsel 5,3 sn ONCE

Kelime sayilari [23, 25, 24, 7, 7, 19], oran 3,57.

⚠️ Kaymanin IKINCI yarisi: hakem `lettering_text`'i klibin ORTASINDAN okuyor,
yani KAYMIS eslesmeyi degerlendiriyor. O videonun "aile fotografi
'assassinated in Tiflis' cumlesini karsilamiyor" sikayeti bir gorsel SECIMI
kusuru degil, bir ZAMANLAMA artefaktiydi. Yani bu kapi hakem skorunu da
ilgilendiriyor.

⚠️ Kapi kaymayi SINIRLIYOR, bitirmiyor. Yapisal cozum yuva basina ayri sure
(#50); ikisi birlikte calisiyor.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def _plan(*kelime_sayilari: int) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="Cemal Pasha",
        title="baslik",
        script="metin",
        scenes=[
            {"narration": " ".join(["kelime"] * n), "search_term": "t"}
            for n in kelime_sayilari
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


# --- Olcum ------------------------------------------------------------------


def test_YAYINLANAN_video_kapiya_TAKILIYOR():
    """⚠️ Asil iddia: bu kapi olsaydi Cemal Pasha planı geri cevrilirdi."""
    kusur = ya.anlatim_dengesi_kusuru(_plan(23, 25, 24, 7, 7, 19))

    assert kusur, "3,57 oranli plan gecmemeliydi"
    assert "25" in kusur and "7" in kusur, "mesaj olculen sayilari tasimali"


def test_DENGELI_plan_geciyor():
    assert not ya.anlatim_dengesi_kusuru(_plan(18, 20, 17, 19, 21, 18))


def test_SINIRDA_gecen_plan():
    """Tam esikte kalan plan REDDEDILMEZ — kapsayici okunuyor."""
    assert not ya.anlatim_dengesi_kusuru(_plan(10, 25))


def test_esigin_BIR_TIK_ustu_dusuyor():
    assert ya.anlatim_dengesi_kusuru(_plan(10, 26))


# --- Sinir durumlari --------------------------------------------------------


def test_TEK_sahne_kapiyi_tetiklemiyor():
    """Karsilastirilacak ikinci sahne yok; oran tanimsiz."""
    assert not ya.anlatim_dengesi_kusuru(_plan(40))


def test_sahnesiz_plan_PATLAMIYOR():
    plan = _plan()
    plan.scenes = []

    assert ya.anlatim_dengesi_kusuru(plan) == ""


def test_BOS_anlatim_boleni_SIFIRLAMIYOR():
    """⚠️ Bos anlatim min=0 yapip ZeroDivisionError'a ya da her plani
    reddetmeye goturebilirdi. Bos sahneler zaten `validate_content_plan`in
    kendi kapisinda yakalaniyor; burada yok sayiliyorlar."""
    plan = _plan(20, 18)
    plan.scenes.append({"narration": "", "search_term": "t"})

    assert not ya.anlatim_dengesi_kusuru(plan)


def test_uzun_format_planlari_da_olculuyor():
    """Kapi bicime bakmiyor: kayma uzun formatta DAHA cok birikiyor
    (`UZUN_YONERGE` ayni maddeyi zaten yaziyla soyluyor)."""
    assert ya.anlatim_dengesi_kusuru(_plan(*([45] * 30 + [8])))


# --- Mesaj ------------------------------------------------------------------


def test_kusur_metni_NE_YAPILACAGINI_soyluyor():
    """⚠️ Dogrulama hatasi modele geri besleniyor. Yalnizca kurali tekrarlayan
    mesajlarda model ayni plani geri yaziyor — `visual anchor` mesajinin
    gerekcesinde olculdu."""
    kusur = ya.anlatim_dengesi_kusuru(_plan(30, 6))

    assert "same number of seconds" in kusur, "NEDENI soylemeli"
    assert "splitting" in kusur and "merging" in kusur, "NE YAPILACAGINI soylemeli"


# --- Baglanti ---------------------------------------------------------------


def test_kapi_YUMUSAK():
    """⚠️ SART: esik tek olcume dayaniyor, kalibre DEGIL. Sert kapi olsaydi
    kalibresiz bir sayi bes denemeyi de yakabilirdi."""
    assert "if yumusak_kapilar_acik and (kusur := anlatim_dengesi_kusuru(plan)):" in KAYNAK


def test_SHORTS_istemi_de_esit_uzunluk_istiyor():
    """Kapi tek basina yetmez: model neyi hedefleyecegini bilmeli.

    ⚠️ Madde uzun formatta ZATEN vardi (`UZUN_YONERGE`), Shorts'ta YOKTU —
    gerekcesi "8 sahnede kayma gorunmuyordu"ydu ve 6 sahnede gorundu.
    """
    assert "GIVE EVERY SCENE ABOUT THE SAME NUMBER OF WORDS" in ya.EDITORYAL_YONERGE


def test_ESIK_ISTEME_YAZILMIYOR():
    """⚠️ DW-87: esigi bilen model olcmeyi birakip esigin bir tik altina
    yaziyor. Istemde NITEL madde var, SAYI yok."""
    for yonerge in (ya.EDITORYAL_YONERGE, ya.UZUN_YONERGE):
        assert str(ya.ANLATIM_DENGESI) not in yonerge


def test_esik_SABITTEN_geliyor_elle_yazilmiyor():
    """`test_kalite_kapisi.py` ayni kalibi kovaliyor: kapi govdesinde ciplak
    sayi olmamali, yoksa esik iki yerde yasar ve biri sessizce eskir."""
    govde = KAYNAK[KAYNAK.index("def anlatim_dengesi_kusuru(") :]
    govde = govde[: govde.index("\n\n\nKARE_YUVASI")]

    assert "ANLATIM_DENGESI" in govde
    assert not re.search(r"\*\s*\d+\.\d", govde), "esik elle yazilmis"
