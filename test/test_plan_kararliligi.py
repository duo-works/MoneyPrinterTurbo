"""Plan uretimi kararli: sahne sayisini KOD belirliyor, capa ONARILIYOR.

⚠️ OLCULDU (2026-08-15, DOKUZUNCU Herculaneum koşumu). Bes denemenin dordu
soyle dustu:

    1/5  926 kelime (1200 gerekli) · 39 sahne · capa 'Villa of the Papyri'
    2/5  alinti kapisi: arsivde 38 gorsel, plan 41 sahne istiyor
    3/5  capa 'Villa of the Papyri' konuyla ortak kelime tasimiyor
    4/5  acilis tarihle basliyor · 35 sahne · 876 kelime

Uc yapisal sebep vardi ve ucu de burada kilitleniyor:

1. SAHNE SAYISINI MODEL SECIYORDU. Istem zaten arzi soyluyordu ("at most 38
   scenes") ve model 41 yazdi — SOYLEMEK yetmiyor (DW-87). Sayi artik koddan.

2. IKI KAPI ZIT TALIMAT VERIYORDU. `alinti_kusuru` "capayi baska bir seye
   bagla" diyor, capa kapisi "capa konunun kendisi olmali" diyordu. Model
   birincisine uyup reddediliyordu.

3. KELIME TABANI MODELIN DOGAL CIKTISININ USTUNDEYDI. Dokuz koşumda model
   876-1.353 kelime uretti; 1.200 taban dagilimin ortasini kesiyordu.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(capa: str, sahne: int = 30) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Herculaneum",
        visual_anchor=capa,
        title="Herculaneum: What the Ash Preserved",
        script="Herculaneum was buried. " + "word " * 1200,
        scenes=[
            {
                "narration": f"sahne {i} anlatimi",
                "search_term": f"{capa} detay {i}",
                "kaynak_dosya": f"D{i}.jpg",
            }
            for i in range(1, sahne + 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


# --- C3: kelime tabani -----------------------------------------------------


def test_taban_modelin_OLCULEN_ciktisinin_altinda():
    """⚠️ Dokuz koşumda olculen en kisa senaryo 876 kelimeydi."""
    en_az, _ = ya.UZUN_BICIMI.kelime_araligi

    assert en_az <= 900


def test_900_kelime_hala_UZUN_FORMAT():
    """YouTube uzun format esigi 60 saniye; 900 kelime 5,3 dakika."""
    en_az, _ = ya.UZUN_BICIMI.kelime_araligi

    assert en_az / 170 * 60 > 300


def test_istem_TABANI_sayiyla_yazmiyor():
    """⚠️ Sayi gomulu kalsaydi taban degisince istem sessizce yalan sylerdi."""
    uzun = ya.editoryal_sistem_yonergesi(ya.UZUN_BICIMI)

    assert "under 1200" not in uzun
    assert "under the floor" in uzun


# --- C1: sahne sayisi arzdan ------------------------------------------------


def test_sahne_tavani_RITMI_bozmuyor():
    """⚠️ 900 kelimede 45 sahne 7,0 sn/kare verirdi; belgesel tabani 8 sn.

    Kanalin olculen kusuru tam burada: izleyicinin ucte biri ilk sahne
    degisiminde gidiyor, yani kesmeyi hizlandirmak en yanlis yon.
    """
    en_az_kelime, _ = ya.UZUN_BICIMI.kelime_araligi
    _, en_cok_sahne = ya.UZUN_BICIMI.sahne_araligi

    assert (en_az_kelime / 170 * 60) / en_cok_sahne >= 8


def test_ARZ_PAYI_secim_ozgurlugu_birakiyor():
    """⚠️ 38 menuye 38 sahne demek, modelin her dosyayi kullanmak zorunda
    kalmasi demek — anlatiya uymayan bir gorseli bile atlayamaz."""
    assert ya.ARZ_PAYI >= 1


def test_sahne_sayisi_KODDAN_geliyor():
    """Baglanti testi: turetme yoksa model yine aralik kenarinda dolasir."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "sahne_tavani = min(bicim.sahne_araligi[1], len(on_menu))" in kaynak


def test_CLI_yasagi_DURUYOR():
    """⚠️ `--uzun ile --sahne-sayisi` yasagi INSANIN elle sayi vermesini
    engelliyor; degisen sey kodun kendi turettigi sayi."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "--uzun ile --sahne-sayisi birlikte kullanılamaz" in kaynak


# --- C2: zit talimat --------------------------------------------------------


def test_UZUN_kipte_kapi_capayi_degistirmeyi_ISTEMIYOR(monkeypatch):
    """⚠️ Asil celiski: bu mesaj capa kapisinin yasakladigi hamleyi
    oneriyordu ve model ona uyup reddediliyordu."""
    monkeypatch.setattr(
        ya, "arsiv_envanteri", lambda *_a, **_k: [{"dosya": f"D{i}.jpg"} for i in range(5)]
    )

    kusur = ya.alinti_kusuru(_plan("Herculaneum", 30), "Herculaneum", bicim=ya.UZUN_BICIMI)

    assert "Anchor the video on a different" not in kusur
    assert "Keep the same visual anchor" in kusur
    assert "write at most 5 scenes" in kusur


def test_SHORTS_kipinde_eski_mesaj_DURUYOR(monkeypatch):
    """Shorts'ta capayi daraltmak DOGRU cozum — kalibre edilmis davranis."""
    monkeypatch.setattr(
        ya, "arsiv_envanteri", lambda *_a, **_k: [{"dosya": f"D{i}.jpg"} for i in range(3)]
    )

    kusur = ya.alinti_kusuru(_plan("Anita Hemmings", 8), "Anita Hemmings")

    assert "Anchor the video on a different" in kusur


