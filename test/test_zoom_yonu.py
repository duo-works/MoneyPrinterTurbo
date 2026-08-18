"""Duragan gorsellere uygulanan zoom: kapatilabilmeli ve YONU degisebilmeli.

⚠️ IKI ASAMALI HIKAYE, ikisi de kanal sahibinin sesli notundan:

**2026-08-14 — zoom tamamen kapatildi.** "Bir de su zoom olayi, benim hosuma
gitmiyor."

**2026-08-17 — zoom DONUSUMLU olarak geri acildi.** Kod okununca asil kusurun
zoom'un KENDISI degil YONU oldugu gorüldü: her klip 1,00'dan basliyor, yani
onceki klip 1,00+Δ'da biterken sinirda ani bir kucultme oluyordu.
`youtube_automation.kare_duzeni` uc durumdan IKISINDE ayni gorseli iki ardisik
yuvaya koyuyor:

    [A, B]     iki gorsel de kirpilabiliyor  -> farkli icerik
    [AB, AB]   ikisi de bant ister           -> AYNI piksel
    [A, A]     ikinci gorsel yok             -> AYNI piksel

Yani sicrama piksel birebir ayniyken oluyordu — en gorunur hali. Donusumlu
kipte tek numarali kare iceri, cift numarali kare disari zoomluyor; olcek HER
sinirda surekli kalmali.

**2026-08-18 — donusumlu kip `[A, A]`da CALISMIYORDU, olculdu ve duzeltildi.**
Yukaridaki "olcek her sinirda surekli kalir" iddiasi tam da hedefledigi
durumda gecersizdi. Kusur zoom mantiginda degil `preprocess_video`'nun cikti
ADINDaydi: yol kaynak dosyadan turuyordu, `[A, A]` iki yuvaya AYNI dosyayi
koyuyor, ikinci koşum birincinin ciktisini eziyor ve iki yuva ayni klibi
oynatiyordu — ikisi de 1,00'dan basliyor, sinirda 1,00+Δ -> 1,00 sicramasi
oluyordu. Yayinlanmis videodan olculdu (Cemal Pasha):

    [A, A] sinirlari            0,896 · 0,942 · 0,937 · 0,719
    ayni aralik KLIP ICINDE     0,999

⚠️ Ve bu dosyadaki donusumlu testler o sirada YESILDI — cunku hepsi gorseli
iki AYRI ada kopyaliyor (`_cift_mp4_uret`). Docstring'i ezilmeyi biliyor ve
ondan KACINIYORDU ("ayni adi verirsek ikinci klip birinciyi ezer"), yani kusur
bir kisit olarak yaziya dokulmustu. Uretimin gercek sekli asagida ayri bir
bolumde sinaniyor.

⚠️ CEKIRDEK SERVIS DEGISTIRILMIYOR, PARAMETRELESIYOR. `app/services/video.py`
webui tarafindan da kullaniliyor; davranisi topyekun degistirmek bu hattin
disina tasardi. Varsayilan bugunku davranisi (duz zoom) KORUYOR, yalnizca
bizim hat donusumlu geciyor. Ayni ilke `dikeye_uydur` docstring'inde de yazili.

⚠️ Bu testler gorseli GERCEKTEN render ediyor ve kareleri karsilastiriyor.
Kaynak metninde "zoom" dizesi aramak bunu goremezdi: 2026-08-14'te ayni sinif
kusur (dize dogru, cagri yolu calismiyor) uc uretim koşumunu oldurdu.

**2026-08-18 — "donusumlu zoom hakem puanini dusuruyor" suphesi OLCULDU ve
DUSTU.** Sunu KAYIT icin yaziyorum ki bir sonraki oturum alti render'lik
pahali A/B'yi bastan kurmasin.

Suphe gercekti ve ciddiye alindi:

    zoom oncesi (16 Agu→)  n=33   ≥75 alan: 15  (%45)
    zoom sonrasi           n=6    ≥75 alan:  0

Iki bagimsiz olcum sucu dusurdu:

1. **Geometri.** `create_review_montage` kareyi klibin ORTASINDAN aliyor;
   orada olcek her iki yonde de 1,0435 — yani duz ve donusumlu zoom hakemin
   GORDUGU karede AYNI. Kirpilan ~%4 karenin KENARI ve kenar zaten
   `GaussianBlur` bandi; net bant ortada ve oransal olarak BUYUYOR.

2. **Sonuc.** #43-#47 indikten SONRA, zoom ACIKKEN iki video pes pese
   yayinlandi (11:17 Gobekli Tepe 78 · 12:23 Cemal Pasha 75). Yani %0'lik
   seri zoom'un degil, kuyrugun kurumasinin ve 72'nin konuyu yakmasinin
   sonucuymus.

⚠️ Dogru okuma: n=6'lik bir seri bir NEDEN degil bir SORU'ydu. Mekanizmasi
cürütülen bir hipotez icin render harcanmadi.
"""

