"""Arsiv konuyu KENDI adiyla degil, Commons'in adiyla bulmali (DW-122).

⚠️ Olculdu (2026-08-10). Wikidata uzerinden cozulen gercek kategoriler:

    "Franziska Scanagatta"       → Category:Francesca Scanagatta
    "Theresian Military Academy" → Category:Theresianische Militärakademie
    "Chaco Canyon"               → Category:Chaco Culture National Historical Park

Ilk satir, Scanagatta videosunun 6/6 sahnesinin neden AI ile uretildigini tek
basina acikliyor: gorsel arsivde VARDI; biz "Franziska" diye aradik, Commons
"Francesca" diye sakliyor.

Kategori ayrica DW-116'daki YANLIS OZNE kusurunu da cozuyor: tam metin
aramasi ayni madalyayi paylasan baska adamlarin portrelerini getirmisti,
`Category:William Hardham` ise 8 dosyanin 8'inde dogru adami veriyor.
"""

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402


class _Yanit:
    def __init__(self, govde):
        self._govde = govde

    def json(self):
        return self._govde


def _wikidata_hatti(monkeypatch, *, qid="Q86025", kategori="Francesca Scanagatta"):
    """Wikipedia → Wikidata → P373 zincirini yamar; istekleri kaydeder."""
    istekler: list[str] = []

    def sahte_get(url, *, params=None, timeout=None, **_k):
        istekler.append(url)
        if url == wm.VIKIPEDI_API_URL:
            sayfa = {"title": params["titles"]}
            if qid:
                sayfa["pageprops"] = {"wikibase_item": qid}
            return _Yanit({"query": {"pages": [sayfa]}})
        if url == wm.VIKIVERI_API_URL:
            if not kategori:
                return _Yanit({"claims": {}})
            return _Yanit(
                {
                    "claims": {
                        "P373": [
                            {"mainsnak": {"datavalue": {"value": kategori}}}
                        ]
                    }
                }
            )
        raise AssertionError(f"beklenmeyen istek: {url}")

    monkeypatch.setattr(wm, "_get_with_retry", sahte_get)
    monkeypatch.setattr(wm, "_KATEGORI_ONBELLEGI", {})
    return istekler


# --- Kategori cozumu ------------------------------------------------------


def test_konu_adi_farkliysa_bile_kategori_bulunuyor(monkeypatch, gercek_kategori_cozumu):
    """Asil kosul — olculen kusur buydu."""
    _wikidata_hatti(monkeypatch)
    assert wm.commons_kategorisi("Franziska Scanagatta") == "Francesca Scanagatta"


def test_kategori_ingilizce_olmak_zorunda_degil(monkeypatch, gercek_kategori_cozumu):
    _wikidata_hatti(
        monkeypatch, qid="Q568705", kategori="Theresianische Militärakademie"
    )
    assert (
        wm.commons_kategorisi("Theresian Military Academy")
        == "Theresianische Militärakademie"
    )


def test_wikidata_ogesi_yoksa_none(monkeypatch, gercek_kategori_cozumu):
    _wikidata_hatti(monkeypatch, qid="")
    assert wm.commons_kategorisi("Uydurma Konu") is None


def test_p373_yoksa_none(monkeypatch, gercek_kategori_cozumu):
    _wikidata_hatti(monkeypatch, kategori="")
    assert wm.commons_kategorisi("Konu") is None


def test_ag_hatasi_uretimi_durdurmuyor(monkeypatch, gercek_kategori_cozumu):
    """⚠️ Kategori bir IYILESTIRME; dusmesi tam metin aramasini engellememeli."""

    def patlat(*_a, **_k):
        raise requests.ConnectionError("ag yok")

    monkeypatch.setattr(wm, "_get_with_retry", patlat)
    monkeypatch.setattr(wm, "_KATEGORI_ONBELLEGI", {})
    assert wm.commons_kategorisi("Chaco Canyon") is None


def test_kategori_bir_kez_cozuluyor(monkeypatch, gercek_kategori_cozumu):
    """Sahne basina istek atilmamali."""
    istekler = _wikidata_hatti(monkeypatch)
    wm.commons_kategorisi("Franziska Scanagatta")
    wm.commons_kategorisi("Franziska Scanagatta")
    wm.commons_kategorisi("franziska scanagatta")  # buyuk/kucuk harf ayni konu
    assert len(istekler) == 2, istekler


# --- Hatta baglanti -------------------------------------------------------


def _sayfa(ad: str, url: str, *, en=1000, boy=1400) -> dict:
    return {
        "title": ad,
        "imageinfo": [
            {
                "mime": "image/jpeg",
                "url": url,
                "descriptionurl": f"https://commons.wikimedia.org/wiki/{ad}",
                "width": en,
                "height": boy,
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "ImageDescription": {"value": ""},
                },
            }
        ],
    }


def _hat(monkeypatch, tmp_path, havuz, *, kategori="Francesca Scanagatta"):
    monkeypatch.setattr(wm, "search_commons", lambda *_a, **_k: [])
    monkeypatch.setattr(wm, "commons_kategorisi", lambda _k: kategori)
    monkeypatch.setattr(wm, "kategori_gorselleri", lambda *_a, **_k: list(havuz))
    monkeypatch.setattr(wm, "download_met_scene_material", lambda *_a, **_k: None)
    monkeypatch.setattr(wm, "_tekrar_mi", lambda *_a, **_k: False)
    monkeypatch.setattr(wm, "_izi_ekle", lambda *_a, **_k: None)

    def sahte_indir(url, hedef, **_k):
        hedef.write_bytes(b"x" * 20_000)

    monkeypatch.setattr(wm, "_download", sahte_indir)


