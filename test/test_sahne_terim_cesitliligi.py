"""Her sahnenin KENDI arama terimi olmali — aynisini tekrarlamak portre yigini uretiyor.

⚠️ Olculdu (2026-08-13). Uretilen planlarda 8 sahnenin 8'i de birebir ayni
terimi tasiyordu ("Mehmed II", "Murad III"). Ayni sorgu her sahnede ayni
sirali aday listesini getiriyor; `used_titles` yalnizca birebir tekrari
engelledigi icin sahne N listenin N'inci gorselini aliyor — hepsi ayni
havuzun tepesindeki portreler.

Hakem bunu her koşumda ayni cumleyle cezalandirdi ("static portraits",
"repeated portrait format") ve gorsel skor uc ayri Murad III koşumunda
76-78'de takildi (kapi 80). Arsivde tugra, berat, harita ve minyatur
dururken video alti portre oluyordu.

Istem cesitliligi ZATEN istiyordu ("Vary what the camera is actually on:
the person, their hands or possessions, the room, the wider place..."). DW-87
dersi: modele soylemek yetmiyor, KOD kontrol etmeli.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(*terimler: str) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Murad III",
        visual_anchor="Murad III",
        script=(
            "Murad III did not take the Ottoman throne quietly. In 1574 he reached "
            "Istanbul by boat at night and claimed the empire before dawn, while the "
            "old sultan's death was still being kept secret. He never left the capital "
            "again in twenty one years of rule, governing through letters and seals "
            "rather than campaigns, and the commanders he never met sent him reports "
            "from three continents. His tughra was pressed onto orders that reached "
            "Cairo, Buda and Baghdad. He died inside his palace in 1595, and the "
            "empire he never toured stretched further than he had ever seen with his "
            "own eyes."
        ),
        description="d",
        tags=["a", "b", "c"],
        title="Who Was Murad III? #Shorts",
        scenes=[
            {"narration": f"Sentence number {sira} of the narration.", "search_term": terim}
            for sira, terim in enumerate(terimler, 1)
        ],
    )


ALTI_FARKLI = (
    "Murad III portrait",
    "Murad III tughra",
    "Murad III imperial berat",
    "Murad III Topkapi palace",
    "Murad III Ottoman map",
    "Murad III court miniature",
)


def test_farkli_terimler_geciyor():
    ya.validate_content_plan(_plan(*ALTI_FARKLI))


def test_hepsi_ayni_terim_reddediliyor():
    """⚠️ Asil kusur: uretimde 8/8 sahne birebir ayniydi."""
    with pytest.raises(ValueError, match="repeat across scenes"):
        ya.validate_content_plan(_plan(*(["Murad III portrait"] * 6)))


def test_tek_bir_tekrar_bile_reddediliyor():
    terimler = list(ALTI_FARKLI)
    terimler[4] = terimler[1]

    with pytest.raises(ValueError, match="repeat across scenes"):
        ya.validate_content_plan(_plan(*terimler))


def test_kelime_sirasi_tekrari_gizlemiyor():
    """"tughra Murad III" ile "Murad III tughra" ayni sorgudur."""
    terimler = list(ALTI_FARKLI)
    terimler[4] = "tughra Murad III"

    with pytest.raises(ValueError, match="repeat across scenes"):
        ya.validate_content_plan(_plan(*terimler))


def test_yalnizca_capadan_ibaret_terim_reddediliyor():
    """⚠️ "Murad III" iki kelime ve capayi iceriyor — eski kapiyi geciyordu.

    Capayi TEKRARLAMAK yetmiyor, capaya bir sey EKLEMEK gerekiyor; yoksa
    arsiv her sahnede ayni portre havuzunu doner.
    """
    terimler = list(ALTI_FARKLI)
    terimler[3] = "Murad III"

    with pytest.raises(ValueError, match="only the visual anchor"):
        ya.validate_content_plan(_plan(*terimler))


def test_mesaj_ne_yapilacagini_soyluyor():
    """Dogrulama hatasi modele geri besleniyor; kural tekrari donguyu kirmiyor."""
    with pytest.raises(ValueError) as hata:
        ya.validate_content_plan(_plan(*(["Murad III portrait"] * 6)))

    mesaj = str(hata.value)
    assert "its OWN concrete" in mesaj
    assert "document" in mesaj


def test_capa_kurali_hala_geceli():
    """Cesitlilik kurali capa zorunlulugunu GEVSETMEMELI."""
    terimler = list(ALTI_FARKLI)
    terimler[2] = "Ottoman siege of Vienna"

    with pytest.raises(ValueError, match="visual anchor"):
        ya.validate_content_plan(_plan(*terimler))