import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from moviepy.video.io.VideoFileClip import VideoFileClip

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schema import MaterialInfo, VideoParams  # noqa: E402
from app.services import video as vd  # noqa: E402
from app.utils import utils  # noqa: E402

KAYNAK_GORSEL = Path(__file__).resolve().parent / "resources" / "1.png"


def _mp4_uret(ad: str, *, zoom: bool) -> str:
    """Tek gorseli klibe cevirir ve dosya yolunu doner."""
    yerel = utils.storage_dir("local_videos", create=True)
    hedef = os.path.join(yerel, ad)
    shutil.copy2(KAYNAK_GORSEL, hedef)

    malzeme = MaterialInfo()
    malzeme.url = os.path.basename(hedef)
    malzeme.provider = "local"

    sonuc = vd.preprocess_video([malzeme], clip_duration=1, zoom=zoom)
    assert sonuc, "preprocess_video bos dondu"
    return sonuc[0].url


def _ilk_son_farki(mp4: str) -> float:
    """Ilk ve son karenin ortalama mutlak farki.

    ⚠️ BIREBIR ESITLIK ARANAMAZ, olculdu: video H.264 ile kayipli
    sikistiriliyor, yani ayni goruntunun iki karesi bile bit bit ayni
    donmuyor. Ilk surum `array_equal` kullaniyordu ve zoom kapaliyken bile
    kirmizi veriyordu — kusur kodda degil olcumdeydi.

    Olculen ayrim buyuk (2026-08-14, test/resources/1.png, 1 sn klip):

        zoom KAPALI : 0,00075
        zoom ACIK   : 4,82        → 6400 kat

    `ESIK` bu iki sayinin arasinda, ikisine de uzak.
    """
    with VideoFileClip(mp4) as klip:
        sure = float(klip.duration)
        ilk = klip.get_frame(0.0).astype(float)
        son = klip.get_frame(max(sure - 0.05, 0.0)).astype(float)
    return float(np.abs(ilk - son).mean())


ESIK = 0.1


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_zoom_KAPALIYKEN_kare_degismiyor():
    """Asil talep: duragan gorsel duragan kalsin."""
    fark = _ilk_son_farki(_mp4_uret("zoom-kapali.png", zoom=False))

    assert fark < ESIK, f"zoom kapaliyken kare degismemeli (fark {fark:.5f})"


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_zoom_VARSAYILAN_olarak_hala_calisiyor():
    """⚠️ Webui ayni servisi kullaniyor — varsayilan davranis KORUNMALI.

    Bu test gecmezse degisiklik cekirdek servisin davranisini topyekun
    degistirmis demektir ve bu hattin disina tasmis oluruz.
    """
    fark = _ilk_son_farki(_mp4_uret("zoom-acik.png", zoom=True))

    assert fark > ESIK, f"varsayilan zoom kareyi degistirmeli (fark {fark:.5f})"


def test_parametre_varsayilani_zoom_ACIK():
    """Imza duzeyinde de acik: cagirmayan taraf eski davranisi alir."""
    import inspect

    imza = inspect.signature(vd.preprocess_video)
    assert imza.parameters["zoom"].default is True


def test_video_params_zoom_alani_tasiyor():
    # `video_subject` zorunlu alan; varsayilani sinamak icin doldurulur.
    assert VideoParams(video_subject="konu").video_zoom is True


def test_task_katmani_parametreyi_GECIRIYOR():
    """⚠️ Zincirin kopabilecegi yer burasi.

    `preprocess_video` zoom'u destekleyip `task.py` onu gecirmezse bayrak
    sessizce etkisiz kalir — CLI'da gorunur, videoda gorunmez.
    """
    kaynak = Path(vd.__file__).resolve().parent.joinpath("task.py").read_text(encoding="utf-8")

    assert "zoom=params.video_zoom" in kaynak


def test_cli_bayragi_ve_eslemesi_var():
    kok = Path(vd.__file__).resolve().parent.parent.parent
    kaynak = (kok / "cli.py").read_text(encoding="utf-8")

    assert '"--no-video-zoom"' in kaynak
    # Eslemeye eklenmezse argparse bayragi alir ama VideoParams'a hic gecmez.
    assert '"video_zoom"' in kaynak


