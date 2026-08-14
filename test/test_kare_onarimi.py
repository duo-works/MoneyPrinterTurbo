"""Bozuk kare videoyu coplemez — gorseli degistirilir.

⚠️ Olculdu (2026-08-14, Roman Dodecahedron). Video gorsel 89, altyazi 88
aldi — kanalin yayinlanmis en iyi videosu 90 — ve SEKIZ karenin YEDISI
temizdi. Tek kusur 6. karedeydi: dodekahedron yerine faseti taslar (montaj
gozle de dogrulandi, hakem hakliydi).

Hat o videoyu cope atip konuyu bastan planliyordu ve yeniden deneme daha
kotusunu uretti (88, uc kusur). Oysa hakem hangi karenin bozuk oldugunu
ZATEN soyluyor.

⚠️ Anlatim DEGISMIYOR: ses `plan.script`ten uretiliyor ve zaten kayitli.
Degisen yalnizca o an gosterilen resim, ve secim menudeki gercek dosyalar
arasindan yapiliyor — rastgele bir dosya koymak, kapatilan anlatim-gorsel
uyusmazligini geri acardi.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _menu(*adlar: str) -> list[dict[str, str]]:
    return [{"dosya": ad, "gosterdigi": f"{ad} gorseli", "tarih": "1900"} for ad in adlar]


def _plan(*alintilar: str) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="Roman Dodecahedron",
        title="baslik",
        script="metin",
        scenes=[
            {
                "narration": f"sahne {sira} anlatimi",
                "search_term": f"Roman Dodecahedron detay {sira}",
                "kaynak_dosya": ad,
            }
            for sira, ad in enumerate(alintilar, 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def _review(*kusurlar: str) -> ya.QualityReview:
    return ya.QualityReview(False, 89, 88, agir_kusurlar=list(kusurlar))


# --- Kare numarasi cikarma ------------------------------------------------


def test_kare_numarasi_SAHNEYE_cevriliyor():
    """⚠️ 2026-08-14: sahne basina IKI kare var (`KARE_YUVASI`).

    Hakem KARE numarasi bildiriyor, onarim ise `plan.scenes` uzerinde
    calisiyor. Cevrim yapilmazsa hakemin isaretledigi kusur YANLIS sahneyi
    onartir ve bozuk kare videoda kalir.

        kare 1-2 -> sahne 1 · kare 3-4 -> sahne 2 · kare 5-6 -> sahne 3
    """
    review = _review("kare 6: konuyla ilgisiz modern goruntu", "kare 2: donem uyusmuyor")

    assert ya.agir_kusurlu_kareler(review) == [1, 3]


def test_kareden_sahneye_esleme_tablosu():
    assert [ya.kareden_sahneye(k) for k in (1, 2, 3, 4, 5, 6)] == [1, 1, 2, 2, 3, 3]


def test_AYNI_SAHNENIN_iki_karesi_bir_kez_sayiliyor():
    review = _review("kare 3: donem uyusmuyor", "kare 4: konuyla ilgisiz modern goruntu")

    assert ya.agir_kusurlu_kareler(review) == [2]


def test_ayni_kare_iki_kusurla_bir_kez_sayiliyor():
    review = _review("kare 3: donem uyusmuyor", "kare 3: konuyla ilgisiz modern goruntu")

    assert ya.agir_kusurlu_kareler(review) == [2]


def test_kusur_yoksa_bos():
    assert ya.agir_kusurlu_kareler(_review()) == []


# --- Onarim ----------------------------------------------------------------


def test_bozuk_karenin_gorseli_degisiyor(monkeypatch):
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: _menu("A.jpg", "B.jpg", "YENI.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u: {"picks": [{"n": 2, "source_file": "YENI.jpg"}]}
    )
    plan = _plan("A.jpg", "B.jpg")

    # ⚠️ "kare 3" -> SAHNE 2 (sahne basina iki kare). Eski test "kare 2"
    # diyordu ve o artik sahne 1 demek; sayiyi guncellemek testin ne
    # olctugunu degistirmez, cevrimin yerinde oldugunu dogrular.
    degisen = ya.kareyi_onar(plan, _review("kare 3: konuyla ilgisiz modern goruntu"))

    assert degisen == [2]
    assert plan.scenes[1]["kaynak_dosya"] == "YENI.jpg"
    assert plan.scenes[0]["kaynak_dosya"] == "A.jpg", "temiz kare dokunulmamali"


def test_anlatim_DEGISMIYOR(monkeypatch):
    """⚠️ Ses zaten kayitli; anlatimi degistirmek sesle alt yaziyi ayirirdi."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: _menu("A.jpg", "YENI.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u: {"picks": [{"n": 1, "source_file": "YENI.jpg"}]}
    )
    plan = _plan("A.jpg")
    onceki = plan.scenes[0]["narration"]

    ya.kareyi_onar(plan, _review("kare 1: konuyla ilgisiz modern goruntu"))

    assert plan.scenes[0]["narration"] == onceki


