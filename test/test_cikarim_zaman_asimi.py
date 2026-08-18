"""Cikarim zaman asimi DENEMEYI yakmali, koşumu degil.

⚠️ OLCULDU (2026-08-19, 00:05 koşumu). Dort deneme tamamlandi, besinci
`hermes` cagrisi 180 saniyede takildi ve butun koşum `HATA / cikis 1` ile
oldu — hicbir kapi bir plani reddetmemisken. Ayni takilma BIRINCI denemede
olsaydi, video uretecek bir koşum tek bir asili cagri yuzunden cope
giderdi.

Iki ayri is yapiliyor ve ikisi de gerekli:

  1. Sinir gpt-4.1'e gore yeniden kalibre edildi (180 -> 360). 180 sayisi
     KIMI'ye gore konmustu; gerekce `CIKARIM_ZAMAN_ASIMI` docstring'inde.
  2. Zaman asimi denemeyi tuketiyor, koşumu oldurmuyor.

⚠️ AMA YALNIZCA ZAMAN ASIMI. Saglayici hatasi (403/429) da yutulsaydi olu
bir anahtar bes denemeyi yakar ve zamanlayici loguna "red | skor 0"
yazilirdi — o satir "kalite kapilari bes plani reddetti" ile AYIRT
EDILEMEZ. Bu deponun tekrar eden korlugu: `hermes -z` birincil hatayi ayni
bicimde yutup yedege dusuyordu ve teshis gunlerce yanlis yone gitti.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan_yaniti(baslik: str = "What Did Sutton Hoo Hide? #Shorts") -> dict:
    return {
        "topic": "konu",
        "visual_anchor": "Sutton Hoo",
        "title": baslik,
        "script": (
            "Sutton Hoo held a ship no one saw arrive. The mound covered an "
            "entire vessel and the timbers had rotted into the sand, leaving "
            "only their iron rivets in place. Diggers traced the hull by those "
            "rivets alone in nineteen thirty nine, working with brushes because "
            "a spade would have destroyed the outline they were following. "
            "Inside lay a helmet, a shield and gold shoulder clasps of "
            "astonishing work, along with silver bowls carried from the far "
            "eastern Mediterranean. No body was ever found in the chamber "
            "itself, and the acid soil may have taken it. "
            "Nobody has opened the second chamber yet."
        ),
        "scenes": [
            {"narration": f"sahne {i}", "search_term": f"Sutton Hoo detay {i}"}
            for i in range(1, 7)
        ],
        "description": "aciklama",
        "tags": ["a", "b", "c"],
    }


def _cevreyi_sustur(monkeypatch):
    monkeypatch.setattr(ya, "_son_basliklar", lambda: [])
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: [])


def test_zaman_asimi_DENEMEYI_yakar_kosumu_degil(monkeypatch):
    """Olculen vakanin kendisi: bir asili cagri koşumu oldurmemeli."""
    _cevreyi_sustur(monkeypatch)
    cagrilar: list[str] = []

    def sahte(system: str, user: str, **_) -> dict:
        cagrilar.append(user)
        if len(cagrilar) == 1:
            raise ya.CikarimZamanAsimi("Hermes CLI inference timed out after 360 seconds")
        return _plan_yaniti()

    monkeypatch.setattr(ya, "_json_completion", sahte)

    plan = ya.generate_content_plan(konu=None)

    assert plan.visual_anchor == "Sutton Hoo"
    assert len(cagrilar) == 2, "zaman asimi denemeyi tuketip devam etmeliydi"


def test_zaman_asimi_GERI_BILDIRIM_eklemiyor(monkeypatch):
    """Ortada elestirilecek bir plan yok — istem buyumemeli."""
    _cevreyi_sustur(monkeypatch)
    istemler: list[str] = []

    def sahte(system: str, user: str, **_) -> dict:
        istemler.append(user)
        if len(istemler) == 1:
            raise ya.CikarimZamanAsimi("timed out")
        return _plan_yaniti()

    monkeypatch.setattr(ya, "_json_completion", sahte)

    ya.generate_content_plan(konu=None)

    assert istemler[0] == istemler[1], "zaman asimi istemi degistirmemeliydi"


def test_SAGLAYICI_hatasi_yutulmuyor(monkeypatch):
    """⚠️ Kapinin asil sinavi: 403 yutulursa olu anahtar 'kalite reddi' gibi gorunur."""
    _cevreyi_sustur(monkeypatch)
    cagrilar: list[str] = []

    def sahte(system: str, user: str, **_) -> dict:
        cagrilar.append(user)
        raise RuntimeError("Error code: 403 - Key limit exceeded (total limit)")

    monkeypatch.setattr(ya, "_json_completion", sahte)

    with pytest.raises(RuntimeError, match="403"):
        ya.generate_content_plan(konu=None)

    assert len(cagrilar) == 1, "saglayici hatasi denemeleri yakmamali, DISARI cikmali"


def test_BES_zaman_asimi_kalite_reddi_gibi_GORUNMUYOR(monkeypatch):
    """Saglayici bes kez asili kalirsa bu bir kalite sonucu degil, ariza."""
    _cevreyi_sustur(monkeypatch)
    cagrilar: list[str] = []

    def sahte(system: str, user: str, **_) -> dict:
        cagrilar.append(user)
        raise ya.CikarimZamanAsimi("timed out")

    monkeypatch.setattr(ya, "_json_completion", sahte)

    with pytest.raises(ya.CikarimZamanAsimi):
        ya.generate_content_plan(konu=None)

    assert len(cagrilar) == 5
    # ⚠️ Tur AYRI olmali: `DistinctTopicUnavailableError` zamanlayici loguna
    # "red" yaziyor ve ariza orada kalite reddine benzerdi.
    assert not issubclass(ya.CikarimZamanAsimi, ya.DistinctTopicUnavailableError)


def test_sinir_KIMI_olcusunun_ustunde_ve_uzun_formatin_altinda():
    """⚠️ Ciplak sayi degil ILISKI olculuyor (`test_kalite_kapisi` kalibi).

    360'in kendisi kutsal degil; kutsal olan iki sey: Shorts siniri artik
    olculen ~120 sn'lik tipik cagrinin epey ustunde, ve uzun formatin
    siniriyla karistirilmamis durumda.
    """
    assert ya.CIKARIM_ZAMAN_ASIMI > 180, "eski KIMI olcusu gpt-4.1'i oldurdu"
    assert ya.CIKARIM_ZAMAN_ASIMI < ya.UZUN_CIKARIM_ZAMAN_ASIMI
    # En kotu durum 5 deneme, ve bu 3 saatlik koşum araligina sigmali.
    assert 5 * ya.CIKARIM_ZAMAN_ASIMI < 3 * 60 * 60
