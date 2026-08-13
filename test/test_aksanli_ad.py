"""Aksanli ozel ad kelime sinirini kirmamali (DW-131).

⚠️ Bu bir gorunum kusuru degil, DETERMINISTIK KILITTI. Uretimde yasandi
(2026-08-12, Carl Friedrich von Weizsäcker koşumu): `_normalize_topic`
`[a-z0-9]+` suzgecini kullaniyordu ve aksanli harf kelimeyi ikiye boluyordu.

    "Carl Friedrich von Weizsäcker" → {carl, friedrich, von, weizs, cker}

Dort kelimelik ad bes belirtec verince "gorsel capa 1-4 kelime" kurali
hicbir zaman gecilemedi. Model uc kez uyarilip ayni adi geri yazdi,
dorduncu cikarim 180 saniyede zaman asimina ugradi ve kosum coktu.

Yani aksanli ve uc kelimeden uzun her ozel ad uretilemezdi — huninin Alman,
Turk ve Ispanyol adaylarinin buyuk kismi.
"""

import pytest

import youtube_automation as ya


@pytest.mark.parametrize(
    "ad, beklenen",
    [
        ("Carl Friedrich von Weizsäcker", {"carl", "friedrich", "von", "weizsacker"}),
        ("Götz von Berlichingen", {"gotz", "von", "berlichingen"}),
        ("Feza Gürsey", {"feza", "gursey"}),
        ("Batalla de Boyacá", {"batalla", "de", "boyaca"}),
        ("Hüsrev Gerede", {"husrev", "gerede"}),
    ],
)
def test_aksan_kelimeyi_bolmuyor(ad, beklenen):
    assert ya._normalize_topic(ad) == beklenen


def test_ayirt_edici_belirtec_olusuyor():
    """⚠️ Sinsi olan ikinci zarar: adin AYIRT EDICI belirteci hic olusmuyordu.

    `is_duplicate_topic` ve `_ensure_visual_anchor` o belirtec uzerinden
    esliyor; ikisi de sessizce zayifliyordu. Kilit acilsa bile bu kalirdi.
    """
    assert "weizsacker" in ya._normalize_topic("Ernst von Weizsäcker")
    assert "weizs" not in ya._normalize_topic("Ernst von Weizsäcker")


def test_dort_kelimelik_aksanli_ad_capa_kapisini_geciyor():
    """Asil kosul — olculen kusur buydu."""
    plan = ya.ContentPlan(
        topic="Carl Friedrich von Weizsäcker",
        visual_anchor="Carl Friedrich von Weizsäcker",
        title="Who Was Carl Friedrich von Weizsäcker? #Shorts",
        script=_senaryo(),
        # ⚠️ Terimler farkli olmali: ayni terimi tekrarlayan plan artik
        # dogrulamadan gecmiyor (portre yigini kusuru, 2026-08-13). Testin
        # konusu AKSANLI CAPA, bu yuzden hepsi capayi tasiyor ama ayrisiyor.
        scenes=[
            {"narration": "n", "search_term": f"Weizsäcker {ayrinti}"}
            for ayrinti in (
                "portrait photograph", "lecture hall", "Göttingen laboratory",
                "signed manifesto", "physics conference", "later years",
            )
        ],
        description="d",
        tags=["a", "b", "c"],
    )

    ya.validate_content_plan(plan)


def test_gercekten_uzun_capa_HALA_reddediliyor_ve_nasil_kisaltilacagini_soyluyor():
    """Kilit acilirken kural gevsetilmedi: bes kelime bes kelimedir.

    Mesaj artik NE YAPILACAGINI soyluyor; eski mesaj yalnizca kurali
    tekrarliyordu ve model uc denemede de ayni adi geri yaziyordu.
    """
    plan = ya.ContentPlan(
        topic="x",
        visual_anchor="Carl Friedrich Freiherr von Weizsäcker",
        title="t",
        script=_senaryo(),
        scenes=[
            {"narration": "n", "search_term": f"Weizsäcker {ayrinti}"}
            for ayrinti in (
                "portrait", "lecture hall", "laboratory",
                "manifesto", "conference", "later years",
            )
        ],
        description="d",
        tags=["a", "b", "c"],
    )

    with pytest.raises(ValueError, match="at most 4"):
        ya.validate_content_plan(plan)


def _senaryo() -> str:
    """80-120 kelimelik, kanca kapisini gecen bir senaryo."""
    return "The iron hand was also a poet. " + "He wrote a line nobody expected. " * 15
