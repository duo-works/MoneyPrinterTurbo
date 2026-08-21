"""Onarilan plan RENDER EDILMEDEN dongu bitmemeli (2026-08-22).

⚠️ OLCULDU — 41 telemetrili red slotu:

    son denemesi ONARILABILIR olan        : 14 slot (%34)
    bunlarin skor esigini ZATEN gecenleri :  6 slot

    Persepolis 78 (1 sahne) · King Philip's War 78 (1) · Moai 80 (1)
    Tikal 78 (1) · PETN 78 (2) · May Ayim 85 (1)

Alti slot TEK RENDER uzaktaydi. `kareyi_onar` denemenin SONUNDA calisiyor ve
plani BIR SONRAKI deneme icin degistiriyor; ucuncu denemede yapilan onarim
hicbir zaman render edilmiyordu.

Canli hali (May Ayim, 21 Agu 21:05): 72/16 -> 75/8 -> 85/2 ve butce bitti.
Bir sonraki tetige 106 dakika vardi.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _review(gorsel, *, agir=None, altyazi=85) -> ya.QualityReview:
    return ya.QualityReview(False, gorsel, altyazi, [], agir_kusurlar=list(agir or []))


def _kur(monkeypatch, tmp_path, akis, *, onarim=True):
    """`run_cycle`i aga cikmadan kosturur; KAC DENEME yapildigini dondurur.

    `akis` bitince son inceleme tekrarlanir — bu bilincli: testin olctugu sey
    "kac deneme yapildi", "akis kac uzun" degil. Akisi tavandan uzun tutmak
    testi tavanin kendisine bagimli kilardi.
    """
    durum = {"published": [], "rejected": [], "completed_slots": []}
    monkeypatch.setattr(ya, "load_state", lambda: durum)
    monkeypatch.setattr(ya, "save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)
    monkeypatch.setattr(
        ya, "create_review_montage", lambda *_a, **_k: tmp_path / "m.jpg"
    )
    # ⚠️ `kareyi_onar` HER ZAMAN onariyor (ya da hic): testin degiskeni bu.
    monkeypatch.setattr(ya, "kareyi_onar", lambda *_a, **_k: [1] if onarim else [])
    monkeypatch.setattr(ya, "refine_search_terms", lambda plan, *_a, **_k: plan)

    sayac = {"deneme": 0, "plan": 0}

    # ⚠️ KACAK DONGU KORUMASI. Dongu `for` degil `while` ve yanlis bir tavan
    # onu sonsuza cevirebilir. Mutasyon testinde tam bu oldu: tavani kaldiran
    # surum pytest'i ON DAKIKA dondurdu ve kaynak canli checkout'ta mutasyonlu
    # kaldi. Asili kalan test, DUSEN testten cok daha kotu — burada sesli olur.
    KACAK_SINIRI = ya.AZAMI_DENEME + ya.ONARIM_EK_DENEME + 3

    def _uret(*_a, **_k):
        sayac["deneme"] += 1
        if sayac["deneme"] > KACAK_SINIRI:
            raise AssertionError(
                f"kacak dongu: {sayac['deneme']} deneme, tavan "
                f"{ya.AZAMI_DENEME + ya.ONARIM_EK_DENEME}"
            )
        return (
            "gorev",
            tmp_path / "v.mp4",
            tmp_path / "s.txt",
            [],
            0,
            tmp_path / "malzeme",
        )

    monkeypatch.setattr(ya, "run_generator", _uret)

    def _plan_uret(*_a, **_k):
        sayac["plan"] += 1
        return ya.ContentPlan(
            topic=f"konu-{sayac['plan']}",
            visual_anchor=f"capa-{sayac['plan']}",
            title="baslik",
            script="metin",
            scenes=[{"narration": "x", "search_term": "y"} for _ in range(6)],
            description="aciklama",
            tags=["a", "b", "c"],
        )

    monkeypatch.setattr(ya, "generate_content_plan", _plan_uret)

    sira = list(akis)

    def _inceleme(*_a, **_k):
        return sira.pop(0) if len(sira) > 1 else sira[0]

    monkeypatch.setattr(ya, "review_video", _inceleme)

    ya.run_cycle(konu_override="Gobekli Tepe", dry_run=True)
    return sayac["deneme"]


# --- Cekirdek davranis ------------------------------------------------------


def test_ONARIM_son_denemede_butceyi_UZATIYOR(monkeypatch, tmp_path):
    """⚠️ ASIL TEST — May Ayim'in birebir sekli: her deneme onarilabilir,
    her deneme onariliyor. Bugune kadar dongu UC denemede bitiyordu."""
    deneme = _kur(monkeypatch, tmp_path, [_review(72)])

    assert deneme == ya.AZAMI_DENEME + ya.ONARIM_EK_DENEME, (
        f"onarim butceyi uzatmadi: {deneme} deneme yapildi"
    )


def test_uzatma_TAVANLI(monkeypatch, tmp_path):
    """⚠️ Her onarim yeni bir onarim dogurabilir; sinirsiz uzatma slotu
    kilitlerdi. Tavan `AZAMI_DENEME + ONARIM_EK_DENEME`."""
    deneme = _kur(monkeypatch, tmp_path, [_review(72)])

    assert deneme <= ya.AZAMI_DENEME + ya.ONARIM_EK_DENEME
    assert ya.ONARIM_EK_DENEME >= 1, "ek deneme yoksa kusur geri gelir"


def test_ONARIM_YOKSA_butce_DEGISMIYOR(monkeypatch, tmp_path):
    """⚠️ Regresyon kilidi: onarim olmayan koşumda taban butce aynen kalmali,
    yoksa bu degisiklik her koşumu pahalilastirirdi."""
    deneme = _kur(monkeypatch, tmp_path, [_review(72)], onarim=False)

    assert deneme == ya.AZAMI_DENEME, f"onarimsiz koşum {deneme} deneme yapti"


def test_YAYIN_dongunun_ilk_denemesinde_kesiyor(monkeypatch, tmp_path):
    """Uzatma yayin kapisini gevsetmiyor — gecen video hemen cikiyor."""
    yayinlanabilir = ya.QualityReview(True, 90, 90, [], [])
    deneme = _kur(monkeypatch, tmp_path, [yayinlanabilir])

    assert deneme == 1


def test_AGIR_KUSURLU_ama_onarilabilir_render_EDILIYOR(monkeypatch, tmp_path):
    """⚠️ May Ayim'in son denemesi tam buydu: skor 85, iki agir kusur karesi
    (tek sahne). `f5034ee` onu onarilabilir yapti, bu degisiklik de onarilmis
    plani RENDER ediyor."""
    agir = [
        "kare 3: konuyla ilgisiz modern goruntu",
        "kare 4: konuyla ilgisiz modern goruntu",
    ]
    deneme = _kur(monkeypatch, tmp_path, [_review(85, agir=agir)])

    assert deneme > ya.AZAMI_DENEME, (
        "85 puanli, tek sahnesi bozuk video icin ek deneme verilmedi"
    )


# --- Sabitler ---------------------------------------------------------------


def test_sabitler_KODDAN_geliyor():
    """⚠️ `range(1, 4)` govdeye gomuluydu ve iki yerde `attempt < 3` olarak
    tekrarlaniyordu; tavani degistirmek uc yeri birden tutturmayi
    gerektiriyordu."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def run_cycle(") :]
    govde = govde[: govde.index("\ndef ", 10)]

    assert "range(1, 4)" not in govde, "deneme tavani hala govdeye gomulu"
    assert "attempt < 3" not in govde, "yeniden planlama siniri hala sabit"
    assert "azami_deneme" in govde