# --- Donusumlu yon (2026-08-17) --------------------------------------------


def _cift_mp4_uret(onek: str, *, donusumlu: bool) -> tuple[str, str]:
    """AYNI gorselden iki ardisik klip — `[A, A]` duzeninin birebir taklidi.

    ⚠️ Iki AYRI dosya adi sart: `preprocess_video` ciktiyi
    `<kaynak>.mp4` diye yaziyor, ayni adi verirsek ikinci klip birinciyi
    ezer ve test kendi kendini kandirir.
    """
    yerel = utils.storage_dir("local_videos", create=True)
    malzemeler = []
    for sira in (1, 2):
        hedef = os.path.join(yerel, f"{onek}-{sira}.png")
        shutil.copy2(KAYNAK_GORSEL, hedef)
        malzeme = MaterialInfo()
        malzeme.url = os.path.basename(hedef)
        malzeme.provider = "local"
        malzemeler.append(malzeme)

    sonuc = vd.preprocess_video(
        malzemeler, clip_duration=1, zoom=True, donusumlu_zoom=donusumlu
    )
    assert len(sonuc) == 2, "iki klip beklenmisti"
    return sonuc[0].url, sonuc[1].url


def _sinir_ve_hareket(onceki_mp4: str, sonraki_mp4: str) -> tuple[float, float]:
    """(sinirdaki sicrama, klip ICINDEKI hareket).

    Sinir farki: onceki klibin SON karesi ile sonraki klibin ILK karesi —
    izleyicinin kesme aninda gordugu sey tam olarak bu.

    ⚠️ OLCUT MUTLAK DEGIL ORANSAL, ve bu bilincli. Sinirda birebir esitlik
    beklenemez: gorsel yeniden orneklenip H.264 ile kayipli sikistiriliyor,
    yani kucuk bir kalinti her zaman var. Anlamli soru "sinirdaki degisim,
    klibin kendi icindeki harekete gore ne kadar buyuk" — cunku sicramayi
    gorunur kilan sey tam olarak bu oran.

    Olculdu (2026-08-17, test/resources/1.png):

        klip 1,0 sn   duz %100   donusumlu  %13
        klip 2,9 sn   duz %100   donusumlu   %5    <- uretimin gercek suresi

    Duz kipte oran TAM %100: sinirdaki sicrama, zoom'un butun yolculugu
    kadar. Donusumlu kipte kalinti klip uzadikca ORANSAL olarak kuculuyor
    (mutlak degeri ~0,7'de sabit kaliyor), yani bir olcek sureksizligi degil
    sabit bir yeniden orneklem artigi.
    """
    with VideoFileClip(onceki_mp4) as klip:
        sure = float(klip.duration)
        ilk_a = klip.get_frame(0.0).astype(float)
        son_a = klip.get_frame(max(sure - 1 / 30, 0.0)).astype(float)
    with VideoFileClip(sonraki_mp4) as klip:
        ilk_b = klip.get_frame(0.0).astype(float)
    return float(np.abs(son_a - ilk_b).mean()), float(np.abs(son_a - ilk_a).mean())


