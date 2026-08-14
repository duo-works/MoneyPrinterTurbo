"""Duragan gorsellere uygulanan yavas zoom kapatilabilmeli.

⚠️ NEDEN — kanal sahibinin sesli notu (2026-08-14), videolari izleyerek:
"Bir de su zoom olayi, benim hosuma gitmiyor."

⚠️ CEKIRDEK SERVIS DEGISTIRILMIYOR, PARAMETRELESIYOR. `app/services/video.py`
webui tarafindan da kullaniliyor; davranisi topyekun degistirmek bu hattin
disina tasardi. Varsayilan bugunku davranisi (zoom acik) KORUYOR, yalnizca
bizim hat kapali geciyor. Ayni ilke `dikeye_uydur` docstring'inde de yazili.

⚠️ Zoom'un kalkmasi ayrica bir SONRAKI adimin on kosulu: sahne basina iki
kare duzeninde, dikey yapistirilmis bir kare iki yuvaya birden konuyor. Her
gorsel kendi mp4'u olarak render edildigi ve zoom her klip sinirinda %100'e
sifirlandigi icin, zoom acikken ek yerinde gorunur bir sicrama olurdu.

⚠️ Bu testler gorseli GERCEKTEN render ediyor ve kareleri karsilastiriyor.
Kaynak metninde "zoom" dizesi aramak bunu goremezdi: bu oturumda ayni sinif
kusur (dize dogru, cagri yolu calismiyor) uc uretim koşumunu oldurdu.
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


def test_uretim_hatti_zoomu_KAPALI_cagiriyor():
    kok = Path(vd.__file__).resolve().parent.parent.parent
    kaynak = (kok / "youtube_automation.py").read_text(encoding="utf-8")

    assert "--no-video-zoom" in kaynak
