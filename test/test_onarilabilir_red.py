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


def test_TEK_KARELIK_agir_kusur_ONARILABILIR():
    """⚠️ DAVRANIS DEGISTI (2026-08-21). Eskiden agir kusurun VARLIGI kapiyi
    kapatiyordu; artik YAYILIMI kapatiyor. Olculdu: 88 telemetrili denemenin
    22'si skor esigini GECMISKEN yalnizca agir kusurdan dustu ve 14'u
    `AZAMI_ONARIM` butcesine siğiyordu (Moai 98, Hadrian's Wall 85)."""
    assert ya.onarilabilir_mi(_review(72, agir=["kare 3: anlatilan kisi degil"]))


def test_BUTCEYI_ASAN_agir_kusur_onarilamaz():
    """⚠️ Eski gerekce burada AYNEN gecerli: o kadar kare bozuksa planin
    kendisi yanlis. Sinir `AZAMI_ONARIM` — yeni sabit icat edilmedi.

    Shorts'ta yuva 2, yani kare 1/3/5/7 DORT ayri sahne eder."""
    agir = [f"kare {n}: donem uyusmuyor" for n in (1, 3, 5, 7)]
    assert not ya.onarilabilir_mi(_review(78, agir=agir))


def test_TAM_BUTCE_kadar_agir_kusur_hala_onarilabilir():
    """Sinirin kendisi disarida degil: uc sahne butcenin tamami."""
    agir = [f"kare {n}: donem uyusmuyor" for n in (1, 3, 5)]
    assert ya.onarilabilir_mi(_review(78, agir=agir))


def test_agir_kusur_VARKEN_esigi_GECEN_skor_da_onarilir():
    """⚠️ 12:05 koşumunun gercek sekli: skor 78 (esik 75) ve dusuren sey
    `agir_kusurlar`di. Band yalnizca agir kusur varken yukari aciliyor."""
    assert ya.onarilabilir_mi(_review(78, agir=["kare 3: donem uyusmuyor"]))


def test_agir_kusur_YOKKEN_esigi_gecen_skor_ONARILMIYOR():
    """⚠️ Bandin ust ucu agir kusursuz halde AYNEN duruyor — 78 yayin
    yolunda, onarim yolunda degil."""
    assert not ya.onarilabilir_mi(_review(78))


def test_HEDEFLENEMEYEN_agir_kusur_onarilamaz():
    """⚠️ `agir_kusurlu_kareler` kati turkce kalibi okuyor. Kusur var ama
    hangi kareye ait oldugu cozulemiyorsa onarim ne yapacagini bilmez —
    eski davranis korunuyor."""
    assert not ya.onarilabilir_mi(_review(72, agir=["frame 3 is wrong period"]))


def test_agir_kusur_sahneye_CEVRILIYOR_kare_sayilmiyor():
    """⚠️ Yuva 2'de kare 1-2-3-4 IKI sahne eder; kare olarak sayilsa dort
    olur ve butce bosuna dolardi. Cevrim `hakem_karesinden_sahne`den gecmeli."""
    agir = [f"kare {n}: donem uyusmuyor" for n in (1, 2, 3, 4)]
    assert ya.onarilabilir_mi(
        _review(
            78,
            agir=agir,
        ),
    )


def test_MODERN_FOOTAGE_render_onarilabilir_DEGIL():
    """Mevcut davranis korunuyor: bu ifade konuyu bitiriyor."""
    assert not ya.onarilabilir_mi(_review(72, issues=["Scene 2 uses modern footage"]))


# --- Kapinin kendisi --------------------------------------------------------


def test_temiz_72_KONUYU_YAKMIYOR():
    """⚠️ Asil regresyon. Bu satir False donmezse hat yine konu coplemeye baslar."""
    assert not ya.should_abandon_topic(_review(72))


def test_55_KONUYU_YAKIYOR():
    assert ya.should_abandon_topic(_review(55))


def test_tek_kareli_agir_kusur_KONUYU_YAKMIYOR():
    """⚠️ DAVRANIS DEGISTI (2026-08-21): onarim denenmeden konu atilmiyor."""
    assert not ya.should_abandon_topic(_review(72, agir=["kare 3: donem uyusmuyor"]))


def test_YAYILMIS_agir_kusur_KONUYU_YAKIYOR():
    """Butceyi asan kusur hala konuyu bitiriyor — eski gerekce orada gecerli."""
    agir = [f"kare {n}: donem uyusmuyor" for n in (1, 3, 5, 7)]
    assert ya.should_abandon_topic(_review(72, agir=agir))


