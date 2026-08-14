"""Montaj sahne basina BIR kare almali — sabit 8 degil.

⚠️ Olculdu (2026-08-13, Murad III koşumu). Montaj senaryoda kac sahne olursa
olsun her zaman 8 kare ornekliyordu, ama plan 6-10 sahneye izin veriyor. 6
sahnelik bir videoda 8 kare iki sahneyi IKI KEZ ornekliyor ve hakem bunu
"agir tekrar" diye cezalandiriyordu.

Kusurun kaniti hakemin KENDI etiketleri: kare 2 -> sahne 2, kare 3 -> sahne 2;
kare 6, 7, 8 -> ucu de sahne 6. Ardindan "frames 2-3 are duplicates, frames
6-8 reuse the same engraving" yazip gorsel skorunu dusurdu. Yani ceza gercek
bir kusura degil, olcum yontemine aitti.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


class _SahteKlip:
    """`VideoFileClip` yerine — gercek dosya acmadan sure ve fps verir."""

    def __init__(self, sure: float = 40.0, fps: float = 30.0):
        self.duration = sure
        self.fps = fps

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _komutu_yakala(monkeypatch, tmp_path, *, sahne: int, sure=40.0, fps=30.0):
    """`create_review_montage`i cagirip ffmpeg komutunu dondurur."""
    yakalanan: dict = {}

    monkeypatch.setattr(ya, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(ya, "VideoFileClip", lambda _yol: _SahteKlip(sure, fps))
    monkeypatch.setattr(ya, "get_ffmpeg_exe", lambda: "ffmpeg")

    def sahte_run(command, **_k):
        yakalanan["command"] = command
        # ffmpeg'in yazacagi dosyayi taklit et.
        Path(command[-1]).write_bytes(b"x" * 100)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(ya.subprocess, "run", sahte_run)

    ya.create_review_montage(tmp_path / "video.mp4", "gorev", sahne)
    return yakalanan["command"]


def _vf(command: list[str]) -> str:
    return command[command.index("-vf") + 1]


@pytest.mark.parametrize("sahne", [6, 7, 8, 9, 10])
def test_kare_sayisi_sahne_sayisina_esit(monkeypatch, tmp_path, sahne):
    """⚠️ Asil kusur: sayi sabit 8'di."""
    vf = _vf(_komutu_yakala(monkeypatch, tmp_path, sahne=sahne))

    assert vf.count("eq(n") == sahne


def test_izgara_butun_kareleri_aliyor(monkeypatch, tmp_path):
    """Hucre sayisi kare sayisindan AZ olursa kareler sessizce dusardi."""
    for sahne in range(6, 11):
        sutun, satir = ya.montaj_izgarasi(sahne)

        assert sutun * satir >= sahne, f"{sahne} kare {sutun}x{satir}'e sigmiyor"


def test_kareler_sahnenin_ortasindan_aliniyor(monkeypatch, tmp_path):
    """Kesme noktasindaki kare bir onceki sahneyi gosterebilir.

    8 sahne, 40 sn, 30 fps → klip 5 sn → ortalar 2.5, 7.5, ... saniye →
    kare 75, 225, 375, ...
    """
    vf = _vf(_komutu_yakala(monkeypatch, tmp_path, sahne=8, sure=40.0, fps=30.0))

    assert r"eq(n\,75)" in vf, "ilk kare sahne 1'in ORTASINDAN alinmali"
    assert r"eq(n\,225)" in vf
    assert r"eq(n\,0)" not in vf, "sifirinci kare kesme noktasi — alinmamali"


def test_kare_numaralari_videonun_fps_inden(monkeypatch, tmp_path):
    """fps sabit varsayilirsa baska fps'li videoda yanlis kare secilir."""
    vf = _vf(_komutu_yakala(monkeypatch, tmp_path, sahne=8, sure=40.0, fps=60.0))

    assert r"eq(n\,150)" in vf, "60 fps'te sahne 1'in ortasi 150. kare"


def test_kare_cogaltma_kapali(monkeypatch, tmp_path):
    """⚠️ `select` ile birlikte sart.

    Varsayilan kip eksik kareleri cogaltip zaman tabanini duzler, yani ayni
    kare tekrar tekrar dizilir — tam da kaldirmaya calistigimiz tekrar.
    """
    command = _komutu_yakala(monkeypatch, tmp_path, sahne=6)

    assert "-fps_mode" in command
    assert command[command.index("-fps_mode") + 1] == "passthrough"


def test_istem_kare_sayisini_ve_eslemeyi_soyluyor():
    """Hakem esleme soylenmezse ayni sahnenin iki ornegini kopya sanardi.

    ⚠️ 2026-08-14'te esleme DEGISTI: sahne basina iki kare var
    (`KARE_YUVASI`), yani kare 1-2 sahne 1. Eski istem "exactly ONE frame
    per scene" diyordu; kare duzeni degisip istem degismeseydi hakem her
    sahneyi iki ayri sahne sanar ve tekrar sikayeti uydururdu.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def review_video(") :][:4000]

    assert "8-frame chronological montage" not in govde, "sayi sabit yazilmamali"
    assert "{len(plan.scenes) * KARE_YUVASI}-frame" in govde
    assert "{KARE_YUVASI} frames per scene" in govde
    # Ayni karenin iki yuvada gorunmesi kasitli; tekrar sayilmamali.
    assert "deliberate layout" in govde


def test_montaj_cagrisi_KARE_sayisini_geciyor():
    """⚠️ Baglanti testi — fonksiyon dogru olsa bile cagri eksikse kusur surer.

    Sahne sayisi gecilseydi montaj her sahnenin TAM ORTASINDAN kare
    alirdi, yani iki gorselin EK YERINDEN.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "len(plan.scenes) * KARE_YUVASI" in kaynak
