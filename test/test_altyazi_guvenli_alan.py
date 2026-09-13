"""Shorts altyazisi YouTube arayuzunun altinda kalmasin (DW-141).

⚠️ OLCULDU (2026-09-13, kanal sahibinin telefon ekran goruntusu, Baalbek
1sf6rULIR2Q): 3 satirlik altyazi hem sol alttaki kanal adi/baslik blogunun
hem de sagdaki Kaydet/Paylas sutununun altinda. 23 Agu'daki "altyazi zaten
guvenli bantta" hukmu harfleri dogru olcmus ama hedef banti YouTube'un
arayuzunden degil tablo_sessiz'in %22'sinden odunc almisti.

Bu dosya GERCEK zinciri olcuyor: `altyazi_bayraklari` → `cli.parse_args` →
`build_video_params` → `generate_video` → altyazi klipleri. Kaynak metinde
sayi aramak (eski `test_dikey_kare` yaklasimi) arayuzle kesismeyi goremezdi;
kusur tam da "kod 78 diyor ama harfler 1545'te" idi.

Video/ses/yazici sahte (CI gercek kodlama yapmaz), altyazi klipleri GERCEK:
font, sarma, kontur ve konum uretimdekiyle birebir.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli  # noqa: E402
import youtube_automation as ya  # noqa: E402
from app.services import video as vd  # noqa: E402

# Baalbek'in gercek cumleleri + iki uzun kurgu: 1, 2, 4 ve 5 satir. Satir
# sayisi genisligiyle birlikte degisir; test satir sayisini VARSAYMAZ, olcer.
CUMLELER = [
    "Baalbek, Lebanon.",
    "Roman engineers built temples on top of them.",
    "The platform beneath Jupiter's temple uses stones far larger than anything "
    "Rome moved elsewhere.",
    "Every empire that touched Baalbek claimed the gods, but none claimed the "
    "platform, and nobody ever quarried a bigger stone.",
]

ESKI_BAYRAKLAR = [
    # 13 Eyl oncesi uretim ayari: kutu %78'e, genislik kareye gore %90.
    "--subtitle-enabled",
    "--subtitle-position",
    "custom",
    "--custom-position",
    "78",
    "--text-fore-color",
    "#FFFFFF",
    "--font-size",
    "56",
    "--stroke-color",
    "#000000",
    "--stroke-width",
    "7",
    "--no-subtitle-background-enabled",
]

ASGARI_PAY = 16
"""Harf kutusu ile arayuz bolgesi arasinda istenen en az bosluk (px)."""


class _SahteKlip:
    """generate_video'nun video/ses tarafi icin en kucuk MoviePy yuzeyi."""

    duration = 12
    fps = 44100
    w, h = ya.SHORTS_EN, ya.SHORTS_BOY

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def close(self):
        pass

    def with_effects(self, _):
        return self

    def with_audio(self, _):
        return self


def _srt_yaz(yol: Path) -> None:
    satirlar: list[str] = []
    for i, cumle in enumerate(CUMLELER, 1):
        bas, son = (i - 1) * 3, (i - 1) * 3 + 2
        satirlar += [str(i), f"00:00:{bas:02d},000 --> 00:00:{son:02d},500", cumle, ""]
    # ⚠️ Son bos satir ZORUNLU: MoviePy bir cue'yu ancak ardindan bos satir
    # gelince listeye ekliyor; olmazsa son cumle sessizce dusuyor.
    yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")


