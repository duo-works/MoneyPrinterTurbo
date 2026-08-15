"""Tekrarlayan arama terimi PLANI OLDURMEMELI — uzun formatta onarilir.

⚠️ NEDEN — olculdu (2026-08-15, ilk Herculaneum koşumu). Bes denemenin
ucuncusu tam gecerli bir plandi: 1.353 kelime, 31 sahne, 31/31 gecerli
arsiv alintisi. 31 terimin 3'u benzestigi icin PLANIN TAMAMI reddedildi.
Koşum 9,6 dakika sonra hic video uretmeden dustu.

Kapinin olculmus gerekcesi (2026-08-13) uzun formatta gecerli DEGIL: o kapi
ayni terimin ayni sirali arama sonucunu getirmesine karsiydi. Uzun formatta
sahne gorselini ARAMADAN degil ALINTIDAN aliyor (`wikimedia_materials`
once `kaynak_dosya`yi indiriyor); terim yalnizca alinti dustugunde devreye
giren bir yedek.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(sahneler: list[tuple[str, str]]) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="Herculaneum",
        title="baslik",
        script="metin",
        scenes=[
            {"narration": f"sahne {i}", "search_term": terim, "kaynak_dosya": dosya}
            for i, (terim, dosya) in enumerate(sahneler, 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def test_tekrarlayan_terim_DOSYADAN_ayirt_ediliyor():
    plan = _plan(
        [
            (
                "Herculaneum House of the Stags",
                "Herculaneum Casa dei Cervi peristyle.jpg",
            ),
            (
                "Herculaneum House of the Stags",
                "Herculaneum Casa dei Cervi marble deer.jpg",
            ),
        ]
    )

    assert ya.arama_terimlerini_tekillestir(plan) == 1

    terimler = [s["search_term"] for s in plan.scenes]
    assert terimler[0] != terimler[1], "terimler hala ayni"
    # ⚠️ Ayirt edici bilgi UYDURULMUYOR, alintilanan dosyadan aliniyor.
    assert "marble" in terimler[1] or "deer" in terimler[1]


def test_onarim_sonrasi_KAPI_geciyor():
    """Asil kazanc: 1.353 kelimelik gecerli plan artik cope gitmiyor."""
    plan = _plan(
        [
            ("Herculaneum boat chambers", "Herculaneum boat chambers skeletons.jpg"),
            ("Herculaneum boat chambers", "Herculaneum ancient shoreline arches.jpg"),
            ("Herculaneum papyrus scroll", "Herculaneum Villa dei Papiri scroll.jpg"),
        ]
    )
    ya.arama_terimlerini_tekillestir(plan)

    terimler = [
        " ".join(sorted(ya._normalize_topic(s["search_term"]))) for s in plan.scenes
    ]
    assert len(set(terimler)) == len(terimler), "tekrar kaldi, kapi yine reddeder"


def test_ALINTISIZ_sahne_onarilmiyor():
    """⚠️ Alintisi olmayan sahnede terim TEK gorsel kaynagi; orada sert kapi
    durmali, yoksa kapatilan kusur (ayni sirali sonuc) geri acilir."""
    plan = _plan(
        [
            ("Herculaneum forum", "Herculaneum forum arch.jpg"),
            ("Herculaneum forum", ""),
        ]
    )

    assert ya.arama_terimlerini_tekillestir(plan) == 0
    assert plan.scenes[1]["search_term"] == "Herculaneum forum"


def test_TEKIL_terimler_bozulmuyor():
    plan = _plan(
        [
            ("Herculaneum boat chambers", "a.jpg"),
            ("Herculaneum papyrus scroll", "b.jpg"),
        ]
    )
    onceki = [s["search_term"] for s in plan.scenes]

    assert ya.arama_terimlerini_tekillestir(plan) == 0
    assert [s["search_term"] for s in plan.scenes] == onceki


def test_dosya_yeni_kelime_vermiyorsa_DOKUNULMUYOR():
    """Ayirt edilemiyorsa sert kapiya birakiliyor — uydurma yapilmiyor."""
    plan = _plan(
        [
            ("Herculaneum forum", "Herculaneum forum.jpg"),
            ("Herculaneum forum", "forum Herculaneum.jpg"),
        ]
    )

    assert ya.arama_terimlerini_tekillestir(plan) == 0


def test_SHORTS_kipinde_onarim_CALISMIYOR():
    """⚠️ Shorts'ta kapi olculerek kondu ve sert kalmali (2026-08-13:
    8 sahnenin 8'i de "Mehmed II" terimini tasiyordu)."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index(
        "arama_terimlerini_tekillestir(plan)",
        kaynak.index("def generate_content_plan("),
    )
    onceki = kaynak[i - 200 : i]

    assert "bicim.kare_yuvasi == 1" in onceki


def test_hata_mesaji_SON_KUSURU_tasiyor():
    """⚠️ Eski mesaj her zaman "konu yeterince farkli degil" diyordu; konu
    disaridan sabitlenmisken bu olgusal olarak yanlis ve teshisi yanlis yone
    gonderiyor. 9,6 dakikalik bir koşum tam bu yuzden korlemesine incelendi.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "son kusur:" in kaynak
    assert "son_kusur = str(exc)" in kaynak
