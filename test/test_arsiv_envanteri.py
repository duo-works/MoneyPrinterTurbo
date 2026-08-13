"""Plan istemine ARSIV ENVANTERI veriliyor — model neyi gosterebilecegini bilmeli.

⚠️ Olculdu (2026-08-13, Murad III). Sahne terimlerinin farkli olmasi zorunlu
kilininca (62c4d05) portre yigini bitti ama YENI bir kusur cikti: model bu
kez arsivde OLMAYAN seyler istedi — "Murad III Ottoman map", "Murad III
coin", "Murad III mausoleum". Arsivde harita da sikke de turbe de yoktu;
arama havuzdaki minyaturu dondurdu ve hakem "harita istedin, minyatur geldi"
diyerek skoru 38/67/33'e indirdi (onceki koşum 78'di).

Kusur ozensizlik degil BILGISIZLIK: model konuyu yalnizca adiyla goruyor.
Kaynak metni (DW-114) modele NE ANLATACAGINI soyluyor; envanter NEYI
GOSTEREBILECEGINI. Ikisi ayri bilgi.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402
import wikimedia_materials as wm  # noqa: E402


def _sayfa(baslik: str) -> dict:
    return {"title": baslik}


def test_envanter_dosya_adlarini_donduruyor(monkeypatch):
    monkeypatch.setattr(wm, "commons_kategorisi", lambda _k: "Murad III")
    monkeypatch.setattr(
        wm,
        "kategori_gorselleri",
        lambda _k: [_sayfa("File:Tughra of Murad III.JPG"), _sayfa("File:Berat 1593.jpg")],
    )

    assert ya.arsiv_envanteri("Murad III") == [
        "Tughra of Murad III.JPG",
        "Berat 1593.jpg",
    ]


def test_kategori_yoksa_bos_donuyor(monkeypatch):
    """Kategorisi olmayan konuda uretim DURMAMALI."""
    monkeypatch.setattr(wm, "commons_kategorisi", lambda _k: None)

    assert ya.arsiv_envanteri("Bilinmeyen Konu") == []


def test_ag_hatasi_uretimi_durdurmuyor(monkeypatch):
    """⚠️ Envanter bir IYILESTIRME; cekilemezse hat eskisi gibi calismali.

    Plan asamasindayiz, yani elde henuz hicbir sey yok: burada patlamak
    butun koşumu bir 429 yuzunden coplerdi.
    """

    def patla(_k):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(wm, "commons_kategorisi", patla)

    assert ya.arsiv_envanteri("Murad III") == []


def test_liste_sinirlaniyor(monkeypatch):
    """Istem sinirsiz buyumemeli."""
    monkeypatch.setattr(wm, "commons_kategorisi", lambda _k: "X")
    monkeypatch.setattr(
        wm, "kategori_gorselleri", lambda _k: [_sayfa(f"File:{i}.jpg") for i in range(500)]
    )

    assert len(ya.arsiv_envanteri("X")) == ya.ARSIV_ENVANTER_SINIRI


def test_bos_baslik_atlaniyor(monkeypatch):
    monkeypatch.setattr(wm, "commons_kategorisi", lambda _k: "X")
    monkeypatch.setattr(
        wm,
        "kategori_gorselleri",
        lambda _k: [_sayfa(""), _sayfa("File:Gercek.jpg"), {}],
    )

    assert ya.arsiv_envanteri("X") == ["Gercek.jpg"]


def test_envanter_isteme_giriyor(monkeypatch):
    """⚠️ Baglanti testi — fonksiyon dogru olsa bile isteme girmezse kusur surer."""
    yakalanan: dict = {}

    def sahte_cikarim(system: str, user: str) -> dict:
        yakalanan["user"] = user
        raise RuntimeError("dur")

    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: ["Tughra of Murad III.JPG"])
    monkeypatch.setattr(wm, "vikipedi_ozeti", lambda *_a, **_k: "Murad III was a sultan.")
    monkeypatch.setattr(ya, "_json_completion", sahte_cikarim)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])

    try:
        ya.generate_content_plan(konu="Murad III")
    except Exception:
        pass

    istem = yakalanan.get("user", "")
    assert "ARCHIVE INVENTORY" in istem
    assert "Tughra of Murad III.JPG" in istem


def test_envanter_yoksa_istem_bozulmuyor(monkeypatch):
    """Envanter bos donerse blok hic eklenmemeli, istem gecerli kalmali."""
    yakalanan: dict = {}

    def sahte_cikarim(system: str, user: str) -> dict:
        yakalanan["user"] = user
        raise RuntimeError("dur")

    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: [])
    monkeypatch.setattr(wm, "vikipedi_ozeti", lambda *_a, **_k: "Murad III was a sultan.")
    monkeypatch.setattr(ya, "_json_completion", sahte_cikarim)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])

    try:
        ya.generate_content_plan(konu="Murad III")
    except Exception:
        pass

    istem = yakalanan.get("user", "")
    assert "ARCHIVE INVENTORY" not in istem
    assert "AUTHORITATIVE SOURCE" in istem