def _altyazi_klipleri(bayraklar: list[str], tmp_path: Path) -> list:
    """Bayraklari gercek zincirden gecirir, altyazi kliplerini dondurur."""
    yakalanan: list[list] = []

    def sahte_composite(clips, *args, **kwargs):
        yakalanan.append(list(clips))
        return _SahteKlip()

    args = cli.parse_args(
        ["--video-subject", "x", "--video-aspect", "9:16", "--bgm-type", "none", *bayraklar]
    )
    params = cli.build_video_params(args)
    srt = tmp_path / "subtitle.srt"
    _srt_yaz(srt)
    with (
        patch.object(vd, "_open_video_clip_quietly", return_value=_SahteKlip()),
        patch.object(vd, "AudioFileClip", return_value=_SahteKlip()),
        patch.object(vd, "CompositeVideoClip", side_effect=sahte_composite),
        patch.object(vd, "_write_videofile_with_codec_fallback"),
        patch.object(vd, "_get_configured_video_codec", return_value="libx264"),
    ):
        vd.generate_video(
            video_path="combined.mp4",
            audio_path="audio.mp3",
            subtitle_path=str(srt),
            output_file=str(tmp_path / "final.mp4"),
            params=params,
        )
    assert len(yakalanan) == 1, "altyazi bileşimi tam bir kez kurulmali"
    klipler = yakalanan[0][1:]  # ilk oge video
    assert len(klipler) == len(CUMLELER), "her cue bir klip olmali"
    return klipler


def _harf_kutusu(klip) -> tuple[int, int, int, int]:
    """Karede gorunen harflerin (x0, y0, x1, y1) kutusu — maskeden, kutudan degil."""
    x, y = klip.pos(0)
    if x == "center":
        x = (ya.SHORTS_EN - klip.w) / 2
    if y == "center":
        y = (ya.SHORTS_BOY - klip.h) / 2
    maske = klip.mask.get_frame(0)
    ys, xs = np.where(maske > 0.01)
    return (int(x + xs.min()), int(y + ys.min()), int(x + xs.max()), int(y + ys.max()))


def _kesisen_bolgeler(kutu, pay: int = 0) -> list[int]:
    x0, y0, x1, y1 = kutu
    return [
        i
        for i, (bx0, by0, bx1, by1) in enumerate(ya.SHORTS_ARAYUZ_BOLGELERI)
        if x1 + pay >= bx0 and x0 - pay < bx1 and y1 + pay >= by0 and y0 - pay < by1
    ]


def _satir_sayisi(klip) -> int:
    return klip.text.count("\n") + 1


@pytest.fixture(scope="module")
def yeni_klipler(tmp_path_factory):
    return _altyazi_klipleri(
        ya.altyazi_bayraklari(ya.SHORTS_BICIMI), tmp_path_factory.mktemp("yeni")
    )


@pytest.fixture(scope="module")
def eski_klipler(tmp_path_factory):
    return _altyazi_klipleri(ESKI_BAYRAKLAR, tmp_path_factory.mktemp("eski"))


def test_hicbir_harf_arayuz_bolgesine_girmiyor(yeni_klipler):
    for klip in yeni_klipler:
        kutu = _harf_kutusu(klip)
        assert _kesisen_bolgeler(kutu, ASGARI_PAY) == [], (
            f"{_satir_sayisi(klip)} satir: harfler {kutu} arayuze {ASGARI_PAY}px'ten yakin"
        )


def test_harflerin_alt_kenari_satir_sayisindan_bagimsiz(yeni_klipler):
    """Blok YUKARI dogru buyur: 1 satir da 5 satir da ayni alt kenarda biter."""
    hedef = ya.SHORTS_BOY * ya.ALTYAZI_ALT_KENAR_YUZDE / 100
    satirlar = set()
    for klip in yeni_klipler:
        _, _, _, alt = _harf_kutusu(klip)
        assert abs((alt + 1) - hedef) <= 2, f"{_satir_sayisi(klip)} satir: alt kenar {alt + 1}"
        satirlar.add(_satir_sayisi(klip))
    assert len(satirlar) >= 3, f"test en az uc farkli satir sayisi gormeli: {satirlar}"


