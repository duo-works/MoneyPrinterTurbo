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
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "B.jpg", "YENI.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u, **_: {"picks": [{"n": 2, "source_file": "YENI.jpg"}]}
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
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "YENI.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u, **_: {"picks": [{"n": 1, "source_file": "YENI.jpg"}]}
    )
    plan = _plan("A.jpg")
    onceki = plan.scenes[0]["narration"]

    ya.kareyi_onar(plan, _review("kare 1: konuyla ilgisiz modern goruntu"))

    assert plan.scenes[0]["narration"] == onceki


def test_uydurulan_dosya_kabul_edilmiyor(monkeypatch):
    """Menude olmayan bir ad, onarimi kusurun kaynagina cevirirdi."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "YENI.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u, **_: {"picks": [{"n": 1, "source_file": "uydurma.jpg"}]}
    )
    plan = _plan("A.jpg")

    assert ya.kareyi_onar(plan, _review("kare 1: modern")) == []
    assert plan.scenes[0]["kaynak_dosya"] == "A.jpg"


def test_ZATEN_KULLANILAN_dosya_secilemiyor(monkeypatch):
    """Ayni gorselin iki sahnede cikmasi kullanicinin birebir sikayetiydi."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "B.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u, **_: {"picks": [{"n": 2, "source_file": "A.jpg"}]}
    )
    plan = _plan("A.jpg", "B.jpg")

    assert ya.kareyi_onar(plan, _review("kare 2: modern")) == []


def test_menu_tukendiyse_bos_donuyor(monkeypatch):
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg"))
    plan = _plan("A.jpg")

    assert ya.kareyi_onar(plan, _review("kare 1: modern")) == []


def test_cikarim_dusunce_kosum_devam_ediyor(monkeypatch):
    """⚠️ Onarim bir IYILESTIRME; patlarsa koşumu oldurmemeli."""

    def patla(*_a, **_k):
        raise RuntimeError("hermes timeout")

    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "YENI.jpg"))
    monkeypatch.setattr(ya, "_json_completion", patla)
    plan = _plan("A.jpg")

    assert ya.kareyi_onar(plan, _review("kare 1: modern")) == []


def test_ISTEMDEKI_menuye_bakiyor(monkeypatch):
    """Kapiyla ayni kural: menu anahtari huni konusu, planin capasi degil."""
    menuler = {"Cutty Sark": _menu("A.jpg", "YENI.jpg"), "Jock Willis": _menu("Z.jpg")}
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda k, **_: menuler.get(k, []))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u, **_: {"picks": [{"n": 1, "source_file": "YENI.jpg"}]}
    )
    plan = _plan("A.jpg")
    plan.visual_anchor = "Jock Willis"

    assert ya.kareyi_onar(plan, _review("kare 1: modern"), "Cutty Sark") == [1]


# --- Hatta baglanti --------------------------------------------------------