# --- C4: capa onarimi -------------------------------------------------------


def test_dar_capa_KONUYA_genisletiliyor():
    plan = _plan("Villa of the Papyri")

    eski = ya.capayi_konuya_genislet(plan, "Herculaneum")

    assert eski == "Villa of the Papyri"
    assert plan.visual_anchor == "Herculaneum"


def test_onarim_TERIMLERI_de_yeniliyor():
    """⚠️ Terimler eski capaya goreydi; yenilenmezse sahne kapisi bu kez
    ONLARI reddederdi."""
    plan = _plan("Villa of the Papyri")

    ya.capayi_konuya_genislet(plan, "Herculaneum")

    assert all("herculaneum" in s["search_term"].lower() for s in plan.scenes)


def test_onarim_sahnenin_SOMUT_kelimesini_koruyor():
    """"Villa of the Papyri scrolls" bilgisi kaybolmamali."""
    plan = _plan("Villa of the Papyri")

    ya.capayi_konuya_genislet(plan, "Herculaneum")

    assert any("detay" in s["search_term"] for s in plan.scenes)


def test_capa_ZATEN_dogruysa_dokunulmuyor():
    plan = _plan("Herculaneum")
    onceki = [s["search_term"] for s in plan.scenes]

    assert ya.capayi_konuya_genislet(plan, "Herculaneum") == ""
    assert [s["search_term"] for s in plan.scenes] == onceki


def test_onarim_dogrulamayi_GECIRIYOR():
    """Onarimdan sonra plan capa kapisindan gecmeli — yoksa bir ise yaramaz."""
    plan = _plan("Villa of the Papyri")

    ya.capayi_konuya_genislet(plan, "Herculaneum")
    ya.validate_content_plan(plan, bicim=ya.UZUN_BICIMI, konu="Herculaneum")


def test_onarim_DONGUYE_bagli():
    """⚠️ Fonksiyon dogru olsa da cagrilmazsa kusur surer."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "capayi_konuya_genislet(plan, konu)" in kaynak


def test_onarim_TERIM_ONARIMINDAN_once():
    """⚠️ Sirasi ters olsaydi tekillestirilen terimler uzerine yazilirdi."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    capa = kaynak.index("capayi_konuya_genislet(plan, konu)")
    terim = kaynak.index("arama_terimlerini_tekillestir(plan)")

    assert capa < terim


# --- C1b: TAVAN, tam sayi degil --------------------------------------------
#
# ⚠️ OLCULDU (2026-08-15, ONUNCU koşum). Ilk C1 tasarimi TAM SAYI istiyordu
# ve bes denemenin ikisini TEK BASINA yakti:
#
#     2/5  tam 35 sahne gerekli, 38 geldi  (1.176 kelime, gecerli plan)
#     4/5  tam 35 sahne gerekli, 34 geldi  (1.444 kelime, gecerli plan)
#
# Iki plan da baska her acidan gecerliydi. Tam sayi, araliktan olculebilir
# sekilde daha zor; arzi korumaya TAVAN yetiyor.


def _tavan_plani(sahne: int) -> ya.ContentPlan:
    plan = _plan("Herculaneum", sahne)
    plan.script = "Herculaneum was buried. " + "word " * 1200
    return plan


def test_TAVANIN_ALTINDAKI_sahne_sayilari_geciyor():
    """Onuncu koşumun iki reddi de bu testle kapaniyor."""
    for sahne in (34, 36, 38):
        ya.validate_content_plan(
            _tavan_plani(sahne), bicim=ya.UZUN_BICIMI, sahne_tavani=38
        )


def test_TAVANIN_USTU_reddediliyor():
    """Arsiv 38 dosya veriyorsa 41 sahnelik plan alinti kapisinda duserdi."""
    with pytest.raises(ValueError, match="24-38 scenes"):
        ya.validate_content_plan(
            _tavan_plani(39), bicim=ya.UZUN_BICIMI, sahne_tavani=38
        )


def test_tavan_BICIMIN_ust_sinirini_asamiyor():
    """Menu bol olsa bile ritim tavani (39) baglayici kalmali."""
    with pytest.raises(ValueError, match="24-39 scenes"):
        ya.validate_content_plan(
            _tavan_plani(45), bicim=ya.UZUN_BICIMI, sahne_tavani=60
        )


def test_TAM_SAYI_kipi_Shorts_icin_DURUYOR():
    """⚠️ `--sahne-sayisi` deneyi Shorts koluna ait ve bozulmamali."""
    kisa = ya.ContentPlan(
        topic="konu",
        visual_anchor="capa",
        title="baslik #Shorts",
        script="Capa vardi. " + "word " * 97,
        scenes=[
            {"narration": f"sahne {i}", "search_term": f"capa detay {i}"}
            for i in range(1, 10)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )

    with pytest.raises(ValueError, match="exactly 8 scenes"):
        ya.validate_content_plan(kisa, 8)
