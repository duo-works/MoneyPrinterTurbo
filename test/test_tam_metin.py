"""Uzun format icin KAYNAK METIN derinligi.

⚠️ NEDEN — olculdu (2026-08-15), ozet ile tam makale arasindaki fark:

    konu                ozet      tam makale
    Roman aqueduct        39        7.539     (193x)
    Herculaneum           32        3.207     (100x)
    Egyptian pyramids     56        3.208      (57x)
    Bayeux Tapestry      102        6.456      (63x)
    Mastaba               55        1.492      (27x)

`vikipedi_ozeti` giris paragrafini veriyor. 80-120 kelimelik Shorts
senaryosuna yetiyor; uzun format ~2.000 kelime konusuyor ve model 56
kelimelik ozetten 2.000 kelime yazmak zorunda kalirsa aradaki farki
UYDURUR.

Bu, bu hatta ZATEN OLCULMUS bir kusur (DW-114): "Franziska Scanagatta"
konusu modele yalnizca ADIYLA verilince senaryo "Italian opera, 19th
century music" diye yazildi; gercekte 1794'te erkek kiligina girip
Habsburg ordusunda subaylik yapmis bir kadin. Uzun formatta ayni risk
kelime basina degil, kelime SAYISIYLA olcekleniyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402


class _Yanit:
    def __init__(self, veri):
        self._veri = veri

    def json(self):
        return self._veri


def _sayfa(metin: str) -> dict:
    return {"query": {"pages": {"1": {"extract": metin}}}}


def test_tam_metin_govdeyi_donduruyor(monkeypatch):
    monkeypatch.setattr(
        wm, "_get_with_retry", lambda *_a, **_k: _Yanit(_sayfa("Birinci cumle. Ikinci cumle."))
    )

    assert wm.vikipedi_tam_metin("Konu") == "Birinci cumle. Ikinci cumle."


def test_KAYNAKCA_bolumleri_atiliyor(monkeypatch):
    """⚠️ "Retrieved 12 March 2019" gibi satirlarin anlatima sizmasi, bu
    hatta olculmus bir kusur sinifinin (kaynagin kendisini anlatmak)
    besleyicisi olurdu."""
    ham = (
        "Govde cumlesi.\n"
        "== History ==\n"
        "Tarihsel bilgi.\n"
        "== References ==\n"
        "Smith, J. Retrieved 12 March 2019.\n"
        "== External links ==\n"
        "https://ornek.invalid\n"
    )
    monkeypatch.setattr(wm, "_get_with_retry", lambda *_a, **_k: _Yanit(_sayfa(ham)))

    sonuc = wm.vikipedi_tam_metin("Konu")

    assert "Govde cumlesi." in sonuc
    assert "Tarihsel bilgi." in sonuc
    assert "Retrieved" not in sonuc
    assert "ornek.invalid" not in sonuc


def test_bolum_basliklari_metne_karismiyor(monkeypatch):
    monkeypatch.setattr(
        wm, "_get_with_retry", lambda *_a, **_k: _Yanit(_sayfa("== History ==\nMetin."))
    )

    assert wm.vikipedi_tam_metin("Konu") == "Metin."


def test_kelime_tavani_uygulaniyor(monkeypatch):
    monkeypatch.setattr(
        wm, "_get_with_retry", lambda *_a, **_k: _Yanit(_sayfa("kelime " * 9000))
    )

    assert len(wm.vikipedi_tam_metin("Konu").split()) == wm.TAM_METIN_AZAMI_KELIME


def test_tavan_SHORTS_senaryosundan_belirgin_genis():
    """Model SECEBILMELI: kaynak, konusulacak metinden genis olmali.

    15 dakikalik video ~2.000 kelime; tavan ondan belirgin yukarida ama
    sinirsiz degil (baglam ve maliyet).
    """
    assert wm.TAM_METIN_AZAMI_KELIME >= 2000 * 2


def test_bos_makale_BOS_donuyor(monkeypatch):
    """Kaynak yoksa uretim durmamali — `vikipedi_ozeti` ile ayni sozlesme."""
    monkeypatch.setattr(wm, "_get_with_retry", lambda *_a, **_k: _Yanit(_sayfa("")))

    assert wm.vikipedi_tam_metin("Konu") == ""


def test_ag_hatasi_patlatmiyor(monkeypatch):
    def patlat(*_a, **_k):
        raise wm.requests.RequestException("ag koptu")

    monkeypatch.setattr(wm, "_get_with_retry", patlat)

    assert wm.vikipedi_tam_metin("Konu") == ""


def test_bozuk_json_patlatmiyor(monkeypatch):
    class _Bozuk:
        def json(self):
            raise ValueError("json degil")

    monkeypatch.setattr(wm, "_get_with_retry", lambda *_a, **_k: _Bozuk())

    assert wm.vikipedi_tam_metin("Konu") == ""


def test_eksik_anahtar_patlatmiyor(monkeypatch):
    monkeypatch.setattr(wm, "_get_with_retry", lambda *_a, **_k: _Yanit({"batch": True}))

    assert wm.vikipedi_tam_metin("Konu") == ""


def test_bos_konu_istek_atmiyor(monkeypatch):
    def patlat(*_a, **_k):
        raise AssertionError("bos konu icin ag istegi atilmamali")

    monkeypatch.setattr(wm, "_get_with_retry", patlat)

    assert wm.vikipedi_tam_metin("   ") == ""


def test_yonlendirme_izleniyor(monkeypatch):
    """`redirects=1`: "Pyramids of Egypt" -> "Egyptian pyramids"."""
    gecen = {}

    def sahte(*_a, **k):
        gecen.update(k.get("params") or {})
        return _Yanit(_sayfa("Metin."))

    monkeypatch.setattr(wm, "_get_with_retry", sahte)
    wm.vikipedi_tam_metin("Pyramids of Egypt")

    assert gecen.get("redirects") == "1"
    assert gecen.get("explaintext") == "1"
