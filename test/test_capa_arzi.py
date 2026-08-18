"""Modelin sectigi CAPA'nin arsivi videoyu tasiyabiliyor mu (DW-51 / #37).

⚠️ OLCULDU (2026-08-17, slot 14, canli). Huni kipinde terfi kapisi KUYRUK
BASLIGINI olcuyor, uretim ise modelin sectigi CAPA'yi kullaniyor:

    kuyruk basligi          menu | modelin capasi    menu
    King Philip's War         16 | Metacom              1
    Köktürk                   18 | Göktürks           10
    Operation Storm           15 | Operation Storm    15   <- uyumlu
    Cemal Bajá                13 | Djemal Pasha       29   <- uyumlu

King Philip's War terfi kapisini 16 ile gecti ve reddedildi: model olayi
birakip KISIYI capa secti, o kisinin arsivi 1 dosya. Sahne 9-12 modern
fotograflarla doldu, hakem 8 agir kusur yazdi.

⚠️ Kapi TERFIYE eklenemez — capayi model seciyor, terfi aninda o menu
heNUZ YOKTUR. Dogru yer plan kurulduktan sonra: capa artik bilinir ve
dongu geri bildirimle yeniden deneyebilir.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(capa: str, sahne: int = 6) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor=capa,
        title="baslik",
        script="metin",
        scenes=[{"narration": "x", "search_term": "y"} for _ in range(sahne)],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def _menu(monkeypatch, adet: int):
    monkeypatch.setattr(
        ya,
        "arsiv_envanteri",
        lambda konu, **_k: [
            {"dosya": f"{konu}-{i}.jpg", "gosterdigi": "x", "tarih": ""}
            for i in range(adet)
        ],
    )


# ⚠️ OLCUT DEGISTI (2026-08-18) ve bu bir TEST DUZELTMESI DEGIL, kararin
# kendisi degisti. Kapi eskiden `ikinci_gorsel_istenebilir`i (sahne x 2 = 12)
# cagiriyordu; artik `arsiv_videoyu_tasir`i (sahne x 1 = 6) cagiriyor.
#
# Sebep: 12 "her sahne IKI ayri dosya alabilir mi" demek ve o, ikinci ALINTI
# istenip istenmeyecegini belirleyen dogru sorudur. Ama bu kapida sorulan sey
# farkli — "bu arsiv bir video cikarabilir mi". Ikinci gorsel bir IYILESTIRME
# (bkz. `ikincil_gorseller`) ve `_menu_talimati` artik kucuk menude KISMI
# ikinci gorsel istiyor, yani 8 dosyalik bir arsiv 6 birincil + 2 ikincil
# verip gayet iyi bir video cikariyor.
#
# Eski esigin YANLIS RED verdigi yukaridaki tablodan okunuyor: `Göktürks` 10
# dosyayla reddediliyordu. Canlida da olculdu — kuyruktaki 6 adaydan biri
# (Ernst Hanfstaengl, menu 8) yalnizca bu yuzden atlaniyordu.
#
# ⚠️ BILINEN BEDELI: 6-11 dosyalik KISI capalari da geciyor ve olculdu ki
# kisi konulari 9-11 kusur aliyor (anit/yer 0-3). Bu sayiyla korunmuyordu
# zaten — sayi ARZI olcer, konu sinifini olcmez. Yanlis kisi/donem gosteren
# video hakemin AGIR KUSUR kapisinda duruyor ve o kapi DEGISMEDI.


def test_ZAYIF_capa_kusur_bildiriyor(monkeypatch):
    """Canli hal: `Metacom` 1 dosya — hangi esikle olcursen olc gecmemeli."""
    _menu(monkeypatch, 1)

    kusur = ya._capa_arzi_kusuru(_plan("Metacom"), bicim=ya.SHORTS_BICIMI)

    assert kusur, "1 dosyalik capa gecmemeli"
    assert "Metacom" in kusur
    # ⚠️ Mesaj KAPININ OLCTUGU sayiyi soylemeli. Bu oturumda (#41) tam ters
    # kusur olculdu: modele 80-120 deniyor, kapi 80-150 olcuyordu.
    assert "6" in kusur, "gereken sahne sayisi mesajda olmali"
    assert "12" not in kusur, "eski olcut mesajda kalmis"


def test_SINIRDAKI_capa_geciyor(monkeypatch):
    """Tam 6 = her sahneye bir birincil — kapi sinirda ACIK."""
    _menu(monkeypatch, 6)

    assert ya._capa_arzi_kusuru(_plan("Tikal"), bicim=ya.SHORTS_BICIMI) == ""


def test_ESKIDEN_REDDEDILEN_bant_artik_geciyor(monkeypatch):
    """⚠️ Gerilemenin yonu: 6-11 arasi ARTIK GECMELI.

    `Göktürks` 10 dosyayla reddediliyordu (yukaridaki tablo) ve `Ernst
    Hanfstaengl` 8 ile kuyrukta atlaniyordu. Ikisi de 6 sahneye ayri
    birincil verebiliyor.
    """
    for adet in (8, 10, 11):
        _menu(monkeypatch, adet)
        assert (
            ya._capa_arzi_kusuru(_plan("Göktürks"), bicim=ya.SHORTS_BICIMI) == ""
        ), f"{adet} dosya 6 sahneye yetmeliydi"


def test_sinirin_ALTI_dusuyor(monkeypatch):
    """5 dosya, 6 sahne — bir sahne kacinilmaz olarak tekrar gosterirdi."""
    _menu(monkeypatch, 5)

    assert ya._capa_arzi_kusuru(_plan("Metacomet"), bicim=ya.SHORTS_BICIMI) != ""


def test_MENU_CEKILEMEZSE_kusur_YOK(monkeypatch):
    """⚠️ Menu bir IYILESTIRME, on kosul degil.

    `arsiv_envanteri` ag hatasinda `[]` donduruyor. Bos menuyu kusur saymak,
    tek bir 429'un butun koşumu reddettirmesi demek olurdu.
    """
    _menu(monkeypatch, 0)

    assert ya._capa_arzi_kusuru(_plan("Herhangi"), bicim=ya.SHORTS_BICIMI) == ""


def test_sahne_sayisi_VERILIRSE_ona_bakiyor(monkeypatch):
    """Sahne sayisi kod tarafindan sabitlenebiliyor; olcut ona uymali."""
    _menu(monkeypatch, 5)

    # 4 sahne -> 5 dosya yeter
    assert ya._capa_arzi_kusuru(
        _plan("X", sahne=6), bicim=ya.SHORTS_BICIMI, sahne_sayisi=4
    ) == ""
    # 6 sahne -> 5 dosya yetmez
    assert ya._capa_arzi_kusuru(
        _plan("X", sahne=6), bicim=ya.SHORTS_BICIMI, sahne_sayisi=6
    ) != ""


def test_olcut_arsiv_videoyu_tasir_ILE_AYNI(monkeypatch):
    """⚠️ Kapi olcutu KENDI yazmamali, ortak fonksiyonu cagirmali.

    Iki yerde iki ayri hesap tutmak, kuyruk kapisinin gecirdigi adayi plan
    kapisinin reddetmesi demek olurdu: slot yine yanar, ama bu kez sessizce.
    """
    cagrildi: list[tuple] = []
    gercek = ya.arsiv_videoyu_tasir

    def izle(menu, sahne_sayisi):
        cagrildi.append((len(menu), sahne_sayisi))
        return gercek(menu, sahne_sayisi)

    monkeypatch.setattr(ya, "arsiv_videoyu_tasir", izle)
    _menu(monkeypatch, 20)

    ya._capa_arzi_kusuru(_plan("Tikal"), bicim=ya.SHORTS_BICIMI)

    assert cagrildi == [(20, 6)]


def test_IKINCI_GORSEL_olcutu_AYRI_kaldi():
    """⚠️ `ikinci_gorsel_istenebilir` DEGISMEDI ve degismemeli: onun sorusu
    hala "her sahne iki ayri dosya alabilir mi" ve istem o cevaba gore
    tam/kismi ikinci gorsel istiyor."""
    menu = [{"dosya": f"{i}.jpg", "gosterdigi": "x", "tarih": ""} for i in range(8)]

    assert ya.arsiv_videoyu_tasir(menu, 6), "8 dosya videoyu tasir"
    assert not ya.ikinci_gorsel_istenebilir(menu, 6), "ama 12 kare vermez"


def test_kapi_PLAN_dongusunde_calisiyor(monkeypatch):
    """Kusur bildirmek yetmez; `generate_content_plan` onu KULLANMALI.

    Zayif capali ilk plan reddedilip ikinci deneme istenmeli — ve reddin
    gerekcesi isteme yazilmali ki model ayni capayi tekrar secmesin.
    """
    kaynak = Path(ya.__file__).read_text()
    # ⚠️ BOSLUKTAN BAGIMSIZ: cagri 2026-08-18'de `konu=` alinca satir sardi ve
    # bitisik dize arayan eski hali bunu "kapi baglanmamis" sandi. Kusur kodda
    # degil, testin kodu okuma bicimindeydi (ayni ders `test_uzun_senaryo`de).
    bosluksuz = re.sub(r"\s+", "", kaynak)

    assert "_capa_arzi_kusuru(plan" in bosluksuz, "kapi donguye baglanmamis"
    # ⚠️ VE KONUYU GECIRMELI: kapi capanin degil, MODELE GOSTERILEN menunun
    # arzini olcuyor. `konu=` dusarse kapi sessizce eski (yanlis) listeye
    # doner — olculdu: Köktürk konusu 18 dosya GECER, modelin capasi
    # 'Bilge Qaghan' 1 dosya RED.
    assert "sahne_sayisi=sahne_sayisi,konu=konu" in bosluksuz, "konu gecirilmiyor"


def test_KUYRUK_kapisi_ayni_olcutu_kullaniyor():
    """⚠️ Iki kapinin ayrisması sessiz slot yakar; ortak fonksiyon sart."""
    kaynak = Path(ya.__file__).read_text()

    assert "arsiv_videoyu_tasir(envanter, asgari_menu)" in kaynak


def test_UZUN_bicimde_de_sahne_basina_BIR_gorsel(monkeypatch):
    """⚠️ Eskiden burasi bir farki donduruyordu: olcut global `KARE_YUVASI`
    (2) idi, yani uzun bicimde `kare_yuvasi` 1 olmasina ragmen kapi 2 yuva
    sayiyordu. Yeni olcut yuvadan BAGIMSIZ (sahne basina bir birincil), yani
    o tuhaflik kendiliginden kalkti.
    """
    _menu(monkeypatch, 6)

    assert ya._capa_arzi_kusuru(
        _plan("X", sahne=6), bicim=ya.UZUN_BICIMI, sahne_sayisi=6
    ) == ""
    assert ya._capa_arzi_kusuru(
        _plan("X", sahne=7), bicim=ya.UZUN_BICIMI, sahne_sayisi=7
    ) != ""


# --- KAPI HANGI MENUYE BAKIYOR (2026-08-18) ---------------------------------
#
# ⚠️ NEDEN VAR — kapi `plan.visual_anchor`in arsivini sorguluyordu, ama sahne
# birincilleri o sorgudan GELMIYOR: model istemde KONU menusunu goruyor ve
# sahneler o menuden alinti yapiyor (`alinti_kusuru` bunu zorunlu tutuyor).
# Yani kapi modele hic gosterilmemis bir listeyi olcup plani reddediyordu.
#
# Olculdu (18 Agu aksami, canli, kapinin KENDI olcutuyle, 6 sahne):
#
#     KONU  'Köktürk'              18 dosya  GECER
#       capa 'Kül Tigin'            2 dosya  RED
#       capa 'Orkhon inscriptions'  4 dosya  RED
#       capa 'Bilge Qaghan'         1 dosya  RED
#     KONU  "King Philip's War"    16 dosya  GECER
#       capa 'Metacom'              1 dosya  RED
#
# O aksam olen iki koşumun ikisi de bu kapida oldu ve ikisinin de KONU
# menusu fazlasiyla yetiyordu.
#
# ⚠️ `alinti_kusuru`nun "Jock Willis" dersinin birebir aynisi (2026-08-14):
# "kapinin modele gosterilenden BASKA bir listeye bakmasi, kapiyi cozdugu
# kusurun kaynagina cevirir."


def _menu_haritasi(monkeypatch, harita: dict[str, int]):
    """Anahtara GORE farkli buyuklukte menu — hangi anahtarin sorguldugunu olcer."""
    sorulan: list[str] = []

    def sahte(konu, **_k):
        sorulan.append(konu)
        return [
            {"dosya": f"{konu}-{i}.jpg", "gosterdigi": "x", "tarih": ""}
            for i in range(harita.get(konu, 0))
        ]

    monkeypatch.setattr(ya, "arsiv_envanteri", sahte)
    return sorulan


def test_KONU_verilirse_ONUN_menusu_olculuyor(monkeypatch):
    """Canli vakanin birebir kopyasi: Köktürk 18, Bilge Qaghan 1."""
    sorulan = _menu_haritasi(monkeypatch, {"Köktürk": 18, "Bilge Qaghan": 1})

    kusur = ya._capa_arzi_kusuru(
        _plan("Bilge Qaghan"), bicim=ya.SHORTS_BICIMI, sahne_sayisi=6, konu="Köktürk"
    )

    assert kusur == "", f"konu menusu 18 dosya, kapi susmaliydi: {kusur}"
    assert sorulan == ["Köktürk"], sorulan


def test_KONU_YOKSA_capaya_dusuyor(monkeypatch):
    """Yedek kipte konu yok; o zaman capa TEK olculebilir sey."""
    sorulan = _menu_haritasi(monkeypatch, {"Bilge Qaghan": 1})

    kusur = ya._capa_arzi_kusuru(
        _plan("Bilge Qaghan"), bicim=ya.SHORTS_BICIMI, sahne_sayisi=6
    )

    assert kusur != "", "arzsiz capa yedek kipte de gecmemeli"
    assert sorulan == ["Bilge Qaghan"], sorulan


def test_KONU_menusu_de_YETMEZSE_kapi_calisiyor(monkeypatch):
    """⚠️ Kapi KALDIRILMADI — yalnizca paydasi duzeldi."""
    _menu_haritasi(monkeypatch, {"Ufak Konu": 3})

    kusur = ya._capa_arzi_kusuru(
        _plan("Herhangi"), bicim=ya.SHORTS_BICIMI, sahne_sayisi=6, konu="Ufak Konu"
    )

    assert "3 gorsel" in kusur, kusur


def test_mesaj_OLCULEN_anahtari_soyluyor(monkeypatch):
    """Kusur metni gunluge giriyor; yanlis adi yazmak teshisi saptirirdi."""
    _menu_haritasi(monkeypatch, {"Ufak Konu": 2})

    kusur = ya._capa_arzi_kusuru(
        _plan("Baska Capa"), bicim=ya.SHORTS_BICIMI, sahne_sayisi=6, konu="Ufak Konu"
    )

    assert "Ufak Konu" in kusur and "Baska Capa" not in kusur, kusur


def test_alinti_kapisiyla_AYNI_anahtar():
    """⚠️ Iki kapi ayni menuye bakmali; ayrisirlarsa biri digerinin cozdugu
    kusuru geri getirir. `alinti_kusuru` anahtari `menu_konusu or capa`."""
    kaynak = Path(ya.__file__).read_text()
    bosluksuz = re.sub(r"\s+", "", kaynak)

    assert "menu_konusu.strip()orplan.visual_anchor" in bosluksuz
    assert "konu.strip()orplan.visual_anchor" in bosluksuz