SINIR_ORANI = 0.25
"""Sinirdaki sicrama, klip ici harekete gore en fazla bu kadar olabilir.

Olculen iki deger (%5 ve %100) arasinda ve ikisine de uzak.
"""


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_DONUSUMLU_zoomda_klip_sinirinda_SICRAMA_YOK():
    """⚠️ Bu dosyanin asil iddiasi.

    Ayni gorselden uretilen iki ardisik klipte, birincinin son karesi ile
    ikincinin ilk karesi ayni olceke denk gelmeli: birinci 1,00+Δ'da bitiyor,
    ikinci 1,00+Δ'dan basliyor.
    """
    sinir, hareket = _sinir_ve_hareket(*_cift_mp4_uret("donusumlu", donusumlu=True))

    assert hareket > ESIK, "olcum bozuk: klip icinde hic hareket yok"
    assert sinir / hareket < SINIR_ORANI, (
        f"donusumlu zoomda sinir surekli olmaliydi "
        f"(sinir {sinir:.4f} / hareket {hareket:.4f})"
    )


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_DUZ_zoomda_klip_sinirinda_sicrama_VAR():
    """⚠️ Karsit ornek — kusurun gercek oldugunu gosteren olcum.

    Bu test gecmezse yukaridaki test bir sey KANITLAMIYOR demektir: ikisi de
    yesilse olcum sinirdaki farki hic gormuyor olurdu.
    """
    sinir, hareket = _sinir_ve_hareket(*_cift_mp4_uret("duz", donusumlu=False))

    assert sinir / hareket > SINIR_ORANI, (
        f"duz zoomda sinirda sicrama olmaliydi "
        f"(sinir {sinir:.4f} / hareket {hareket:.4f})"
    )


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_iki_yonun_klip_OLCULERI_ayni():
    """⚠️ NEDEN VAR — olculdu (2026-08-17), donusumlu kip yazilirken cikti.

    MoviePy tuvali t=0'daki klip boyutundan turetiyor. Iceri zoomlayan kare
    1,00'dan basliyor, DISARI zoomlayan kare 1,00+Δ'dan — yani tuval de o
    kadar buyuyordu:

        tek numarali kare  580x751
        cift numarali kare 597x773   <- %3 buyuk

    Donusumlu kip, olculeri birbirini tutmayan klipler uretip
    `combine_videos`a veriyordu. `CompositeVideoClip(..., size=clip.size)`
    ile tuval sabitlendi.
    """
    ilk, ikinci = _cift_mp4_uret("olcu", donusumlu=True)

    with VideoFileClip(ilk) as k:
        ilk_olcu = tuple(k.size)
    with VideoFileClip(ikinci) as k:
        ikinci_olcu = tuple(k.size)

    assert ilk_olcu == ikinci_olcu, (
        f"iki yonun klip olculeri ayni olmaliydi ({ilk_olcu} vs {ikinci_olcu})"
    )


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_donusumlu_kipte_kareler_HALA_HAREKETLI():
    """Sureklilik ugruna zoom'u sessizce kapatmis olmayalim.

    Kanal sahibi zoom'u GERI ISTEDI; her iki karenin de kendi icinde
    hareket etmesi gerekiyor, yalnizca sinirlar dikissiz olmali.
    """
    ilk, ikinci = _cift_mp4_uret("hareket", donusumlu=True)

    assert _ilk_son_farki(ilk) > ESIK, "tek numarali kare hareketsiz kalmis"
    assert _ilk_son_farki(ikinci) > ESIK, "cift numarali kare hareketsiz kalmis"


# --- AYNI dosya iki yuvada: uretimin GERCEK sekli (2026-08-18) --------------
#
# ⚠️ NEDEN AYRI BIR BOLUM — yukaridaki donusumlu testler gecerken uretimde
# sicrama VARDI, cunku hepsi gorseli IKI AYRI ADA kopyaliyor
# (`_cift_mp4_uret`). Uretimde ise `[A, A]` duzeni AYNI dosyayi iki yuvaya
# koyuyor ve `preprocess_video` ciktiyi kaynak yolundan turetiyordu, yani
# ikinci koşum birincinin ciktisini eziyor ve iki yuva ayni klibi oynatiyordu.
#
# ⚠️ `_cift_mp4_uret` docstring'i bu ezilmeyi BILIYORDU ve ondan KACINIYORDU:
# "iki AYRI dosya adi sart... ayni adi verirsek ikinci klip birinciyi ezer".
# Yani test, kusuru yakalamak yerine kusuru bir KISIT olarak yaziya dokmustu.
# Bu deponun tekrar eden hata sinifi: testin dogruladigi yolu uretim hic
# kosmuyor (bkz. `test_acilis_kadraji.py`, `ACILIS_KARELERI`).
#
# ⚠️ OLCULDU (2026-08-18, Cemal Pasha, yayinlanmis video). Sahne ici yuva
# sinirinin ±0,10 sn'si, 64x64 gri iz:
#
#     [A, A] sinirlari            0,896 · 0,942 · 0,937 · 0,719
#     ayni aralik KLIP ICINDE     0,999
#
# Dort sinirin dordunde de gorunur sicrama.