def test_AGIR_KUSURLU_video_YAYINLANMIYOR():
    """⚠️ ASIL KILIT. Onarim yolu agir kusura acildi; YAYIN kapisi acilMADI.
    Bu satir duşerse hat yanlis donemli kareyi yayina verir."""
    assert not ya.should_publish(
        _review(88, altyazi=90, agir=["kare 3: donem uyusmuyor"])
    )


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
    assert list(ya.sikayet_sahneleri(_review(72, issues=["Frames 9-10 are dark"]))) == [
        5
    ]


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
    return [
        {"dosya": ad, "gosterdigi": f"{ad} gorseli", "tarih": "1900"} for ad in adlar
    ]


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
        ya,
        "_json_completion",
        lambda *_a, **_k: {"picks": [{"n": 2, "source_file": "yeni-a.jpg"}]},
    )

    review = _review(
        72, issues=["Frames 3-4 (scene 2): the aerial view is green-washed"]
    )

    assert ya.kareyi_onar(plan, review, "Gobekli Tepe") == [2]
    assert plan.scenes[1]["kaynak_dosya"] == "yeni-a.jpg"


def test_onarim_TAVANLA_sinirli(monkeypatch):
    """⚠️ Sinir SART: siradan sikayetler cogu render'da sahnelerin
    yarisindan fazlasini aniyor. Hepsini degistirmek "onarim" degil plani
    bastan secmek olurdu — ve bastan secim yazi-tura (8/8/10)."""
    plan = _plan()
    monkeypatch.setattr(
        ya,
        "arsiv_envanteri",
        lambda *_a, **_k: _menu(*[f"yeni-{i}.jpg" for i in range(9)]),
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
        ya,
        "arsiv_envanteri",
        lambda *_a, **_k: _menu(*[f"yeni-{i}.jpg" for i in range(9)]),
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
            agir=["kare 11: donem uyusmuyor"],  # sahne 6
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
        plan,
        _review(72, issues=["Scene 2 (frames 3-4): the graffiti is not legible"]),
        "Gobekli Tepe",
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


def test_yeniden_planlama_IKI_DEGISKENI_de_sifirliyor():
    """Yoksa B konusu hic soguma gormezdi (kayit borcu A ile kapanmis sayilirdi).

    ⚠️ Ikinci degisken 2026-08-19'da eklendi: `son_render` artik EN IYI turu
    sakliyor, en sonuncusunu degil. Sifirlanmazsa A konusunun yuksek skorlu
    turu B konusunun kaydina yazilirdi.

    ⚠️ Bu test YAPIYI pinliyor (iki yeniden planlama noktasinin IKISI de
    sifirliyor mu); DAVRANISI asagidaki
    `test_ONCEKI_konunun_yuksek_skoru_yeni_konuya_YAZILMIYOR` kosturuyor.
    Yorum metni kasitli olarak disarida: bir yorumu duzenlemek testi
    dusurmemeli.
    """
    assert (
        KAYNAK.count(
            "son_plan_kayitli = False\n                        son_render = None"
        )
        == 2
    )


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


def _kur(monkeypatch, tmp_path, akis, *, bicim=None):
    """`run_cycle`i aga cikmadan kosturur; `akis` her denemenin incelemesi.

    ⚠️ `bicim` KEYWORD ve varsayilani `None`: mevcut cagrilarin hicbiri
    degismesin diye. `None` gelince `run_cycle` kendi varsayilanini
    (SHORTS_BICIMI) kullaniyor."""
    durum = {"published": [], "rejected": [], "completed_slots": []}
    monkeypatch.setattr(ya, "load_state", lambda: durum)
    monkeypatch.setattr(ya, "save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)  # uretim loglarina DOKUNMA
    monkeypatch.setattr(
        ya, "create_review_montage", lambda *_a, **_k: tmp_path / "m.jpg"
    )
    monkeypatch.setattr(ya, "kareyi_onar", lambda *_a, **_k: [1])
    monkeypatch.setattr(
        ya,
        "run_generator",
        lambda *_a, **_k: (
            "gorev",
            tmp_path / "v.mp4",
            tmp_path / "s.txt",
            [],
            0,
            tmp_path / "malzeme",
        ),
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

    # ⚠️ AKIS TUKENINCE SON DEGER TEKRARLANIYOR (2026-08-22). Dongu artik
    # onarim yapildiginda uzayabiliyor (`ONARIM_EK_DENEME`) ve sabit uc
    # elemanli bir taklit `StopIteration` ile dusuyordu. Testin olctugu sey
    # DIZI, akisin uzunlugu degil.
    sira = list(akis)
    monkeypatch.setattr(
        ya,
        "review_video",
        lambda *_a, **_k: sira.pop(0) if len(sira) > 1 else sira[0],
    )

    ek = {} if bicim is None else {"bicim": bicim}
    ya.run_cycle(konu_override="Gobekli Tepe", dry_run=True, **ek)
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
            # ⚠️ KALDIRAC DEGISTI (2026-08-21), sinanan ozellik DEGISMEDI.
            # Konuyu yakmak icin eskiden tek agir kusur yetiyordu; artik
            # butceyi (`AZAMI_ONARIM`) asmasi gerekiyor. Test kayit
            # muhasebesini olcuyor, yakma esigini degil.
            _review(72, agir=[f"kare {n}: anlatilan kisi degil" for n in (1, 3, 5, 7)]),
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


def test_EN_IYI_tur_kaydediliyor_en_SONUNCUSU_degil(monkeypatch, tmp_path):
    """⚠️ Olculdu (2026-08-19 02:41, Moai): koşum 98 aldi, onarim turlari 94
    ve 80 verdi ve kayda 80 yazildi — `zamanlayici.log` da "en son skor 80"
    dedi. Darbogaz siralamasi bu sayilar uzerinden yapiliyor, yani en kotu
    turu yazmak konuyu oldugundan zayif gosteriyor.

    ⚠️ `son_render` YAYIN SECMIYOR, yalnizca red kaydini besliyor; bu bir
    teshis duzeltmesi, bir yayin duzeltmesi degil.
    """
    # ⚠️ Skorlar TEK BASINA yetmez: 98/85 yayin esigini gecer ve koşum
    # birinci denemede yayinlanirdi. Moai'nin gercek sekli agir kusur
    # tasiyordu — `should_publish` onu bu yuzden dusurdu, skor yuzunden
    # degil — ve `should_abandon_topic` 98'i "yakilacak konu" saymadigi
    # icin akis onarim daline gitti. Testin uc turu de o sekli tasiyor.
    agir = ["kare 8: konuyla ilgisiz modern goruntu"]
    redler = _kur(
        monkeypatch,
        tmp_path,
        [_review(98, agir=agir), _review(94, agir=agir), _review(80, agir=agir)],
    )

    assert len(redler) == 1
    assert redler[0]["visual_alignment_score"] == 98, (
        f"en iyi tur yazilmaliydi, yazilan: {redler[0]['visual_alignment_score']}"
    )


def test_ONCEKI_konunun_yuksek_skoru_yeni_konuya_YAZILMIYOR(monkeypatch, tmp_path):
    """⚠️ "En iyiyi sakla" degisikliginin actigi RISK, kilit altinda.

    Dizi:
        deneme 1  konu-1, 74 + agir kusur -> konu YAKILIR, kayit VAR (74),
                                             konu-2'ye gecilir
        deneme 2  konu-2, 65 onarilabilir -> onarim, kayit yok
        deneme 3  konu-2, 65 onarilabilir -> onarim, slot duser -> kayit

    `son_render` konu degisiminde sifirlanmazsa konu-1'in 74'u konu-2'nin
    kaydina yazilir: kayit dogru konu adini ama YANLIS skoru tasir ve
    bu, kaydin varolus amaci olan soguma/darbogaz muhasebesini bozar.
    """
    redler = _kur(
        monkeypatch,
        tmp_path,
        [
            # ⚠️ Yakma kaldiraci: butceyi asan yayilim (bkz. yukaridaki not).
            _review(74, agir=[f"kare {n}: anlatilan kisi degil" for n in (1, 3, 5, 7)]),
            _review(65),
            _review(65),
        ],
    )

    assert len(redler) == 2, f"iki kayit bekleniyordu, {len(redler)}"
    assert redler[0]["visual_alignment_score"] == 74
    assert redler[1]["visual_alignment_score"] == 65, (
        f"onceki konunun skoru sizdi: {redler[1]['visual_alignment_score']}"
    )
    assert redler[0]["topic"] != redler[1]["topic"]


# --- Yuva cevrimi CAGRI YERINDE de dogru mu --------------------------------


def test_KARE_YUVASI_cagri_yerinden_geliyor_VARSAYILANDAN_degil(monkeypatch, tmp_path):
    """⚠️ MUTASYON M9 BURADAN IKI KEZ KACTI (2026-08-21). `should_abandon_topic`
    dogru sayiyordu ama `run_cycle` ona `yuva`/`ornekler` gecirmeyi birakinca
    HICBIR test dusmuyordu — yani "deger dogru" olculmus, "hat onu KULLANIYOR"
    olculmemisti. Bu oturumda ayni sekil dorduncu kez.

    ⚠️ ILK denemem de kacti ve sebebi ogreticiydi: ayirt edici olarak "kayit
    yazildi mi"yi almistim, oysa slot dusunce ONARIM dali da kayit yaziyor
    (bkz. `test_UC_DENEME_de_onarilirsa_slot_dusunce_TEK_kayit`). Iki yol da
    "kayit var" diyordu. Olculerek duzeltildi — gercek fark KONU SAYISI:

        UZUN   (yuva 1): kare 1-2-3-4 -> DORT sahne, butce asilir
                         -> konu yakilir, her deneme yeni konu -> 3 kayit
        SHORTS (yuva 2): ayni kareler -> IKI sahne, butceye sigar
                         -> onarim dali, konu korunur           -> 1 kayit

    ⚠️ Skor 72 SART: 78 esigin ustunde oldugu icin `should_abandon_topic`
    zaten False doner ve iki bicim de ayni sonucu verir — ilk olcumumde
    tam bu yuzden fark cikmadi.
    """
    agir = [f"kare {n}: donem uyusmuyor" for n in (1, 2, 3, 4)]
    redler = _kur(
        monkeypatch,
        tmp_path,
        [_review(72, agir=agir), _review(72, agir=agir), _review(72, agir=agir)],
        bicim=ya.UZUN_BICIMI,
    )

    konular = [r["topic"] for r in redler]
    assert len(set(konular)) == 3, (
        "uzun formatta dort sahne butceyi asar, her deneme konuyu yakmaliydi; "
        f"tek konu gorunuyorsa cagri yeri varsayilan yuvayi (2) kullaniyor: {konular}"
    )


def test_ayni_kareler_SHORTS_formatinda_butceye_SIGIYOR(monkeypatch, tmp_path):
    """Ustteki testin karsi kutbu — cevrimin gercekten yuvaya bagli oldugunu
    gosterir, yoksa ust test "her zaman yakar" ile de gecerdi."""
    agir = [f"kare {n}: donem uyusmuyor" for n in (1, 2, 3, 4)]
    redler = _kur(
        monkeypatch,
        tmp_path,
        [_review(72, agir=agir), _review(72, agir=agir), _review(72, agir=agir)],
    )

    konular = [r["topic"] for r in redler]
    assert konular == ["konu-1"], f"onarim daline gitmeliydi, kayitlar: {konular}"


def test_ORNEKLEM_sahne_sayimini_degistirebiliyor():
    """`ornekler` parametresinin anlamini kilitler.

    ⚠️ DURUSTLUK NOTU (2026-08-21). `ornekler` baglantisini cagri yerinden
    kesen mutasyon (M10) hicbir testi dusurmedi ve sebebi olculdu: bu kapi
    yalnizca AYRIK SAHNE SAYIYOR, ve hattin bugun urettigi hicbir yapilandirmada
    ornekleme o sayiyi degistiremiyor —

        UZUN   25 sahne: ornek [1,3,5,8,...]  kare1-4 -> 4 sahne
                         ornekSIZ             kare1-4 -> 4 sahne   (ayni)
        SHORTS 10 sahne: ornekleme kimlige esit                    (ayni)

    Yani M10 kacan degil ESDEGER bir mutasyon. Parametre yine de geciriliyor
    (`kareyi_onar` ile ayni cagri sekli) ve anlami burada sabitleniyor: sayimi
    DEGISTIREBILDIGI bir ornekemde dogru davranmali. Bu test, ileride kapi
    sahne KIMLIKLERINI kullanmaya baslarsa sessiz kalmaz.
    """
    agir = [f"kare {n}: donem uyusmuyor" for n in (1, 2, 3, 4)]

    # yuva 2, ornekleme YOK: kare 1-2-3-4 -> sahne 1,1,2,2 = IKI sahne
    assert ya.onarilabilir_mi(_review(72, agir=agir), yuva=2) is True

    # ayni kareler, seyrek ornekem: gercek kareler 1,3,5,7 -> DORT sahne
    assert (
        ya.onarilabilir_mi(_review(72, agir=agir), yuva=2, ornekler=[1, 3, 5, 7])
        is False
    )
