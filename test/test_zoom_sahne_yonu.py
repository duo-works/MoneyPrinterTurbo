"""Zoom yonu SAHNE basina degisir, KARE basina degil (2026-08-23).

⚠️ KANAL SAHIBININ TARIFI, birebir: "bazen sahneler arasi tam oturuyor bu
baya iyi, bazen de bir sahneye zoom yapip tekrar uzaklasiyor o kotu bir
goruntu olusturuyor."

Kok sebep olculdu. `preprocess_video` yonu `len(valid_materials) % 2` ile,
yani KARE paritesiyle seciyordu. Shorts'ta sahne basina IKI yuva var
(`SHORTS_BICIMI.kare_yuvasi == 2`) ve `youtube_automation.kare_yerlesimi` uc
duzenden IKISINDE ayni gorseli iki ardisik yuvaya koyuyor:

    [A, B]     iki gorsel de kirpilabiliyor  -> FARKLI icerik  -> "iyi"
    [AB, AB]   ikisi de bant ister           -> AYNI piksel    -> "kotu"
    [A, A]     ikinci gorsel yok             -> AYNI piksel    -> "kotu"

Son iki duzende olan sey:

    sahne1 yuva1 [A]  1,00 -> 1,12   iceri
    sahne1 yuva2 [A]  1,12 -> 1,00   GERI    <- ayni goruntu, ayni sahne

Yani izleyici TEK bir fotografin once buyuyup sonra kuculdugunu goruyor.
`[A, B]` duzeninde ayni donus var ama goruntu degistigi icin fark edilmiyor —
"bazen iyi bazen kotu" tam bu ayrim.

⚠️ Uzun formatta kusur HIC yoktu (`UZUN_BICIMI.kare_yuvasi == 1`): orada yon
zaten sahne basina degisiyor. Bu yuzden `yuva=1` yeni formulde de BIREBIR
eski diziyi uretmeli — asagidaki ilk test onu kilitliyor ve `test_zoom_yonu`
dosyasindaki butun donusumlu testler `yuva` GECIRMEDEN kosuyor.

⚠️ OLCUM PIKSELDEN, PARAMETREDEN DEGIL. Klipler gercekten render ediliyor ve
kareler okunuyor; kaynak metnine cakili bir test bu kusuru goremezdi cunku
kusur ifadede degil DAVRANISTAydi.
"""

import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from moviepy.video.io.VideoFileClip import VideoFileClip

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schema import MaterialInfo  # noqa: E402
from app.services import video as vd  # noqa: E402
from app.utils import utils  # noqa: E402

KAYNAK_GORSEL = Path(__file__).resolve().parent / "resources" / "1.png"


def _sahne_klipleri(onek: str, *, yuva: int, kare: int = 2) -> list[str]:
    """`[A, A]` duzeninin birebir taklidi: AYNI gorsel, ardisik yuvalar.

    ⚠️ Iki AYRI dosya adi sart — `preprocess_video` ciktiyi kaynak adindan
    tureterek yaziyor ve ayni ad verilirse ikinci klip birinciyi ezer.
    (`test_zoom_yonu` docstring'inde olculmus bir kusur.)
    """
    yerel = utils.storage_dir("local_videos", create=True)
    malzemeler = []
    for sira in range(1, kare + 1):
        hedef = os.path.join(yerel, f"{onek}-{sira}.png")
        shutil.copy2(KAYNAK_GORSEL, hedef)
        malzeme = MaterialInfo()
        malzeme.url = os.path.basename(hedef)
        malzeme.provider = "local"
        malzemeler.append(malzeme)

    sonuc = vd.preprocess_video(
        malzemeler, clip_duration=1, zoom=True, donusumlu_zoom=True, yuva=yuva
    )
    assert len(sonuc) == kare, f"{kare} klip beklenmisti"
    return [m.url for m in sonuc]