def _ayni_dosyadan_cift(onek: str) -> tuple[str, str]:
    """TEK bir kaynak dosyadan iki ardisik klip — `[A, A]` duzeninin birebiri.

    ⚠️ Fark yukaridaki `_cift_mp4_uret`ten TEK bir seyde: dosya bir kez
    kopyalaniyor ve iki materyal AYNI adi gosteriyor. Uretimin yaptigi tam
    olarak bu; ayri adlar vermek kusuru gormezden gelmekti.
    """
    yerel = utils.storage_dir("local_videos", create=True)
    hedef = os.path.join(yerel, f"{onek}.png")
    shutil.copy2(KAYNAK_GORSEL, hedef)

    malzemeler = []
    for _ in range(2):
        malzeme = MaterialInfo()
        malzeme.url = os.path.basename(hedef)
        malzeme.provider = "local"
        malzemeler.append(malzeme)

    sonuc = vd.preprocess_video(
        malzemeler, clip_duration=1, zoom=True, donusumlu_zoom=True
    )
    assert len(sonuc) == 2, "iki klip beklenmisti"
    return sonuc[0].url, sonuc[1].url


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_AYNI_dosya_iki_yuvada_AYRI_klip_uretiyor():
    """Ezilme olursa iki yuva ayni dosyayi gosterir ve donusumlu zoom oluyor."""
    ilk, ikinci = _ayni_dosyadan_cift("ayni-kaynak-ad")

    assert ilk != ikinci, (
        "ayni kaynaktan uretilen iki klip AYNI dosyaya yazilmis; ikinci "
        "on-isleme birincinin ciktisini eziyor"
    )
    assert Path(ilk).exists() and Path(ikinci).exists(), "klip dosyasi yok"


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_AYNI_dosya_iki_yuvada_SINIRDA_SICRAMA_YOK():
    """⚠️ Asil iddia — ve 2026-08-18'e kadar uretimde DUSUYORDU.

    Yukaridaki `test_DONUSUMLU_zoomda_klip_sinirinda_SICRAMA_YOK` ile ayni
    olcut, ama uretimin gercek girdisiyle: tek kaynak dosya, iki yuva.
    """
    sinir, hareket = _sinir_ve_hareket(*_ayni_dosyadan_cift("ayni-kaynak-sinir"))

    assert hareket > ESIK, "olcum bozuk: klip icinde hic hareket yok"
    assert sinir / hareket < SINIR_ORANI, (
        f"ayni gorsel iki yuvadayken sinir surekli olmaliydi "
        f"(sinir {sinir:.4f} / hareket {hareket:.4f})"
    )


def test_cikti_adi_KAYNAK_YOLUNDAN_TEK_BASINA_turemiyor():
    """⚠️ Kaynak duzeyinde nobetci: render eden testler yavas ve atlanabilir
    (`skipif`), bu ise her koşumda calisir. Ad yalnizca kaynak yolundan
    turerse ezilme sessizce geri gelir.
    """
    kaynak = Path(vd.__file__).read_text(encoding="utf-8")

    # ⚠️ ATAMA aranıyor, cıplak dize DEGIL: eski bicim yukaridaki aciklama
    # yorumunda gerekcesiyle birlikte ANILIYOR ve dizeyi aramak o yorumu
    # kusur sanardi. Ilk surumum tam bu yuzden kirmizi verdi.
    assert 'video_file = f"{material_source_path}.mp4"' not in kaynak, (
        "cikti adi yine yalnizca kaynak yolundan turuyor — ayni dosya iki "
        "yuvadayken ikinci klip birinciyi ezer"
    )
    assert "len(valid_materials):02d" in kaynak, "cikti adi sira numarasi tasimali"


def test_donusumlu_VARSAYILAN_OLARAK_KAPALI():
    """⚠️ Webui'nin davranisi degismemeli — varsayilan duz zoom."""
    import inspect

    imza = inspect.signature(vd.preprocess_video)
    assert imza.parameters["donusumlu_zoom"].default is False
    assert VideoParams(video_subject="konu").video_zoom_donusumlu is False


def test_task_katmani_DONUSUMLU_bayragini_da_geciriyor():
    """Zincirin kopabilecegi ikinci yer; `zoom` icin ayni kusur yasanmisti."""
    kaynak = (
        Path(vd.__file__).resolve().parent.joinpath("task.py").read_text(encoding="utf-8")
    )

    assert "donusumlu_zoom=params.video_zoom_donusumlu" in kaynak


def test_cli_donusumlu_bayragi_ve_eslemesi_var():
    kok = Path(vd.__file__).resolve().parent.parent.parent
    kaynak = (kok / "cli.py").read_text(encoding="utf-8")

    assert '"--video-zoom-alternating"' in kaynak
    assert '"video_zoom_donusumlu"' in kaynak


def test_uretim_hatti_zoomu_DONUSUMLU_cagiriyor():
    """⚠️ DAVRANIS DEGISIKLIGI, test duzeltmesi degil: hat 14 Agu'dan beri
    `--no-video-zoom` geciyordu, artik donusumlu zoom aciyor."""
    kok = Path(vd.__file__).resolve().parent.parent.parent
    kaynak = (kok / "youtube_automation.py").read_text(encoding="utf-8")

    assert "--video-zoom-alternating" in kaynak
    assert "--no-video-zoom" not in kaynak, "hat artik zoom'u kapatmiyor"