@pytest.mark.parametrize("ad", ["AZAMI_DENEME", "ONARIM_EK_DENEME"])
def test_sabit_TANIMLI(ad):
    assert isinstance(getattr(ya, ad), int)


def test_taban_butce_DEGISMEDI():
    """⚠️ Bu bir butce buyutmesi degil: taban 3, yalnizca ONARIM uzatiyor."""
    assert ya.AZAMI_DENEME == 3


def test_MUTLAK_TAVAN_dongu_kosulunda(monkeypatch, tmp_path):
    """⚠️ SONSUZ DONGU SINIFI — `for`dan `while`a gecerken ACILDI.

    Olculdu, iki kez: tavan hesabini bozan mutasyon pytest'i on dakika
    dondurdu ve kaynak CANLI CHECKOUT ta mutasyonlu kaldi. Test kurgusuna
    kacak sayaci koymak yetmedi (baska test dosyalarinin kendi kurgulari
    var), o yuzden savunma KODA kondu: dongu kosulu `AZAMI_TOPLAM_DENEME`yi
    de okuyor.

    Bu test o kosulu kilitliyor: `azami_deneme` bozulsa bile tavan asilamaz.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def run_cycle(") :]
    govde = govde[: govde.index("\ndef ", 10)]

    assert "while attempt <" in govde, "deneme dongusu bulunamadi"
    bas = govde.index("while attempt <")
    kosul = govde[bas : govde.index(":", bas)]
    assert "AZAMI_TOPLAM_DENEME" in kosul, (
        f"dongu kosulu mutlak tavani okumuyor — sonsuz koşum riski: {kosul!r}"
    )


def test_mutlak_tavan_iki_sabitin_TOPLAMI():
    """Ucuncu bir sayi ICAT EDILMEDI; tavan tureti."""
    assert ya.AZAMI_TOPLAM_DENEME == ya.AZAMI_DENEME + ya.ONARIM_EK_DENEME
