"""Uzun format SENARYO URETIMI — istem, kaynak metin ve gorsel butcesi.

⚠️ NEDEN ISTEM DEGISTIRILIYOR, USTUNE YAZILMIYOR: ilk tasarim "80-120
kelime" cumlesini yerinde birakip sonuna bir gecersiz kilma blogu eklemekti.
Birakilsaydi istem kendi kendisiyle celisirdi ve her celiskili deneme
~2.000 kelimelik bir cikarim koşumu demek. `generate_content_plan` bes
denemeden sonra pes ediyor; bu hatta bes denemenin yanmasi HIC VIDEO
URETILMEMESI demek ve bu olculmus bir kusur (18:05 koşumu).
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402
import youtube_automation as ya  # noqa: E402


def _menu(n: int) -> list[dict[str, str]]:
    return [
        {"dosya": f"D{i}.jpg", "gosterdigi": f"gorsel {i}", "tarih": "1900"}
        for i in range(n)
    ]


def _istemi_yakala(monkeypatch, menu, konu="Herculaneum", **ek):
    """Planlamayi ilk cikarim cagrisinda durdurup isteme bakar."""
    yakalanan: dict = {}

    def sahte_cikarim(system: str, user: str, **_) -> dict:
        yakalanan["system"] = system
        yakalanan["user"] = user
        raise RuntimeError("dur")

    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: menu)
    monkeypatch.setattr(ya, "_json_completion", sahte_cikarim)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [])
    monkeypatch.setattr(ya, "_son_basliklar", lambda: [])
    monkeypatch.setattr(wm, "vikipedi_ozeti", lambda *_a, **_k: "OZET METNI")
    monkeypatch.setattr(wm, "vikipedi_tam_metin", lambda *_a, **_k: "TAM MAKALE METNI")

    try:
        ya.generate_content_plan(konu=konu, **ek)
    except RuntimeError:
        pass
    return yakalanan


# --- Sistem yonergesi ------------------------------------------------------


def test_SHORTS_yonergesi_YALNIZCA_kelime_araligi_kadar_farkli():
    """⚠️ Shorts hatti olculerek kalibre edildi; uzun format ona dokunmamali.

    ⚠️ IDDIA 2026-08-18'de DEGISTI ve bu bir test duzeltmesi DEGIL: eskiden
    Shorts yonergesi `EDITORYAL_YONERGE` ile BIREBIR ayniydi, cunku Shorts
    dali sozlesmeyi hic degistirmiyordu. Kusur tam da oydu — tavan 16 Agu'da
    150'ye cikarildi ama istemdeki sabit metin "80-120" kaldi, yani modele
    tutturamayacagi bir hedef soyleniyordu (bkz. `test_istem_kapiyla_tutarli`).

    Artik iki kip de sayiyi bicimden enjekte ediyor. Testin KORUDUGU sey
    degismedi: uzun formata ozgu hicbir metin Shorts'a sizmamali; Shorts
    yonergesi ile ham sozlesme arasindaki TEK fark kelime araligi olmali.
    """
    shorts = ya.editoryal_sistem_yonergesi(ya.SHORTS_BICIMI)

    assert shorts == ya.editoryal_sistem_yonergesi(), "varsayilan bicim Shorts olmali"

    # Kelime cumlesi geri konunca ham sozlesmenin AYNISI cikmali: baska hicbir
    # sey degismedi.
    en_az, en_cok = ya.SHORTS_BICIMI.kelime_araligi
    geri = shorts.replace(
        f"The script must be {en_az}-{en_cok} spoken English words",
        ya.KELIME_CUMLESI,
    )
    assert geri == ya.KANAL_SESI + ya.EDITORYAL_YONERGE

    # Uzun kipe ozgu metinler Shorts'a SIZMAMALI.
    assert "documentary channel" not in shorts
    assert "NEVER put #Shorts" not in shorts


def test_uzun_yonergede_SHORTS_SAYILARI_YOK():
    """⚠️ Asil mesele bu: eski sayilar kalirsa istem kendisiyle celisir."""
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert "80-120 spoken English words" not in uzun
    assert "Create 6-10 chronological scenes." not in uzun


def test_uzun_yonerge_BICIMIN_sayilarini_tasiyor():
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)
    kelime_en_az, kelime_en_cok = ya.UZUN_BICIMI.kelime_araligi
    sahne_en_az, sahne_en_cok = ya.UZUN_BICIMI.sahne_araligi

    assert f"{kelime_en_az}-{kelime_en_cok} spoken English words" in uzun
    assert f"Create {sahne_en_az}-{sahne_en_cok} chronological scenes." in uzun


def test_uzun_yonergede_baslik_SHORTS_ETIKETI_ISTEMIYOR():
    """⚠️ `#Shorts` kalirsa YouTube videoyu Shorts sayar ve IZLENME SAATI
    YAZMAZ — uzun formatin butun amaci o saatler."""
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert "and contain #Shorts." not in uzun
    assert "NEVER put #Shorts" in uzun


def test_uzun_yonerge_kanali_SHORTS_KANALI_diye_tanitmiyor():
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert "YouTube Shorts channel" not in uzun
    assert "YouTube documentary channel" in uzun


def test_uzun_yonerge_BOLUMLU_anlati_istiyor():
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert ya.UZUN_YONERGE in uzun
    assert "three to five thematic sections" in uzun


def test_uzun_yonerge_sahne_anlatimlarini_ESIT_UZUNLUKTA_istiyor():
    """⚠️ Kozmetik degil: `run_generator` her kareye ESIT sure veriyor, yani
    sahne i'nin karesi sesin i'nci esit diliminde ekranda. 45 sahnede
    dengesizlik birikir ve gorsel soylenenden kopar."""
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert "THE SCENE NARRATIONS ARE THE SCRIPT" in uzun
    assert "same length as the others" in uzun


# --- Sahne basina kelime hedefi -------------------------------------------
#
# ⚠️ Olculdu (2026-08-15, dorduncu Herculaneum koşumu): bes denemenin
# sonuncusu 1.055 kelimeydi ve sozlesme 1.200-2.200 istiyor. Koşum #1'de
# ayni model 1.353 kelime uretmisti, yani YAPABILIYOR ama tutarli degil.
#
# Sebep aritmetik: istem TOPLAM kelimeyi soyluyordu, sahne BASINA hicbir sey
# soylemiyordu. Model Shorts uzunlugunda (~30 kelime) anlatimlar yazip 35
# sahneye boluyor: 35 x 30 = 1.050, tabanin hemen altinda.


def test_uzun_yonerge_SAHNE_BASINA_kelime_soyluyor():
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert "45 words per narration at 35 scenes" in uzun


def test_uzun_yonerge_SHORTS_UZUNLUGUNDA_anlatimi_acikca_yasakliyor():
    """Modelin dustugu tuzak adiyla anilmali; genel "uzun yaz" yetmedi."""
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert "25-30 words is a Short's scene" in uzun


def test_uzun_yonerge_CARPMAYI_istiyor():
    """⚠️ Model sayilari once carpmazsa hatayi ancak 20 dakika sonra goruyoruz."""
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert "Multiply the number of scenes" in uzun
    # ⚠️ Taban SAYI olarak yazilmiyor: kelime araligi bicimden geliyor ve
    # 1.200 -> 900 degisiminde istem sessizce yanlis sayiyi tasirdi.
    assert "under the floor the plan is rejected" in uzun


def test_anlatimlar_SENARYONUN_KENDISI_oldugu_yaziyor():
    """Model anlatimlari senaryonun OZETI sanirsa toplam kelime tutmuyor."""
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert "not a summary of it" in uzun


def test_SHORTS_yonergesi_bu_maddelerden_ETKILENMIYOR():
    """⚠️ Sahne basina 45 kelime Shorts'ta 8x45 = 360 kelime demek; sozlesme
    80-120 istiyor. Madde Shorts'a sizarsa her Shorts plani reddedilir."""
    kisa = ya.editoryal_sistem_yonergesi(ya.SHORTS_BICIMI)

    assert "45 words per narration" not in kisa
    assert "Multiply the number of scenes" not in kisa


