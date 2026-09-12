"""Ayni slotta reddedilen havuz capasi SIRANIN SONUNA gider.

⚠️ OLCULDU (2026-09-12, 18:38 tetigi, iki koşum, $0,138, 0 yayin). Havuz
sirasi sabitti ve `_yedek_capa_sec` her cagrida ILK uygun capayi aliyordu;
ret capayi butcesi dolana kadar ilk sirada BIRAKIYORDU:

    18:55  Ayasofya  62  kare 7-12 donem uyusmuyor      (1. koşum)
    19:06  Ayasofya  72  kare 3-8, 13-14 donem uyusmuyor (2. koşum, plan 1)
    19:15  Ayasofya  62  kare 9-16 donem uyusmuyor      (2. koşum, plan 2)
    19:19  Baalbek   45  kaynak asamasi                  (capa 3/3 olunca degisti)

Ucu de ayni kusur: Commons kategorisi modern turist fotografi, anlatim
Bizans. Capa ancak `RET_DENEME_BUTCESI` dolunca degisti. `state.json`
(334 olay, 5 Agu - 12 Eyl) ayni deseni kanalin butun tarihinde gosteriyor:

    capanin ilk denemesi             20/143   %14
    AYNI slotta yeniden               1/116   %0,9
    FARKLI slotta yeniden (<24 saat)   6/29   %21
    FARKLI slotta yeniden (>=24 saat)  9/46   %20

Yani butce dogru, israf yalnizca AYNI slottaki tekrarda. Cozum engel degil
ERTELEME: capa listede kalir, sona gider. 24 saatlik soguma bilerek
kullanilmadi — farkli slotta 2,6 saat sonra yayinlar var (Mesa Verde, Petra).
"""

import ast
import inspect
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402
import wikimedia_materials as wm  # noqa: E402

SLOT = "2026-09-12-18"


def _ret(capa: str, slot: str = SLOT) -> dict:
    return {
        "stage": "video",
        "slot": slot,
        "visual_anchor": capa,
        "topic": f"{capa} konusu",
        "visual_alignment_score": 62,
        "rejected_at": "2026-09-12T18:55:06+03:00",
    }


@pytest.fixture
def havuz(monkeypatch):
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", ["Ayasofya", "Baalbek", "Petra"])


# --- siralama --------------------------------------------------------------


def test_AYNI_slotta_reddedilen_capa_SONA_gidiyor(havuz):
    state = {"rejected": [_ret("Ayasofya")], "published": []}

    assert ya.uygun_capalar(state, slot=SLOT) == ["Baalbek", "Petra", "Ayasofya"]


def test_erteleme_ENGEL_degil_listeden_cikarmiyor(havuz):
    """Ucu de bu slotta dustuyse havuz yine ucunu veriyor — 0 capa = uretim durur."""
    state = {
        "rejected": [_ret("Ayasofya"), _ret("Baalbek"), _ret("Petra")],
        "published": [],
    }

    assert sorted(ya.uygun_capalar(state, slot=SLOT)) == ["Ayasofya", "Baalbek", "Petra"]


def test_FARKLI_slottaki_ret_sirayi_BOZMUYOR(havuz):
    """Farkli slotta tekrar %20 ile ilk denemeden bile iyi — dokunulmuyor."""
    state = {"rejected": [_ret("Ayasofya", slot="2026-09-12-16")], "published": []}

    assert ya.uygun_capalar(state, slot=SLOT) == ["Ayasofya", "Baalbek", "Petra"]


def test_BUTCESI_DOLAN_capa_ertelenmiyor_ENGELLENIYOR(havuz):
    """Erteleme butcenin ustune gelmiyor: 3/3 olan capa listede hic yok."""
    state = {
        "rejected": [_ret("Ayasofya", slot=s) for s in ("2026-09-10-06", "2026-09-11-11", SLOT)],
        "published": [],
    }

    assert ya.uygun_capalar(state, slot=SLOT) == ["Baalbek", "Petra"]


def test_slot_verilmezse_SAAT_anahtari(havuz, monkeypatch):
    monkeypatch.setattr(ya, "publication_slot_key", lambda *_a, **_k: SLOT)
    state = {"rejected": [_ret("Ayasofya")], "published": []}

    assert ya.uygun_capalar(state)[0] == "Baalbek"


