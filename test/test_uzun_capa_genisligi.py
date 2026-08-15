"""Uzun kipte capa KONUNUN KENDISI olmali — dar capa arsivi tuketiyor.

⚠️ Olculdu (2026-08-15, dorduncu Herculaneum koşumu, 20,4 dakika, video
uretilmedi). Model `visual_anchor` olarak "Herculaneum" yerine "House of
the Stags" (tek bir ev) sectI.

Mekanizma: `validate_content_plan` her sahnenin arama teriminin capayi
TASIMASINI zorunlu kiliyor. Capa "House of the Stags" olunca 35 sahnenin
35'i de "Stags" aradi, arsiv modern geyik heykelleri dondurdu ve kaynak
kapisi 63 puan verip 9 kusur bildirdi:

    "11, 12: modern heykeller, Herculaneum'dan degil"
    "18: modern kadinlarin Roma kiyafetiyle resmi"

⚠️ Kusur uzun formata OZGU ve bu yuzden kapi `bicim`e bagli: 8 sahnede dar
capa CALISIYOR ve Shorts'ta kasitli (bkz. "Vassar College" gerekcesi —
kisi videosunda capa kurum olursa video yanlis insani gosterir). 35 sahnede
ise o capanin arsivi tukeniyor.

⚠️ Ikinci gerekce olcum butunlugu: arz olcumunu (`arsiv_arzi_olc.py`) biz
KONU uzerinde yapiyoruz. Model olculmemis bir alt kumeye gecerse, "38
gorsel var" diye baslatilan koşum baska bir seyin arsivinden uretiliyor.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(capa: str, sahne_terimi: str | None = None) -> ya.ContentPlan:
    terim = sahne_terimi or f"{capa} detay"
    return ya.ContentPlan(
        topic="Herculaneum",
        visual_anchor=capa,
        title="Herculaneum: What the Ash Preserved",
        script="Herculaneum was buried. " + "word " * 1497,
        scenes=[
            {"narration": f"sahne {i} anlatimi", "search_term": f"{terim} {i}"}
            for i in range(1, 31)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def test_DAR_capa_reddediliyor():
    """Dorduncu koşumun birebir durumu."""
    with pytest.raises(ValueError, match="shares no word with the topic"):
        ya.validate_content_plan(
            _plan("House of Stags"), bicim=ya.UZUN_BICIMI, konu="Herculaneum"
        )


def test_KONUNUN_KENDISI_capa_olarak_geciyor():
    ya.validate_content_plan(_plan("Herculaneum"), bicim=ya.UZUN_BICIMI, konu="Herculaneum")


def test_konunun_BIR_kelimesi_yetiyor():
    """Konu cok kelimeliyse capanin kisa hali kabul edilmeli.

    "Baghdad" capasi "House of Wisdom Baghdad" konusu icin gecerli: capa
    kisitinin kendisi 1-4 kelime istiyor, yani tam esitlik istenemez.
    """
    ya.validate_content_plan(
        _plan("Baghdad", "Baghdad manuscript"),
        bicim=ya.UZUN_BICIMI,
        konu="House of Wisdom Baghdad",
    )


def test_SHORTS_kipinde_dar_capa_SERBEST():
    """⚠️ Shorts'ta dar capa KASITLI; kapi oraya sizarsa kalibre bir kural bozulur."""
    kisa = ya.ContentPlan(
        topic="Anita Hemmings",
        visual_anchor="Anita Hemmings",
        title="baslik #Shorts",
        script="Anita Hemmings enrolled. " + "word " * 97,
        scenes=[
            {"narration": f"sahne {i}", "search_term": f"Anita Hemmings portre {i}"}
            for i in range(1, 9)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )

    # Konu ile capa hic ortusmuyor ama Shorts oldugu icin gecmeli.
    ya.validate_content_plan(kisa, konu="Vassar College")


def test_KONUSUZ_cagride_kapi_calismiyor():
    """Yedek kipte capayi model seciyor; karsilastirilacak konu YOK."""
    ya.validate_content_plan(_plan("House of Stags"), bicim=ya.UZUN_BICIMI)


def test_dogrulama_mesaji_NE_YAPILACAGINI_soyluyor():
    """⚠️ Mesaj modele geri besleniyor; kurali soyleyip cozumu soylemezse
    model ayni adi geri yaziyor ve bes deneme yaniyor (olculdu, capa
    uzunlugu kapisinda)."""
    with pytest.raises(ValueError) as hata:
        ya.validate_content_plan(
            _plan("House of Stags"), bicim=ya.UZUN_BICIMI, konu="Herculaneum"
        )

    mesaj = str(hata.value)
    assert "Use the topic itself as the visual anchor" in mesaj
    assert "scene search terms" in mesaj


def test_uretim_cagrisi_KONUYU_geciriyor():
    """⚠️ Kapi dogru olsa da cagri konuyu gecirmezse HIC calismaz.

    Ayni sinif kusur bu oturumda bir koşum oldurdu: `refine_search_terms`
    dogruydu ama `bicim` gecirilmiyordu.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def generate_content_plan(") :]
    govde = govde[: govde.index("\ndef ", 10)]

    assert "validate_content_plan(plan, sahne_sayisi, bicim=bicim, konu=konu or \"\")" in govde
