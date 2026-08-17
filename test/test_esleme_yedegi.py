"""Bant isteyen sahneye kategoriden ESLEME bulunuyor — bulanik bant azalsin.

⚠️ NEDEN — kanal sahibinin sesli notu (2026-08-14): "ekrani kaplamayan
gorseller olmamali, cok kalitesiz duruyor" ve karari: "oyle fotograflarda
alt alta iki tane koyalim ekrana."

OLCULDU (son 4 koşumun 24 arsiv gorseli): **13'u (%54)** tam kareye
kirpilamiyor. Plan o sahneye ikinci dosya vermediginde eski bulanik bant
yolu geri geliyordu. Lycurgus Cup koşumunda (yeni duzenle render edilen
ilk video) 12 karenin 2'si boyle cikti ve hakem de yazdi:

    "frames 11-12 uses a heavily cropped composition with the upper half
     blurred, leaving only part of the cup clearly visible"

⚠️ ESLEME YALNIZCA BANT ISTEYEN SAHNEYE aciliyor. Kirpilabilen bir
gorsel zaten tam ekran ve iyi duruyor; onu ikiye bolmek kucultmek olurdu.

⚠️ Kategori havuzundan esleme neden guvenli: uyeligi Commons'in kendi
kuratoryasi belirliyor, yani OZNE garantili. Ayni gevsetme tam metin
aramasinda yapilmiyor — orada isabeti bozdugu olculmustu (DW-116).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402


def _havuz(*adlar: str) -> list[dict]:
    return [
        {
            "title": f"File:{ad}",
            "url": f"https://example.invalid/{ad}",
            "mime": "image/jpeg",
            "source_url": f"https://commons.example/{ad}",
            "license": "public domain",
            "artist": "bilinmiyor",
            "width": 2000,
            "height": 1200,
        }
        for ad in adlar
    ]


def _sahneler(adet: int, ikinciler: list[str] | None = None) -> list[dict]:
    ikinciler = ikinciler or [""] * adet
    return [
        {"search_term": f"terim {i}", "kaynak_dosya_2": ikinciler[i - 1]}
        for i in range(1, adet + 1)
    ]


def _indirmeyi_taklit(monkeypatch, tmp_path):
    """Gercek ag yok; indirilen dosya olusturuluyor."""
    inen: list[str] = []

    def sahte_indir(url, hedef):
        inen.append(url)
        Path(hedef).parent.mkdir(parents=True, exist_ok=True)
        Path(hedef).write_bytes(b"jpeg")

    monkeypatch.setattr(wm, "_download", sahte_indir)
    monkeypatch.setattr(wm, "_alinti_adayi", lambda *_a, **_k: None)
    # ⚠️ `query` 2026-08-17'de eklendi: kor secim yerine sahnenin arama terimi
    # veriliyor. Bu stub imza uyumu icin esnetildi; SORGUNUN GERCEKTEN
    # GECTIGI ayri dosyada olculuyor (`test_ikincil_secimi.py`).
    monkeypatch.setattr(
        wm,
        "_kategori_adaylari",
        lambda havuz, kullanilan, *_a, **_k: [
            a for a in havuz if a["title"] not in kullanilan
        ],
    )
    return inen


def test_bant_isteyen_sahneye_kategoriden_ESLEME_bulunuyor(monkeypatch, tmp_path):
    _indirmeyi_taklit(monkeypatch, tmp_path)

    dosyalar, krediler = wm.ikincil_gorseller(
        _sahneler(1), tmp_path, _havuz("A.jpg"), esleme_gerekli=[True]
    )

    assert dosyalar[0] is not None, "bant isteyen sahne eslesmeliydi"
    assert krediler and krediler[0]["scene"] == 1, "kredi zorunlu (CC BY atfi)"


def test_kirpilabilen_sahneye_ESLEME_ARANMIYOR(monkeypatch, tmp_path):
    """⚠️ Tam ekran duran kareyi ikiye bolmek onu kucultmek olurdu."""
    _indirmeyi_taklit(monkeypatch, tmp_path)

    dosyalar, _ = wm.ikincil_gorseller(
        _sahneler(1), tmp_path, _havuz("A.jpg"), esleme_gerekli=[False]
    )

    assert dosyalar == [None]


def test_bayrak_verilmezse_eski_davranis(monkeypatch, tmp_path):
    """Geriye donuk uyum: `esleme_gerekli` yoksa yalnizca alinti kullanilir."""
    _indirmeyi_taklit(monkeypatch, tmp_path)

    dosyalar, _ = wm.ikincil_gorseller(_sahneler(1), tmp_path, _havuz("A.jpg"))

    assert dosyalar == [None]


def test_havuz_bosalinca_kalan_sahneler_bos(monkeypatch, tmp_path):
    """Iki sahne bant istiyor ama havuzda tek dosya var."""
    _indirmeyi_taklit(monkeypatch, tmp_path)

    dosyalar, _ = wm.ikincil_gorseller(
        _sahneler(2), tmp_path, _havuz("A.jpg"), esleme_gerekli=[True, True]
    )

    assert dosyalar[0] is not None
    assert dosyalar[1] is None, "havuz tukendiginde sessizce bos donmeli"


def test_ayni_dosya_iki_sahneye_verilmiyor(monkeypatch, tmp_path):
    _indirmeyi_taklit(monkeypatch, tmp_path)

    dosyalar, _ = wm.ikincil_gorseller(
        _sahneler(2), tmp_path, _havuz("A.jpg", "B.jpg"), esleme_gerekli=[True, True]
    )

    assert dosyalar[0] != dosyalar[1]


def test_birincil_basliklar_disariniyor(monkeypatch, tmp_path):
    """Birincil gecisin kullandigi gorsel ikinci yuvada tekrar cikmasin."""
    _indirmeyi_taklit(monkeypatch, tmp_path)

    dosyalar, _ = wm.ikincil_gorseller(
        _sahneler(1),
        tmp_path,
        _havuz("A.jpg"),
        used_titles={"File:A.jpg"},
        esleme_gerekli=[True],
    )

    assert dosyalar == [None], "tek aday zaten birincilde kullanilmisti"


def test_hat_bayragi_BANT_ISTEYENE_gore_kuruyor():
    """⚠️ Baglanti testi: bayrak yanlis hesaplanirsa esleme hic calismaz."""
    kaynak = Path(wm.__file__).resolve().parent.joinpath("youtube_automation.py")

    assert "esleme_gerekli=[bool(p) and bant_ister(p) for p in material_files]" in (
        kaynak.read_text(encoding="utf-8")
    )
