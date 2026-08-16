"""Kategori kolu ILAN ETTIGI kadar dosya okumali (DW-51).

⚠️ Olculdu (2026-08-16). Commons `prop=imageinfo`'yu batch basina yalnizca
**50 sayfa** icin dolduruyor; `imageinfo`'suz sayfalar `_puanli_adaylar`'da
sessizce atiliyor. `kategori_gorselleri` `continue` belirtecini takip etmedigi
icin `MENU_KATEGORI_SINIRI = 500` istemek hicbir sey degistirmiyordu:

    Karnak kategorisi   380 sayfa geldi -> 13 aday   (imageinfo 50'de)
    Masada kategorisi   500 sayfa geldi -> 47 aday   (≈50 tavani)

Sayfalama eklendikten sonra ayni olcum:

    Karnak    kat_aday  13 -> 128     kapi menusu   14 -> 32
    Ephesus   kat_aday   6 ->  43     kapi menusu    6 -> 40  (kapiyi GECTI)
    Masada    kat_aday  47 -> 113     kapi menusu   22 -> 40

⚠️ Ephesus bu kalemin neden onemli oldugunun kaniti: H2'den sonra hala 6'da
kalmisti ve "ham arzi gercekten ince" diye kaydedilmisti. Ince degildi —
okunmuyordu.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402


class _Yanit:
    def __init__(self, govde):
        self._govde = govde

    def json(self):
        return self._govde


def _sayfa(kimlik: int, *, bilgili: bool) -> dict:
    sayfa = {"pageid": kimlik, "title": f"File:{kimlik}.jpg"}
    if bilgili:
        sayfa["imageinfo"] = [{"url": f"https://x/{kimlik}.jpg", "width": 1080, "height": 1920}]
    return sayfa


def test_continue_takip_ediliyor(monkeypatch):
    """Tek turda 50 `imageinfo` geliyorsa kalanlar icin tur atilmali."""
    turlar: list[dict] = []

    def sahte_get(url, *, params=None, timeout=None, **_k):
        turlar.append(dict(params))
        tur = len(turlar)
        if tur > 3:
            return _Yanit({"query": {"pages": []}})
        sayfalar = [_sayfa(i, bilgili=True) for i in range((tur - 1) * 50, tur * 50)]
        govde = {"query": {"pages": sayfalar}}
        if tur < 3:
            govde["continue"] = {"gcmcontinue": f"tur{tur}", "continue": "gcmcontinue||"}
        return _Yanit(govde)

    monkeypatch.setattr(wm, "_get_with_retry", sahte_get)

    sayfalar = wm.kategori_gorselleri("Karnak", limit=150)

    assert len(sayfalar) == 150, "continue takip edilmezse 50'de kalir"
    assert len(turlar) == 3
    assert turlar[1].get("gcmcontinue") == "tur1", "continue belirteci geri gonderilmeli"


def test_ayni_sayfa_BIRLESTIRILIYOR(monkeypatch):
    """⚠️ `iicontinue` ayni sayfalari `imageinfo` ile tekrar gonderir.

    Birlestirilmezse ya cift sayilirlar ya da bilgisiz kopya kalir.
    """
    turlar: list[dict] = []

    def sahte_get(url, *, params=None, timeout=None, **_k):
        turlar.append(dict(params))
        if len(turlar) == 1:
            return _Yanit(
                {
                    "query": {"pages": [_sayfa(1, bilgili=True), _sayfa(2, bilgili=False)]},
                    "continue": {"iicontinue": "x", "continue": "||"},
                }
            )
        return _Yanit({"query": {"pages": [_sayfa(2, bilgili=True)]}})

    monkeypatch.setattr(wm, "_get_with_retry", sahte_get)

    sayfalar = wm.kategori_gorselleri("Karnak", limit=100)

    assert len(sayfalar) == 2, "ayni sayfa iki kez sayilmamali"
    assert all(s.get("imageinfo") for s in sayfalar), "eksik imageinfo sonraki turdan dolmali"


def test_limit_dolunca_DURUYOR(monkeypatch):
    """Gereksiz tur atmamali — huni aday BASINA menu kuruyor."""
    turlar: list[dict] = []

    def sahte_get(url, *, params=None, timeout=None, **_k):
        turlar.append(dict(params))
        return _Yanit(
            {
                "query": {"pages": [_sayfa(i, bilgili=True) for i in range(60)]},
                "continue": {"gcmcontinue": "daha-var"},
            }
        )

    monkeypatch.setattr(wm, "_get_with_retry", sahte_get)

    wm.kategori_gorselleri("Karnak", limit=50)

    assert len(turlar) == 1, "limit dolduysa yeni tur atilmamali"


def test_tur_tavani_SONSUZ_dongyu_engelliyor(monkeypatch):
    """⚠️ Sunucu her turda `continue` dondururse hat asili kalmamali."""
    turlar: list[dict] = []

    def sahte_get(url, *, params=None, timeout=None, **_k):
        turlar.append(dict(params))
        return _Yanit(
            {
                "query": {"pages": [_sayfa(len(turlar), bilgili=True)]},
                "continue": {"gcmcontinue": "hep-var"},
            }
        )

    monkeypatch.setattr(wm, "_get_with_retry", sahte_get)

    wm.kategori_gorselleri("Karnak", limit=10_000)

    assert len(turlar) == wm.KATEGORI_TUR_TAVANI


def test_MENU_SINIRI_tur_tavanina_siyiyor():
    """⚠️ Iki sabit birbirine bagli: batch basina ~50 `imageinfo` geliyor,
    yani `MENU_KATEGORI_SINIRI` en fazla `KATEGORI_TUR_TAVANI * 50` olabilir.
    Buyuk olsaydi sinir sessizce erisilemez olurdu."""
    assert wm.MENU_KATEGORI_SINIRI <= wm.KATEGORI_TUR_TAVANI * 50
