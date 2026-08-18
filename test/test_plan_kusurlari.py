"""Plan dogrulamasi BUTUN kusurlari birden bildirmeli — kostebek oyunu.

⚠️ NEDEN VAR — 2026-08-18'de koşum duzeyinde olculdu. 15-18 Agustos arasi 44
zamanlayici koşumundan yalnizca 2'si yayinla bitti. Kaybin bir kismi kalite
kapilarinda degil, PLAN asamasinda: bir plani gecirmek icin ~23 kapi var
(13'u `plan_kusurlari`, ~10'u dongudeki yumusak kapilar) ve her deneme modele
BIR tanesini soyluyordu. Model onu duzeltip baskasini boziyordu.

`logs/plan-redleri.log` (13 red, hepsi 18 Agustos):

    07:25  kelime(201) -> baslik bicimi -> baslik bicimi
    13:15  sahne sayisi -> kelime(183) -> baslik bicimi -> kelime(212)
    15:12  capa -> kelime(185) -> resmedilemez -> acilis -> kelime(153)

13:15 ve 15:12 bes denemeyi de tuketti; o saatlerde HIC video uretilmedi.
Kapilarin hicbiri GEVSETILMEDI — yalnizca hepsi ayni anda bildiriliyor.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


# ⚠️ ESIKLER CIPLAK YAZILMIYOR, bicimden turetiliyor (`test_kalite_kapisi.py`
# kalibi). Tavan yarin 170 olursa bu testler yine dogru olani olcmeli — bu
# deponun iki gununu tam da istem ile kapinin AYRI AYRI yazilmasi yemisti.
KELIME_EN_AZ, KELIME_EN_COK = ya.SHORTS_BICIMI.kelime_araligi
ASIRI = KELIME_EN_COK + 51


def _plan(**degisiklik) -> ya.ContentPlan:
    """Her acidan GECERLI bir plan; testler tek tek bozuyor."""
    alan = {
        "topic": "Sigiriya rock fortress",
        "visual_anchor": "Sigiriya",
        "title": "Why Was Sigiriya Abandoned? #Shorts",
        "script": " ".join(["word"] * ((KELIME_EN_AZ + KELIME_EN_COK) // 2)),
        "scenes": [
            {
                "narration": f"The builders cut stairs into the rock in year {i}.",
                "search_term": f"Sigiriya frescoes level {i}",
                "kaynak_dosya": "",
            }
            for i in range(1, 7)
        ],
        "description": "aciklama",
        "tags": ["a", "b", "c"],
    }
    alan.update(degisiklik)
    return ya.ContentPlan(**alan)


# --- Once: saglam plan sessiz olmali ----------------------------------------


def test_GECERLI_plan_kusursuz():
    """⚠️ Bu test once gelmeli: kusur listesi her plani reddediyorsa asagidaki
    testlerin hepsi 'gecer' ve hicbir sey olculmemis olur."""
    assert ya.plan_kusurlari(_plan()) == []


# --- Asil is: HEPSI birden -------------------------------------------------


def test_UC_kusur_AYNI_ANDA_bildiriliyor():
    """Kostebek oyununun ta kendisi: eskiden bu plan uc DENEME yakardi."""
    bozuk = _plan(
        script=" ".join(["word"] * ASIRI),  # kelime tavani
        tags=["a"],                        # etiket sayisi
        title="x" * 120,                   # baslik uzunlugu
    )

    kusurlar = ya.plan_kusurlari(bozuk)

    birlesik = " | ".join(kusurlar)
    assert f"{KELIME_EN_AZ}-{KELIME_EN_COK} words" in birlesik, birlesik
    assert "three tags" in birlesik, birlesik
    assert "100 characters" in birlesik, birlesik
    assert len(kusurlar) >= 3


def test_sahne_kusurlari_da_ayni_listede():
    bozuk = _plan(script=" ".join(["word"] * ASIRI))
    bozuk.scenes[2]["search_term"] = "x"

    kusurlar = ya.plan_kusurlari(bozuk)

    assert any(f"{KELIME_EN_AZ}-{KELIME_EN_COK} words" in k for k in kusurlar)
    assert any("scene 3" in k for k in kusurlar)


# --- Davranis korunuyor -----------------------------------------------------


def test_validate_ILK_kusuru_firlatiyor_METNI_AYNI():
    """⚠️ SOZLESME. Mesajlar hem testlerde hem MODELE giden geri bildirimde
    kullaniliyor; degisirlerse dongu kirilmaz ama model ne yapacagini
    bilemez."""
    bozuk = _plan(script=" ".join(["word"] * ASIRI), tags=["a"])

    beklenen = f"script must contain {KELIME_EN_AZ}-{KELIME_EN_COK} words, got {ASIRI}"
    with pytest.raises(ValueError, match=re.escape(beklenen)):
        ya.validate_content_plan(bozuk)


def test_validate_gecerli_planda_SUSUYOR():
    ya.validate_content_plan(_plan())  # patlarsa test duser


def test_ilk_kusur_LISTENIN_BASI():
    """Sarmalayici ile toplayici ayni siraya bakmali."""
    bozuk = _plan(script=" ".join(["word"] * ASIRI), tags=["a"])

    kusurlar = ya.plan_kusurlari(bozuk)
    with pytest.raises(ValueError) as exc:
        ya.validate_content_plan(bozuk)

    assert str(exc.value) == kusurlar[0]


# --- Gurultu bastirma -------------------------------------------------------


def test_BOZUK_CAPA_sahne_kapilarini_SUSTURUYOR():
    """⚠️ Capa okunamiyorsa ona bagli kapilar toplanmamali: 6 sahnenin 6'si
    birden 'terim capayi icermiyor' derdi ve asil kusur gurultuye gomulurdu."""
    bozuk = _plan(visual_anchor="His Excellency Mister Anders Great Fortress Lord")

    kusurlar = ya.plan_kusurlari(bozuk)

    assert any("visual anchor" in k for k in kusurlar)
    assert not any("must include the visual anchor" in k for k in kusurlar), kusurlar
    assert not any("only the visual anchor" in k for k in kusurlar), kusurlar


def test_sahne_basina_TEK_kusur():
    """Bir sahne dort kapiya birden takilabilir; dordunu de yazmak 6 sahnede
    24 satir eder."""
    # ⚠️ VAKA OZENLE SECILDI: bu sahne IKI ayri kapiya birden takiliyor —
    # terim tek kelime (somut terim yok) VE terim capadan baska bir sey
    # icermiyor. `elif` zinciri bozulursa sayi 2'ye cikar.
    bozuk = _plan()
    bozuk.scenes[0]["narration"] = ""
    bozuk.scenes[0]["search_term"] = "Sigiriya"

    kusurlar = ya.plan_kusurlari(bozuk)

    assert sum(1 for k in kusurlar if k.startswith("scene 1")) == 1, kusurlar


# --- Baglanti: donguye gercekten bagli mi -----------------------------------


def test_DONGU_kusurlarin_HEPSINI_geri_besliyor(monkeypatch):
    """⚠️ ASIL BAGLANTI TESTI — donguyu gercekten suruyor.

    Ilk hali yalnizca kaynak metninde `plan_kusurlari(` ariyordu ve donguyu
    "listeyi al ama ILK maddeye kirp" diye bozunca YESIL kaliyordu: yani
    degisikligin amacini (butun kusurlarin modele gitmesi) hic olcmuyordu.
    Simdi ikinci denemeye giden istem okunuyor.
    """
    istemler: list[str] = []

    def sahte(system: str, user: str, **_):
        istemler.append(user)
        if len(istemler) > 1:
            raise RuntimeError("dur")
        # UC kusurlu plan: kelime tavani + etiket + baslik uzunlugu
        return {
            "topic": "Sigiriya rock fortress",
            "visual_anchor": "Sigiriya",
            "title": "x" * 120,
            "script": " ".join(["word"] * ASIRI),
            "scenes": [
                {"narration": f"The stairs were cut in year {i}.",
                 "search_term": f"Sigiriya frescoes level {i}"}
                for i in range(1, 7)
            ],
            "description": "aciklama",
            "tags": ["a"],
        }

    monkeypatch.setattr(ya, "_json_completion", sahte)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [])
    monkeypatch.setattr(ya, "_son_basliklar", lambda: [])
    monkeypatch.setattr(ya, "_yedek_capa_sec", lambda *_a, **_k: None)
    try:
        ya.generate_content_plan(sahne_sayisi=6)
    except RuntimeError:
        pass

    assert len(istemler) >= 2, "dongu ikinci denemeye hic gecmedi"
    geri_bildirim = istemler[1]
    assert f"{KELIME_EN_AZ}-{KELIME_EN_COK} words" in geri_bildirim, geri_bildirim[-600:]
    assert "three tags" in geri_bildirim, geri_bildirim[-600:]
    assert "100 characters" in geri_bildirim, geri_bildirim[-600:]


# --- Sahne basina KELIME BUTCESI istemde (2026-08-18) -----------------------
#
# ⚠️ NEDEN VAR — modele "TAM N sahne" ve kelime araligi AYRI AYRI
# soyleniyordu, aralarindaki aritmetik hic soylenmiyordu. Olculdu:
#
#     6 sahne -> 13-25 kelime/sahne · modelin dogal hizi ~18-22 -> GECIYOR
#     8 sahne -> 10-18 kelime/sahne · ayni hiz ~23            -> TASIYOR
#
# `plan-redleri.log`'daki dort 8-sahne denemesinin DORDU de tasti (183, 212,
# 185, 153); yayinlanan 6-sahne planlari 105-133 ile rahat geciyor. Kapi
# bozuk degil, ARITMETIK eksikti; hicbir esik gevsetilmedi.


def _istem(monkeypatch, sahne_sayisi):
    """Planlamayi ilk cikarim cagrisinda durdurup kullanici istemine bakar."""
    yakalanan: dict = {}

    def sahte(system: str, user: str, **_):
        yakalanan["user"] = user
        raise RuntimeError("dur")

    monkeypatch.setattr(ya, "_json_completion", sahte)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [])
    monkeypatch.setattr(ya, "_son_basliklar", lambda: [])
    # ⚠️ AG CAGRISI KESILIYOR. Bu uc test ilk yazildiginda 5-10 saniye
    # suruyordu: `_yedek_capa_sec` capa havuzunu Commons'a SORARAK seciyor.
    # Suite'e canli ag bagimliligi sokmak hem yavas hem kirilgan.
    monkeypatch.setattr(ya, "_yedek_capa_sec", lambda *_a, **_k: None)
    try:
        ya.generate_content_plan(sahne_sayisi=sahne_sayisi)
    except RuntimeError:
        pass
    return yakalanan.get("user", "")


def _butce(sahne: int) -> int:
    return ((KELIME_EN_AZ + KELIME_EN_COK) // 2) // sahne


def test_8_SAHNE_kolunda_butce_soyleniyor(monkeypatch):
    """⚠️ Sikisan kol bu: 8 sahnede tavan sahne basina 18,75 kelime birakiyor."""
    metin = _istem(monkeypatch, 8)

    assert f"{_butce(8)} words per scene" in metin, metin[-400:]


def test_6_SAHNE_kolunda_butce_DAHA_GENIS(monkeypatch):
    """Butce sabit degil, sahne sayisindan turuyor."""
    assert _butce(6) > _butce(8), "6 sahnede sahne basina daha cok kelime dusmeli"
    assert f"{_butce(6)} words per scene" in _istem(monkeypatch, 6)


def test_butce_OLCULEN_degerle_uyumlu():
    """⚠️ Sayi uydurulmadi: yayinlanan TEK 8-sahne videosu (Herculaneum,
    14 Agu) 113 kelime / 8 sahne = 14,1 kelime/sahne tutturmustu. Hesap ayni
    kolda 14 veriyor — yani modelden erisilemez bir sey istenmiyor."""
    assert _butce(8) == 14


def test_sahne_sayisi_YOKSA_butce_de_YOK(monkeypatch):
    """Serbest sahne sayisinda bolecek bir sey yok; satir hic cikmamali."""
    assert "words per scene" not in _istem(monkeypatch, None)


# --- YUMUSAK kapilar da tek geciste (2026-08-18) ----------------------------
#
# ⚠️ NEDEN VAR — 18:05 koşumu: bes deneme, bes AYRI kapi, sifir video.
#
#     1 alinti -> 2 alinti -> 3 anlatim dengesi -> 4 resmedilemez -> 5 capa arzi
#
# Sert kapilari toplamak bunun yalnizca yarisini cozuyordu: model hepsini
# duzeltince ikinci denemede yumusak kapilardan birine takiliyordu.


def _gecerli_json() -> dict:
    """Butun SERT kapilari gecen bir plan sozlugu."""
    return {
        "topic": "Sigiriya rock fortress",
        "visual_anchor": "Sigiriya",
        "title": "Why Was Sigiriya Abandoned?",
        "script": " ".join(["word"] * ((KELIME_EN_AZ + KELIME_EN_COK) // 2)),
        "scenes": [
            {"narration": f"The builders cut stairs into the rock in year {i}.",
             "search_term": f"Sigiriya frescoes level {i}"}
            for i in range(1, 7)
        ],
        "description": "aciklama",
        "tags": ["a", "b", "c"],
    }


def test_IKI_yumusak_kusur_AYNI_ANDA_bildiriliyor(monkeypatch, capsys):
    """⚠️ Dizeye degil DAVRANISA bakiyor: donguyu gercekten suruyor."""
    istemler: list[str] = []

    def sahte(system: str, user: str, **_):
        istemler.append(user)
        if len(istemler) > 1:
            raise RuntimeError("dur")
        return _gecerli_json()

    monkeypatch.setattr(ya, "_json_completion", sahte)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [])
    monkeypatch.setattr(ya, "_son_basliklar", lambda: [])
    monkeypatch.setattr(ya, "_yedek_capa_sec", lambda *_a, **_k: None)
    # ⚠️ `alinti_kusuru` TOPLU BLOGUN ONUNDE ve orada kalmasi BILEREK
    # (menuye bagli, bkz. `yumusak_kapi_kusurlari` docstring'i). Bu test onu
    # olcmuyor, o yuzden susturuluyor — yoksa akis toplu bloga hic varmiyor.
    monkeypatch.setattr(ya, "alinti_kusuru", lambda *_a, **_k: "")
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda *_a, **_k: [])
    # IKI ayri yumusak kapi birden tetikleniyor.
    monkeypatch.setattr(ya, "_kapanis_tekrari", lambda *_a, **_k: True)
    monkeypatch.setattr(ya, "_baslik_bicimi_tekrari", lambda *_a, **_k: True)

    try:
        ya.generate_content_plan(sahne_sayisi=6)
    except RuntimeError:
        pass

    assert len(istemler) >= 2, "dongu ikinci denemeye hic gecmedi"
    geri = istemler[1]
    assert "closing line repeats" in geri, geri[-500:]
    assert "title repeats the shape" in geri, geri[-500:]

    # ⚠️ VE IKISI DE GUNLUGE dusmeli: `plan-redleri.log` bu satirlari
    # okuyor ve bir sonraki teshis onlara bakiyor.
    ciktilar = capsys.readouterr().out
    assert "kapanis kalibi onceki videoyla ayni" in ciktilar
    assert "baslik bicimi tekrari" in ciktilar


def test_yumusak_kapi_SON_denemelerde_gecirilyor(monkeypatch):
    """⚠️ Uretimi kaybetmemek sarti: yumusak kapi 4. denemede susmali.

    Aksi halde toplulastirma, bes denemeyi birden yakan bir kapiya donerdi.
    """
    cagrildi: list[int] = []

    def sahte_kapi(plan, **_):
        cagrildi.append(1)
        return [("x", "y")]

    monkeypatch.setattr(ya, "yumusak_kapi_kusurlari", sahte_kapi)
    monkeypatch.setattr(ya, "_json_completion", lambda *a, **k: _gecerli_json())
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [])
    monkeypatch.setattr(ya, "_son_basliklar", lambda: [])
    monkeypatch.setattr(ya, "_yedek_capa_sec", lambda *_a, **_k: None)
    monkeypatch.setattr(ya, "alinti_kusuru", lambda *_a, **_k: "")
    monkeypatch.setattr(ya, "ikincil_alintilari_temizle", lambda *_a, **_k: 0)

    plan = ya.generate_content_plan(sahne_sayisi=6)

    assert plan is not None, "yumusak kapi bes denemeyi de yakti"
    # ⚠️ `YUMUSAK_KAPI_DENEMESI` fonksiyon ICINDE tanimli (modul duzeyinde
    # degil), o yuzden sayi kaynaktan okunuyor — testte ciplak 3 yazmak,
    # sabit degisince testin sessizce yanlis seyi olcmesi demekti.
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    beklenen = int(
        re.search(r"YUMUSAK_KAPI_DENEMESI = (\d+)", kaynak).group(1)
    )
    assert len(cagrildi) == beklenen, cagrildi


# --- Toplayicidaki BES kapinin her biri ayri ayri (2026-08-18) ---------------
#
# ⚠️ NEDEN VAR — mutasyon testi bir bosluk buldu: toplayicidan bir kapiyi
# `if False and ...` ile dusurunce TUM suite yesil kaldi. Mevcut testler
# kaynakta `_kanca_tekrari(` dizesini ariyordu ve mutasyon o dizeyi
# BIRAKIYORDU. Yani kapilarin gercekten CALISTIGI hic olculmuyordu.


def _yumusak(plan, **ek):
    varsayilan = {"onceki_kapanislar": [], "onceki_basliklar": [], "onceki_kancalar": []}
    varsayilan.update(ek)
    return ya.yumusak_kapi_kusurlari(plan, **varsayilan)


def test_toplayici_SAGLAM_planda_susuyor():
    """⚠️ Once bu: toplayici her plani reddediyorsa asagidakiler bos gecer."""
    assert _yumusak(_plan()) == []


def test_kapi_KANCA_kalibi():
    onceki = ["Mehmed II did not rule once.", "The Colosseum swallowed 50,000 people."]
    plan = _plan(script="Murad III did not take the throne quietly. Devam.")

    kusurlar = _yumusak(plan, onceki_kancalar=onceki)

    assert any("opening line repeats" in metin for _, metin in kusurlar), kusurlar


def test_kapi_KAPANIS_kalibi(monkeypatch):
    monkeypatch.setattr(ya, "_kapanis_tekrari", lambda *_a, **_k: True)

    kusurlar = _yumusak(_plan())

    assert any("closing line repeats" in metin for _, metin in kusurlar), kusurlar


def test_kapi_BASLIK_bicimi(monkeypatch):
    monkeypatch.setattr(ya, "_baslik_bicimi_tekrari", lambda *_a, **_k: True)

    kusurlar = _yumusak(_plan())

    assert any("title repeats the shape" in metin for _, metin in kusurlar), kusurlar


def test_kapi_ACILIS_kadraji():
    """1. sahne uzak plan alintiliyorsa toplayici susmamali."""
    plan = _plan()
    plan.scenes[0]["kaynak_dosya"] = "File:Sigiriya rock from a distance.jpg"

    kusurlar = _yumusak(plan)

    assert any("opened badly" in metin for _, metin in kusurlar), kusurlar


def test_kapi_ANLATIM_dengesi():
    """En uzun/en kisa orani esigi asarsa toplayici susmamali."""
    plan = _plan()
    plan.scenes[0]["narration"] = " ".join(["word"] * 30)
    plan.scenes[1]["narration"] = "iki kelime"

    kusurlar = _yumusak(plan)

    assert any("unevenly paced" in metin for _, metin in kusurlar), kusurlar


def test_BIRDEN_COK_kapi_ayni_listede(monkeypatch):
    """Toplayicinin var olus sebebi."""
    monkeypatch.setattr(ya, "_kapanis_tekrari", lambda *_a, **_k: True)
    monkeypatch.setattr(ya, "_baslik_bicimi_tekrari", lambda *_a, **_k: True)

    assert len(_yumusak(_plan())) == 2


def test_her_kusur_ETIKET_ve_GERI_BILDIRIM_tasiyor(monkeypatch):
    """Etiket gunluge, geri bildirim modele gidiyor; ikisi de bos olmamali."""
    monkeypatch.setattr(ya, "_baslik_bicimi_tekrari", lambda *_a, **_k: True)

    for etiket, metin in _yumusak(_plan()):
        assert etiket.strip() and metin.strip()