def test_tam_metin_bulamayinca_kategoriden_geliyor(monkeypatch, tmp_path):
    """Asil kosul: eskiden bu sahne AI'ya giderdi."""
    _hat(monkeypatch, tmp_path, [_sayfa("File:Francesca Scanagatta.jpg", "u1")])

    dosyalar, kunyeler = wm.download_scene_materials(
        "Franziska Scanagatta",
        [{"narration": "n", "search_term": "Franziska Scanagatta portrait"}],
        tmp_path,
        visual_anchor="Franziska Scanagatta",
    )

    assert dosyalar and dosyalar[0] is not None
    assert kunyeler[0]["title"] == "File:Francesca Scanagatta.jpg"


def test_kategoride_capa_adi_aranmiyor(monkeypatch, tmp_path):
    """⚠️ Bu testin kilitledigi sey duzeltmenin TA KENDISI.

    Kategori uyeliginin garantisi Commons kuratoryasidir. Dosya adinda capa
    kelimelerini aramak "Francesca" dosyasini "Franziska" capasina takilip
    elerdi — yani kusur aynen surerdi.
    """
    _hat(monkeypatch, tmp_path, [_sayfa("File:Ritratto.jpg", "u1")])

    dosyalar, _ = wm.download_scene_materials(
        "Franziska Scanagatta",
        [{"narration": "n", "search_term": "Franziska Scanagatta portrait"}],
        tmp_path,
        visual_anchor="Franziska Scanagatta",
    )

    assert dosyalar[0] is not None, "capa adi kategori havuzunda sart kosulmamali"


def test_tam_metin_aramasinda_capa_HALA_sart(monkeypatch):
    """⚠️ Gevsetme yalnizca kategoride; tam metin aramasinda DEGIL.

    Olculdu (2026-08-10): capa "Victoria Cross" iken "herhangi bir capa
    kelimesi" kurali "Medal, campaign", "Medal, miniature" gibi 13 adsiz
    madalyayi iceri aliyordu — DW-116'daki yanlis ozne kusurunun ta kendisi.
    """
    sayfalar = [_sayfa("File:Medal, campaign (AM 2001.25.843-2).jpg", "u1")]
    assert (
        wm.select_candidate(
            sayfalar, set(), query="Victoria Cross medal", required_anchor="Victoria Cross"
        )
        is None
    )


def test_kategori_havuzu_bos_ise_met_e_dusuyor(monkeypatch, tmp_path):
    _hat(monkeypatch, tmp_path, [])
    with pytest.raises(wm.MaterialsUnavailableError):
        wm.download_scene_materials(
            "Konu",
            [{"narration": "n", "search_term": "bir terim"}],
            tmp_path,
            visual_anchor="Konu",
        )


def test_kategori_sahne_basina_degil_bir_kez_cekiliyor(monkeypatch, tmp_path):
    cagri: list[int] = []
    havuz = [
        _sayfa("File:a.jpg", "u1"),
        _sayfa("File:b.jpg", "u2"),
        _sayfa("File:c.jpg", "u3"),
    ]
    _hat(monkeypatch, tmp_path, havuz)
    monkeypatch.setattr(
        wm,
        "kategori_gorselleri",
        lambda *_a, **_k: (cagri.append(1), list(havuz))[1],
    )

    dosyalar, _ = wm.download_scene_materials(
        "Konu",
        [
            {"narration": "n", "search_term": "t1"},
            {"narration": "n", "search_term": "t2"},
            {"narration": "n", "search_term": "t3"},
        ],
        tmp_path,
        visual_anchor="Konu",
    )

    assert len(cagri) == 1, f"kategori {len(cagri)} kez cekildi"
    assert all(d is not None for d in dosyalar)


def test_ayni_gorsel_iki_sahnede_kullanilmiyor(monkeypatch, tmp_path):
    havuz = [_sayfa("File:a.jpg", "u1"), _sayfa("File:b.jpg", "u2")]
    _hat(monkeypatch, tmp_path, havuz)

    _dosyalar, kunyeler = wm.download_scene_materials(
        "Konu",
        [
            {"narration": "n", "search_term": "t1"},
            {"narration": "n", "search_term": "t2"},
        ],
        tmp_path,
        visual_anchor="Konu",
    )

    assert len({k["title"] for k in kunyeler}) == 2


def test_kategori_gorselleri_sayfa_donduruyor(monkeypatch):
    monkeypatch.setattr(
        wm,
        "_get_with_retry",
        lambda *_a, **_k: _Yanit({"query": {"pages": [{"title": "File:x.jpg"}]}}),
    )
    assert wm.kategori_gorselleri("Bir Kategori") == [{"title": "File:x.jpg"}]


def test_kategori_gorselleri_hatada_bos_liste(monkeypatch):
    def patlat(*_a, **_k):
        raise requests.Timeout("yavas")

    monkeypatch.setattr(wm, "_get_with_retry", patlat)
    assert wm.kategori_gorselleri("Bir Kategori") == []
