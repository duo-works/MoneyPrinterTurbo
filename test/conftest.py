"""Testler aga cikmasin.

⚠️ `download_scene_materials` artik konunun Commons KATEGORISINI de deniyor
(DW-122). Bu, tam metin aramasini mock'layan testlerin GERCEKTEN aga
cikmasina yol aciyordu: `search_commons` mock'lu oldugu icin hicbir sey
bulunamiyor, hat kategori yoluna dusuyor ve Wikipedia/Wikidata/Commons'a
istek atiyordu. Olculdu: takim 91 saniye suruyordu, bu dosyayla 20.

Varsayilan "kategori yok": mevcut testlerin anlami degismiyor (arsiv
bulamadi → Met → hata). Kategori cozumunun KENDISINI sinayan testler
`gercek_kategori_cozumu` fixture'ini isteyerek gercek islevi geri alir.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as _wm  # noqa: E402
import youtube_automation as _ya  # noqa: E402

_GERCEK_KATEGORI_COZUMU = _wm.commons_kategorisi


@pytest.fixture(autouse=True)
def _kategori_cozumu_kapali(monkeypatch):
    monkeypatch.setattr(_wm, "commons_kategorisi", lambda _konu: None)
    monkeypatch.setattr(_wm, "_KATEGORI_ONBELLEGI", {})
    # ⚠️ QID ve kisi onbellekleri de test basina sifirlanmali. QID adimi
    # `commons_kategorisi` ile `kisi_mi` arasinda PAYLASILIYOR; sifirlanmazsa
    # bir testin doldurdugu QID digerinde ag cagrisini atlatir ve "kac istek
    # atildi" olcen testler yanlis dusuyor (bir kez oldu, 2026-08-13).
    monkeypatch.setattr(_wm, "_QID_ONBELLEGI", {})
    monkeypatch.setattr(_wm, "_KISI_ONBELLEGI", {})
    # ⚠️ Ayni tuzak ikinci kez: modul duzeyindeki HER onbellek test basina
    # sifirlanmali, yoksa testler birbirinin sonucunu okuyor. Yeni bir
    # onbellek eklenirse buraya da eklenmeli.
    monkeypatch.setattr(_ya, "_ENVANTER_ONBELLEGI", {})


@pytest.fixture
def gercek_kategori_cozumu(monkeypatch):
    """Autouse susturmasini geri alir — ag katmani testte ayrica yamanmali."""
    monkeypatch.setattr(_wm, "commons_kategorisi", _GERCEK_KATEGORI_COZUMU)
    return _GERCEK_KATEGORI_COZUMU
