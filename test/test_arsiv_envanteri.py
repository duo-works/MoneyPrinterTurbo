"""Plan istemine ARSIV MENUSU veriliyor — model neyi gosterebilecegini bilmeli.

⚠️ Olculdu (2026-08-13, Murad III). Sahne terimlerinin farkli olmasi zorunlu
kilininca (62c4d05) portre yigini bitti ama YENI bir kusur cikti: model bu
kez arsivde OLMAYAN seyler istedi — "Murad III Ottoman map", "Murad III
coin", "Murad III mausoleum". Arsivde harita da sikke de turbe de yoktu;
arama havuzdaki minyaturu dondurdu ve hakem "harita istedin, minyatur geldi"
diyerek skoru 38/67/33'e indirdi.

⚠️ Ikinci olcum (2026-08-14): envanter DOSYA ADI olarak verildiginde kusur
surdu. Sebep, adlarin cogunun hicbir sey soylememesi — Borobudur
kategorisinin ilki `20190415 151806b.jpg`, `500px photo (50204564).jpeg`,
`Ujung.jpg`. Ayni dosyalarin Commons aciklamasi ise kullanilabilir bilgi
tasiyor ("The clipper CUTTY SARK re-conditioned at anchor at Falmouth",
1922 sonrasi). Menu artik ACIKLAMA ve TARIH tasiyor; kapisi
`test_arsiv_alintisi.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402
import wikimedia_materials as wm  # noqa: E402


def _aday(baslik: str, aciklama: str = "", tarih: str = "") -> dict:
    return {"title": baslik, "aciklama": aciklama, "tarih": tarih}


def test_menu_dosya_aciklama_ve_tarih_tasiyor(monkeypatch):
    monkeypatch.setattr(
        wm,
        "arsiv_menusu",
        lambda _k, **_kw: [
            _aday("File:Tughra of Murad III.JPG", "Imperial monogram", "1593"),
            _aday("File:Berat 1593.jpg", "Decree on paper", "1593"),
        ],
    )

    assert ya.arsiv_envanteri("Murad III") == [
        {
            "dosya": "Tughra of Murad III.JPG",
            "gosterdigi": "Imperial monogram",
            "tarih": "1593",
        },
        {"dosya": "Berat 1593.jpg", "gosterdigi": "Decree on paper", "tarih": "1593"},
    ]


def test_menu_yoksa_bos_donuyor(monkeypatch):
    """Menusu kurulamayan konuda uretim DURMAMALI."""
    monkeypatch.setattr(wm, "arsiv_menusu", lambda _k, **_kw: [])

    assert ya.arsiv_envanteri("Bilinmeyen Konu") == []


def test_ag_hatasi_uretimi_durdurmuyor(monkeypatch):
    """⚠️ Menu bir IYILESTIRME; cekilemezse hat eskisi gibi calismali.

    Plan asamasindayiz, yani elde henuz hicbir sey yok: burada patlamak
    butun koşumu bir 429 yuzunden coplerdi.
    """

    def patla(_k, **_kw):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(wm, "arsiv_menusu", patla)

    assert ya.arsiv_envanteri("Murad III") == []


def test_aciklama_kirpiliyor(monkeypatch):
    """Istem sinirsiz buyumemeli: 40 girdi x uzun aciklama isteme sigmaz."""
    monkeypatch.setattr(
        wm, "arsiv_menusu", lambda _k, **_kw: [_aday("File:X.jpg", "a" * 500, "b" * 200)]
    )

    girdi = ya.arsiv_envanteri("X")[0]

    assert len(girdi["gosterdigi"]) == ya.ACIKLAMA_SINIRI
    assert len(girdi["tarih"]) == 40


def test_bos_baslik_atlaniyor(monkeypatch):
    monkeypatch.setattr(
        wm, "arsiv_menusu", lambda _k, **_kw: [_aday(""), _aday("File:Gercek.jpg"), {}]
    )

    assert [g["dosya"] for g in ya.arsiv_envanteri("X")] == ["Gercek.jpg"]


def test_menu_isteme_giriyor(monkeypatch):
    """⚠️ Baglanti testi — fonksiyon dogru olsa bile isteme girmezse kusur surer."""
    yakalanan: dict = {}

    def sahte_cikarim(system: str, user: str) -> dict:
        yakalanan["user"] = user
        raise RuntimeError("dur")

    monkeypatch.setattr(
        ya,
        "arsiv_envanteri",
        lambda _k: [
            {
                "dosya": "Tughra of Murad III.JPG",
                "gosterdigi": "Imperial monogram",
                "tarih": "1593",
            }
        ],
    )
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
    assert "ARCHIVE MENU" in istem
    assert "Tughra of Murad III.JPG" in istem
    assert "Imperial monogram" in istem
    # ⚠️ Asil talimat: once goruntuyu sec, sonra cumleyi yaz.
    assert "source_file" in istem


def test_menu_yoksa_istem_bozulmuyor(monkeypatch):
    """Menu bos donerse blok hic eklenmemeli, istem gecerli kalmali."""
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
    assert "ARCHIVE MENU" not in istem
    assert "AUTHORITATIVE SOURCE" in istem
