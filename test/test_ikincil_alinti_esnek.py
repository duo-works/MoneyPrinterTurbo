"""Ikinci alinti PLANI OLDURMEZ — olculmus bir gerilemenin kapisi.

⚠️ NEDEN VAR — olculdu (2026-08-14, ayni gun icinde eklenip duzeltildi).
Sahne basina iki kare duzeni gelince istem her sahne icin IKI dosya
istemeye basladi ve alinti kapisi ikinci alintiyi da birincil kadar sert
denetliyordu: uydurma ya da tekrarlayan bir `source_file_2` PLANIN
TAMAMINI reddediyordu.

Yedek capa havuzunda olculen menu boyutlari (6 sahne 12 ayri dosya ister):

    Newgrange 7 · Notre Dame 5 · Sigiriya 8 · Sacsayhuaman 11 ·
    Hadrian's Wall 11        -> 14 capanin 5'i KARSILAYAMIYOR

Model imkansiz talebi karsilamak icin dosya tekrar ediyor, plan
reddediliyor, bes deneme yaniyordu. 18:05 zamanlanmis koşumu tam bu
yuzden hic video uretmeden dustu — materyal dizini bile olusmadi.

⚠️ DOGRU DAVRANIS: ikinci gorsel bir IYILESTIRME. Birincil alinti
sahnenin anlatimini tasiyor, yanlissa video yanlis olur ve orada
reddetmek dogru. Ikinci gorsel yoksa sahne birincil kareyi iki yuvada
gosterir ve bugunku haliyle birebir ayni durur. Iyilestirme ugruna
calisan bir plani cope atmak, kazanci maliyetten kucuk bir takas.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _menu(*adlar: str) -> list[dict[str, str]]:
    return [{"dosya": ad, "gosterdigi": "bir sey", "tarih": "1900"} for ad in adlar]


def _plan(ciftler: list[tuple[str, str]]) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="Sutton Hoo",
        title="baslik #Shorts",
        script="metin",
        scenes=[
            {
                "narration": f"sahne {sira}",
                "search_term": f"Sutton Hoo detay {sira}",
                "kaynak_dosya": birinci,
                "kaynak_dosya_2": ikinci,
            }
            for sira, (birinci, ikinci) in enumerate(ciftler, 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


# --- Menu yetiyor mu ------------------------------------------------------


def test_menu_yetiyorsa_ikinci_gorsel_istenebilir():
    assert ya.ikinci_gorsel_istenebilir(_menu(*[f"{i}.jpg" for i in range(12)]), 6)


def test_menu_yetmiyorsa_istenmiyor():
    """Newgrange 7 dosya, 6 sahne 12 ister."""
    assert not ya.ikinci_gorsel_istenebilir(_menu(*[f"{i}.jpg" for i in range(7)]), 6)


def test_tam_sinirda_isteniyor():
    assert ya.ikinci_gorsel_istenebilir(_menu(*[f"{i}.jpg" for i in range(12)]), 6)
    assert not ya.ikinci_gorsel_istenebilir(_menu(*[f"{i}.jpg" for i in range(11)]), 6)


def test_istem_kucuk_menude_ikinci_dosya_ISTEMIYOR():
    """⚠️ Imkansiz talep, modelin dosya uydurmasinin dogrudan sebebi."""
    metin = ya._menu_talimati(_menu("A.jpg", "B.jpg", "C.jpg"), 6)

    assert "Leave source_file_2 empty for every scene" in metin
    assert "ALSO pick a SECOND entry" not in metin


def test_istem_buyuk_menude_ikinci_dosya_ISTIYOR():
    metin = ya._menu_talimati(_menu(*[f"{i}.jpg" for i in range(12)]), 6)

    assert "ALSO pick a SECOND entry" in metin


# --- Kapi ikinci alinti yuzunden REDDETMIYOR ------------------------------


def test_uydurma_ikinci_alinti_plani_REDDETMIYOR(monkeypatch):
    """⚠️ Gerilemenin ta kendisi: burada bos donmezse koşum video uretmez."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "B.jpg"))
    plan = _plan([("A.jpg", "YOK.jpg"), ("B.jpg", "")])

    assert ya.alinti_kusuru(plan) == ""