def test_uzun_yonerge_KIMLIGI_ve_SOZLESMEYI_koruyor():
    """Kanal sesi ve JSON sozlesmesi dusmemeli — yalnizca sayilar degisiyor."""
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert "ONE FIXED EDITORIAL ANGLE" in uzun
    assert "Say what is NOT known" in uzun
    assert "JSON keys:" in uzun
    assert "NEVER USE A DASH CHARACTER" in uzun


def test_hedef_cumle_kaybolursa_SESSIZ_GECMIYOR():
    """⚠️ Sessiz `str.replace` en tehlikeli hali olurdu: Shorts sozlesmesi
    degisirse uzun istem eski sayilari tasimaya devam eder ve kusur ancak
    bes deneme yandiktan sonra fark edilir."""
    with pytest.raises(RuntimeError, match="artik istemde yok"):
        ya._yonerge_degistir("bambaska bir metin", "olmayan cumle", "yeni")


# --- Kaynak metin ----------------------------------------------------------


def test_uzun_kipte_TAM_MAKALE_veriliyor(monkeypatch):
    """⚠️ Olculdu: ozet 32-102 kelime, tam makale 1.492-7.539 (27-193 kat).
    56 kelimelik ozetten 2.000 kelime yazmasi istenen model uydurur."""
    yakalanan = _istemi_yakala(monkeypatch, _menu(40), bicim=ya.UZUN_BICIMI)

    assert "TAM MAKALE METNI" in yakalanan["user"]
    assert "OZET METNI" not in yakalanan["user"]


