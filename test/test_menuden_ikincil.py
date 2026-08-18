"""Ikinci gorsel MENUDEN de gelebilmeli — kategori havuzu dogru kaynak degil.

⚠️ NEDEN VAR — olculdu (2026-08-18, Cemal Pasha, YAYINLANMIS video). Menu 32
girdiydi, birincil olarak 6'si kullanilmisti ve **26'si BOSTA** duruyordu:
hepsi lisans, kadraj ve ACIKLAMA suzgecinden gecmis, konuya ait dosyalar
("Djemal Pasha - The Turkish Minister of Marine", "Last review by Jamal Pasha
in Jerusalem"). Arz vardi; hicbir kod ona bakmiyordu.

Zincir soyleydi: model ikinci alinti yazmadiginda sahne dogrudan KATEGORI
havuzuna dusuyor, orada da aday cikmiyordu. Sonuc: 6 sahnenin 1'inde iki ayri
gorsel, 5'inde ayni fotograf iki yuvada ([A, A]).

⚠️ Kaynagin menu olmasi gerektigini BU DEPO ZATEN YAZMISTI —
`ikincil_gorseller` icindeki kategori notu: "Gorsel ritmini geri getirmek ayri
bir is ve dogru kaynak KATEGORI DEGIL ARSIV MENUSU". Bu dosya o notu
uyguluyor.

⚠️ Olculen kazanc (ayni koşumun gercek sahneleri ve gercek menusuyle):

    yayinlanan hali   6 sahnenin 1'i iki ayri gorsel
    menu yedegiyle    6 sahnenin 5'i

⚠️ KATMANLAR KALDIRILMADI: secilen dosya yine algisal tekrar elemesinden
(`_tekrar_mi`) ve gorü denetiminden (`ikincil_gorselleri_denetle`) geciyor.
Menu yedegi arzi artiriyor, kapilari gevsetmiyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402

KAYNAK = Path(wm.__file__).read_text(encoding="utf-8")

# ⚠️ Girdiler CANLI menuden; uydurulmadi.
MENU = [
    {"dosya": "Ahmed Djemal at desk, 1915.jpg",
     "gosterdigi": "Djemal Pasha - The Turkish Minister of Marine, Who Shares with Enver Pasha the Control",
     "tarih": "1915"},
    {"dosya": "Enver Pasha and Jamal (Cemal) Pasha visiting the Dome of the Rock.jpg",
     "gosterdigi": "Enver Pasha and Jamal (Cemal) Pasha visiting Alaqsa Mosque, Palestine, Jerusalem",
     "tarih": "1916"},
    {"dosya": "Cemal Pasha portrait.jpg",
     "gosterdigi": "A portrait of Cemal Pasha",
     "tarih": "1915"},
]
CAPA = {"cemal", "pasha"}


def _sahne(terim: str, anlatim: str = "") -> dict[str, str]:
    return {"search_term": terim, "narration": anlatim}


# --- Asil is ----------------------------------------------------------------


def test_ESLESEN_girdi_seciliyor():
    secim = wm._menuden_ikincil(
        MENU, _sahne("Cemal Pasha Dome of the Rock Jerusalem"), set(), CAPA
    )

    assert secim.startswith("Enver Pasha and Jamal")


def test_EN_COK_eseleseni_seciyor():
    secim = wm._menuden_ikincil(
        MENU, _sahne("Cemal Pasha", "the naval minister sat at his desk"), set(), CAPA
    )

    assert secim == "Ahmed Djemal at desk, 1915.jpg"


def test_KULLANILAN_dosya_secilmiyor():
    """⚠️ Ayni gorsel bir sahnenin iki yuvasinda cikarsa tam da kacinilmak
    istenen tekrari uretiriz."""
    kullanilan = {"Enver Pasha and Jamal (Cemal) Pasha visiting the Dome of the Rock.jpg"}

    secim = wm._menuden_ikincil(
        MENU, _sahne("Cemal Pasha Dome of the Rock Jerusalem"), kullanilan, CAPA
    )

    assert not secim.startswith("Enver Pasha and Jamal")


def test_kullanilan_FILE_onekiyle_de_eleniyor():
    """`used_titles` birincil gecisten `File:` onekli geliyor."""
    kullanilan = {"File:Ahmed Djemal at desk, 1915.jpg"}

    secim = wm._menuden_ikincil(
        MENU, _sahne("Cemal Pasha", "the minister at his desk"), kullanilan, CAPA
    )

    assert secim != "Ahmed Djemal at desk, 1915.jpg"


# --- Capa kelimeleri sinyal tasimiyor ---------------------------------------


def test_YALNIZCA_CAPA_eslesirse_aday_YOK():
    """⚠️ Menunun HER girdisinde capa geciyor; capayla eslesme sifir bilgi.
    Ayni delik birincil yolda olculup belgelenmis (`select_candidate` notu:
    "iki terimlik bir sorguda asgari eslesme 1'e DUSUYOR")."""
    secim = wm._menuden_ikincil(MENU, _sahne("Cemal Pasha"), set(), CAPA)

    assert secim == "", f"capa tek basina yeterli olmus: {secim!r}"


def test_ANLAMSIZ_kelimeler_sayilmiyor():
    """"the", "of", "photograph" gibi kelimeler Commons aciklamalarinin
    yarisinda var ve esigi dejenere eder."""
    secim = wm._menuden_ikincil(
        MENU, _sahne("the a of", "a photograph of the view"), set(), CAPA
    )

    assert secim == ""


def test_KISA_kelimeler_sayilmiyor():
    secim = wm._menuden_ikincil(MENU, _sahne("at he of an"), set(), CAPA)

    assert secim == ""


# --- Eslesmeyen sahne bos donuyor -------------------------------------------


def test_ESLESMEYEN_sahne_BOS_donuyor():
    """⚠️ Rastgele bir menu girdisi koymak, tam da `ikincil_gorselleri_denetle`
    nin dusurdugu kusuru uretirdi. Bos donmek `[A, A]` demek — bugunku
    davranis."""
    secim = wm._menuden_ikincil(
        MENU, _sahne("Cemal Pasha assassination Tiflis 1922"), set(), CAPA
    )

    assert secim == ""


def test_BOS_menu_PATLAMIYOR():
    assert wm._menuden_ikincil([], _sahne("herhangi bir terim"), set(), CAPA) == ""


def test_BOS_sahne_PATLAMIYOR():
    assert wm._menuden_ikincil(MENU, _sahne("", ""), set(), CAPA) == ""


def test_BOZUK_girdi_PATLAMIYOR():
    bozuk = [{"gosterdigi": "aciklama"}, {"dosya": ""}]

    assert wm._menuden_ikincil(bozuk, _sahne("desk minister"), set(), CAPA) == ""


# --- Baglanti ---------------------------------------------------------------


def test_menu_yedegi_MODEL_ALINTISINDAN_SONRA():
    """⚠️ Sira: once modelin secimi (anlatimi o yazdi), sonra menu, en son
    kategori havuzu."""
    govde = KAYNAK[KAYNAK.index("    for index, scene in enumerate(scenes, 1):") :][:6000]

    # ⚠️ Once VARLIK, sonra SIRA. `str.index` ile dogrudan karsilastirmak
    # "substring not found" verirdi ve kapinin neden bozuldugu okunmazdi.
    for capa in ("_alinti_adayi(alinti", "_menuden_ikincil(", "_kategori_adaylari("):
        assert capa in govde, f"secim zincirinde {capa} YOK"

    model = govde.index("_alinti_adayi(alinti")
    menu_yolu = govde.index("_menuden_ikincil(")
    kategori = govde.index("_kategori_adaylari(")

    assert model < menu_yolu < kategori, "secim sirasi bozulmus"


def test_menu_yalnizca_BANT_isteyen_sahneye():
    """Kirpilabilen birincil zaten tam ekran; ikiye bolmek onu kucultmek olur."""
    govde = KAYNAK[KAYNAK.index("        if aday is None and menu") :][:200]

    assert "esleme_gerekli" in govde


def test_DENETIM_ve_TEKRAR_elemesi_KALDIRILMADI():
    """⚠️ Menu yedegi arzi artiriyor, KAPILARI GEVSETMIYOR. #34'un koydugu
    denetim ve algisal tekrar elemesi yerinde durmali."""
    assert "_tekrar_mi(hedef, izler)" in KAYNAK

    otomasyon = (Path(wm.__file__).parent / "youtube_automation.py").read_text(
        encoding="utf-8"
    )
    assert "ikincil_gorselleri_denetle(" in otomasyon


def test_cagiran_MENUYU_ve_CAPAYI_geciriyor():
    """⚠️ Zincirin kopabilecegi yer: parametre eklenip cagiran taraf
    gecirmezse yedek sessizce hic calismaz."""
    otomasyon = (Path(wm.__file__).parent / "youtube_automation.py").read_text(
        encoding="utf-8"
    )
    govde = otomasyon[otomasyon.index("wikimedia_materials.ikincil_gorseller(") :][:2600]

    assert "menu=arsiv_envanteri(" in govde
    assert "capa=plan.visual_anchor" in govde
