"""Menu goru aciklamasi — `menuyu_zenginlestir` ve bagli oldugu yerler.

⚠️ OLCULMUS KUSUR (2026-08-20, kaynak hakemi 65/70): model menuden KOR
seciyor. Herculaneum menusunde 19/30 girdinin `gosterdigi`si dosya adinin
aynisi, dordu ("Herculaneum 002/003/004/007") ayni 140 karakterlik yer
metnini paylasiyor ve biri YALAN soyluyor (adi "View of Casa d'Argo",
kare mimari bir cephe cizimi). Hakemin sekiz kusurunun besi bu yoldan.

Olcum sondasi: 30 girdi, 3 sayfa, 32 saniye, 30/30 somut aciklama; ayni
kunyeyi paylasan dort girdi dort AYRI sey olarak tarif edildi.
"""

import json
from pathlib import Path

import pytest

import wikimedia_materials
import youtube_automation as ya


@pytest.fixture(autouse=True)
def _temiz_onbellek(tmp_path, monkeypatch):
    """Her test kendi disk onbellegiyle — gercek dosyaya dokunulmuyor.

    ⚠️ `REVIEW_DIR` DE YONLENDIRILIYOR: `create_source_montage` sayfayi
    diske yaziyor ve testler onu monkeypatch'lemiyor. Ilk surumde bes
    sahte kontak sayfasi URETIM klasorune (`storage/.../reviews/`) yazildi
    ve gercek hakem ciktilarinin arasina karisti — o klasor geriye donuk
    "hakem ne gordu" incelemesinin tek kaydi.
    """
    monkeypatch.setattr(ya, "MENU_GORUSU_DOSYASI", tmp_path / "menu_gorusu.json")
    monkeypatch.setattr(ya, "REVIEW_DIR", tmp_path / "reviews")
    ya._ENVANTER_ONBELLEGI.clear()
    yield
    ya._ENVANTER_ONBELLEGI.clear()


def _menu(n: int, *, kunye: str = "") -> list[dict[str, str]]:
    return [
        {
            "dosya": f"Dosya {sira}.jpg",
            "gosterdigi": kunye or f"Dosya {sira}",
            "tarih": "1900",
        }
        for sira in range(1, n + 1)
    ]


def _goruyu_bagla(monkeypatch, *, eksik: set[int] = frozenset()) -> list[dict]:
    """Sahte goru: her numaraya kendi aciklamasini yazar. Cagrilari sayar."""
    cagrilar: list[dict] = []

    def sahte_goru(istem, yol, **_k):
        cagrilar.append({"istem": istem, "yol": yol})
        return {
            "captions": [
                {
                    "n": girdi["n"],
                    "goruntu": f"karede {girdi['n']} numarali sey var",
                    "tur": "photo",
                }
                for girdi in istem["entries"]
                if girdi["n"] not in eksik
            ]
        }

    monkeypatch.setattr(ya, "_vision_json", sahte_goru)
    return cagrilar


def _kucukleri_bagla(monkeypatch, tmp_path, *, dusen: set[str] = frozenset()):
    """Sahte kucuk resim indirici — gercek 1x1 JPEG yaziyor."""
    from PIL import Image

    def sahte(dosyalar, hedef_dizin):
        hedef_dizin = Path(hedef_dizin)
        hedef_dizin.mkdir(parents=True, exist_ok=True)
        yollar = {}
        for sira, ad in enumerate(dosyalar):
            if ad in dusen:
                continue
            yol = hedef_dizin / f"k-{sira:03d}.jpg"
            Image.new("RGB", (40, 30), "white").save(yol)
            yollar[ad] = yol
        return yollar

    monkeypatch.setattr(wikimedia_materials, "menu_kucuk_resimleri", sahte)


# --- Degismezler ----------------------------------------------------------


def test_zenginlestirme_GIRDI_KUMESINI_degistirmiyor(monkeypatch, tmp_path):
    """⚠️ Deponun imza kusurunun panzehiri.

    `arsiv_envanteri` ayni zamanda kapma kapisi ve huni terfi olcutu.
    Zenginlestirme bir girdiyi elerse `on_menu`nun saydigi kume ile modele
    gosterilen kume ayrisir — ve o ayrisma tam da `alinti_kusuru`nun
    "Jock Willis" dersinde olculmus kusur.

    Aciklamasi GELMEYEN girdi bile listede kalmali.
    """
    _kucukleri_bagla(monkeypatch, tmp_path)
    _goruyu_bagla(monkeypatch, eksik={2, 5})
    menu = _menu(6)

    zengin = ya.menuyu_zenginlestir(menu, "Konu", bicim=ya.UZUN_BICIMI)

    assert len(zengin) == len(menu)
    assert [g["dosya"] for g in zengin] == [g["dosya"] for g in menu]
    # Aciklamasi gelmeyenler de duruyor, yalnizca `goruntu` tasimiyorlar.
    assert not zengin[1].get("goruntu")
    assert zengin[0]["goruntu"]


