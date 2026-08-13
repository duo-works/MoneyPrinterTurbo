"""Gercek hakem ciktilariyla gerileme koruması — kapilar sessizce gevsemesin.

Girdiler UYDURMA DEGIL: hepsi `storage/youtube_automation/state.json`'dan,
gercek koşumlardan alindi (2026-08-06 → 2026-08-13). Test, BUGUNKU standardin
o girdilerde ne karar verdigini kilitliyor.

⚠️ Bazi kayitlar YAYINLANMIS ama bugun gecmezdi (Treaty of Breda 68, Götz
72). Bu bir gerileme degil, standardin BILEREK yukseltilmesi: o videolar
esik 50 iken yayinlandi, esik olculmus veriye dayanarak 80'e cikarildi
(68-78 alanlarda 9-11 kusur vardi, 85-90 alanlarda 0). Test bunu kayit
altina aliyor ki ileride "eskiden geciyordu" diye geri indirilmesin.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from youtube_automation import (  # noqa: E402
    MIN_SOURCE_VISUAL_SCORE,
    MIN_VISUAL_SCORE,
    QualityReview,
    agir_kusurlari_ayikla,
    should_publish,
)

# (capa, gorsel, altyazi, bugun_gecer_mi, not)
GERCEK_KAYITLAR = [
    ("The Viking Longship", 90, 85, True, "anit/nesne konusu, 0 kusur"),
    ("Colosseum", 85, 90, True, "anit konusu, 0 kusur"),
    ("Dholavira Water Reservoir", 85, 90, True, "anit konusu, 0 kusur"),
    ("Mehmed II", 84, 88, True, "kisi konusu ama skor yeterli"),
    ("Götz von Berlichingen", 72, 84, False, "esik 50 iken yayinlandi, bugun gecmez"),
    ("Karnak Temple", 70, 85, False, "esik 50 iken yayinlandi, bugun gecmez"),
    ("Treaty of Breda", 68, 89, False, "esik 50 iken yayinlandi, bugun gecmez"),
    ("Friedrich Hayek", 68, 90, False, "esik 50 iken yayinlandi, bugun gecmez"),
]


@pytest.mark.parametrize("capa,gorsel,altyazi,gecer,gerekce", GERCEK_KAYITLAR)
def test_gercek_kayitta_bugunku_karar(capa, gorsel, altyazi, gecer, gerekce):
    review = QualityReview(
        publishable=True,  # modelin bayragi bilerek yok sayiliyor
        visual_alignment_score=gorsel,
        subtitle_readability_score=altyazi,
    )

    assert should_publish(review) is gecer, f"{capa}: {gerekce}"


# Gercek reddedilmis koşumlar — kaynak kapisindaki skorlar.
GERCEK_REDLER = [
    ("Talaat Pasha", 63),
    ("Murad III", 50),
    ("Ibn Saud", 31),
    ("Franklin expedition", 25),
    ("Piltdown Man", 30),
    ("Sutton Hoo", 25),
    ("Antikythera Mechanism", 43),
]


@pytest.mark.parametrize("konu,skor", GERCEK_REDLER)
def test_reddedilmis_kaynaklar_hala_reddediliyor(konu, skor):
    """Kaynak on-kapisi bu koşumlari gecirmemeli — hicbiri 70'i gecmiyor."""
    assert skor < MIN_SOURCE_VISUAL_SCORE, f"{konu} kaynak kapisini gecmemeliydi"


def test_kaynak_kapisi_video_kapisindan_gevsek_KALMALI():
    """Ikisi esitlenirse kisi konulari render'a hic ulasamaz (olculdu 2026-08-13)."""
    assert MIN_SOURCE_VISUAL_SCORE < MIN_VISUAL_SCORE


# Gercek hakem cevabindan alinan kare olgulari.
def test_gercek_yanlis_kisi_kaydi_agir_kusur_uretiyor():
    """Franklin koşumu: sahne 1'de Franklin istendi, CROZIER geldi.

    ⚠️ Bu vaka, kapinin GEVSETILMEMESI gerektiginin kaniti: baska bir
    tanimlanabilir kisi gelmesi "secilemiyor" degil, YANLIS. Sahne 4'e de
    MODERN TIBBI CADIR fotografi girmisti — konuyla ilgisiz modern goruntu,
    gercek nesnenin bugunku fotografi degil (ayrimin gerekcesi
    `agir_kusurlari_ayikla` icinde).
    """
    kareler = [
        {"n": 1, "person": "wrong", "period": "correct", "modern": False},
        {
            "n": 4,
            "person": "none",
            "period": "wrong",
            "modern": True,
            "authentic_subject": False,
        },
    ]

    kusurlar = agir_kusurlari_ayikla(kareler)

    assert "kare 1: anlatilan kisi degil" in kusurlar
    assert "kare 4: konuyla ilgisiz modern goruntu" in kusurlar


def test_yuksek_skorlu_video_agir_kusurla_dusuyor():
    """⚠️ Standardin ozu: 90 alan bir video yanlis kisi gosteriyorsa gecmez."""
    review = QualityReview(
        publishable=True,
        visual_alignment_score=90,
        subtitle_readability_score=95,
        agir_kusurlar=["kare 1: anlatilan kisi degil"],
    )

    assert should_publish(review) is False
