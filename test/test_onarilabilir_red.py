"""Esigin HEMEN ALTINDAKI render konuyu yakmaz — onarilir.

⚠️ NEDEN VAR — olculdu 2026-08-18. Hat 17 Agu 15:01'den beri hic yayin
yapmiyordu. Esik 75'e indikten sonraki YEDI render:

    72, 72, 72, 72, 65, 55, 72        <- yedisi de konuyu cope atti

Sebep `should_abandon_topic`ti: yalnizca "skor < MIN_VISUAL_SCORE" diye
bakiyordu, yani ucuz onarim yolu (`kareyi_onar`, cagrisi `else` dalinda)
hattin SUREKLI aldigi skorda yapisal olarak ERISILEMEZDI.

Atmanin bedeli de olculdu (n=26, ayni slottaki ardisik denemeler):

    yeniden planlama -> iyilesti 8 · kotulesti 8 · ayni 10

Yani konu atmak bir yazi-tura ve her atisin bedeli tam bir render.

⚠️ YAYIN KARARI DEGISMEDI. `should_publish` ellenmedi; 72 hala
yayinlanmiyor. Bu dosyanin korudugu sey REDDEN SONRA NE OLDUGU.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def _review(gorsel, *, issues=None, agir=None, altyazi=85) -> ya.QualityReview:
    # ⚠️ `agir_kusurlar` ANAHTAR KELIMEYLE veriliyor: alanlar arasinda
    # `revised_search_terms`, `problem_scene_numbers` ve `kareler` var, yani
    # besinci konum agir kusur DEGIL. Konumla verince testler sessizce
    # yesillenirdi (bu dosyayi yazarken tam bunu yaptim).
    return ya.QualityReview(
        False, gorsel, altyazi, list(issues or []), agir_kusurlar=list(agir or [])
    )


# --- Onarilabilir band ------------------------------------------------------


@pytest.mark.parametrize("skor", [72, 65, 74])
def test_esigin_HEMEN_altindaki_temiz_render_ONARILABILIR(skor):
    """Gozlenen skorlar: 72 (12/31 render) ve 65. Ikisi de bandin icinde."""
    assert ya.onarilabilir_mi(_review(skor))


@pytest.mark.parametrize("skor", [55, 40, 25])
def test_bandin_ALTINDAKI_render_onarilamaz(skor):
    """⚠️ 55 bilerek disarida: "birkac karesi bozuk" degil, video yanlis."""
    assert not ya.onarilabilir_mi(_review(skor))


def test_esigi_GECEN_render_onarilabilir_sayilmaz():
    """Band esigin ALTI icin; 78 zaten yayin yolunda."""
    assert not ya.onarilabilir_mi(_review(78))


def test_AGIR_KUSURLU_render_onarilabilir_DEGIL():
    """⚠️ Agir kusur "yanlis kisi/yanlis donem" demek — bir kare
    degisikligiyle kapanmaz, planin kendisi yanlistir."""
    assert not ya.onarilabilir_mi(_review(72, agir=["kare 3: anlatilan kisi degil"]))


def test_MODERN_FOOTAGE_render_onarilabilir_DEGIL():
    """Mevcut davranis korunuyor: bu ifade konuyu bitiriyor."""
    assert not ya.onarilabilir_mi(_review(72, issues=["Scene 2 uses modern footage"]))


# --- Kapinin kendisi --------------------------------------------------------


def test_temiz_72_KONUYU_YAKMIYOR():
    """⚠️ Asil regresyon. Bu satir False donmezse hat yine konu coplemeye baslar."""
    assert not ya.should_abandon_topic(_review(72))


def test_55_KONUYU_YAKIYOR():
    assert ya.should_abandon_topic(_review(55))


def test_agir_kusurlu_72_KONUYU_YAKIYOR():
    assert ya.should_abandon_topic(_review(72, agir=["kare 3: donem uyusmuyor"]))


def test_modern_footage_esigi_GECSE_DE_konuyu_bitiriyor():
    """Eski davranis: skor yuksek olsa bile bu ifade konuyu bitirir."""
    assert ya.should_abandon_topic(_review(88, issues=["clearly modern footage here"]))


def test_YAYIN_KARARI_DEGISMEDI():
    """⚠️ `test_kapi_gerileme.py` 72/84'u FAIL olarak sabitliyor (Gotz von
    Berlichingen). Onarim yolu acilirken yayin kapisina dokunulmadigini
    burada da tutuyoruz — ikisi ayri kararlar."""
    assert not ya.should_publish(_review(72, altyazi=84))
    assert ya.should_publish(ya.QualityReview(True, 85, 90, [], []))


def test_esik_ELLE_yazilmiyor():
    """⚠️ `test_kalite_kapisi.py` ayni kurali `should_abandon_topic` icin
    kovaliyor; band sabiti de ayni kurala tabi olmali."""
    govde = KAYNAK[
        KAYNAK.index("def onarilabilir_mi(") : KAYNAK.index("def should_abandon_topic(")
    ]

    assert "ONARILABILIR_BANT" in govde
    assert "MIN_VISUAL_SCORE" in govde
    assert not re.search(r"<=?\s*(65|72)\b", govde), "band elle yazilmis"


def test_band_sabiti_HICBIR_ISTEME_girmiyor():
    """DW-87: esigi bilen model olcmuyor, esigin bir tik altini yaziyor."""
    for fonksiyon in ("review_video", "review_source_materials"):
        basla = KAYNAK.index(f"def {fonksiyon}(")
        yonerge = KAYNAK[basla : KAYNAK.index("_vision_json(prompt", basla)]
        assert "ONARILABILIR_BANT" not in yonerge
        assert str(ya.MIN_VISUAL_SCORE - ya.ONARILABILIR_BANT) not in yonerge


# --- Siradan sikayetlerin ayristirilmasi ------------------------------------
#
# ⚠️ Uc bicim de CANLI ciktidan alindi (2026-08-17/18 redleri). Hakem
# ingilizce yaziyor ve `agir_kusurlu_kareler`in katı turkce kalibi
# (`kare 7: ...`) bunlarin hicbirini tutmuyor.


@pytest.mark.parametrize(
    "metin,beklenen",
    [
        ("Frame 11 (scene 6, first frame) is heavily blurred", 6),
        ("Frames 3-4 (scene 2): the aerial view is green-washed", 2),
        ("Scene 4 (frames 7-8): the statues are Toltec-style", 4),
        ("Scene 2 (frames 3–4): rock-face close-ups are ambiguous", 2),
    ],
)
def test_siradan_sikayet_SAHNEYE_baglaniyor(metin, beklenen):
    assert list(ya.sikayet_sahneleri(_review(72, issues=[metin]))) == [beklenen]


def test_SAHNE_yaziliysa_kare_cevrimi_YAPILMIYOR():
    """⚠️ Asil incelik. "Frame 11 (scene 6...)" iki sayi tasiyor; kare
    cevrimi 11'i sahne 6'ya goturur ama orneklemeli uzun formatta ayni
    cevrim YANLIS sahneyi gosterir. Hakem sahneyi zaten yazmisken tahmin
    etmeye gerek yok."""
    sikayet = "Frame 11 (scene 3, first frame) is blurred"

    # Kare 11 -> sahne 6 olurdu; sahne acikca 3 yaziyor.
    assert list(ya.sikayet_sahneleri(_review(72, issues=[sikayet]))) == [3]


def test_yalnizca_KARE_yaziliysa_cevriliyor():
    assert list(ya.sikayet_sahneleri(_review(72, issues=["Frames 9-10 are dark"]))) == [5]


def test_SAHNESIZ_sikayet_DISARIDA_kaliyor():
    """⚠️ Bilincli: onarim bir GORSEL degistiriyor. Sahnesi belli olmayan
    sikayet icin degistirilecek gorsel de belli degil.

    Kanca sikayeti tam boyle ve yedi reddin YEDISINDE geciyor — sahneye
    baglanabilseydi her onarim turu bosa 1. sahneyi degistirirdi.
    """
    review = _review(72, issues=["The curiosity hook in the first 2-3 seconds is weak"])

    assert ya.sikayet_sahneleri(review) == {}


# --- Onarim siradan sikayetleri de hedefliyor -------------------------------


def _menu(*adlar):
    return [{"dosya": ad, "gosterdigi": f"{ad} gorseli", "tarih": "1900"} for ad in adlar]


def _plan(sahne=6):
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="Gobekli Tepe",
        title="baslik",
        script="metin",
        scenes=[
            {
                "narration": f"sahne {s} anlatimi",
                "search_term": f"Gobekli Tepe {s}",
                "kaynak_dosya": f"eski-{s}.jpg",
            }
            for s in range(1, sahne + 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def test_AGIR_KUSUR_YOKKEN_de_onarim_yapiliyor(monkeypatch):
    """⚠️ ASIL DUZELTME. Esik altinda kalan yedi reddin DORDUNDE agir kusur
    SIFIRDI; onarim yolu acilsa bile eskiden BOS donerdi, cunku hedefleme
    yalnizca `agir_kusurlar` listesini okuyordu."""
    plan = _plan()
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda *_a, **_k: _menu("yeni-a.jpg"))
    monkeypatch.setattr(
        ya, "_json_completion", lambda *_a, **_k: {"picks": [{"n": 2, "source_file": "yeni-a.jpg"}]}
    )

    review = _review(72, issues=["Frames 3-4 (scene 2): the aerial view is green-washed"])

    assert ya.kareyi_onar(plan, review, "Gobekli Tepe") == [2]
    assert plan.scenes[1]["kaynak_dosya"] == "yeni-a.jpg"


def test_onarim_TAVANLA_sinirli(monkeypatch):
    """⚠️ Sinir SART: siradan sikayetler cogu render'da sahnelerin
    yarisindan fazlasini aniyor. Hepsini degistirmek "onarim" degil plani
    bastan secmek olurdu — ve bastan secim yazi-tura (8/8/10)."""
    plan = _plan()
    monkeypatch.setattr(
        ya, "arsiv_envanteri", lambda *_a, **_k: _menu(*[f"yeni-{i}.jpg" for i in range(9)])
    )
    gorulen = {}

    def _sahte(_yonerge, govde, *_a, **_k):
        import json

        gorulen["sahneler"] = [s["n"] for s in json.loads(govde)["scenes"]]
        return {"picks": []}

    monkeypatch.setattr(ya, "_json_completion", _sahte)

    ya.kareyi_onar(
        plan,
        _review(72, issues=[f"Scene {s}: image does not match" for s in range(1, 7)]),
        "Gobekli Tepe",
    )

    assert len(gorulen["sahneler"]) == ya.AZAMI_ONARIM


def test_AGIR_kusurlar_tavanda_ONCELIKLI(monkeypatch):
    """Tavan dolarsa elenecek olan siradan sikayet olmali: agir kusur tek
    basina videoyu reddettiriyor, siradan sikayet yalnizca skoru dusuruyor."""
    plan = _plan()
    monkeypatch.setattr(
        ya, "arsiv_envanteri", lambda *_a, **_k: _menu(*[f"yeni-{i}.jpg" for i in range(9)])
    )
    gorulen = {}

    def _sahte(_yonerge, govde, *_a, **_k):
        import json

        gorulen["sahneler"] = [s["n"] for s in json.loads(govde)["scenes"]]
        return {"picks": []}

    monkeypatch.setattr(ya, "_json_completion", _sahte)

    ya.kareyi_onar(
        plan,
        _review(
            72,
            issues=[f"Scene {s}: image does not match" for s in (1, 2, 3, 4, 5)],
            agir=["kare 11: donem uyusmuyor"],   # sahne 6
        ),
        "Gobekli Tepe",
    )

    assert 6 in gorulen["sahneler"], "agir kusurlu sahne tavana kurban gitti"


def test_sikayet_METNI_de_modele_veriliyor(monkeypatch):
    """Sahneyi secip gerekcesini vermemek, modelden "bu cumleye ne uyar"
    yerine rastgele baska bir dosya almak demekti."""
    plan = _plan()
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda *_a, **_k: _menu("yeni-a.jpg"))
    gorulen = {}

    def _sahte(_yonerge, govde, *_a, **_k):
        import json

        gorulen["govde"] = govde
        return {"picks": []}

    monkeypatch.setattr(ya, "_json_completion", _sahte)

    ya.kareyi_onar(
        plan, _review(72, issues=["Scene 2 (frames 3-4): the graffiti is not legible"]), "Gobekli Tepe"
    )

    assert "graffiti is not legible" in gorulen["govde"]


# --- Slot dustugunde kayit --------------------------------------------------


def test_slot_dustugunde_red_KAYDA_geciyor():
    """⚠️ Onarim dali YENI BIR CIKIS YOLU acti: son deneme kareyi onarirsa
    dongu hicbir `rejected` kaydi yazmadan biter, `aday_sogumada_mi` okuyacak
    bir sey bulamaz ve aday ertesi koşumda yine kuyrugun basinda olur —
    #38'in kapattigi dongunun aynisi (`43d2a8b` ile planlama yolunda ayni
    delik kapatilmisti)."""
    assert "if not son_plan_kayitli and son_render is not None:" in KAYNAK
    assert "_video_reddini_kaydet(*son_render)" in KAYNAK


def test_yeniden_planlama_kayit_borcunu_SIFIRLIYOR():
    """Yoksa B konusu hic soguma gormezdi (kayit borcu A ile kapanmis sayilirdi)."""
    assert KAYNAK.count("# Yeni konu, yeni kayit borcu.\n                        son_plan_kayitli = False") == 2


def test_kayit_TEK_YERDE_uretiliyor():
    """⚠️ Cifte yakma korumasi: iki ayri kayit govdesi olsaydi biri
    guncellenip digeri unutulurdu ve capa butcesi (`RET_DENEME_BUTCESI`)
    yanlis beslenirdi."""
    assert KAYNAK.count("def _video_reddini_kaydet(") == 1
    assert KAYNAK.count("_video_reddini_kaydet(") == 3  # tanim + iki cagri


# --- Kayit muhasebesi: GERCEK dongu uzerinde --------------------------------
#
# ⚠️ Yukaridaki uc test DIZE ariyor; boşluk ve cifte-yakma ise MANTIK
# hatalari ve dize testi onlari yakalayamaz. Asagisi `run_cycle`i gercekten
# kosturuyor.


def _kur(monkeypatch, tmp_path, akis):
    """`run_cycle`i aga cikmadan kosturur; `akis` her denemenin incelemesi."""
    durum = {"published": [], "rejected": [], "completed_slots": []}
    monkeypatch.setattr(ya, "load_state", lambda: durum)
    monkeypatch.setattr(ya, "save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)  # uretim loglarina DOKUNMA
    monkeypatch.setattr(ya, "create_review_montage", lambda *_a, **_k: tmp_path / "m.jpg")
    monkeypatch.setattr(ya, "kareyi_onar", lambda *_a, **_k: [1])
    monkeypatch.setattr(
        ya,
        "run_generator",
        lambda *_a, **_k: ("gorev", tmp_path / "v.mp4", tmp_path / "s.txt", [], 0),
    )

    sayac = {"n": 0}

    def _plan_uret(*_a, **_k):
        sayac["n"] += 1
        return ya.ContentPlan(
            topic=f"konu-{sayac['n']}",
            visual_anchor=f"capa-{sayac['n']}",
            title="baslik",
            script="metin",
            scenes=[{"narration": "x", "search_term": "y"} for _ in range(6)],
            description="aciklama",
            tags=["a", "b", "c"],
        )

    monkeypatch.setattr(ya, "generate_content_plan", _plan_uret)

    sira = iter(akis)
    monkeypatch.setattr(ya, "review_video", lambda *_a, **_k: next(sira))

    ya.run_cycle(konu_override="Gobekli Tepe", dry_run=True)
    return durum["rejected"]


def test_UC_DENEME_de_onarilirsa_slot_dusunce_TEK_kayit(monkeypatch, tmp_path):
    """⚠️ Delik buydu: uc deneme de onarim daline giderse eskiden HIC kayit
    yazilmiyordu, aday sogumuyordu ve ertesi koşumda yine kuyrugun basindaydi."""
    redler = _kur(monkeypatch, tmp_path, [_review(72), _review(72), _review(72)])

    assert len(redler) == 1, f"tam bir kayit bekleniyordu, {len(redler)} bulundu"
    assert redler[0]["stage"] == "video"
    assert redler[0]["visual_alignment_score"] == 72
    assert "aday_basligi" in redler[0], "soguma bu alani okuyor"


def test_KARISIK_dizi_ne_bosluk_ne_CIFTE_yakma(monkeypatch, tmp_path):
    """⚠️ Iki yonlu hata riski tasiyan dizi:

        deneme 1  konu-1 onarildi                -> kayit YOK
        deneme 2  konu-1 agir kusurla birakildi  -> kayit VAR, konu-2'ye gecildi
        deneme 3  konu-2 onarildi, slot dustu    -> konu-2 yazilmali,
                                                    konu-1 IKINCI KEZ yazilmamali
    """
    redler = _kur(
        monkeypatch,
        tmp_path,
        [
            _review(72),
            _review(72, agir=["kare 3: anlatilan kisi degil"]),
            _review(72),
        ],
    )

    konular = [r["topic"] for r in redler]
    assert len(redler) == 2, f"iki kayit bekleniyordu, {len(redler)}: {konular}"
    assert len(set(konular)) == 2, f"ayni konu iki kez yakildi: {konular}"


def test_SON_DENEME_konuyu_birakirsa_kayit_IKI_KEZ_yazilmiyor(monkeypatch, tmp_path):
    """Terkedilen son deneme kaydi zaten yaziyor; dongu sonrasi tekrar yazmamali."""
    redler = _kur(monkeypatch, tmp_path, [_review(72), _review(72), _review(55)])

    assert len(redler) == 1, f"tek kayit bekleniyordu, {len(redler)} bulundu"
    assert redler[0]["visual_alignment_score"] == 55
