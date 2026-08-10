"""Gorsel capasinin ADI goruntu modeline gitmez (DW-116) + hakem sorulari (DW-117).

⚠️ Olculdu (2026-08-10, dort videoluk uretim). Uc ayri kusur, TEK kok:

  1. Franziska Scanagatta, sahne 2 — kadraji kaplayan kazili tas:
     "THERESIANISCHES MILITÄRAKADEMIE WIENER NEUSTADT". Capa
     "Theresian Military Academy" idi ve gorsel istemine BIREBIR yaziliyordu.
     DW-112 bu nesneleri zaten yasakliyordu; yasak tutmadi cunku model
     gordugu adi yazar. Gercekte akademilerin adi kapisina kazilidir —
     model hata yapmiyor, isteneni yapiyor.

  2. Jacopo de' Pazzi — 6 sahnenin 5'i Palazzo Pazzi. Capa bina secildigi ve
     her sahne capayi icermek zorunda oldugu icin video bastan sona ayni
     yapinin farkli acilari. Kanal sahibinin "hepsinde ayni video var"
     geri bildirimi bu.

  3. William Hardham — ekranda Hardham yok, "Temp. 2nd-Lieut. H. KELLY,
     V.C." ve "Capt. J. F. P. BUTLER, V.C." yazili baska adamlarin
     portreleri var. Capa kisi degil MADALYA secilmisti ("Victoria Cross"),
     arsiv de madalyayla ilgili herhangi birini getirdi.

⚠️ Ad gorsel istemine UC kanaldan giriyordu: `Visual anchor:` cumlesi, arama
terimi (capayi icermek zorunda) ve anlatim cumlesi. Ilk ikisi kesildi;
ucuncusu kesilemez — anlatim sahnenin ne oldugunu soyleyen tek sey. Kalan
kanal icin isteme adi hedefleyen ayri bir kural konuldu.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def test_bina_capasi_ada_donmeden_ture_ceviriliyor():
    """Olculen kusur: 'Theresian Military Academy' adi kadraja kazindi."""
    ifade = ya.adsiz_gorsel_ifadesi("Theresian Military Academy")
    assert ifade == "military academy building"
    assert "theresian" not in ifade.lower()


def test_bilinen_turler_ozel_adi_sizdirmiyor():
    """Ayiklanan sey OZEL ad; tur adi ('college') kalabilir ve kalmali.

    Kadraja kazinan sey "Vassar" gibi tanimlayici ozel addir; "college"
    zaten modelin ne cizecegini soyleyen tur bilgisi.
    """
    for capa, beklenen, ozel_ad in (
        ("Palazzo Pazzi", "renaissance palace", "pazzi"),
        ("Vassar College", "college campus building", "vassar"),
        ("Victoria Cross", "military gallantry medal", "victoria"),
        ("Chaco Canyon", "canyon landscape", "chaco"),
        ("Theresian Military Academy", "military academy building", "theresian"),
    ):
        ifade = ya.adsiz_gorsel_ifadesi(capa)
        assert ifade == beklenen
        assert ozel_ad not in ifade.lower(), f"{capa} → {ifade}"


def test_kisi_capasinda_bos_donuyor():
    """Uydurma bir tur vermek yanlis donemde bina cizdirmekten kotu."""
    assert ya.adsiz_gorsel_ifadesi("Franziska Scanagatta") == ""
    assert ya.adsiz_gorsel_ifadesi("William Hardham") == ""


def test_arama_teriminden_de_ad_ayikliniyor():
    """⚠️ Tek kanali kapatmak yetmez — ad iki yerden giriyordu."""
    temiz = ya.adsiz_sahne_tarifi(
        "Theresian Military Academy entrance gate", "Theresian Military Academy"
    )
    assert "theresian" not in temiz.lower()
    assert "entrance" in temiz and "gate" in temiz


def test_terim_tamamen_capadan_ibaretse_bos_birakilmiyor():
    """Bos 'gorunmesi gereken detay' sahneyi tamamen modelin insafina birakir."""
    terim = "Palazzo Pazzi"
    assert ya.adsiz_sahne_tarifi(terim, "Palazzo Pazzi") == terim


def test_gorsel_isteminde_capa_adi_yok():
    """Kaynakta eski satir gercekten kalkmis mi."""
    assert 'f"Visual anchor: {plan.visual_anchor}. Scene' not in KAYNAK
    assert "adsiz_sahne_tarifi(visual_detail, plan.visual_anchor)" in KAYNAK


def test_moderasyon_yedegi_de_ad_gondermiyor():
    """Iki istem ayni kurala uymazsa kusurun geri donus yolu kalir."""
    assert 'f"Show only this neutral subject: {plan.visual_anchor}' not in KAYNAK


def test_kalan_kanal_icin_ad_kurali_var():
    """Anlatim cumlesindeki ad kesilemiyor; istem onu ISARET etmeli."""
    assert "Any proper name that appears in this description is context for you" in KAYNAK


def test_plan_istemi_kisi_konusunda_kisi_capasi_istiyor():
    """Hardham'in kusuru burada dogar: kisi hikayesine madalya capasi secilmisti."""
    yonerge = ya.editoryal_sistem_yonergesi()
    assert "THE VISUAL_ANCHOR MUST BE THAT PERSON'S NAME" in yonerge
    assert "Victoria Cross" in yonerge  # olculen ornek istemde aniliyor


