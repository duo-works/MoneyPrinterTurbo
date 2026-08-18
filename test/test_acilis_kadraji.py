"""1. sahne ARSIV yolunda da yakin kadraj almali.

⚠️ NEDEN VAR — `test_acilis_karesi.py` zaten var, geciyor ve URETIMIN HIC
KOSMADIGI bir yolu doguruluyor. `ACILIS_KARELERI`/`acilis_karesi` (DW-121)
dogru teshisi koydu ama tek cagri yeri `generate_ai_scene_materials` ve o yol
`enable_ai_visual_fallback = false` bayraginin arkasinda. Arsivden gelen 1.
sahne gorseli duzeltmeden HIC etkilenmiyordu.

⚠️ Teshis olculdu (DW-121, Chaco Canyon ilk 11 saat): 374 goruntuleme,
trafigin %97,3'u Shorts akisi — dagitim CALISIYOR ama izleyicilerin %73'u
IZLEMEDEN geciyor. Kalanlar iyi izliyor (33 sn videoda ortalama 0:20, %61).
Yani govde tutuyor, ACILIS tutmuyor.

⚠️ Kusurun arsiv yolunda da surdugu olculdu (2026-08-18), 1. sahne dosyalari:

    "Remote view of Sigiriya rock, Central Province, Sri Lanka..."
    "Sigiriya rock from a distance.jpg"
    "Hadrian's Wall east of Walltown Quarry, Northumberland 01.jpg"

Hakem de bagimsiz olarak ayni seyi yazdi: "The opening frames (1-2) are
passive scenic overlooks", "frames 1-2 show standard pastoral wall views".
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def _plan(*alintilar: str) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="Sigiriya",
        title="baslik",
        script="metin",
        scenes=[
            {"narration": f"sahne {i}", "search_term": "t", "kaynak_dosya": ad}
            for i, ad in enumerate(alintilar, 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


# --- Isaretler --------------------------------------------------------------


@pytest.mark.parametrize(
    "ad",
    [
        # ⚠️ Ikisi de CANLI ciktidan; uydurulmadi.
        "File:Remote view of Sigiriya rock, Central Province, Sri Lanka.jpg",
        "File:Sigiriya rock from a distance.jpg",
        "File:Aerial view of the fortress.jpg",
        "File:Panoramic view of the valley.jpg",
    ],
)
def test_UZAK_kadraj_yakalaniyor(ad):
    assert ya.uzak_kadraj_mi(ad)


@pytest.mark.parametrize(
    "ad",
    [
        # ⚠️ Bunlar da canli ciktidan ve YAKIN — kapi bunlari elerse
        # uretim durur.
        "File:Göbekli Tepe (2).jpg",
        "File:Philip King of Mount Hope by Paul Revere.jpeg",
        "File:Stonehenge Cremation.jpg",
        "File:Climb exit from Cliff Palace.jpg",
    ],
)
def test_YAKIN_kadraj_geciyor(ad):
    assert not ya.uzak_kadraj_mi(ad)


def test_AD_SUZGECININ_SINIRI_karsi_ornek():
    """⚠️ BU DOSYA YUKARIDAKI LISTEDE "YAKIN" ORNEGI OLARAK DURUYORDU ve bu
    YANLISTI — 2026-08-18'de olculdu.

    `Ahmet Cemal Paşa on the shore of the Dead Sea.jpg` yayinlanan videonun
    acilis karesiydi. Ad "kiyida" diyor ve ad suzgecinden GECIYOR; GORUNTU ise
    uzak plan: Cemal at ustunde kucucuk bir siluet, yuz ~15 piksel, karenin
    ~%45'i ozelliksiz krem bulaniklik. Anlatimin iddiasi ("shows him SMILING")
    kadrajda gorunmuyor.

    Yani ad bazli kapinin bir SINIRI var ve o sinir bu dosyada olculdu.
    Kapatilmasi `uzak_acilis_kareleri`ne birakildi: kaynak kapisi goruntuyu
    ZATEN goruyor. Ad suzgeci kaldirilmadi — ucuz, ag istegi gerektirmiyor ve
    plan asamasinda, render'dan ONCE calisiyor.

    ⚠️ Bu test AD SUZGECININ BUGUNKU DAVRANISINI kaydediyor, onu suclamiyor:
    dosya adindan uzak plan oldugu ANLASILAMIYOR.
    """
    ad = "File:Ahmet Cemal Paşa on the shore of the Dead Sea.jpg"

    assert not ya.uzak_kadraj_mi(ad), "ad suzgecinin bu dosyayi yakalamasi beklenmiyor"
    # Goruntu tarafindaki kapi onu yakaliyor:
    assert ya.uzak_acilis_kareleri(
        [{"n": 1, "subject_scale": "small"}], ya.SHORTS_BICIMI
    ) == [1]


# --- Kapi -------------------------------------------------------------------


def test_uzak_acilis_REDDEDILIYOR():
    kusur = ya.acilis_kadraji_kusuru(_plan("File:Sigiriya rock from a distance.jpg"))

    assert kusur, "1. sahne uzak plan aliyor, kapi susmamali"


def test_yakin_acilis_GECIYOR():
    assert not ya.acilis_kadraji_kusuru(_plan("File:Göbekli Tepe (2).jpg"))


def test_kapi_YALNIZCA_birinci_sahneye_bakiyor():
    """⚠️ Diger sahnelerde uzak plan MESRU — genis plan anlatimi tasiyabilir.
    Kapi hepsini kovalasaydi arsivi olmayan konularda uretim kilitlenirdi."""
    plan = _plan("File:Göbekli Tepe (2).jpg", "File:Aerial view of the site.jpg")

    assert not ya.acilis_kadraji_kusuru(plan)


def test_ALINTISIZ_sahne_kapiyi_tetiklemiyor():
    assert not ya.acilis_kadraji_kusuru(_plan(""))


def test_sahnesiz_plan_PATLAMIYOR():
    plan = _plan()
    plan.scenes = []

    assert ya.acilis_kadraji_kusuru(plan) == ""


def test_kusur_metni_NE_YAPILACAGINI_soyluyor():
    """Gerekce modele geri besleniyor; "kotu" demek yetmez, alternatif ister."""
    kusur = ya.acilis_kadraji_kusuru(_plan("File:Remote view of Sigiriya rock.jpg"))

    assert "closer entry" in kusur
    assert "narration" in kusur


# --- Baglanti ---------------------------------------------------------------


def test_kapi_YUMUSAK():
    """⚠️ SART: bazi arsivlerde ozne yalnizca uzaktan fotograflanmis
    (Sigiriya kayasi boyle). Sert kapi olsaydi o konularda bes deneme de
    yanardi. Yumusak kapi ilk uc denemede zorluyor, sonra geciriyor."""
    assert "if yumusak_kapilar_acik and (kusur := acilis_kadraji_kusuru(plan)):" in KAYNAK


def test_istem_de_1_SAHNEYI_ayri_soyluyor():
    """Kapi tek basina yeterli degil: model neyi arayacagini bilmeli."""
    metin = ya._menu_talimati(
        [{"dosya": f"{i}.jpg", "gosterdigi": "x", "tarih": "1900"} for i in range(12)], 6
    )

    assert "SCENE 1 IS DIFFERENT" in metin


def test_UZUN_kipte_1_sahne_talimati_YOK():
    """⚠️ Kanca teshisi Shorts akisina ozgu (%73 kaydirma). Uzun formatta
    izleyici videoyu SECEREK aciyor, ayni baski yok."""
    metin = ya._menu_talimati(
        [{"dosya": f"{i}.jpg", "gosterdigi": "x", "tarih": "1900"} for i in range(40)],
        30,
        bicim=ya.UZUN_BICIMI,
    )

    assert "SCENE 1 IS DIFFERENT" not in metin


def test_olculen_isaretler_LISTEDE_duruyor():
    """⚠️ Bu ikisi gozlendi; listeden cikarilirsa gerileme sessiz olur."""
    assert "remote view" in ya.UZAK_KADRAJ_ISARETLERI
    assert "from a distance" in ya.UZAK_KADRAJ_ISARETLERI


# --- GORUNTU tarafi: kaynak kapisi kadraji OLCUYOR (2026-08-18) --------------
#
# ⚠️ NEDEN VAR — ad bazli kapinin sinirini yukarida olctuk. Kaynak kapisi 1.
# sahnenin gorselini ZATEN goruyor, yani fazladan ag istegi ya da model cagrisi
# yok: `frames` semasina bir OLGU alani eklendi (`subject_scale`) ve karari
# KOD veriyor (DW-87).


def test_KUCUK_ozne_sorunlu():
    assert ya.uzak_acilis_kareleri(
        [{"n": 1, "subject_scale": "small"}], ya.SHORTS_BICIMI
    ) == [1]


@pytest.mark.parametrize("olcek", ["dominant", "moderate"])
def test_DOLGUN_kadraj_geciyor(olcek):
    assert ya.uzak_acilis_kareleri(
        [{"n": 1, "subject_scale": olcek}], ya.SHORTS_BICIMI
    ) == []


def test_YALNIZCA_1_SAHNEYE_bakiyor():
    """⚠️ Diger sahnelerde genis plan MESRU; hepsini kovalamak arsivi olmayan
    konularda uretimi kilitlerdi."""
    kareler = [
        {"n": 1, "subject_scale": "dominant"},
        {"n": 2, "subject_scale": "small"},
        {"n": 3, "subject_scale": "small"},
    ]

    assert ya.uzak_acilis_kareleri(kareler, ya.SHORTS_BICIMI) == []


def test_UZUN_kipte_kapi_KAPALI():
    """⚠️ Kanca teshisi Shorts akisina ozgu (%73 kaydirma); uzun formatta
    izleyici videoyu SECEREK aciyor."""
    assert ya.uzak_acilis_kareleri(
        [{"n": 1, "subject_scale": "small"}], ya.UZUN_BICIMI
    ) == []


def test_ALAN_YOKSA_sorun_YOK():
    """Eski kayitlarda ve model alani atladiginda kapi susmali — yoksa her
    koşum 1. sahneyi degistirir."""
    assert ya.uzak_acilis_kareleri([{"n": 1, "kind": "photo"}], ya.SHORTS_BICIMI) == []


def test_BOZUK_kare_verisi_PATLAMIYOR():
    bozuk = [None, "x", {"n": "a", "subject_scale": "small"}, {"subject_scale": "small"}]

    assert ya.uzak_acilis_kareleri(bozuk, ya.SHORTS_BICIMI) == []


def test_kapi_SORUNLU_SAHNELERE_baglanmis():
    """⚠️ Zincirin kopabilecegi yer: fonksiyon yazilip cagrilmazsa olcum
    yapilir ama hicbir sey degismez (`ACILIS_KARELERI`nin bastan basina
    gelen sey)."""
    assert "for numara in uzak_acilis_kareleri(kareler, bicim):" in KAYNAK


def test_istem_OLGU_soruyor_KARAR_sormuyor():
    """DW-87: "bu acilis iyi mi" diye sorulsaydi model konudan konuya keyfi
    cevap verirdi."""
    i = KAYNAK.index("def review_source_materials(")
    istem = KAYNAK[i : KAYNAK.index("data = _vision_json", i)]

    assert '"subject_scale"' in istem
    assert "how much " in istem
    assert "good opening" not in istem
    assert "hook" not in istem
