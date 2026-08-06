"""Kalite kapisi — esigi KOD uygular, inceleyici model degil.

Ayri dosya, cunku `test_youtube_automation.py` Windows'a ozgu yollar kullaniyor
(`WindowsPath`) ve macOS'ta toplanamiyor. Buradaki testler platformdan bagimsiz.

Arka plan (DW-87): prompt gecme esigini soyledigi surece model olcmeyi birakip
esigin bir tik altina oy yaziyordu. Ayni kagit, ayni model, ayni sicaklik:
esik anilinca 45/45/45, anilmayinca 75/75/70. Asagidaki iki metin testi o
cumlenin geri sizmasini engelliyor.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402
from youtube_automation import (  # noqa: E402
    MIN_SUBTITLE_SCORE,
    MIN_VISUAL_SCORE,
    QualityReview,
    should_abandon_topic,
    should_publish,
    yayina_uygun,
)

KAYNAK = Path(__file__).resolve().parent.parent / "youtube_automation.py"


def _yonerge(fonksiyon_adi: str) -> str:
    """Bir inceleme fonksiyonunun prompt metnini kaynaktan cikarir."""
    kaynak = KAYNAK.read_text(encoding="utf-8")
    basla = kaynak.index(f"def {fonksiyon_adi}(")
    bit = kaynak.index("_vision_json(prompt", basla)
    return kaynak[basla:bit]


def test_kaynak_incelemesi_promptu_esigi_soylemiyor():
    """Kapiyi acan sayiyi kapinin kendisi yazmamali."""
    yonerge = _yonerge("review_source_materials")

    assert "at least 50" not in yonerge
    assert "below 50" not in yonerge
    assert "publishable" not in yonerge


def test_video_incelemesi_promptu_esigi_soylemiyor():
    """Ayni kusur ikinci kapida da vardi (50 ve 80 promptta yaziliydi)."""
    yonerge = _yonerge("review_video")

    assert "at least 50" not in yonerge
    assert "at least 80" not in yonerge
    assert "below 50" not in yonerge
    assert "publishable" not in yonerge


def test_esik_sabitlerden_geliyor_elle_yazilmiyor():
    """`should_abandon_topic` eskiden `< 50` yaziyordu; sabitten kopuktu."""
    kaynak = KAYNAK.read_text(encoding="utf-8")
    govde = kaynak[
        kaynak.index("def should_abandon_topic(") : kaynak.index(
            "def publication_slot_key("
        )
    ]

    assert "MIN_VISUAL_SCORE" in govde
    assert not re.search(r"<\s*50\b", govde)


def test_iki_skor_da_esigi_gecerse_uygun():
    assert yayina_uygun(MIN_VISUAL_SCORE, MIN_SUBTITLE_SCORE) is True


def test_gorsel_skor_esigin_altindaysa_uygun_degil():
    assert yayina_uygun(MIN_VISUAL_SCORE - 1, 100) is False


def test_altyazi_skoru_esigin_altindaysa_uygun_degil():
    assert yayina_uygun(100, MIN_SUBTITLE_SCORE - 1) is False


def test_yayin_karari_modelin_bayragina_bakmiyor():
    """Model "publishable: true" dese bile dusuk skor gecmemeli.

    Bayrak artik kod tarafindan turetiliyor; yine de `should_publish` onu
    okumuyor ki ileride modelden gelen bir deger sessizce geri sizmasin.
    """
    yalanci = QualityReview(
        publishable=True,
        visual_alignment_score=10,
        subtitle_readability_score=100,
    )

    assert should_publish(yalanci) is False


def test_yuksek_skor_bayrak_false_olsa_da_geciyor():
    """Bunun tersi de gecerli — asil kusur buydu.

    Model 73 gibi gercek bir skor verip yine de "publishable: false" derse
    video yayindan dusmemeli; karar skorlarin.
    """
    kararsiz = QualityReview(
        publishable=False,
        visual_alignment_score=73,
        subtitle_readability_score=100,
    )

    assert should_publish(kararsiz) is True


def test_esigi_gecen_konu_terk_edilmiyor():
    olculen = QualityReview(True, 73, 100, ["Scene 3 is a little generic."], [], [3])

    assert should_abandon_topic(olculen) is False


def test_modern_goruntu_esik_gecse_de_konuyu_bitiriyor():
    """Onceki davranis korunuyor."""
    review = QualityReview(True, 90, 100, ["Contains modern footage of a car."], [])

    assert should_abandon_topic(review) is True


def test_kaynak_incelemesi_skoru_koddan_turetiyor(monkeypatch):
    """Model bayrak gondermese bile karar uretiliyor."""
    monkeypatch.setattr(
        ya,
        "_vision_json",
        lambda prompt, gorsel: {
            "visual_alignment_score": 73,
            "issues": ["Scene 3 is generic."],
            "revised_search_terms": ["Hadrian's Wall construction"],
            "problem_scene_numbers": [3],
        },
    )
    plan = ya.ContentPlan(
        topic="t",
        visual_anchor="a",
        script="s",
        description="d",
        tags=[],
        title="b",
        scenes=[{"narration": "n", "search_term": "s"} for _ in range(8)],
    )

    review = ya.review_source_materials(plan, Path("montaj.jpg"))

    assert review.visual_alignment_score == 73
    assert review.publishable is True
    assert review.problem_scene_numbers == [3]
