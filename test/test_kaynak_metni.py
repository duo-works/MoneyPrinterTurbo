"""Huni konusuna KAYNAK METIN verilmesi (DW-114).

⚠️ Olculdu (2026-08-09): huniden gelen "Franziska Scanagatta" konusu icin
model senaryoyu ve etiketleri tamamen uydurdu — "Italian opera",
"19th century music", "opera history". Gercekte Scanagatta 1794'te Theresian
Askeri Akademisi'ne girebilmek icin erkek kiligina giren ve Habsburg
ordusunda subay olan bir kadin; opera ile hicbir ilgisi yok.

Kusur yapisal: `generate_content_plan` modele yalnizca konunun ADINI
veriyordu. Huninin varlik sebebi arzi az konular bulmak, arzin az olmasinin
en yaygin sebebi de konunun az bilinmesi — yani huni ne kadar iyi calisirsa
modelin bilmedigi konu o kadar cok geliyor ve uydurma riski ARTIYOR.
"""

import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402
import youtube_automation as ya  # noqa: E402


class _SahteYanit:
    def __init__(self, govde, *, patlat=False):
        self._govde = govde
        self._patlat = patlat

    def json(self):
        if self._patlat:
            raise ValueError("JSON degil")
        return self._govde


# ⚠️ Plan `validate_content_plan`den GECMEK ZORUNDA, yoksa uretici tekrar
# deneme dongusune girip DistinctTopicUnavailableError atiyor ve test, olcmek
# istedigi seyi degil dogrulama kurallarini olcmus olur. Sartlar: 80-120
# sozcuk, 6-10 sahne, capa 1-4 sozcuk, her sahnenin arama terimi capayi
# icermeli, en az 3 etiket.
_SENARYO = " ".join(["word"] * 90)
_GECERLI_PLAN = {
    "topic": "Scanagatta",
    "visual_anchor": "Theresian Academy",
    "title": "Who Was Franziska Scanagatta? #Shorts",
    "script": _SENARYO,
    "scenes": [
        {"narration": f"Sahne {i}", "search_term": "Theresian Academy building"}
        for i in range(1, 7)
    ],
    "description": "d",
    "tags": ["a", "b", "c"],
}


# --- Ozet cekme ----------------------------------------------------------


def test_ozet_donuyor(monkeypatch):
    monkeypatch.setattr(
        wm, "_get_with_retry",
        lambda *_a, **_k: _SahteYanit({"extract": "Bir Habsburg subayi."}),
    )

    assert wm.vikipedi_ozeti("Franziska Scanagatta") == "Bir Habsburg subayi."


def test_baslik_url_icin_kodlaniyor(monkeypatch):
    """Bosluk ve aksanli harf ham gecerse istek 404 doner."""
    gorulen = {}

    def yakala(url, **_k):
        gorulen["url"] = url
        return _SahteYanit({"extract": "x"})

    monkeypatch.setattr(wm, "_get_with_retry", yakala)
    wm.vikipedi_ozeti("Ernst von Weizsäcker")

    assert " " not in gorulen["url"]
    assert "Ernst_von_Weizs" in gorulen["url"]


def test_belirsizlik_sayfasi_kaynak_SAYILMIYOR(monkeypatch):
    """⚠️ "X birden fazla seye isaret edebilir" metni modele hicbir olgu
    vermez; daha kotusu, yanlis dala sapmasina yol acar. Kaynak yok sayilmali.
    """
    monkeypatch.setattr(
        wm, "_get_with_retry",
        lambda *_a, **_k: _SahteYanit(
            {"type": "disambiguation", "extract": "may refer to:"}
        ),
    )

    assert wm.vikipedi_ozeti("Mercury") == ""