def test_son_satir_kirpilmiyor(yeni_klipler):
    """Sabit kutu son satirin kuyruklarini kesiyordu (800px, 3 satir: 13px).

    Kirpilmayan klipte harflerin altinda bos satirlar kalir; kirpilanda maske
    tuvalin son satirina kadar doludur.
    """
    for klip in yeni_klipler:
        ys, _ = np.where(klip.mask.get_frame(0) > 0.01)
        assert ys.max() <= klip.h - 4, f"{_satir_sayisi(klip)} satir: harfler tuvalin dibine dayanmis"


def test_eski_ayar_kesismeyi_BULUYOR(eski_klipler):
    """Olcum aleti calisiyor mu: 13 Eyl oncesi ayarda kusur gorunmeli.

    Ekran goruntusundeki 3 satirlik altyazi iki bolgeye de giriyordu; ayni
    duzenek onu goremiyorsa yukaridaki yesil testlerin degeri yok.
    """
    kesisen = {_satir_sayisi(k): _kesisen_bolgeler(_harf_kutusu(k)) for k in eski_klipler}
    cok_satirli = [b for s, b in kesisen.items() if s >= 2]
    assert cok_satirli and all(b == [0, 1] for b in cok_satirli), kesisen


def test_yatay_bicim_eski_konumda():
    """Uzun/yatay videoyu YouTube arayuzsuz oynatir; oradaki ayar degismedi."""
    yatay = ya.altyazi_bayraklari(ya.UZUN_BICIMI)
    assert yatay[yatay.index("--custom-position") + 1] == "78"
    assert "--subtitle-text-bottom" not in yatay
    dikey = ya.altyazi_bayraklari(ya.SHORTS_BICIMI)
    assert "--custom-position" not in dikey
    assert dikey[dikey.index("--subtitle-text-bottom") + 1] == str(ya.ALTYAZI_ALT_KENAR_YUZDE)
    # Font, kontur ve serit kararlari (DW-93, DW-103) iki bicimde de ayni.
    for bayraklar in (yatay, dikey):
        assert bayraklar[bayraklar.index("--font-size") + 1] == "56"
        assert bayraklar[bayraklar.index("--stroke-width") + 1] == "7"
        assert "--no-subtitle-background-enabled" in bayraklar


def test_sabitler_arayuz_tablosuyla_tutarli():
    """Sayilar degisirse birbirine gore yeniden dogrulansin."""
    for x0, y0, x1, y1 in ya.SHORTS_ARAYUZ_BOLGELERI:
        assert 0 <= x0 < x1 <= ya.SHORTS_EN and 0 <= y0 < y1 <= ya.SHORTS_BOY
    alt_kenar = ya.SHORTS_BOY * ya.ALTYAZI_ALT_KENAR_YUZDE / 100
    en_ust_bolge = min(y0 for x0, y0, x1, y1 in ya.SHORTS_ARAYUZ_BOLGELERI if x0 == 0)
    assert en_ust_bolge - alt_kenar >= 48, "harflerin alti sol alt bloga cok yakin"
    genislik = ya.SHORTS_EN * ya.ALTYAZI_GENISLIK_YUZDE / 100
    merkez = ya.SHORTS_EN * ya.ALTYAZI_MERKEZ_X_YUZDE / 100
    sag_sutun = min(x0 for x0, y0, x1, y1 in ya.SHORTS_ARAYUZ_BOLGELERI if x0 > 0)
    assert merkez + genislik / 2 <= sag_sutun - ASGARI_PAY, "blok sag sutuna giriyor"
    assert merkez - genislik / 2 >= 49 + ASGARI_PAY, "blok uzun telefonda kirpilan sol kenara giriyor"


def test_hakem_istemi_altyaziyi_oldugu_yerde_tarif_ediyor():
    """Istem altyaziyi 'along the bottom' derse hakem alt yarinin ortasindaki
    metni resim ici yazi sayar — istem kendi kapisini besler."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    assert "burned along the bottom" not in kaynak
    assert kaynak.count("burned into the lower half of the frame") == 2