def test_erteleme_CAPA_ESLEMESINI_kullaniyor(havuz):
    """Ret kaydi kucuk harfle yazilmis olsa da ayni capa: `is_duplicate_visual_anchor`."""
    state = {"rejected": [_ret("ayasofya")], "published": []}

    assert ya.uygun_capalar(state, slot=SLOT)[-1] == "Ayasofya"


def test_capasiz_planlama_reddi_hicbir_seyi_ertelemiyor(havuz):
    """`stage: planning` kaydinin capasi bos — bir capayi yakmadigi gibi ertelemiyor da."""
    state = {"rejected": [_ret("")], "published": []}

    assert ya.uygun_capalar(state, slot=SLOT) == ["Ayasofya", "Baalbek", "Petra"]


# --- yedek kip gercekten SONRAKI capayi aliyor ------------------------------


def _menu(n: int) -> list[dict[str, str]]:
    return [
        {"dosya": f"{i}.jpg", "gosterdigi": f"gorunum {i}", "tarih": "1900"}
        for i in range(1, n + 1)
    ]


@pytest.fixture
def hat(monkeypatch):
    """Istemi yakalar; secilen capaya gore GECERLI bir plan dondurur."""
    yakalanan: dict = {}

    def sahte(system: str, user: str, **_) -> dict:
        yakalanan["user"] = user
        eslesme = re.search(r'every scene:\n"([^"]+)"\n', user)
        capa = eslesme.group(1) if eslesme else "Ephesus"
        yakalanan["capa"] = capa
        return {
            "topic": f"{capa} library facade and its optical trick",
            "visual_anchor": capa,
            "title": f"{capa} facade trick #Shorts",
            "script": " ".join(
                [
                    f"The library of {capa} stood at the end of a marble street and its",
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
                {"narration": f"cumle {i}", "search_term": f"{capa} terim {i}"}
                for i in range(1, 7)
            ],
            "description": "aciklama",
            "tags": ["archaeology", "ancient rome", "history"],
        }

    monkeypatch.setattr(ya, "_json_completion", sahte)
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [])
    monkeypatch.setattr(ya, "_son_basliklar", lambda: [])
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_kw: _menu(40))
    monkeypatch.setattr(wm, "vikipedi_ozeti", lambda *_a, **_k: "It was a city.")
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", ["Baalbek", "Ephesus"])
    return yakalanan


def test_yedek_kip_bu_slotta_DUSEN_capayi_degil_SONRAKINI_aliyor(hat, monkeypatch):
    monkeypatch.setattr(ya, "load_state", lambda: {"rejected": [_ret("Baalbek")], "published": []})

    plan = ya.generate_content_plan(slot=SLOT)

    assert hat["capa"] == "Ephesus"
    assert plan.visual_anchor == "Ephesus"


def test_kontrol_ret_YOKSA_ilk_capa(hat, monkeypatch):
    """Ayni kurulum, ret yok: Baalbek yine ilk sirada — degisiklik sirayi baska turlu bozmuyor."""
    monkeypatch.setattr(ya, "load_state", lambda: {"rejected": [], "published": []})

    assert ya.generate_content_plan(slot=SLOT).visual_anchor == "Baalbek"


def test_kontrol_BASKA_slotun_reddi_ilk_capayi_degistirmiyor(hat, monkeypatch):
    monkeypatch.setattr(
        ya, "load_state", lambda: {"rejected": [_ret("Baalbek", slot="2026-09-12-16")], "published": []}
    )

    assert ya.generate_content_plan(slot=SLOT).visual_anchor == "Baalbek"


# --- run_cycle slotunu HER cagriya geciriyor -------------------------------


def test_run_cycle_her_plan_ve_havuz_cagrisina_slot_veriyor():
    """Saatten yeniden hesaplansaydi koşum ici yeniden planlama kendi retlerini
    gormezdi (koşum saat sinirini geciyor: 18:56'da baslayan koşum 19:06 ve
    19:15'te ret yazdi, ucu de "…-18"). Yeni bir cagri noktasi unutulmasin."""
    agac = ast.parse(inspect.getsource(ya.run_cycle))
    cagrilar = [
        dugum
        for dugum in ast.walk(agac)
        if isinstance(dugum, ast.Call)
        and getattr(dugum.func, "id", "") in {"generate_content_plan", "uygun_capalar"}
    ]

    assert len(cagrilar) >= 4, "run_cycle'da plan/havuz cagrisi bekleniyordu"
    for cagri in cagrilar:
        anahtarlar = {kw.arg for kw in cagri.keywords}
        assert "slot" in anahtarlar, ast.unparse(cagri)[:100]