def test_uydurulan_dosya_kabul_edilmiyor(monkeypatch):
    """Menude olmayan bir ad, onarimi kusurun kaynagina cevirirdi."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: _menu("A.jpg", "YENI.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u: {"picks": [{"n": 1, "source_file": "uydurma.jpg"}]}
    )
    plan = _plan("A.jpg")

    assert ya.kareyi_onar(plan, _review("kare 1: modern")) == []
    assert plan.scenes[0]["kaynak_dosya"] == "A.jpg"


def test_ZATEN_KULLANILAN_dosya_secilemiyor(monkeypatch):
    """Ayni gorselin iki sahnede cikmasi kullanicinin birebir sikayetiydi."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: _menu("A.jpg", "B.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u: {"picks": [{"n": 2, "source_file": "A.jpg"}]}
    )
    plan = _plan("A.jpg", "B.jpg")

    assert ya.kareyi_onar(plan, _review("kare 2: modern")) == []


def test_menu_tukendiyse_bos_donuyor(monkeypatch):
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: _menu("A.jpg"))
    plan = _plan("A.jpg")

    assert ya.kareyi_onar(plan, _review("kare 1: modern")) == []


def test_cikarim_dusunce_kosum_devam_ediyor(monkeypatch):
    """⚠️ Onarim bir IYILESTIRME; patlarsa koşumu oldurmemeli."""

    def patla(*_a, **_k):
        raise RuntimeError("hermes timeout")

    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: _menu("A.jpg", "YENI.jpg"))
    monkeypatch.setattr(ya, "_json_completion", patla)
    plan = _plan("A.jpg")

    assert ya.kareyi_onar(plan, _review("kare 1: modern")) == []


def test_ISTEMDEKI_menuye_bakiyor(monkeypatch):
    """Kapiyla ayni kural: menu anahtari huni konusu, planin capasi degil."""
    menuler = {"Cutty Sark": _menu("A.jpg", "YENI.jpg"), "Jock Willis": _menu("Z.jpg")}
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda k: menuler.get(k, []))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u: {"picks": [{"n": 1, "source_file": "YENI.jpg"}]}
    )
    plan = _plan("A.jpg")
    plan.visual_anchor = "Jock Willis"

    assert ya.kareyi_onar(plan, _review("kare 1: modern"), "Cutty Sark") == [1]


# --- Hatta baglanti --------------------------------------------------------


def test_eski_yol_YEDEK_olarak_duruyor():
    """Menusu olmayan konularda tek care arama terimlerini revize etmek."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def run_cycle(") :]

    assert "refine_search_terms(plan, review)" in govde


# ⚠️ Cagri yerinin GERCEKTEN calistigi `test_onarim_dali_calisiyor.py`de
# yuruttulerek dogrulaniyor, burada dize arayarak DEGIL. Sebep olculdu
# (2026-08-14): bu dosyada eskiden `"kareyi_onar(plan, review" in govde`
# diye bir kontrol vardi; dize DOGRUYDU ama cagriya `konu` diye var olmayan
# bir degisken veriliyordu. Test yesil kaldi, uc uretim koşumu video render
# edip `NameError` ile coktu. Kaynak metninde dize aramak, kodun
# calistigini kanitlamaz.