def _uzaklik_dizisi(mp4_yollari: list[str]) -> list[float]:
    """Ilk klibin ILK karesine gore uzaklik; her klipten bas ve son kare.

    Zoom monoton ise dizi monoton artar. Sahne icinde yon donuyorsa dizi
    once buyuyup sonra BASLANGICA yaklasir — olculen sey tam olarak bu.
    """
    with VideoFileClip(mp4_yollari[0]) as klip:
        capa = klip.get_frame(0.0).astype(float)

    uzakliklar: list[float] = []
    for yol in mp4_yollari:
        with VideoFileClip(yol) as klip:
            sure = float(klip.duration)
            for an in (0.0, max(sure - 1 / 30, 0.0)):
                uzakliklar.append(
                    float(np.abs(klip.get_frame(an).astype(float) - capa).mean())
                )
    return uzakliklar


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_SAHNE_ICINDE_zoom_yonu_DONMUYOR():
    """⚠️ Bu dosyanin asil iddiasi — kanal sahibinin sikayet ettigi kusur.

    Sahne basina iki yuva, ikisinde de AYNI gorsel. Olcek dizisi sahne
    boyunca monoton artmali; donerse son kare basa geri gelir.

    Mutasyon: yonu kare paritesine (`sira % 2`) geri almak bu testi dusurur.
    """
    dizi = _uzaklik_dizisi(_sahne_klipleri("sahne-yuva2", yuva=2))

    assert dizi[0] < 1e-6, "olcum bozuk: capa kendisiyle karsilastirilmadi"
    assert dizi[-1] > dizi[1], (
        "sahnenin IKINCI yuvasi birincinin bittigi yerden DEVAM etmeliydi; "
        f"dizi geri donmus: {[round(u, 3) for u in dizi]}"
    )
    for onceki, sonraki in zip(dizi, dizi[1:]):
        assert sonraki >= onceki - 0.5, (
            f"olcek sahne icinde geri gitti: {[round(u, 3) for u in dizi]}"
        )


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_KARSIT_ORNEK_yuva1de_yon_DONUYOR():
    """⚠️ Karsit ornek — olcumun kusuru gercekten gordugunu kanitlar.

    `yuva=1` her kareyi ayri sahne sayar, yani eski davranis: ikinci klip
    ters yone gidiyor ve son kare BASLANGICA geri geliyor. Bu test gecmezse
    yukaridaki test bir sey kanitlamiyor demektir.
    """
    dizi = _uzaklik_dizisi(_sahne_klipleri("sahne-yuva1", yuva=1))

    assert dizi[-1] < dizi[1], (
        "yuva=1'de ikinci klip geri donmeliydi (eski davranis); "
        f"dizi: {[round(u, 3) for u in dizi]}"
    )


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_SINIRDA_olcek_SUREKLI_kaliyor():
    """⚠️ 2026-08-17'nin kazanimi KORUNUYOR: yuva sinirinda sicrama yok.

    Sahne ici sinir (yuva1 sonu -> yuva2 basi) olcekte surekli olmali;
    17 Agu'nun butun gerekcesi buydu ve yeni formul onu bozmamali.

    Mutasyon: dilim araligini kaydirmak (`bas`/`son`) bu testi dusurur.
    """
    dizi = _uzaklik_dizisi(_sahne_klipleri("sahne-sinir", yuva=2))
    sinir = abs(dizi[2] - dizi[1])
    hareket = abs(dizi[1] - dizi[0])

    assert hareket > 0.1, "olcum bozuk: klip icinde hic hareket yok"
    assert sinir / hareket < 0.5, (
        f"yuva sinirinda olcek sicradi (sinir {sinir:.4f} / hareket {hareket:.4f})"
    )


@pytest.mark.skipif(not KAYNAK_GORSEL.exists(), reason="test gorseli yok")
def test_KADRAJ_ARALIGI_buyumuyor():
    """⚠️ Sahne basina TOPLAM buyume `DONUSUMLU_ZOOM_ORANI` KALIYOR.

    Iki yuvanin her biri tam Δ yapsaydi sahne 1,00-1,24'e cikardi, yani
    goruntunun ~%19'u kare disinda kalirdi. Kanal sahibi kadraj araliginin
    KORUNMASINI secti; olcut: iki yuvali sahnenin toplam hareketi, tek
    yuvali (uzun format) bir sahnenin hareketiyle ayni buyuklukte olmali.

    Mutasyon: `bas`/`son` dilimlemesini kaldirip her yuvaya tam Δ vermek bu
    testi dusurur.
    """
    iki_yuva = _uzaklik_dizisi(_sahne_klipleri("kadraj-2", yuva=2))
    tek_yuva = _uzaklik_dizisi(_sahne_klipleri("kadraj-1", yuva=1, kare=1))

    sahne_hareketi = iki_yuva[-1]
    tek_hareket = tek_yuva[-1]

    assert sahne_hareketi < tek_hareket * 1.6, (
        "iki yuvali sahnenin toplam hareketi tek yuvalininkine yakin olmali "
        f"(iki yuva {sahne_hareketi:.3f} · tek yuva {tek_hareket:.3f})"
    )


def test_YUVA_uretim_hattindan_geciyor():
    """Baglanti testi — parametre tanimli olup gecmezse islevsiz.

    ⚠️ Zincir UC halka: `youtube_automation` bayragi basar, `cli.py` onu
    `VideoParams`a cevirir, `task.py` `preprocess_video`ya gecirir. Herhangi
    biri kopsa zoom sessizce eski davranisa doner.
    """
    kok = Path(__file__).resolve().parent.parent

    ya_kaynak = (kok / "youtube_automation.py").read_text(encoding="utf-8")
    assert '"--video-yuva"' in ya_kaynak
    assert "str(bicim.kare_yuvasi)" in ya_kaynak, "yuva BICIMDEN gelmeli"

    cli_kaynak = (kok / "cli.py").read_text(encoding="utf-8")
    assert '"video_yuva"' in cli_kaynak, "VideoParams eslemesine eklenmemis"

    task_kaynak = (kok / "app" / "services" / "task.py").read_text(encoding="utf-8")
    assert "yuva=params.video_yuva" in task_kaynak


def test_VARSAYILAN_yuva_BIR():
    """⚠️ Regresyon kilidi: webui ve `yuva` gecirmeyen her cagiran, bugunku
    davranisi almali. Varsayilan 2 olsaydi tek kareli her hat sessizce
    yariya inen bir zoom alirdi."""
    import inspect

    from app.models.schema import VideoParams

    assert inspect.signature(vd.preprocess_video).parameters["yuva"].default == 1
    assert VideoParams(video_subject="konu").video_yuva == 1