def test_plan_istemi_capanin_her_kareyi_isgal_etmesini_istemiyor():
    """Jacopo'nun kusuru: 6 sahnenin 5'i ayni bina."""
    yonerge = ya.editoryal_sistem_yonergesi()
    assert "does not have to fill every frame" in yonerge


def _istem_metni(fonksiyon_adi: str) -> str:
    """Bir hakem fonksiyonunun govdesi.

    ⚠️ Kaynakta ham arama YAPILMIYOR: istem cumleleri satir sonlarinda
    bolunuyor ("is there readable / lettering"), yani duz `count` yaniltir.
    Govde alinip bosluklar tekillestiriliyor.
    """
    govde = KAYNAK.split(f"def {fonksiyon_adi}")[1].split("\ndef ")[0]
    return " ".join(govde.replace('"', " ").split())


def test_hakem_kadrajdaki_yaziyi_soruyor():
    """⚠️ DW-117: hakem Scanagatta'daki levhayi gormedi ve videoyu GECIRDI.

    Soru IKI kapida da olmali: kaynak kapisi ham gorseli, video kapisi
    kirpilmis ve altyazili nihai kareyi goruyor.
    """
    for kapi in ("review_source_materials", "review_video"):
        assert "is there readable lettering" in _istem_metni(kapi), kapi


def test_hakem_ozne_kimligini_soruyor():
    """⚠️ DW-117: Hardham'i dusurdu ama yanlis sebeple; ozneyi denetlemiyordu."""
    for kapi in ("review_source_materials", "review_video"):
        metin = _istem_metni(kapi)
        assert "medal, uniform, institution or era" in metin, kapi


def test_video_hakemi_altyaziyi_kusur_sanmiyor():
    """Altyazi kadrajin altina BILEREK basiliyor; yeni soru onu suclamamali."""
    assert "not the subtitle burned along the bottom" in _istem_metni("review_video")


def test_hakem_istemlerinde_esik_hala_anilmiyor():
    """⚠️ Yeni sorular eklendi; eski kural bozulmamali.

    Olculdu: esigi bilen model olcmeyi birakip esigin altina oy yaziyor.
    """
    for yasak in ("MIN_VISUAL_SCORE", "at least 70", "above 70", "threshold"):
        assert yasak not in KAYNAK.split("def review_source_materials")[1].split("def ")[0]