def test_eski_yol_YEDEK_olarak_duruyor():
    """Menusu olmayan konularda tek care arama terimlerini revize etmek."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def run_cycle(") :]

    # Argüman listesi ARANMIYOR: cagriya `bicim=` eklendi (2026-08-15).
    assert "refine_search_terms(plan, review" in govde


# ⚠️ Cagri yerinin GERCEKTEN calistigi `test_onarim_dali_calisiyor.py`de
# yuruttulerek dogrulaniyor, burada dize arayarak DEGIL. Sebep olculdu
# (2026-08-14): bu dosyada eskiden `"kareyi_onar(plan, review" in govde`
# diye bir kontrol vardi; dize DOGRUYDU ama cagriya `konu` diye var olmayan
# bir degisken veriliyordu. Test yesil kaldi, uc uretim koşumu video render
# edip `NameError` ile coktu. Kaynak metninde dize aramak, kodun
# calistigini kanitlamaz.


# --- IKINCIL yuva onarimi (2026-08-17) ------------------------------------
#
# ⚠️ Onarim yalnizca `kaynak_dosya`ya yaziyordu, yani sahnenin BIRINCI
# karesine. Sahne basina iki kare var ve cift numarali kare IKINCIL yuva
# (`kaynak_dosya_2`) — o kare bozuksa onarim temiz kareyi degistirip
# bozugu birakiyordu, video ayni kusurla yeniden render ediliyordu.
#
# Olculdu: 84 agir kusur kare 9-12'ye yigildi ve skor kapilarini GECEN uc
# render tek bir kusurla dustu:
#     16:48  85/75  "kare 11: konuyla ilgisiz modern goruntu"
#     18:28  78/85  "kare 10: anlatilan kisi degil"        <- IKINCIL


def _plan2(*ciftler: tuple[str, str]) -> ya.ContentPlan:
    """Her sahnenin iki yuvasi da dolu bir plan."""
    plan = _plan(*[b for b, _ in ciftler])
    for sahne, (_, ikincil) in zip(plan.scenes, ciftler):
        sahne["kaynak_dosya_2"] = ikincil
    return plan


def test_IKINCIL_kare_bozuksa_ikincil_dosya_degisiyor(monkeypatch):
    """18:28 koşumu: "kare 10" -> sahne 5'in IKINCI karesi."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "A2.jpg", "YENI.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u, **_: {"picks": [{"n": 1, "source_file": "YENI.jpg"}]}
    )
    plan = _plan2(("A.jpg", "A2.jpg"))

    degisen = ya.kareyi_onar(plan, _review("kare 2: anlatilan kisi degil"))

    assert degisen == [1]
    assert plan.scenes[0]["kaynak_dosya_2"] == "YENI.jpg", "bozuk olan IKINCIL yuvaydi"
    assert plan.scenes[0]["kaynak_dosya"] == "A.jpg", "temiz birincil dokunulmamali"


def test_BIRINCIL_kare_bozuksa_ikincile_DOKUNULMUYOR(monkeypatch):
    """Karsit durum — yeni mantik eskiyi bozmamali."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "A2.jpg", "YENI.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u, **_: {"picks": [{"n": 1, "source_file": "YENI.jpg"}]}
    )
    plan = _plan2(("A.jpg", "A2.jpg"))

    ya.kareyi_onar(plan, _review("kare 1: konuyla ilgisiz modern goruntu"))

    assert plan.scenes[0]["kaynak_dosya"] == "YENI.jpg"
    assert plan.scenes[0]["kaynak_dosya_2"] == "A2.jpg", "temiz ikincil dokunulmamali"


def test_IKINCIL_dosyalar_da_KULLANILMIS_sayiliyor(monkeypatch):
    """⚠️ Yoksa onarim, ikinci yuvada ZATEN duran dosyayi 'bos' sanip secer
    ve ayni goruntu videoda iki kez cikar.

    Menude bir de gercekten bos dosya (`BOS.jpg`) var ki cikarim CAGRILSIN;
    yoksa aday menu tamamen boşalir, fonksiyon erken doner ve test istemi
    hic goremez — olcmek istedigi seyi olcemez.
    """
    monkeypatch.setattr(
        ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "MEVCUT2.jpg", "BOS.jpg")
    )
    istem: dict = {}

    def yakala(sistem, kullanici, **_):
        istem["u"] = kullanici
        return {"picks": []}

    monkeypatch.setattr(ya, "_json_completion", yakala)
    plan = _plan2(("A.jpg", "MEVCUT2.jpg"))

    ya.kareyi_onar(plan, _review("kare 1: konuyla ilgisiz modern goruntu"))

    assert "BOS.jpg" in istem["u"], "kullanilmamis dosya menude olmali"
    assert "MEVCUT2.jpg" not in istem["u"], "ikincilde duran dosya menuye girmemeli"


def test_UZUN_bicimde_ikincil_yuva_YOK(monkeypatch):
    """`kare_yuvasi == 1`: her kare kendi sahnesi, ikincil yuva kavrami yok.

    Cift numarali kareyi ikincil saymak, uzun formatta var olmayan bir alana
    yazmak demek olurdu.
    """
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu("A.jpg", "B.jpg", "YENI.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda s, u, **_: {"picks": [{"n": 2, "source_file": "YENI.jpg"}]}
    )
    plan = _plan("A.jpg", "B.jpg")

    ya.kareyi_onar(plan, _review("kare 2: donem uyusmuyor"), bicim=ya.UZUN_BICIMI)

    assert plan.scenes[1]["kaynak_dosya"] == "YENI.jpg"
    assert "kaynak_dosya_2" not in plan.scenes[1]