def test_SHORTS_kipi_hala_OZET_aliyor(monkeypatch):
    yakalanan = _istemi_yakala(monkeypatch, _menu(40))

    assert "OZET METNI" in yakalanan["user"]
    assert "TAM MAKALE METNI" not in yakalanan["user"]


# --- Konu zorunlulugu ------------------------------------------------------


def test_uzun_bicim_KONUSUZ_calismiyor():
    """⚠️ Kaynak metin ve arsiv menusu bloklarinin ikisi de `if konu:`
    dalinin icinde. Konusuz uzun plan, 2.000 kelimeyi HAFIZADAN yazmak ve
    alinti kapisini sessizce kapatmak olurdu (DW-114)."""
    with pytest.raises(ValueError, match="konu` zorunlu"):
        ya.generate_content_plan(bicim=ya.UZUN_BICIMI)


# --- Arsiv on kontrolu -----------------------------------------------------


def test_INCE_ARSIV_cikarim_BASLAMADAN_eleniyor(monkeypatch):
    """⚠️ Bu durumu `alinti_kusuru` huni kipinde cozemez: konu sabit ve
    kapinin geri bildirimi "baska bir seye capa at" diyor. Model bunu
    yapamaz, bes deneme yanar, koşum HIC VIDEO URETMEDEN duser."""

    def cagrilmamali(*_a, **_k):
        raise AssertionError("ince arsivde cikarim koşumu baslatilmamali")

    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: _menu(10))
    monkeypatch.setattr(ya, "_json_completion", cagrilmamali)

    with pytest.raises(ya.UzunFormatUygunDegilError, match="10 kullanilabilir"):
        ya.generate_content_plan(konu="Ince Konu", bicim=ya.UZUN_BICIMI)


def test_on_kontrol_esigi_SAHNE_TABANINDAN(monkeypatch):
    """Tam sahne tabani kadar gorsel varsa uretim BASLAMALI."""
    yakalanan = _istemi_yakala(
        monkeypatch, _menu(ya.UZUN_BICIMI.sahne_araligi[0]), bicim=ya.UZUN_BICIMI
    )

    assert yakalanan.get("user"), "esikteki konu elenmemeliydi"


def test_SHORTS_kipinde_on_kontrol_YOK(monkeypatch):
    """Shorts ince arsivde de uretiliyor; kapi yalnizca uzun formatta."""
    yakalanan = _istemi_yakala(monkeypatch, _menu(3))

    assert yakalanan.get("user"), "Shorts ince arsivde durmamali"


# --- Gorsel butcesi --------------------------------------------------------


def test_uzun_kipte_menu_siniri_60():
    assert ya.envanter_siniri(ya.UZUN_BICIMI) == ya.UZUN_ENVANTER_SINIRI == 60
    assert ya.envanter_siniri(ya.SHORTS_BICIMI) == ya.ARSIV_ENVANTER_SINIRI == 40
    assert ya.envanter_siniri() == ya.ARSIV_ENVANTER_SINIRI


def test_menu_siniri_sahne_TAVANINI_karsiliyor():
    """⚠️ 40'lik menuyle 45 sahne istemek imkansizi istemek olurdu: her
    sahne menuden AYRI bir dosya alintilamak zorunda."""
    assert ya.UZUN_ENVANTER_SINIRI >= ya.UZUN_BICIMI.sahne_araligi[1]


def test_onbellek_SINIRA_gore_ayrisiyor(monkeypatch):
    """⚠️ Yalnizca konuyla anahtarlansaydi once calisan Shorts koşumu
    40'lik menuyu onbellege koyar, uzun koşum 60 isteyip 40 alirdi. Kapinin
    modele gosterilenden BASKA listeye bakmasi bu dosyada olculmus bir
    kusur sinifi ("Jock Willis")."""
    ya._ENVANTER_ONBELLEGI.clear()
    istenen: list[int] = []

    def sahte(konu, sinir, **_):
        istenen.append(sinir)
        return [
            # ⚠️ Aciklama ICERIK tasimali: menu artik iceriksiz aciklamayi
            # eliyor. Bu testin konusu onbellek anahtari, aciklama degil.
            {"title": f"File:D{i}.jpg", "aciklama": f"Tomb chamber wall {i}", "tarih": ""}
            for i in range(sinir)
        ]

    monkeypatch.setattr(wm, "arsiv_menusu", sahte)

    assert len(ya.arsiv_envanteri("Konu", sinir=40)) == 40
    assert len(ya.arsiv_envanteri("Konu", sinir=60)) == 60
    assert istenen == [40, 60], "ikinci sinir onbellekten yanlis cevap aldi"

    ya._ENVANTER_ONBELLEGI.clear()


