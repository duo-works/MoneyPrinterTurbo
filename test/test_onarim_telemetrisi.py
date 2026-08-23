"""Onarim KOR bir yazimdi; artik sonucu olculuyor (2026-08-23).

⚠️ NEDEN — olculdu, `state.json`in 19 Agu sonrasi kayitlariyla:

    video asamasi redleri            : 22   (redlerin %47'si)
    agir kusur TASIYAN               : 22/22 (%100)
    saf skor reddi                   :  0/22
    onarim kapisi ACIK olan          : 11/22

Yani onarim redlerin YARISINDA calisiyor ve video yine oluyor. Neden oldugu
hicbir yerde yazmiyordu:

  · `ℹ️ kare onarımı: ...` yalnizca stdout'a basiliyor ve `uret.sh` cikti
    dosyasini `mktemp` ile acip cikista SILIYOR;
  · `plan_redlerini_yaz` yalnizca "reddedildi" satirlarini suzuyor;
  · `state.json`daki red kaydinda onarimla ilgili TEK alan yoktu.

Sonucu: 21 Agu'da sevk edilen onarim duzeltmesi iki gun boyunca
DOGRULANAMADI. Bu dosya o korlugu kapatan iki parcayi sinar:

  1. `onarim_sonucu` — istenen dosya gercekten geldi mi (`tuttu`),
  2. `kareyi_onar(engellenen=...)` — tutmayan secim bir daha sunulmuyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _sahneler(**alanlar) -> list[dict]:
    taban = {
        "sahne": 1,
        "terim": "t",
        "kaynak_dosya": "A.jpg",
        "kaynak_dosya_2": "B.jpg",
        "gelen": "",
        "gelen_2": "",
        "anlatim": "anlatim",
    }
    return [{**taban, **alanlar}]


def test_TESLIM_EDILEN_onarim_tuttu_diyor():
    talep = [{"sahne": 1, "alan": "kaynak_dosya", "istenen": "YENI.jpg"}]

    sonuc = ya.onarim_sonucu(talep, _sahneler(gelen="File:YENI.jpg"))

    assert sonuc[0]["tuttu"] is True
    assert sonuc[0]["gelen"] == "YENI.jpg"


def test_TESLIM_EDILMEYEN_onarim_tutmadi_diyor():
    """⚠️ Asil vaka: onarim plani degistiriyor ama teslim zinciri
    (`_alinti_adayi` → `_tekrar_mi` → Met → Commons aramasi) dosyayi
    dusurup sahneyi DENETLENMEMIS bir arama sonucuyla dolduruyor."""
    talep = [{"sahne": 1, "alan": "kaynak_dosya", "istenen": "YENI.jpg"}]

    sonuc = ya.onarim_sonucu(talep, _sahneler(gelen="File:BASKA.jpg"))

    assert sonuc[0]["tuttu"] is False
    assert sonuc[0]["istenen"] == "YENI.jpg"
    assert sonuc[0]["gelen"] == "BASKA.jpg"


def test_IKINCIL_onarim_gelen_2_ile_olculuyor():
    """⚠️ `kareyi_onar` bozuk olan YUVAYA yaziyor; ikincil onarim `gelen`e
    bakilarak olculseydi HER ikincil onarim 'tutmadi' gorunurdu."""
    talep = [{"sahne": 1, "alan": "kaynak_dosya_2", "istenen": "YENI2.jpg"}]

    sonuc = ya.onarim_sonucu(
        talep, _sahneler(gelen="File:BIRINCIL.jpg", gelen_2="File:YENI2.jpg")
    )

    assert sonuc[0]["tuttu"] is True, "ikincil teslim `gelen_2`den okunmali"


def test_FILE_oneki_karsilastirmayi_bozmuyor():
    """⚠️ Kredi basliklari 'File:' onekli, plan alanlari degil. Onek
    temizlenmezse HER onarim 'tutmadi' gorunur ve kapali dongu saglam
    dosyalari engellemeye baslar."""
    talep = [{"sahne": 1, "alan": "kaynak_dosya", "istenen": "File:YENI.jpg"}]

    sonuc = ya.onarim_sonucu(talep, _sahneler(gelen="YENI.jpg"))

    assert sonuc[0]["tuttu"] is True


def test_BOS_istek_tuttu_SAYILMIYOR():
    """Bos istenen ile bos gelen esit olurdu; onarim yapilmamis sayilmali."""
    talep = [{"sahne": 1, "alan": "kaynak_dosya", "istenen": ""}]

    assert ya.onarim_sonucu(talep, _sahneler(gelen=""))[0]["tuttu"] is False


def test_ONARIM_DENENMEDIYSE_liste_bos():
    assert ya.onarim_sonucu([], _sahneler()) == []


# --- Kapali dongunun ikinci yarisi: engellenen secim -------------------------


def _onarim_hazirla(monkeypatch, *, menu_dosyalari: list[str], secim: str):
    plan = ya.ContentPlan(
        topic="konu",
        visual_anchor="Capa",
        title="baslik",
        script="cumle bir. cumle iki.",
        scenes=[
            {"narration": "bir", "search_term": "t1", "kaynak_dosya": "ESKI.jpg"},
        ],
        description="a",
        tags=["x"],
    )
    monkeypatch.setattr(
        ya,
        "arsiv_envanteri",
        lambda _k, **_: [
            {"dosya": ad, "gosterdigi": "dogru nesne", "tarih": "1900"}
            for ad in menu_dosyalari
        ],
    )
    monkeypatch.setattr(ya, "menuyu_zenginlestir", lambda menu, *_a, **_k: menu)
    monkeypatch.setattr(
        ya,
        "_json_completion",
        lambda s, u, **_: {"picks": [{"n": 1, "source_file": secim}]},
    )
    return plan


def _inceleme() -> ya.QualityReview:
    return ya.QualityReview(
        publishable=False,
        visual_alignment_score=72,
        subtitle_readability_score=90,
        issues=["Frame 1 wrong"],
        revised_search_terms=[],
        problem_scene_numbers=[],
        kareler=[],
        agir_kusurlar=["kare 1: konuyla ilgisiz modern goruntu"],
    )


def test_ENGELLENEN_dosya_bir_daha_SECILMIYOR(monkeypatch):
    """⚠️ Kapali dongunun ikinci yarisi.

    Teslim zinciri bir dosyayi bir kez dusurduyse ikinci turda da dusurur;
    ayni secimi yeniden sunmak onarim butcesini bosa harcar.

    Mutasyon: `engellenen`i `kullanilan`a eklememek bu testi dusurur.
    """
    plan = _onarim_hazirla(
        monkeypatch, menu_dosyalari=["TUTMAYAN.jpg", "IYI.jpg"], secim="TUTMAYAN.jpg"
    )

    degisen = ya.kareyi_onar(plan, _inceleme(), "konu", engellenen={"TUTMAYAN.jpg"})

    assert degisen == [], "engellenen dosya secilmemeliydi"
    assert plan.scenes[0]["kaynak_dosya"] == "ESKI.jpg"


def test_ENGELLENMEYEN_dosya_NORMAL_seciliyor(monkeypatch):
    """⚠️ Regresyon kilidi: engelleme her seyi kapatirsa onarim hic calismaz."""
    plan = _onarim_hazirla(
        monkeypatch, menu_dosyalari=["TUTMAYAN.jpg", "IYI.jpg"], secim="IYI.jpg"
    )

    degisen = ya.kareyi_onar(plan, _inceleme(), "konu", engellenen={"TUTMAYAN.jpg"})

    assert degisen == [1]
    assert plan.scenes[0]["kaynak_dosya"] == "IYI.jpg"


def test_ENGELLENEN_verilmezse_davranis_AYNI(monkeypatch):
    """Geriye donuk uyum: parametreyi gecmeyen cagiran bugunku sonucu alir."""
    plan = _onarim_hazirla(monkeypatch, menu_dosyalari=["IYI.jpg"], secim="IYI.jpg")

    assert ya.kareyi_onar(plan, _inceleme(), "konu") == [1]


# --- Baglanti: kayit yollari -------------------------------------------------


def test_ONARIM_ALANI_hem_RED_hem_YAYIN_kaydinda():
    """⚠️ Yalnizca red yoluna yazilsaydi telemetri yalnizca BASARISIZ
    onarimlari gorurdu ve 'onarim ise yariyor mu' sorusu yapisal olarak
    cevaplanamazdi — kapinin acilmasinin butun amaci buydu.

    ⚠️ KAYNAK AYRISTIRILIYOR, dize sayilmiyor: bu oturumda metne cakili
    testler yedi kez kirildi.
    """
    import ast

    agac = ast.parse(Path(ya.__file__).read_text(encoding="utf-8"))
    onarimli_stage: set[str] = set()
    yayin_kaydinda = False
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Dict):
            continue
        anahtarlar = {
            k.value
            for k in dugum.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        if "onarim" not in anahtarlar:
            continue
        if "stage" in anahtarlar:
            for anahtar, deger in zip(dugum.keys, dugum.values):
                if (
                    isinstance(anahtar, ast.Constant)
                    and anahtar.value == "stage"
                    and isinstance(deger, ast.Constant)
                ):
                    onarimli_stage.add(str(deger.value))
        elif {"topic", "visual_anchor", "title"} <= anahtarlar:
            yayin_kaydinda = True

    assert "video" in onarimli_stage, "video red kaydinda `onarim` yok"
    assert yayin_kaydinda, "yayin kaydinda `onarim` yok"