def test_aciklama_HUCRE_NUMARASIYLA_eslesiyor(monkeypatch, tmp_path):
    """⚠️ Ikinci sayfa 13-24 numarali, ama dosya listesi 0-tabanli.

    Olcum sondasinda tam bu kayma yasandi: dilimlenmis listeye 13-24
    numaralari verilince `create_source_montage`in indeksi tasti ve o
    sayfanin 12 aciklamasinin 12'si de bosa gitti.
    """
    _kucukleri_bagla(monkeypatch, tmp_path)
    _goruyu_bagla(monkeypatch)

    zengin = ya.menuyu_zenginlestir(_menu(20), "Konu", bicim=ya.UZUN_BICIMI)

    # 13. girdi 13 numarali aciklamayi almali, 1 numaraliyi degil.
    assert zengin[12]["goruntu"] == "karede 13 numarali sey var"
    assert zengin[0]["goruntu"] == "karede 1 numarali sey var"


def test_sayfa_HAKEM_ORNEK_TAVANINI_asmiyor(monkeypatch, tmp_path):
    """⚠️ 1600x3600 kontak sayfasinda model BOS cevap donuyor.

    Ders `kaynak_ornegi` docstring'inde olculu (dokuzuncu Herculaneum
    koşumu, 46,2 dakika). Sabit OKUNUYOR, kopyalanmiyor.
    """
    _kucukleri_bagla(monkeypatch, tmp_path)
    cagrilar = _goruyu_bagla(monkeypatch)

    ya.menuyu_zenginlestir(_menu(30), "Konu", bicim=ya.UZUN_BICIMI)

    assert len(cagrilar) == 3
    for cagri in cagrilar:
        assert len(cagri["istem"]["entries"]) <= ya.HAKEM_ORNEK_TAVANI


def test_goru_dususu_MENUYU_AYNEN_donduruyor(monkeypatch, tmp_path):
    """Aciklama bir IYILESTIRME, on kosul degil.

    `arsiv_envanteri`nin `return []` doktrini: goru ucu 429 ya da 5xx
    donerse plan asamasi eski menuyle calismaya devam etmeli.
    """
    _kucukleri_bagla(monkeypatch, tmp_path)
    monkeypatch.setattr(
        ya, "_vision_json", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("429"))
    )
    menu = _menu(4)

    zengin = ya.menuyu_zenginlestir(menu, "Konu", bicim=ya.UZUN_BICIMI)

    assert [g["dosya"] for g in zengin] == [g["dosya"] for g in menu]
    assert not any(g.get("goruntu") for g in zengin)


def test_kucuk_resmi_INMEYEN_girdi_menude_kaliyor(monkeypatch, tmp_path):
    """Teslim edilemeyen dosya sayfaya konmaz ama menuden ELENMEZ."""
    _kucukleri_bagla(monkeypatch, tmp_path, dusen={"Dosya 2.jpg"})
    _goruyu_bagla(monkeypatch)

    zengin = ya.menuyu_zenginlestir(_menu(4), "Konu", bicim=ya.UZUN_BICIMI)

    assert len(zengin) == 4
    assert not zengin[1].get("goruntu")
    assert zengin[2]["goruntu"]


# --- Kapsam ---------------------------------------------------------------


def test_shorts_menusu_ZENGINLESTIRILMIYOR(monkeypatch, tmp_path):
    """Shorts hatti olculerek kalibre ve yayin yapiyor; ayrica butce."""
    _kucukleri_bagla(monkeypatch, tmp_path)
    cagrilar = _goruyu_bagla(monkeypatch)

    zengin = ya.menuyu_zenginlestir(_menu(20), "Konu", bicim=ya.SHORTS_BICIMI)

    assert cagrilar == []
    assert not any(g.get("goruntu") for g in zengin)


def test_bicimsiz_cagri_SHORTS_sayiliyor(monkeypatch, tmp_path):
    """`kare_orani` ile AYNI sozlesme: bicim verilmemesi Shorts demek."""
    _kucukleri_bagla(monkeypatch, tmp_path)
    cagrilar = _goruyu_bagla(monkeypatch)

    ya.menuyu_zenginlestir(_menu(6), "Konu")

    assert cagrilar == []


