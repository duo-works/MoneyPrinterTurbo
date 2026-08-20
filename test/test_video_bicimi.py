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

# ⚠️ OLCULDU (2026-08-15), tahmin degil: `anlatim_suresi` gercek edge-tts
# yolundan uc uzunlukta kosuldu ve ucunde de ayni hiz cikti.
#
#       120 kelime ->  42,10 sn (171 kelime/dk)
#     1.200 kelime -> 423,07 sn (170 kelime/dk)
#     2.200 kelime -> 774,79 sn (170 kelime/dk)
#
# Onceki 150 kelime/dk sayisi TEK bir Shorts orneginden (Anita 41 sn / ~100
# kelime) cikarilmisti; bu olcum onu duzeltiyor. Ayni koşum TTS'in 2.200
# kelimeyi TEK PARCADA uretebildigini de gosterdi — parcalama gerekmiyor.
KONUSMA_HIZI = 170


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

    with pytest.raises(ValueError, match="80-150 words"):
        ya.validate_content_plan(_plan(1500, 8))


def test_SHORTS_tavani_60_SANIYENIN_altinda():
    """⚠️ Tavanin gercek siniri editoryal degil YAPISAL: 60 sn'yi gecen video
    Shorts sayilmaz.

    Tavan 2026-08-16'da 120'den 150'ye cikarildi cunku Kimi dogal olarak
    122-151 kelime yaziyor ve tek koşumda bes denemenin dordu SIRF kelime
    sayisindan yaniyordu. 170 kelime/dk olculdu, yani:
        150 kelime = 52,9 sn  ·  170 kelime = 60,0 sn (SINIR)
    """
    _, en_cok = ya.SHORTS_BICIMI.kelime_araligi

    assert en_cok / ya.KELIME_HIZI * 60 < 58, "Shorts 60 saniyeyi gecemez"


def test_SHORTS_tavani_modelin_OLCULEN_ciktisini_kapsiyor():
    """Olculen redler: 122, 127, 146, 151.

    ⚠️ 151 tavanin BIR KELIME ustunde kaliyor ve bu bilerek boyle: tavan
    kanal sahibinin karari (150 = 52,9 sn), 60 saniyelik Shorts sinirina
    7 saniye pay birakiyor. Yani dagilimin ust ucundaki tek bir cikti hala
    reddedilebilir — kazanc dorttur ucunun kurtarilmasi, hepsinin degil.
    """
    _, en_cok = ya.SHORTS_BICIMI.kelime_araligi

    assert en_cok >= 146, "olculen kumenin govdesi kabul edilmeli"
    assert en_cok == 150, "tavan kanal sahibinin sectigi deger"


def test_uzun_bicim_2000_kelimeyi_KABUL_ediyor():
    """⚠️ Kapi kipe bagli olmasaydi her uzun senaryo reddedilirdi."""
    ya.validate_content_plan(_uzun_plan(1500, 25), bicim=ya.UZUN_BICIMI)


def test_uzun_bicimde_SHORTS_senaryosu_reddediliyor():
    with pytest.raises(ValueError, match="900-2200 words"):
        ya.validate_content_plan(_uzun_plan(100, 30), bicim=ya.UZUN_BICIMI)


def test_uzun_bicim_sahne_araligi():
    # Tavan 45 -> 39 (2026-08-15): kelime tabani 900'e inince 45 sahne
    # 7,0 sn/kare veriyordu ve belgesel ritmi tabani 8 saniye.
    # ⚠️ Tavan 39 -> 26 (2026-08-19), sebebi ritim DEGIL dönem kaymasi:
    # 39 sahnede model malzemeyi tuketip kazi tarihine geciyor.
    # ⚠️ Tavan 26 -> 28 (2026-08-20), sebebi modelin OLCULEN KIP'I: 16
    # denemenin 7'si tam 27 sahne verdi, yani kapi en sik uretilen ciktiyi
    # reddediyordu. Gerekce `UZUN_BICIMI.sahne_araligi` yorumunda.
    ya.validate_content_plan(_uzun_plan(1500, 24), bicim=ya.UZUN_BICIMI)
    ya.validate_content_plan(_uzun_plan(1500, 28), bicim=ya.UZUN_BICIMI)

    with pytest.raises(ValueError, match="24-28 scenes"):
        ya.validate_content_plan(_uzun_plan(1500, 8), bicim=ya.UZUN_BICIMI)
    with pytest.raises(ValueError, match="24-28 scenes"):
        ya.validate_content_plan(_uzun_plan(1500, 39), bicim=ya.UZUN_BICIMI)


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
    """Olculen hizla 900-2.200 kelime = 5,3-12,9 dakika.

    ⚠️ Taban 1.200'den 900'e INDI (2026-08-15, kanal sahibinin karari).
    Sebep olculdu: model dokuz koşumda 876-1.353 kelime uretti, yani 1.200
    dagilimin tam ortasini kesiyordu ve bes deneme bu yuzden yaniyordu.
    1.200 bir YouTube geregi degildi; uzun format esigi 60 saniye.
    """
    en_az, en_cok = ya.UZUN_BICIMI.kelime_araligi

    assert 5 <= en_az / KONUSMA_HIZI <= 6
    assert 11 <= en_cok / KONUSMA_HIZI <= 14


def test_sahne_basina_sure_belgesel_ritmi():
    """En kotu durumda bile kare ekranda makul kaliyor mu.

    900 kelime / 170 = 5,3 dk = 317 sn; 39 sahne -> 8,1 sn/kare. Ust uc:
    2.200 kelime / 24 sahne -> ~32 sn. Ikisi de belgesel araliginda.

    ⚠️ Bu testi 8 saniyede tutmak BILINCLI. Kelime tabani 900'e indirilince
    45 sahne 7,0 sn/kare veriyordu; cozum esigi dusurmek DEGIL, sahne
    tavanini 39'a indirmek oldu. Kanalin olculen kusuru tam burada:
    izleyicinin ucte biri ILK SAHNE DEGISIMINDE gidiyor, yani kesmeyi
    hizlandirmak en yanlis yon.
    """
    en_az_kelime, en_cok_kelime = ya.UZUN_BICIMI.kelime_araligi
    en_az_sahne, en_cok_sahne = ya.UZUN_BICIMI.sahne_araligi

    en_kisa = (en_az_kelime / KONUSMA_HIZI * 60) / en_cok_sahne
    en_uzun = (en_cok_kelime / KONUSMA_HIZI * 60) / en_az_sahne

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