def test_ag_hatasi_uretimi_durdurmuyor(monkeypatch):
    """Kaynak bir yan is — yoklugu videosuzluktan iyidir."""
    def patla(*_a, **_k):
        raise requests.ConnectionError("ag yok")

    monkeypatch.setattr(wm, "_get_with_retry", patla)

    assert wm.vikipedi_ozeti("Herhangi Bir Sey") == ""


def test_bozuk_json_patlamiyor(monkeypatch):
    monkeypatch.setattr(
        wm, "_get_with_retry", lambda *_a, **_k: _SahteYanit(None, patlat=True)
    )

    assert wm.vikipedi_ozeti("X") == ""


def test_ozet_yoksa_bos(monkeypatch):
    monkeypatch.setattr(wm, "_get_with_retry", lambda *_a, **_k: _SahteYanit({}))

    assert wm.vikipedi_ozeti("X") == ""


# --- Isteme baglanti ------------------------------------------------------


def _istemi_yakala(monkeypatch, *, ozet: str):
    """`generate_content_plan`i cagirip modele giden user mesajini dondurur."""
    yakalanan = {}

    class _Mesaj:
        content = json.dumps(_GECERLI_PLAN)

    class _Secim:
        message = _Mesaj()

    class _Yanit:
        choices = [_Secim()]

    class _Tamamlamalar:
        @staticmethod
        def create(**kwargs):
            yakalanan["mesajlar"] = kwargs["messages"]
            return _Yanit()

    class _Sohbet:
        completions = _Tamamlamalar()

    class _Istemci:
        chat = _Sohbet()

    monkeypatch.setattr(ya, "_openai_client", lambda: (_Istemci(), "m"))
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(wm, "vikipedi_ozeti", lambda *_a, **_k: ozet)

    ya.generate_content_plan(konu="Franziska Scanagatta")
    return yakalanan["mesajlar"][-1]["content"]


def test_kaynak_isteme_giriyor(monkeypatch):
    """⚠️ Baglanti testi — fonksiyon dogru olsa bile isteme girmezse kusur surer."""
    ozet = "Franziska Scanagatta was an Italian woman who served as an officer."
    istem = _istemi_yakala(monkeypatch, ozet=ozet)

    assert "AUTHORITATIVE SOURCE" in istem
    assert "served as an officer" in istem


def test_kaynak_yoksa_temkin_uyarisi_giriyor(monkeypatch):
    """Bos kaynak "serbestsin" degil "temkinli ol" demek."""
    istem = _istemi_yakala(monkeypatch, ozet="")

    assert "AUTHORITATIVE SOURCE" not in istem
    assert "Do not invent" in istem


def test_kaynak_yalnizca_huni_kipinde_cekiliyor(monkeypatch):
    """Konu modelin kendi secimiyse ortada cekilecek bir baslik yok."""
    cagrildi = []
    monkeypatch.setattr(
        wm, "vikipedi_ozeti", lambda *a, **k: cagrildi.append(a) or ""
    )
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])

    class _Mesaj:
        content = json.dumps(_GECERLI_PLAN)

    class _Secim:
        message = _Mesaj()

    class _Yanit:
        choices = [_Secim()]

    class _Istemci:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(**_k):
                    return _Yanit()

    monkeypatch.setattr(ya, "_openai_client", lambda: (_Istemci(), "m"))
    ya.generate_content_plan()

    assert cagrildi == []


@pytest.mark.parametrize("konu", ["Franziska Scanagatta", "William Hardham"])
def test_gercek_uctan_ozet_geliyor(konu):
    """⚠️ Ag testi — sahte yanit, ucun bicimini degistirmesini yakalayamaz.

    Bu test agdan gercekten ozet cekiyor; ag yoksa atlaniyor.
    """
    try:
        ozet = wm.vikipedi_ozeti(konu)
    except Exception:  # noqa: BLE001
        pytest.skip("ag yok")
    if not ozet:
        pytest.skip("ozet gelmedi (ag ya da ucta degisiklik)")

    assert konu.split()[-1].lower() in ozet.lower()
