"""Uretim raporu — "standarda sabitledik" diyebilmek icin once olcmek gerek.

⚠️ Olculdu (2026-08-13): kayitlar bu soruyu cevaplayamiyordu. 120 red
kaydinin hicbiri zaman dilimi tasimiyordu, iki asamanin skorlari
ayrismiyordu, hangi kipin urettigi yazilmiyordu. Rapor o eksikleri
gorunur kiliyor ve ileride arayuz bu JSON'u okuyacak.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uretim_rapor  # noqa: E402


def _durum(monkeypatch, tmp_path: Path, govde: dict) -> None:
    yol = tmp_path / "state.json"
    yol.write_text(json.dumps(govde), encoding="utf-8")
    monkeypatch.setattr(uretim_rapor, "STATE_FILE", yol)


ORNEK = {
    "published": [
        {
            "slot": "2026-08-13-15",
            "kaynak": "huni",
            "visual_anchor": "Mehmed II",
            "url": "https://y/1",
            "quality": {"visual_alignment_score": 84, "issues": ["a", "b"]},
        },
        {
            "slot": "2026-08-13-21",
            "kaynak": "yedek",
            "visual_anchor": "Sutton Hoo",
            "url": "https://y/2",
            "quality": {"visual_alignment_score": 90, "issues": []},
        },
    ],
    "rejected": [
        {
            "slot": "2026-08-13-16",
            "kaynak": "huni",
            "stage": "source_materials",
            "visual_alignment_score": 40,
            "agir_kusurlar": ["kare 2: anlatilan kisi degil"],
        },
        {
            "slot": "2026-08-13-17",
            "kaynak": "huni",
            "stage": "video",
            "visual_alignment_score": 60,
            "agir_kusurlar": ["kare 1: anlatilan kisi degil", "kare 3: modern goruntu"],
        },
    ],
}


def test_basari_orani_hesaplaniyor(monkeypatch, tmp_path):
    _durum(monkeypatch, tmp_path, ORNEK)

    veri = uretim_rapor.rapor()

    assert veri["toplam_kosum"] == 4
    assert veri["yayinlanan"] == 2
    assert veri["basari_orani"] == 0.5


def test_asama_kirilimi(monkeypatch, tmp_path):
    """Redlerin cogu render'dan ONCE mi dusuyor — maliyet sorusu."""
    _durum(monkeypatch, tmp_path, ORNEK)

    assert uretim_rapor.rapor()["asama_kirilimi"] == {"source_materials": 1, "video": 1}


def test_kaynak_kirilimi(monkeypatch, tmp_path):
    """Huni mi yedek mi uretti — yedek hattinin ise yarayip yaramadigi buradan."""
    _durum(monkeypatch, tmp_path, ORNEK)

    assert uretim_rapor.rapor()["kaynak_kirilimi"] == {"huni": 1, "yedek": 1}


def test_agir_kusurlar_sayiliyor(monkeypatch, tmp_path):
    """Kare numarasi atilip TUR sayiliyor; "kare 2" ile "kare 3" ayni kusur."""
    _durum(monkeypatch, tmp_path, ORNEK)

    kusurlar = dict(uretim_rapor.rapor()["en_sik_agir_kusur"])

    assert kusurlar["anlatilan kisi degil"] == 2
    assert kusurlar["modern goruntu"] == 1


def test_iki_ayri_skor_yeri_de_okunuyor(monkeypatch, tmp_path):
    """⚠️ Yayin kaydinda skor `quality` altinda, red kaydinda UST DUZEYDE.

    Tek yere bakan bir rapor yayinlari ya da redleri sessizce "skorsuz"
    sayardi.
    """
    _durum(monkeypatch, tmp_path, ORNEK)
    veri = uretim_rapor.rapor()

    assert veri["yayin_skoru"]["ortanca"] == 87
    assert veri["red_skoru_ortanca"] == 50


def test_bos_durum_patlamiyor(monkeypatch, tmp_path):
    _durum(monkeypatch, tmp_path, {"published": [], "rejected": []})

    veri = uretim_rapor.rapor()

    assert veri["toplam_kosum"] == 0
    assert veri["basari_orani"] == 0.0
    assert veri["yayin_skoru"]["ortanca"] is None


def test_dosya_yoksa_patlamiyor(monkeypatch, tmp_path):
    monkeypatch.setattr(uretim_rapor, "STATE_FILE", tmp_path / "yok.json")

    assert uretim_rapor.rapor()["toplam_kosum"] == 0


def test_json_ciktisi_arayuzun_alanlarini_tasiyor(monkeypatch, tmp_path):
    """Arayuz bu JSON'u okuyacak; alan adlari sozlesme."""
    _durum(monkeypatch, tmp_path, ORNEK)

    veri = uretim_rapor.rapor()

    for alan in (
        "toplam_kosum", "yayinlanan", "reddedilen", "basari_orani",
        "asama_kirilimi", "kaynak_kirilimi", "yayin_skoru",
        "en_sik_agir_kusur", "son_yayinlar",
    ):
        assert alan in veri, f"arayuz alani eksik: {alan}"
    assert json.dumps(veri)  # serilestirilebilir olmali
