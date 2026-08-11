"""Teslim proxy'si dusunce arsiv gorseli atilmamali (DW-126).

⚠️ Olculdu (2026-08-10): 15 arsiv dosyasindan 13'u `images.weserv.nl`
uzerinden geldi, 2'si ISRARLA 404 verdi — ve o iki dosya Wikimedia'nin
kendi sunucusunda 200 ve 652 KB olarak duruyordu. Yani gecici bir hata
degil, dosyaya ozel kalici bir teslim kusuru.

Bedeli dogrudan "AI gorsel cok" sikayetine yaziliyor: proxy dusunce
gecerli bir arsiv gorseli atiliyor ve sahne AI ile uretiliyor.
"""

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402

KAYNAK = "https://upload.wikimedia.org/wikipedia/commons/d/d1/Francesca_Scanagatta.jpg"


class _Yanit:
    def __init__(self, icerik=b"x" * 20_000):
        self.content = icerik


def _hata(durum: int) -> requests.HTTPError:
    yanit = requests.Response()
    yanit.status_code = durum
    return requests.HTTPError(f"{durum}", response=yanit)


def test_dogrudan_url_izleme_parametrelerini_atiyor():
    kirli = f"{KAYNAK}?utm_source=commons.wikimedia.org&utm_campaign=x"
    assert wm.dogrudan_url(kirli) == KAYNAK


def test_dogrudan_url_izin_listesi_disini_reddediyor():
    """⚠️ Proxy atlanirken izin listesi GEVSEMEMELI."""
    for kotu in (
        "https://kotu.example/x.jpg",
        "http://upload.wikimedia.org/x.jpg",
        "https://upload.wikimedia.org.kotu.example/x.jpg",
    ):
        with pytest.raises(ValueError):
            wm.dogrudan_url(kotu)


def test_proxy_404_verince_dogrudan_iniyor(monkeypatch, tmp_path):
    """Asil kosul — olculen kusur buydu."""
    cagrilan: list[str] = []

    def sahte_get(url, **_k):
        cagrilan.append(url)
        if url.startswith(wm.DELIVERY_PROXY_URL):
            raise _hata(404)
        return _Yanit()

    monkeypatch.setattr(wm, "_get_with_retry", sahte_get)
    hedef = tmp_path / "x.jpg"
    wm._download(KAYNAK, hedef)

    assert hedef.stat().st_size == 20_000
    assert cagrilan[-1] == KAYNAK, cagrilan


def test_proxy_403_verince_de_dogrudan_iniyor(monkeypatch, tmp_path):
    def sahte_get(url, **_k):
        if url.startswith(wm.DELIVERY_PROXY_URL):
            raise _hata(403)
        return _Yanit()

    monkeypatch.setattr(wm, "_get_with_retry", sahte_get)
    hedef = tmp_path / "x.jpg"
    wm._download(KAYNAK, hedef)
    assert hedef.exists()


def test_5xx_dogrudan_yola_dusmuyor(monkeypatch, tmp_path):
    """⚠️ 5xx'i `_get_with_retry` zaten geri cekilmeyle deniyor.

    Buraya ulasan 5xx kalici demek; proxy'yi atlamak icin sebep degil ve
    yukselmeli — yoksa gercek bir arizayi sessizce yutar.
    """
    def sahte_get(url, **_k):
        if url.startswith(wm.DELIVERY_PROXY_URL):
            raise _hata(503)
        raise AssertionError("5xx'te dogrudan yola dusulmemeli")

    monkeypatch.setattr(wm, "_get_with_retry", sahte_get)
    with pytest.raises(requests.HTTPError):
        wm._download(KAYNAK, tmp_path / "x.jpg")


def test_proxy_calisiyorsa_dogrudan_denenmiyor(monkeypatch, tmp_path):
    """Varsayilan yol proxy olarak kalmali — onbellek ve boyutlandirma orada."""
    cagrilan: list[str] = []

    def sahte_get(url, **_k):
        cagrilan.append(url)
        return _Yanit()

    monkeypatch.setattr(wm, "_get_with_retry", sahte_get)
    wm._download(KAYNAK, tmp_path / "x.jpg")

    assert len(cagrilan) == 1
    assert cagrilan[0].startswith(wm.DELIVERY_PROXY_URL)


def test_dogrudan_gelen_de_boyut_tabanina_tabi(monkeypatch, tmp_path):
    """Proxy atlanirken bozuk/kucuk dosya kontrolu kaybolmamali."""

    def sahte_get(url, **_k):
        if url.startswith(wm.DELIVERY_PROXY_URL):
            raise _hata(404)
        return _Yanit(b"kucuk")

    monkeypatch.setattr(wm, "_get_with_retry", sahte_get)
    hedef = tmp_path / "x.jpg"
    with pytest.raises(RuntimeError):
        wm._download(KAYNAK, hedef)
    assert not hedef.exists()
