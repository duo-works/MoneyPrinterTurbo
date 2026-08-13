"""Sahneler arsivde OLMAYAN seyi isteyemez — istem yetmedi, kod kontrol ediyor.

⚠️ Olculdu (2026-08-13, yedek kip koşumu). Envanter isteme zaten veriliyordu
(572dc2b) ve model yine olmayan seyi istedi:

    Franklin seferi  → sahne 1 Franklin istedi, arsivden CROZIER geldi;
                       sahne 4 ve 5'e MODERN tibbi cadir fotografi girdi
    Antikythera      → sahne 4 "arkeolog Valerios Stais" istedi, yok
    skorlar: 43 / 30 / 25

Ayni ders bu oturumda dorduncu kez: modele soylemek yetmiyor (DW-87).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

ENVANTER = [
    "Tughra of Murad III.JPG",
    "Berat of Sultan Murad III 1593.jpg",
    "Sultan Murad III portrait.jpg",
    "Surname-i huemayun procession.jpg",
]


def _plan(*terimler: str) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Murad III",
        visual_anchor="Murad III",
        script=" ".join(["word"] * 100),
        description="d",
        tags=["a", "b", "c"],
        title="t",
        scenes=[
            {"narration": f"Sentence {sira}.", "search_term": terim}
            for sira, terim in enumerate(terimler, 1)
        ],
    )


def _envanter(monkeypatch, adlar: list[str]):
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: adlar)


def test_arsivde_olan_seyler_geciyor(monkeypatch):
    _envanter(monkeypatch, ENVANTER)
    plan = _plan(
        "Murad III tughra",
        "Murad III berat",
        "Murad III portrait",
        "Murad III procession",
    )

    assert ya.arsiv_destegi_kusuru(plan) == ""


def test_arsivde_olmayan_cogunluk_reddediliyor(monkeypatch):
    """⚠️ Gercek vaka: sahneler arsivde bulunmayan seyleri istiyordu."""
    _envanter(monkeypatch, ENVANTER)
    plan = _plan(
        "Murad III mausoleum",
        "Murad III silver coin",
        "Murad III naval battle",
        "Murad III tughra",
    )

    kusur = ya.arsiv_destegi_kusuru(plan)

    assert kusur != ""
    assert "[1, 2, 3]" in kusur


def test_mesaj_envanteri_tasiyor(monkeypatch):
    """Dogrulama hatasi modele geri besleniyor; liste olmadan duzeltemez."""
    _envanter(monkeypatch, ENVANTER)
    plan = _plan("Murad III coin", "Murad III statue", "Murad III bridge")

    kusur = ya.arsiv_destegi_kusuru(plan)

    assert "Tughra of Murad III.JPG" in kusur
    assert "rewrite those scenes" in kusur


def test_az_sayida_desteksiz_sahne_tolere_ediliyor(monkeypatch):
    """⚠️ Olcut kasten gevsek: arsiv her seyi adiyla anmiyor.

    Asiri sertlik bes denemeyi tuketip kosumu `DistinctTopicUnavailableError`
    ile oldururdu — yani hic video olmamasi demek.
    """
    _envanter(monkeypatch, ENVANTER)
    plan = _plan(
        "Murad III tughra",
        "Murad III berat",
        "Murad III portrait",
        "Murad III mausoleum",
    )

    assert ya.arsiv_destegi_kusuru(plan) == ""


def test_envanter_yoksa_kapi_kapali(monkeypatch):
    """Envanter cekilemezse bu bir KAPI degil; uretim durmamali."""
    _envanter(monkeypatch, [])
    plan = _plan("Murad III mausoleum", "Murad III coin", "Murad III battle")

    assert ya.arsiv_destegi_kusuru(plan) == ""


def test_yalnizca_capadan_ibaret_terim_desteksiz_sayilmiyor(monkeypatch):
    """Capa disi kelimesi olmayan terim bu kapinin konusu degil.

    Onu `validate_content_plan` zaten reddediyor; burada iki kez
    cezalandirmak mesaji yaniltirdi.
    """
    _envanter(monkeypatch, ENVANTER)
    plan = _plan("Murad III", "Murad III", "Murad III tughra")

    assert ya.arsiv_destegi_kusuru(plan) == ""


def test_kapi_plan_donguSUNE_bagli():
    """Baglanti testi — fonksiyon dogru olsa bile cagrilmazsa kusur surer."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def generate_content_plan(")
    govde = kaynak[i : kaynak.index("def refine_search_terms(", i)]

    assert "arsiv_destegi_kusuru(plan)" in govde


def test_envanter_onbellekleniyor(monkeypatch):
    """Bes deneme boyunca ayni kategori tekrar tekrar cekilmemeli."""
    ya._ENVANTER_ONBELLEGI.clear()
    cagri = []

    monkeypatch.setattr(ya.wikimedia_materials, "commons_kategorisi", lambda _k: "Kat")

    def sahte_havuz(_kategori):
        cagri.append(1)
        return [{"title": "File:Tughra of Murad III.JPG"}]

    monkeypatch.setattr(ya.wikimedia_materials, "kategori_gorselleri", sahte_havuz)

    ya.arsiv_envanteri("Murad III")
    ya.arsiv_envanteri("Murad III")

    assert len(cagri) == 1