def test_huni_yolu_HIC_GORU_CAGIRMIYOR(monkeypatch, tmp_path):
    """⚠️ Menuyu SAYAN yollar zenginlestirmiyor — maliyet karari.

    `arsiv_envanteri` icine konsaydi huni her koşumda 54 capa x ~1466
    girdi icin goru faturasi cikarirdi (~122 cagri).
    """
    _kucukleri_bagla(monkeypatch, tmp_path)
    cagrilar = _goruyu_bagla(monkeypatch)
    monkeypatch.setattr(
        ya.wikimedia_materials,
        "arsiv_menusu",
        lambda *_a, **_k: [
            {"title": f"File:D{n}.jpg", "aciklama": f"gercek aciklama {n}", "tarih": ""}
            for n in range(30)
        ],
    )

    ya.arsiv_envanteri("Konu", bicim=ya.UZUN_BICIMI)

    assert cagrilar == []


# --- Onbellek -------------------------------------------------------------


def test_onbellek_IKINCI_CAGRIDA_goru_cagirmiyor(monkeypatch, tmp_path):
    """Maliyet iddiasinin kaniti: sicak onbellekte 0 cagri."""
    _kucukleri_bagla(monkeypatch, tmp_path)
    cagrilar = _goruyu_bagla(monkeypatch)
    menu = _menu(10)

    ilk = ya.menuyu_zenginlestir(menu, "Konu", bicim=ya.UZUN_BICIMI)
    ilk_cagri = len(cagrilar)
    ikinci = ya.menuyu_zenginlestir(menu, "Konu", bicim=ya.UZUN_BICIMI)

    assert ilk_cagri == 1
    assert len(cagrilar) == ilk_cagri
    assert [g.get("goruntu") for g in ikinci] == [g.get("goruntu") for g in ilk]


def test_onbellek_anahtari_KONU_DEGIL_DOSYA(monkeypatch, tmp_path):
    """Ayni Commons dosyasi birden cok capada gecebiliyor.

    Gordugu sey capaya gore degismedigi icin ikinci capa ayni aciklamayi
    onbellekten almali — konuyla anahtarlansaydi ayni dosya iki kez
    aciklanirdi.
    """
    _kucukleri_bagla(monkeypatch, tmp_path)
    cagrilar = _goruyu_bagla(monkeypatch)
    menu = _menu(5)

    ya.menuyu_zenginlestir(menu, "Birinci Konu", bicim=ya.UZUN_BICIMI)
    ya.menuyu_zenginlestir(menu, "Ikinci Konu", bicim=ya.UZUN_BICIMI)

    assert len(cagrilar) == 1


def test_SEMA_SURUMU_degisince_onbellek_dusuyor(monkeypatch, tmp_path):
    """Istem degisirse eski aciklamalar bagliyici olmamali."""
    _kucukleri_bagla(monkeypatch, tmp_path)
    cagrilar = _goruyu_bagla(monkeypatch)
    menu = _menu(5)

    ya.menuyu_zenginlestir(menu, "Konu", bicim=ya.UZUN_BICIMI)
    monkeypatch.setattr(ya, "MENU_GORUSU_SURUMU", ya.MENU_GORUSU_SURUMU + 1)
    ya.menuyu_zenginlestir(menu, "Konu", bicim=ya.UZUN_BICIMI)

    assert len(cagrilar) == 2


# --- Istem ----------------------------------------------------------------


def test_istem_GORUNTU_alanini_ACIKLIYOR():
    """⚠️ Veriyi ekleyip istemi susturmak iki tarafi ayri dile dusururdu.

    Model `goruntu`nun ne oldugunu bilmezse `gosterdigi`ye bakmaya devam
    eder — ki olculen kusur tam olarak o.
    """
    menu = [
        {
            "dosya": "A.jpg",
            "gosterdigi": "A",
            "tarih": "",
            "goruntu": "tas bir duvar",
        }
    ]

    talimat = ya._menu_talimati(menu, 24, bicim=ya.UZUN_BICIMI)

    assert "goruntu" in talimat
    # Celiskide hangisinin kazandigi SOYLENMELI: dosya adi yalan soyleyebiliyor.
    assert "trust 'goruntu'" in talimat


def test_GORUNTUSUZ_menude_aciklama_cumlesi_YOK():
    """Menu zenginlestirilmemisse (Shorts, ya da goru dustu) cumle olmamali.

    Olmayan bir alani anlatan talimat, modeli var olmayan veriye bakmaya
    cagirirdi.
    """
    talimat = ya._menu_talimati(_menu(24), 24, bicim=ya.UZUN_BICIMI)

    assert "trust 'goruntu'" not in talimat


