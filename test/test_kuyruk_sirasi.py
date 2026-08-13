"""Kuyruk sirasi: kisi-olmayan aday one, kisi adayi sona.

⚠️ Olculdu (2026-08-13), yayinlanan 12 videonun kaydi:

    anit / yer / nesne   skor 70-90, hakem kusuru  0-3
    kisi biyografisi     skor 68-84, hakem kusuru 9-11

ELEME DEGIL SIRALAMA: kisi adayi kuyrukta kaliyor. Mehmed II bir kisi
konusuydu ve 84 aldi — sinif kesin kural degil, egilim.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notion_kuyrugu as nk  # noqa: E402


def _aday(baslik: str) -> nk.Aday:
    return nk.Aday(
        kimlik=baslik.lower().replace(" ", "-"),
        baslik=baslik,
        sayfa_url=f"https://notion/{baslik}",
        onerilen_format=None,
        dil="en",
        bosluk_skoru=None,
        talep=None,
    )


def _siniflar(monkeypatch, esleme: dict[str, bool | None]):
    monkeypatch.setattr(nk.wikimedia_materials, "kisi_mi", lambda k: esleme.get(k))


def test_kisi_olmayan_one_aliniyor(monkeypatch):
    _siniflar(monkeypatch, {"Murad III": True, "Colosseum": False})

    sira = nk.sinifa_gore_sirala([_aday("Murad III"), _aday("Colosseum")])

    assert [a.baslik for a in sira] == ["Colosseum", "Murad III"]


def test_bilinmeyen_ortada(monkeypatch):
    """"Bilmiyorum" ne odul ne ceza almali."""
    _siniflar(monkeypatch, {"Kisi": True, "Yer": False, "Bilinmeyen": None})

    sira = nk.sinifa_gore_sirala([_aday("Kisi"), _aday("Bilinmeyen"), _aday("Yer")])

    assert [a.baslik for a in sira] == ["Yer", "Bilinmeyen", "Kisi"]


def test_grup_icinde_huni_sirasi_korunuyor(monkeypatch):
    """Bosluk skoruna gore gelen sira grup icinde bozulmamali."""
    _siniflar(monkeypatch, {"Yer A": False, "Yer B": False, "Yer C": False})

    sira = nk.sinifa_gore_sirala([_aday("Yer A"), _aday("Yer B"), _aday("Yer C")])

    assert [a.baslik for a in sira] == ["Yer A", "Yer B", "Yer C"]


def test_kisi_adayi_ELENMIYOR(monkeypatch):
    """⚠️ Bu testin konusu: sadece kisi adayi varsa kuyruk BOSALMAMALI."""
    _siniflar(monkeypatch, {"Murad III": True, "Talaat Pasha": True})

    sira = nk.sinifa_gore_sirala([_aday("Murad III"), _aday("Talaat Pasha")])

    assert len(sira) == 2, "kisi adaylari kuyrukta kalmali, elenmemeli"


def test_siniflandirma_patlarsa_kuyruk_okunmaya_devam(monkeypatch):
    """⚠️ Siniflandirma bir IYILESTIRME; kuyruk okumayi dusuremez."""

    def patla(_k):
        raise RuntimeError("Wikidata kopuk")

    monkeypatch.setattr(nk.wikimedia_materials, "kisi_mi", patla)

    sira = nk.sinifa_gore_sirala([_aday("A"), _aday("B")])

    assert [a.baslik for a in sira] == ["A", "B"]


def test_kuyrugu_oku_siralamayi_uyguluyor(monkeypatch):
    """Baglanti testi — fonksiyon dogru olsa bile cagrilmazsa kusur surer."""
    import json
    import subprocess

    kayitlar = [
        {"kimlik": "1", "baslik": "Murad III", "sayfa_url": "u1"},
        {"kimlik": "2", "baslik": "Colosseum", "sayfa_url": "u2"},
    ]
    monkeypatch.setattr(
        nk,
        "_kos",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, json.dumps(kayitlar), ""),
    )
    _siniflar(monkeypatch, {"Murad III": True, "Colosseum": False})

    adaylar = nk.kuyrugu_oku(ytoto_path="ytoto")

    assert [a.baslik for a in adaylar] == ["Colosseum", "Murad III"]
