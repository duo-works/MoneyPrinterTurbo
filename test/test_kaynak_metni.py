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
    # ⚠️ Terimler BIRBIRINDEN farkli: ayni terimi tekrarlayan plan artik
    # dogrulamadan gecmiyor (portre yigini kusuru, 2026-08-13).
    "scenes": [
        {"narration": f"Sahne {i}", "search_term": f"Theresian Academy {ayrinti}"}
        for i, ayrinti in enumerate(
            ("building", "parade ground", "cadet uniform", "entrance gate",
             "classroom", "officer register"),
            start=1,
        )
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


def _cikarimi_yamala(monkeypatch, yakalanan: dict) -> None:
    """Model cagrisini `_json_completion` SEVIYESINDE kesip user istemini yakalar.

    ⚠️ Dikis yeri burasi olmali, `_openai_client` DEGIL. Ilk surumde OpenAI
    istemcisi yamalandi ve testler yerelde gecti — ama gecmelerinin sebebi
    yamanin ise yaramasi degildi: `INFERENCE_BACKEND` varsayilani "hermes-cli"
    oldugu icin `_json_completion` OpenAI istemcisine hic ugramiyor, `hermes`
    ikilisini calistiriyor. Yani testler yerelde GERCEK model cagirisi yapti;
    CI'da ikili olmadigi icin "FileNotFoundError: 'hermes'" ile dustuler.

    `_json_completion` iki arka ucun da ustundeki tek dikis; buradan yamamak
    testi hem hermetik hem arka uctan bagimsiz yapiyor.
    """

    def sahte(system: str, user: str, **_) -> dict:
        yakalanan["system"] = system
        yakalanan["user"] = user
        return dict(_GECERLI_PLAN)

    monkeypatch.setattr(ya, "_json_completion", sahte)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])


def _istemi_yakala(monkeypatch, *, ozet: str) -> str:
    """`generate_content_plan`i cagirip modele giden user istemini dondurur."""
    yakalanan: dict = {}
    _cikarimi_yamala(monkeypatch, yakalanan)
    monkeypatch.setattr(wm, "vikipedi_ozeti", lambda *_a, **_k: ozet)

    ya.generate_content_plan(konu="Franziska Scanagatta")
    return yakalanan["user"]


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


def test_istem_bosluğu_anlatmayi_istemiyor(monkeypatch):
    """⚠️ ASIL KUSUR BUYDU (2026-08-13) — istem kendi kendisiyle celisiyordu.

    Kaynak blogu modele "where it is silent, say what is not known ...
    naming the edge of the evidence is this channel's voice" diyordu. Yani
    hicbir arsiv gorselinin gosteremeyecegi cumleleri model ozensizlikten
    degil TALIMAT GEREGI yaziyordu:

        "No one can reconstruct every transition from this summary alone."
        "The record here does not name each turning point."
        "Why it ended is not known from the evidence given."

    Bu, `resmedilemez_kusuru` yasagiyla dogrudan celisiyordu: bir taraf
    yaz diyor, oteki reddediyordu — dogrulama-yeniden deneme dongusu bosa
    donuyordu. Uydurma yasagi (DW-114) KORUNUYOR; degisen sey bosluğun
    nasil kapatilacagi: senaryoya yazmak yerine konuyu daraltmak.

    Iki taraf birden kontrol ediliyor cunku kusur ikisinin CELISKISIYDI.
    """
    for ozet in ("Mehmed II was an Ottoman sultan who ruled twice.", ""):
        istem = _istemi_yakala(monkeypatch, ozet=ozet)

        assert "say what is not known" not in istem
        assert "edge of the evidence" not in istem
        assert "where the record is thin" not in istem
        # Uydurma yasagi her iki dalda da duruyor.
        assert "invent" in istem


def test_kaynak_yalnizca_huni_kipinde_cekiliyor(monkeypatch):
    """Konu modelin kendi secimiyse ortada cekilecek bir baslik yok."""
    cagrildi = []
    _cikarimi_yamala(monkeypatch, {})
    monkeypatch.setattr(wm, "vikipedi_ozeti", lambda *a, **k: cagrildi.append(a) or "")

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
