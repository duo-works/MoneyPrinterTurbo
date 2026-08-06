"""Gorsel cesitliligi — arsiv fotograflari korunur, tek estetige sabitlenmez.

Ayri dosya: bu is kendi sozlesmesine sahip. Testler ag'a cikmaz; indirme ve
AI uretimi yamalanir.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402
import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__)


def _plan(sahne_sayisi: int = 8) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Colosseum",
        visual_anchor="Colosseum",
        title="t",
        script="s",
        scenes=[
            {"narration": f"Scene {i}", "search_term": f"Colosseum detail {i}"}
            for i in range(1, sahne_sayisi + 1)
        ],
        description="d",
        tags=[],
    )


# --- Gorsel dil ----------------------------------------------------------


def test_tek_estetige_sabitlenmiyor():
    """Olculdu: "archival-documentary" her sahneyi sepya yapiyordu.

    Ton cesitliligi 0,08'den 0,17'ye cikti (ayni sahne, iki prompt).
    """
    assert "archival-documentary aesthetic" not in KAYNAK.read_text(encoding="utf-8")


def test_gorsel_dil_uc_yolu_da_tarif_ediyor():
    dil = ya.GORSEL_DIL

    assert "survives today" in dil, "ayakta duran sey gercek fotograf olmali"
    assert "colour photograph" in dil
    assert "historical painting" in dil, "gecmisteki olay renkli resim olmali"
    assert "sepia" in dil, "sepya yalnizca gercekten arsivlik olana"


def test_sahneler_arasi_cesitlilik_isteniyor():
    """Ardisik iki kare birbirine benzememeli."""
    assert "do not look like one another" in ya.GORSEL_DIL


def test_gorsel_kalitesi_yuksek():
    """Shorts tam ekran izleniyor; `medium` doku ve kenar netligini kaybettiriyor."""
    kaynak = KAYNAK.read_text(encoding="utf-8")
    i = kaynak.index('"size": "1024x1536"')

    assert '"quality": "high"' in kaynak[i : i + 400]


# --- Kismi arsiv ---------------------------------------------------------


def test_tek_eksik_sahne_butun_arsivi_atmiyor(tmp_path, monkeypatch):
    """DW-97'nin kapattigi asil kusur.

    8 sahnenin 7'sinde gercek arsiv fotografi bulunmus olsa bile, 8'inci
    bulunamayinca hepsi cope gidiyor ve butun video AI ile uretiliyordu.
    Olculdu: 96 AI gorselin 76'si tam da bu yoldan geldi.
    """
    dosyalar = [tmp_path / f"s{i}.jpg" for i in range(1, 8)] + [None]
    for d in dosyalar[:-1]:
        d.write_bytes(b"x")

    uretilen_sahneler = []

    def sahte_ai(_plan, hedef, scene_numbers=None, **_k):
        uretilen_sahneler.extend(scene_numbers or [])
        yollar = []
        for n in scene_numbers or []:
            p = tmp_path / f"ai-{n}.png"
            p.write_bytes(b"y")
            yollar.append(p)
        return yollar

    monkeypatch.setattr(ya, "_generate_ai_or_reject", sahte_ai)

    sonuc = ya._delikleri_doldur(_plan(8), dosyalar, tmp_path)

    assert uretilen_sahneler == [8], "yalnizca eksik sahne AI ile uretilmeli"
    assert len(sonuc) == 8
    assert sonuc[0].name == "s1.jpg", "bulunan arsiv gorselleri korunmali"
    assert sonuc[7].name == "ai-8.png"


def test_hicbir_delik_yoksa_ai_hic_cagrilmiyor(tmp_path, monkeypatch):
    dosyalar = [tmp_path / f"s{i}.jpg" for i in range(1, 4)]
    for d in dosyalar:
        d.write_bytes(b"x")

    def patla(*_a, **_k):
        raise AssertionError("delik yokken AI cagrilmamali")

    monkeypatch.setattr(ya, "_generate_ai_or_reject", patla)

    assert ya._delikleri_doldur(_plan(3), dosyalar, tmp_path) == dosyalar


def test_kismi_kip_kapaliysa_eski_davranis_suruyor(tmp_path, monkeypatch):
    """AI yedegi yokken delikli video yapilamaz — sert hata dogru davranis."""
    monkeypatch.setattr(wm, "search_commons", lambda *_a, **_k: [])
    monkeypatch.setattr(wm, "download_met_scene_material", lambda *_a, **_k: None)

    with pytest.raises(wm.MaterialsUnavailableError, match="scene 1"):
        wm.download_scene_materials(
            "Colosseum",
            [{"search_term": "Colosseum arch"}],
            tmp_path,
            kismi=False,
        )


def test_kismi_kipte_hicbiri_bulunamazsa_yine_hata(tmp_path, monkeypatch):
    """Bos bir arsiv sonucu, "kismi" degil tam basarisizliktir."""
    monkeypatch.setattr(wm, "search_commons", lambda *_a, **_k: [])
    monkeypatch.setattr(wm, "download_met_scene_material", lambda *_a, **_k: None)

    with pytest.raises(wm.MaterialsUnavailableError, match="any of the"):
        wm.download_scene_materials(
            "Colosseum",
            [{"search_term": f"Colosseum {i}"} for i in range(3)],
            tmp_path,
            kismi=True,
        )


def test_kismi_kip_hatta_baglanmis():
    """Baglanti testi — `_delikleri_doldur` tek basina dogru olsa bile
    `run_generator` onu cagirmazsa kusur geri gelir.

    Mutasyonla bulundu: `kismi=AI_VISUAL_FALLBACK_ENABLED` yerine
    `kismi=False` yazildiginda izole testlerin hicbiri dusmuyordu.
    """
    kaynak = KAYNAK.read_text(encoding="utf-8")
    i = kaynak.index("def run_generator(")
    govde = kaynak[i : i + 2500]

    assert "kismi=AI_VISUAL_FALLBACK_ENABLED" in govde, "kismi kip hatta bagli olmali"
    assert "_delikleri_doldur(" in govde, "delikler doldurulmali"
