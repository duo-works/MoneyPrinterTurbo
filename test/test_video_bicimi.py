"""Video bicimi — uzun format ile Shorts'un sayisal sozlesmesi.

⚠️ NEDEN TEK NESNE, dagitilmis `if uzun_format:` degil: bu sayilar
birbirine bagli. Kelime sayisi konusma suresini, konusma suresi gereken
gorsel sayisini, gorsel sayisi da arsiv arzini belirliyor. Ayri ayri
degistirilirlerse sessizce tutarsiz bir video cikar — bu oturumda ayni
sinif kusur bir kez yasandi (kuyrugun kabul ettigi konuyu besleyici
reddediyordu).

⚠️ SAYILAR OLCUMDEN GELIYOR, tercihten degil:
  * konusma hizi ~150 kelime/dk (Anita 41 sn / ~100 kelime)
  * arsiv arzi (2026-08-15, menu siniri 60): Bagan 49, Herculaneum 37,
    Alhambra 32, Egyptian pyramids 23 kullanilabilir gorsel
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(kelime: int, sahne: int, baslik: str = "baslik #Shorts") -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="Herculaneum",
        title=baslik,
        script="Herculaneum was buried. " + "word " * max(kelime - 3, 0),
        scenes=[
            {"narration": f"sahne {i}", "search_term": f"Herculaneum detay {i}"}
            for i in range(1, sahne + 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def _uzun_plan(kelime: int, sahne: int) -> ya.ContentPlan:
    """Uzun format plani — basligi `#Shorts` TASIMAZ (kapi onu reddediyor)."""
    return _plan(kelime, sahne, baslik="Herculaneum: What the Ash Preserved")


def test_varsayilan_bicim_SHORTS():
    """Mevcut cagrilar degismeden calismali."""
    ya.validate_content_plan(_plan(100, 8))

    with pytest.raises(ValueError, match="80-120 words"):
        ya.validate_content_plan(_plan(1500, 8))


def test_uzun_bicim_2000_kelimeyi_KABUL_ediyor():
    """⚠️ Kapi kipe bagli olmasaydi her uzun senaryo reddedilirdi."""
    ya.validate_content_plan(_uzun_plan(1500, 30), bicim=ya.UZUN_BICIMI)


def test_uzun_bicimde_SHORTS_senaryosu_reddediliyor():
    with pytest.raises(ValueError, match="1200-2200 words"):
        ya.validate_content_plan(_uzun_plan(100, 30), bicim=ya.UZUN_BICIMI)


def test_uzun_bicim_sahne_araligi():
    ya.validate_content_plan(_uzun_plan(1500, 24), bicim=ya.UZUN_BICIMI)
    ya.validate_content_plan(_uzun_plan(1500, 45), bicim=ya.UZUN_BICIMI)

    with pytest.raises(ValueError, match="24-45 scenes"):
        ya.validate_content_plan(_uzun_plan(1500, 8), bicim=ya.UZUN_BICIMI)


def test_sahne_TAVANI_arsiv_arzindan():
    """⚠️ Tavan tercih degil, olculmus arz: en zengin konu (Bagan) 49
    kullanilabilir gorsel veriyor. Daha fazlasini istemek, arzin
    veremedigi videoyu istemek olurdu."""
    assert ya.UZUN_BICIMI.sahne_araligi[1] <= 49


def test_uzun_bicimde_sahne_basina_TEK_kare():
    """⚠️ Shorts'ta iki yuva vardi cunku 5 saniyelik kare altyazidan yavas
    kaliyordu. 15 saniyelik belgesel karesinde o sorun yok, ve ikiye bolmek
    gereken gorsel sayisini iki katina cikarip arzi asardi."""
    assert ya.UZUN_BICIMI.kare_yuvasi == 1
    assert ya.SHORTS_BICIMI.kare_yuvasi == ya.KARE_YUVASI == 2


def test_uzun_bicim_YATAY():
    """⚠️ Uzun format 16:9 olmali. Dikey kalirsa YouTube onu Shorts sayar
    ve IZLENME SAATI YAZMAZ — uzun formatin butun amaci o saatler."""
    assert ya.UZUN_BICIMI.dikey is False
    assert ya.SHORTS_BICIMI.dikey is True


def test_kelime_araligi_sureye_oturuyor():
    """~150 kelime/dk: 1.200-2.200 kelime = 8-15 dakika."""
    en_az, en_cok = ya.UZUN_BICIMI.kelime_araligi

    assert 7 <= en_az / 150 <= 9
    assert 13 <= en_cok / 150 <= 16


def test_sahne_basina_sure_belgesel_ritmi():
    """En kotu durumda bile kare ekranda makul kaliyor mu.

    1.200 kelime / 150 = 8 dk = 480 sn; 45 sahne -> ~11 sn/kare. Ust uc:
    2.200 kelime / 24 sahne -> ~37 sn. Ikisi de belgesel araliginda.
    """
    en_az_kelime, en_cok_kelime = ya.UZUN_BICIMI.kelime_araligi
    en_az_sahne, en_cok_sahne = ya.UZUN_BICIMI.sahne_araligi

    en_kisa = (en_az_kelime / 150 * 60) / en_cok_sahne
    en_uzun = (en_cok_kelime / 150 * 60) / en_az_sahne

    assert en_kisa >= 8, f"kare {en_kisa:.0f} sn — belgesel icin fazla hizli"
    assert en_uzun <= 45, f"kare {en_uzun:.0f} sn — fazla uzun, sikici"


def test_KARE_YUVASI_bicimlerden_ONCE_tanimli():
    """⚠️ Varsayilan degerler `def` aninda hesaplaniyor.

    `KARE_YUVASI` dosyanin ortasinda kaldiginda ice aktarma `NameError`
    ile oluyordu — bu oturumda uc uretim koşumunu olduren kusurun aynisi.
    Kaynak sirasi kilitleniyor.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert kaynak.index("KARE_YUVASI = 2") < kaynak.index("class VideoBicimi")
