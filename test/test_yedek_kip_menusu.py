"""Yedek kip de ARSIV-ONCE calisiyor — menu artik iki kipte de istemde.

⚠️ OLCULDU (2026-08-17). ARSIV MENUSU blogu yalnizca `generate_content_plan`in
`if konu:` dalinda kuruluyordu, yani menu / `source_file` / `source_file_2`
disiplininin TAMAMI kuyruk kipine ozeldi. Yedek kipte model menuyu hic
gormuyordu:

  * `source_file`   istenmiyordu -> sahne gorseli tam metin aramasindan
  * `source_file_2` istenmiyordu -> ikinci gorsel "bulunamiyor" degil hic
    SORULMUYORDU, ve bos kalinca kor kategori yedegine dusuluyordu
    (`ikincil_gorseller`), yani gecenin butun kusurlarinin kaynagi.

O gecenin uc koşumunun ucu de yedek kipteydi (kuyruk fiilen olu).

⚠️ Sebep tavuk-yumurtaydi: menu bir OZNE ister, ozne ise modelden geliyordu.
Kanal sahibi ozneyi KODUN secmesine karar verdi (2026-08-17), boylece menu
istem kuruldugu anda cekilebiliyor ve yedek kip kuyruk kipinin yoluna
giriyor. Model yine aciyi, basligi ve sahneleri yaziyor.

⚠️ Menulu yolun ise yaradigi KOD YAZILMADAN olculdu (ayni istem, kuyruk
kipi): Ephesus 8 sahnenin 5'inde, Borobudur 8'inde `source_file_2` doldu —
16 sahnenin 13'u. Yedek kipteki karsiligi yapisal olarak 0'di.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402
import wikimedia_materials as wm  # noqa: E402

_GECERLI_PLAN = {
    "topic": "Ephesus library",
    "visual_anchor": "Ephesus",
    "title": "Ephesus",
    # ⚠️ Senaryo GERCEKTEN 80-150 kelime olmali: kelime kapisi bes denemeyi
    # de reddedip `DistinctTopicUnavailableError` firlatiyor ve testin
    # olcmek istedigi sey (istemin icerigi) hic gorulmuyor.
    "script": " ".join(
        [
            "The library of Ephesus stood at the end of a marble street and its",
            "facade was built to impress travellers arriving from the harbour.",
            "Builders raised the front wall with columns of different heights so",
            "that the middle appeared taller than it truly was, a trick of the eye",
            "that made the building look larger from below. Inside, niches held",
            "scrolls away from damp walls, and a narrow gap in the masonry carried",
            "air around the collection. An earthquake brought the roof down and",
            "the shelves were lost, yet the facade was raised again from its own",
            "fallen stones in the twentieth century. What stands today is the",
            "front of a building whose rooms no longer exist behind it.",
        ]
    ),
    "scenes": [
        {"narration": f"cumle {i}", "search_term": f"Ephesus terim {i}"}
        for i in range(1, 7)
    ],
    "description": "aciklama",
    "tags": ["ephesus", "ancient rome", "archaeology"],
}


@pytest.fixture
def hat(monkeypatch):
    """Istemi yakalar; ag ve model cagrisi yok."""
    yakalanan: dict = {}

    def sahte(system: str, user: str, **_) -> dict:
        yakalanan["user"] = user
        return dict(_GECERLI_PLAN)

    monkeypatch.setattr(ya, "_json_completion", sahte)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [])
    monkeypatch.setattr(ya, "_son_basliklar", lambda: [])
    monkeypatch.setattr(wm, "vikipedi_ozeti", lambda *_a, **_k: "Ephesus was a city.")
    return yakalanan


def _menu(n: int) -> list[dict[str, str]]:
    return [
        {"dosya": f"{i}.jpg", "gosterdigi": f"gorunum {i}", "tarih": "1900"}
        for i in range(1, n + 1)
    ]


# --- Asil kazanim ---------------------------------------------------------


def test_yedek_kipte_ARSIV_MENUSU_isteme_giriyor(hat, monkeypatch):
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_kw: _menu(40))

    ya.generate_content_plan()

    assert "ARCHIVE MENU" in hat["user"]


def test_yedek_kipte_IKINCI_gorsel_isteniyor(hat, monkeypatch):
    """⚠️ Asil kusur buydu: alan bos kalmiyordu, HIC SORULMUYORDU."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_kw: _menu(40))

    ya.generate_content_plan()

    assert "source_file_2" in hat["user"]
    assert "Leave source_file_2 empty for every scene" not in hat["user"]


def test_capa_KODUN_sectigi_olmali(hat, monkeypatch):
    """Ozne sabitleniyor; model kisa listeden kendi secmiyor."""
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", ["Ephesus"])
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_kw: _menu(40))

    ya.generate_content_plan()

    assert "Build this video about this exact subject" in hat["user"]
    assert "Ephesus" in hat["user"]


def test_menusu_YETMEYEN_capa_atlaniyor(hat, monkeypatch):
    """⚠️ `ikinci_gorsel_istenebilir` esigi: menu < sahne x yuva ise o capa
    her sahneye iki AYRI dosya veremez ve secilmemeli."""
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", ["Ince", "Bol"])
    monkeypatch.setattr(
        ya, "arsiv_envanteri", lambda k, **_kw: _menu(4) if k == "Ince" else _menu(40)
    )

    secilen = ya._yedek_capa_sec(
        ["Ince", "Bol"], bicim=ya.SHORTS_BICIMI, envanter_sinir=40, sahne_sayisi=6
    )

    assert secilen == "Bol"


# --- Korunacak davranislar (regresyon bekcileri) --------------------------


def test_havuz_TUKENMISSE_eski_davranis(hat, monkeypatch):
    """⚠️ Menu bir IYILESTIRME, on kosul degil. Havuz bitince uretim
    durmamali — yoksa tek bir tukenme butun hatti kilitler."""
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", [])
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_kw: _menu(40))

    ya.generate_content_plan()

    assert "Build this video about this exact subject" not in hat["user"]
    assert "unused editorial shortlist" in hat["user"]


def test_menu_CEKILEMEZSE_kosum_durmuyor(hat, monkeypatch):
    """⚠️ Ayni gerekce `arsiv_envanteri`de: tek bir 429 koşumu coplememeli.

    ⚠️ Ag hatasi burada FIRLATILARAK taklit EDILMIYOR, cunku uretimde oyle
    gorunmuyor: `arsiv_envanteri` istisnayi KENDI ICINDE yutup bos liste
    donuyor (`test_arsiv_envanteri.test_ag_hatasi_uretimi_durdurmuyor`).
    Firlatan bir taklit, `alinti_kusuru` gibi ayni fonksiyonu cagiran baska
    yerlerde gercekte olmayan bir cokme uretirdi — yani testin kendisi
    yanlis bir dunyayi olcerdi.
    """
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", ["Ephesus"])
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_kw: [])

    plan = ya.generate_content_plan()

    assert plan.topic, "menu cekilemese de plan uretilmeli"
    assert "unused editorial shortlist" in hat["user"]


def test_KULLANILMIS_capa_secilmiyor(hat, monkeypatch):
    """Capa tekrar kapisi kalkmadi: yanan capa yeniden secilmemeli."""
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", ["Yanan", "Temiz"])
    monkeypatch.setattr(ya, "engellenen_capalar", lambda _s=None: ["Yanan"])
    gorulen: list[str] = []

    def menu(k, **_kw):
        gorulen.append(k)
        return _menu(40)

    monkeypatch.setattr(ya, "arsiv_envanteri", menu)

    ya.generate_content_plan()

    assert "Yanan" not in gorulen
