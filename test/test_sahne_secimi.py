"""Yeniden uretilecek sahnelerin secimi — inceleme ciktisi celisebilir.

Ayri dosya, cunku `test_youtube_automation.py` Windows'a ozgu yollar kullaniyor
(`WindowsPath`) ve macOS'ta toplanamiyor. Buradaki testler platformdan bagimsiz:
saf fonksiyon, ag yok, dosya sistemi yok.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from youtube_automation import QualityReview, sorunlu_sahneler  # noqa: E402


def test_celiskili_ciktida_iki_kume_birlestiriliyor():
    """Olculdu (2026-08-05, "The Marvel of Sigiriya").

    `issues` metni 6 ve 7. sahneleri isaret ederken `problem_scene_numbers`
    [3, 4] dondu. Hat bildirilen listeye guvendi, YANLIS sahneleri yeniden
    uretti; gercekten bozuk olanlara dokunulmadi. Skor 45'te kaldi (esik 50),
    konu reddedildi ve o ana kadar harcanan LLM/gorsel parasi bosa gitti.
    """
    review = QualityReview(
        publishable=False,
        visual_alignment_score=45,
        subtitle_readability_score=100,
        issues=[
            "Scene 6 does not accurately represent the water gardens.",
            "Scene 7 does not depict the royal palace ruins.",
        ],
        revised_search_terms=[],
        problem_scene_numbers=[3, 4],
    )

    assert sorunlu_sahneler(review, 8) == [3, 4, 6, 7]


def test_tutarli_ciktida_davranis_degismiyor():
    """Ayni kosumdaki "Persepolis" tutarliydi — genisletme yalnizca celiskide."""
    review = QualityReview(
        publishable=False,
        visual_alignment_score=45,
        subtitle_readability_score=100,
        issues=[f"Scene {n} is weak." for n in (1, 2, 3)],
        revised_search_terms=[],
        problem_scene_numbers=[1, 2, 3],
    )

    assert sorunlu_sahneler(review, 5) == [1, 2, 3]


def test_hicbir_sahne_isaretlenmemisse_hepsi_doner():
    """Onceki davranis korunuyor."""
    review = QualityReview(False, 40, 100, ["Materials are generic."], [], [])

    assert sorunlu_sahneler(review, 4) == [1, 2, 3, 4]


def test_aralik_disi_numara_atiliyor():
    """LLM var olmayan sahne verirse indeks hatasi olusmamali."""
    review = QualityReview(
        publishable=False,
        visual_alignment_score=45,
        subtitle_readability_score=100,
        issues=["Scene 99 is wrong."],
        revised_search_terms=[],
        problem_scene_numbers=[2, 40],
    )

    assert sorunlu_sahneler(review, 5) == [2]