def test_tekrarlayan_ikinci_alinti_plani_REDDETMIYOR(monkeypatch):
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "B.jpg"))
    plan = _plan([("A.jpg", "B.jpg"), ("B.jpg", "A.jpg")])

    assert ya.alinti_kusuru(plan) == ""


def test_BIRINCIL_alinti_hala_sert_deneteniyor(monkeypatch):
    """⚠️ Gevsetme yalnizca ikinci alintida. Birincil yanlissa video yanlis."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "B.jpg"))

    uydurma = ya.alinti_kusuru(_plan([("YOK.jpg", ""), ("B.jpg", "")]))
    tekrarli = ya.alinti_kusuru(_plan([("A.jpg", ""), ("A.jpg", "")]))

    assert "does not exist" in uydurma
    assert "more than one scene" in tekrarli


# --- Temizlik -------------------------------------------------------------


def test_uydurma_ikinci_alinti_SILINIYOR(monkeypatch):
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "B.jpg", "C.jpg"))
    plan = _plan([("A.jpg", "YOK.jpg"), ("B.jpg", "C.jpg")])

    silinen = ya.ikincil_alintilari_temizle(plan)

    assert silinen == 1
    assert plan.scenes[0]["kaynak_dosya_2"] == ""
    assert plan.scenes[1]["kaynak_dosya_2"] == "C.jpg", "gecerli olan korunmali"


def test_BIRINCILLE_cakisan_ikinci_alinti_siliniyor(monkeypatch):
    """Ayni gorsel bir sahnenin iki yuvasinda cikmasin — sikayet buydu."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "B.jpg"))
    plan = _plan([("A.jpg", "B.jpg"), ("B.jpg", "")])

    silinen = ya.ikincil_alintilari_temizle(plan)

    assert silinen == 1
    assert plan.scenes[0]["kaynak_dosya_2"] == ""


def test_ikinci_alintilar_birbirini_tekrar_edemez(monkeypatch):
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "B.jpg", "X.jpg"))
    plan = _plan([("A.jpg", "X.jpg"), ("B.jpg", "X.jpg")])

    silinen = ya.ikincil_alintilari_temizle(plan)

    assert silinen == 1
    assert [s["kaynak_dosya_2"] for s in plan.scenes] == ["X.jpg", ""]


def test_temiz_plan_bozulmuyor(monkeypatch):
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "B.jpg", "C.jpg", "D.jpg"))
    plan = _plan([("A.jpg", "B.jpg"), ("C.jpg", "D.jpg")])

    assert ya.ikincil_alintilari_temizle(plan) == 0
    assert [s["kaynak_dosya_2"] for s in plan.scenes] == ["B.jpg", "D.jpg"]


def test_menu_yoksa_temizlik_patlamiyor(monkeypatch):
    """Menusu olmayan konularda hat eskisi gibi aramayla calisiyor."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: [])
    plan = _plan([("A.jpg", "B.jpg")])

    assert ya.ikincil_alintilari_temizle(plan) == 0


# --- Hatta baglanti -------------------------------------------------------


def test_temizlik_plan_dongusune_BAGLI():
    """⚠️ Fonksiyon dogru olsa bile cagrilmazsa bozuk alinti indirmeye gider."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    # ⚠️ Kapanis parantezi ARANMIYOR ve bosluklar siliniyor: cagriya
    # sonradan `sinir=` eklendi, satir sardi ve test kirildi. Testin konusu
    # argüman listesi degil, temizligin plan dongusune bagli olmasi.
    def bosluksuz(metin: str) -> str:
        return re.sub(r"\s+", "", metin)

    assert bosluksuz('ikincil_alintilari_temizle(plan, konu or ""') in bosluksuz(kaynak)