def test_goru_istemi_DOSYA_ADI_istemiyor():
    """⚠️ Kunye zaten dosya adinin parafrazi; goru YENI bilgi vermeli."""
    istem = ya._goru_sayfasi_istemi([1, 2, 3])

    metin = json.dumps(istem, ensure_ascii=False).casefold()
    assert "literally" in metin
    assert "filename" in metin
    assert istem["entries"] == [{"n": 1}, {"n": 2}, {"n": 3}]


def test_istemdeki_menu_ile_RED_MESAJINDAKI_menu_AYNI(monkeypatch, tmp_path):
    """⚠️ "Jock Willis" dersinin ikinci yuzu.

    `alinti_kusuru` red mesajinda menuyu BASIYOR, yani o liste de modele
    GOSTERILIYOR. Istem zengin menuyu, red mesaji kunye menusunu
    gosterirse model iki liste arasinda salinir — kapinin modele
    gosterilenden BASKA bir listeye bakmasi, kapiyi cozdugu kusurun
    kaynagina cevirir (`alinti_kusuru` docstring'i).

    Mutasyon: `alinti_kusuru`daki `menuyu_zenginlestir` cagrisini silmek.
    """
    _kucukleri_bagla(monkeypatch, tmp_path)
    _goruyu_bagla(monkeypatch)
    menu = _menu(6)
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: list(menu))

    # Istemin gordugu liste.
    istem = ya._menu_talimati(
        ya.menuyu_zenginlestir(list(menu), "Konu", bicim=ya.UZUN_BICIMI),
        24,
        bicim=ya.UZUN_BICIMI,
    )

    # Kapinin bastigi liste: ayni dosya iki sahnede -> tekrar dali,
    # bostaki girdileri JSON olarak basiyor.
    plan = ya.ContentPlan(
        topic="konu",
        visual_anchor="Konu",
        title="baslik",
        script="metin",
        scenes=[
            {"narration": f"s{n}", "search_term": f"Konu {n}", "kaynak_dosya": ad}
            for n, ad in enumerate(["Dosya 1.jpg", "Dosya 1.jpg", "Dosya 3.jpg"], 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )
    kusur = ya.alinti_kusuru(plan, "Konu", bicim=ya.UZUN_BICIMI)

    assert kusur, "ayni dosya iki sahnede: kapi kusur bildirmeliydi"
    # Istem `goruntu` tasiyorsa red mesaji da tasimali.
    assert "goruntu" in istem
    assert "goruntu" in kusur


def test_goru_istemi_ORTAMI_ANLATMAYI_yasakliyor():
    """⚠️ OLCULMUS REGRESYON (2026-08-20, ilk canli koşum).

    Istemin ilk surumu "if the image is a drawing, engraving or printed
    plate rather than a photograph, say so" diyordu. Model o dili
    `goruntu`ya yazdi ("A printed plate shows...", "A technical drawing
    shows..."), plan modeli aciklamayi anlatima KOPYALADI ve
    `resmedilemez_kusuru` plani reddetti:

        resmedilemez kusuru  2 -> 9
        yedisi dogrudan bu dilden: 'plate shows', 'drawing shows',
        'engraving shows', 'illustrations show', 'painting designs show'

    Yani istem, cozmeye calistigi kusuru BESLIYORDU. Ortam bilgisi
    kaybolmuyor, `tur` alaninda duruyor — orasi anlatima girmiyor.
    """
    metin = ya._goru_sayfasi_istemi([1])["instructions"].casefold()

    # Ortami anlatma YASAGI acikca yazili olmali.
    assert "never the medium" in metin
    # Kapinin cezalandirdigi kelimeler modele ORNEK olarak sunulmamali:
    # yalnizca yasak listesinde gecmeli, "say so" baglaminda degil.
    assert "say so" not in metin
    assert "'tur' field" in metin


def test_goru_TUR_listesi_KAPIYLA_ayni_dili_konusuyor():
    """⚠️ Iki listenin ayrismasi deponun olculmus kusuru.

    `FOTOGRAF_OLMAYAN_TURLER` sahne degistirmeyi gerektiren turleri
    tanimliyor; goru istemi ayni kelimeleri artı degistirme gerektirmeyen
    ikisini (`photo`, `artwork`) sunmali. Yeni bir kelime icat edilirse
    ileride kapiya baglanamaz.
    """
    turler = set(
        ya._goru_sayfasi_istemi([1])["schema"]["captions"][0]["tur"].split("|")
    )

    assert ya.FOTOGRAF_OLMAYAN_TURLER <= turler
    assert turler - ya.FOTOGRAF_OLMAYAN_TURLER == {"photo", "artwork"}