def test_uzun_kipte_IKINCI_GORSEL_istenmiyor():
    """⚠️ Uzun formatta sahne basina TEK kare var; ikinci gorsel istemek
    menunun iki katini tuketir ve ekranda hicbir sey degistirmez."""
    talimat = ya._menu_talimati(_menu(60), 30, bicim=ya.UZUN_BICIMI)

    assert "ALSO pick a SECOND entry" not in talimat
    assert "one picture in this format" in talimat


def test_SHORTS_kipinde_ikinci_gorsel_KORUNUYOR():
    talimat = ya._menu_talimati(_menu(40), 8)

    assert "ALSO pick a SECOND entry" in talimat


def test_uzun_talimat_sahne_TAVANINI_menuden_soyluyor():
    """⚠️ Model menu boyutunu bilmezse 32 dosyalik arsivde 40 sahne yazar,
    `alinti_kusuru` plani reddeder ve bes deneme yanar."""
    talimat = ya._menu_talimati(_menu(32), 45, bicim=ya.UZUN_BICIMI)

    assert "32 usable images" in talimat
    assert "between 24 and 32 scenes" in talimat


def test_menu_tavani_sahne_ARALIGINI_asmiyor():
    """Menu bol olsa bile tavan bicimin ust siniri."""
    # ⚠️ Tavan 45 -> 39 (2026-08-15, belgesel ritmi: 900 kelimede 45 sahne
    # 7,0 sn/kare verir, taban 8 sn).
    talimat = ya._menu_talimati(_menu(60), 39, bicim=ya.UZUN_BICIMI)

    assert "between 24 and 39 scenes" in talimat


def test_SHORTS_talimatinda_tavan_cumlesi_YOK():
    talimat = ya._menu_talimati(_menu(40), 8)

    assert "usable images, so this video can have at most" not in talimat


# --- Baslik kapisi ---------------------------------------------------------


def test_uzun_kipte_SHORTS_ETIKETLI_baslik_REDDEDILIYOR():
    """⚠️ KOD KAPISI, yalnizca istem degil: isteme son basliklar da veriliyor
    ve hepsi `#Shorts` ile bitiyor. Model taklit ederse kapi tutar."""
    plan = ya.ContentPlan(
        topic="konu",
        visual_anchor="Herculaneum",
        title="Herculaneum: What the Ash Kept #Shorts",
        script="Herculaneum was buried. " + "word " * 1400,
        scenes=[
            {"narration": f"sahne {i}", "search_term": f"Herculaneum detay {i}"}
            for i in range(30)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )

    with pytest.raises(ValueError, match="contains #Shorts"):
        ya.validate_content_plan(plan, bicim=ya.UZUN_BICIMI)


def test_SHORTS_kipinde_etiket_hala_SERBEST():
    plan = ya.ContentPlan(
        topic="konu",
        visual_anchor="Herculaneum",
        title="What Did Herculaneum Keep? #Shorts",
        script="Herculaneum was buried. " + "word " * 97,
        scenes=[
            {"narration": f"sahne {i}", "search_term": f"Herculaneum detay {i}"}
            for i in range(8)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )

    ya.validate_content_plan(plan)


# --- Hatta baglanti --------------------------------------------------------


def test_bicim_DOGRULAMAYA_gecirilyor():
    """⚠️ Bu tel unutulursa her uzun plan "80-120 words" ile reddedilir —
    kusur sessiz, cunku mesaj kelime sayisindan bahseder, bicimden degil."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    def bosluksuz(metin: str) -> str:
        return re.sub(r"\s+", "", metin)

    # ⚠️ TAM cagri dizesi ARANMIYOR: cagriya sonradan `konu=` eklendi
    # (2026-08-15, capa genisligi kapisi) ve birebir eslesme bunu kusur
    # sanmisti. Aranan sey telin kendisi — `sahne_sayisi` ve `bicim` ayni
    # cagrida gidiyor mu.
    # ⚠️ CAGRILAN ADI DEGISTI (2026-08-18): dongu artik `plan_kusurlari`
    # cagiriyor, cunku modele tek kusur degil HEPSI geri besleniyor (gerekce
    # o fonksiyonun docstring'inde). KORUNAN OZELLIK AYNI — bu test bicimin
    # dogrulamaya gecirildigini olcuyor, cagrilanin adini degil.
    assert bosluksuz("plan_kusurlari(plan,sahne_sayisi,bicim=bicim") in bosluksuz(kaynak)
    assert bosluksuz("editoryal_sistem_yonergesi(bicim)") in bosluksuz(kaynak)
