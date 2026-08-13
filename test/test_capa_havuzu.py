"""Editoryal capa havuzu — tukenmesi SESSIZ olmamali.

⚠️ Olculdu (2026-08-13): havuzdaki 15 capanin 15'i de kullanilmisti ve
`eligible_anchors` bos gidiyordu. Model bos listeyle ince arsivli
gizemlere kaydi (Baychimo, Vasa, Phaistos Diski, Piltdown) ve kaynak
kapisinda 25-43 aldi. Disaridan bakan biri "model kotu konu seciyor"
sanirdi; oysa hat ona secenek vermiyordu.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def test_havuz_tukenince_uyariliyor(monkeypatch, capsys):
    """⚠️ Testin konusu: fark edilebilirlik."""
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", ["Petra"])
    monkeypatch.setattr(
        ya, "load_state", lambda: {"published": [{"visual_anchor": "Petra"}], "rejected": []}
    )
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(
        ya, "_json_completion", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("dur"))
    )

    try:
        ya.generate_content_plan()
    except RuntimeError:
        pass

    assert "capa havuzu TUKENDI" in capsys.readouterr().out


def test_havuz_doluyken_uyari_yok(monkeypatch, capsys):
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", ["Petra", "Masada"])
    monkeypatch.setattr(
        ya, "load_state", lambda: {"published": [{"visual_anchor": "Petra"}], "rejected": []}
    )
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(
        ya, "_json_completion", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("dur"))
    )

    try:
        ya.generate_content_plan()
    except RuntimeError:
        pass

    assert "TUKENDI" not in capsys.readouterr().out


def test_huni_kipinde_uyari_yok(monkeypatch, capsys):
    """Konu disaridan geliyorsa capa havuzunun bosalmasi sorun degil."""
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", [])
    monkeypatch.setattr(ya, "load_state", lambda: {"published": [], "rejected": []})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "vikipedi_ozeti", lambda *_a, **_k: "", raising=False)
    monkeypatch.setattr(
        ya, "_json_completion", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("dur"))
    )

    try:
        ya.generate_content_plan(konu="Murad III")
    except RuntimeError:
        pass

    assert "TUKENDI" not in capsys.readouterr().out


def test_havuz_olculmus_capalar_tasiyor():
    """⚠️ Havuza tahminle ad eklenmemeli.

    2026-08-13'te eklenen 19 capanin hepsi uretimin kendi kapilariyla
    olculdu ve yalnizca 12+ kullanilabilir gorseli olanlar alindi. Ayni
    olcumde elenenler: Pompeii 0, Leptis Magna 0, Teotihuacan 2, Sutton
    Hoo 7 — sonuncusu bu hattin secip 25 aldigi konuydu.
    """
    havuz = ya.EDITORIAL_ANCHOR_POOL

    assert len(havuz) >= 30, "havuz tukenmeye cok yakin"
    assert len(set(havuz)) == len(havuz), "havuzda tekrar var"
    for elenen in ("Pompeii", "Leptis Magna", "Teotihuacan", "Sutton Hoo"):
        assert elenen not in havuz, f"{elenen} olcumde elendi, havuza girmemeli"
