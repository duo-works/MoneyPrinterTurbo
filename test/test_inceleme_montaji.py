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


def _istemi_yakala(monkeypatch, *, sahne: int, bicim=None) -> str:
    """`review_video`u cagirip hakeme giden TALIMAT metnini dondurur."""
    yakalanan: dict = {}

    def sahte_goru(prompt, _montaj):
        yakalanan["prompt"] = prompt
        return {}

    monkeypatch.setattr(ya, "_vision_json", sahte_goru)
    plan = ya.ContentPlan(
        topic="konu",
        visual_anchor="Herculaneum",
        title="baslik",
        script="metin",
        scenes=[
            {"narration": f"sahne {i}", "search_term": f"Herculaneum {i}"}
            for i in range(1, sahne + 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )
    ya.review_video(plan, Path("montaj.jpg"), bicim=bicim or ya.SHORTS_BICIMI)
    return str(yakalanan["prompt"]["instructions"])


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


def test_istem_kare_sayisini_ve_eslemeyi_soyluyor(monkeypatch):
    """Hakem esleme soylenmezse ayni sahnenin iki ornegini kopya sanardi.

    ⚠️ 2026-08-14'te esleme DEGISTI: sahne basina iki kare var
    (`KARE_YUVASI`), yani kare 1-2 sahne 1. Eski istem "exactly ONE frame
    per scene" diyordu; kare duzeni degisip istem degismeseydi hakem her
    sahneyi iki ayri sahne sanar ve tekrar sikayeti uydururdu.

    ⚠️ Artik ISTEM YAKALANIYOR, kaynak metni dilimlenmiyor: eski hali
    `review_video` govdesinden 4.000 karakter kesip icinde f-string
    PARCALARI ariyordu, yani promptun ne DEDIGINI degil nasil YAZILDIGINI
    test ediyordu. Kip destegi eklenince kirildi — kusur promptta degil,
    testin onu okuma bicimindeydi.
    """
    istem = _istemi_yakala(monkeypatch, sahne=8)

    assert "8-frame chronological montage" not in istem, "sayi sabit yazilmamali"
    assert "16-frame chronological montage" in istem
    assert "2 frames per scene" in istem
    assert "frames 1-2 are scene 1" in istem
    # Ayni karenin iki yuvada gorunmesi kasitli; tekrar sayilmamali.
    assert "deliberate layout" in istem
    # ⚠️ Istem TUTAMAYACAGI SOZ VERMEMELI. Olculdu (2026-08-14, Lycurgus
    # Cup): "iki kare AYNI CUMLEYI resmediyor" denince hakem bunu
    # dogrulamaya calisti ve hizasizligi kusur yazdi. Altyazi sese gore
    # zamanlanir, kare suresi `ses ÷ kare`; ikisi tanim geregi ortusmez.
    assert "not to these frame boundaries" in istem
    assert "illustrate the SAME sentence" not in istem


# --- Uzun format: orneklem ------------------------------------------------


def test_SHORTS_hic_orneklenmiyor():
    """⚠️ Tavan Shorts'a da uygulansaydi 10 sahnelik videoda hakem 20 kare
    yerine 12 gorurdu — olculerek kalibre edilmis bir kapinin gorus alanini
    sessizce daraltmak olurdu."""
    for sahne in range(6, 11):
        kare = sahne * ya.KARE_YUVASI

        assert ya.hakem_kareleri(kare) == list(range(1, kare + 1))


def test_uzun_videoda_TAVAN_uygulaniyor():
    secilen = ya.hakem_kareleri(45, ya.UZUN_BICIMI)

    assert len(secilen) <= ya.HAKEM_ORNEK_TAVANI
    assert secilen == sorted(secilen), "kareler kronolojik sirada kalmali"
    assert len(set(secilen)) == len(secilen), "ayni kare iki kez ornekleniyor"


def test_ILK_ve_SON_kare_her_zaman_iceride():
    """Kanca ve kapanis videonun en cok izlenen iki ani."""
    for toplam in (24, 30, 45):
        secilen = ya.hakem_kareleri(toplam, ya.UZUN_BICIMI)

        assert secilen[0] == 1
        assert secilen[-1] == toplam


def test_kisa_uzun_video_TAM_denetleniyor():
    assert ya.hakem_kareleri(10, ya.UZUN_BICIMI) == list(range(1, 11))


def test_orneklem_ESIT_ARALIKLI():
    secilen = ya.hakem_kareleri(45, ya.UZUN_BICIMI)
    araliklar = [b - a for a, b in zip(secilen, secilen[1:])]

    assert max(araliklar) - min(araliklar) <= 1, f"aralik dengesiz: {araliklar}"


def test_uzun_montaj_YATAY_olcekleniyor(monkeypatch, tmp_path):
    """⚠️ Olcek dikey sabitti (270:480); yatay karede goruntuyu ezerdi ve
    hakem bozuk en-boy oranini "kotu gorsel" diye cezalandirirdi."""
    yakalanan: dict = {}

    monkeypatch.setattr(ya, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(ya, "VideoFileClip", lambda _yol: _SahteKlip(600.0, 30.0))
    monkeypatch.setattr(ya, "get_ffmpeg_exe", lambda: "ffmpeg")

    def sahte_run(command, **_k):
        yakalanan["command"] = command
        Path(command[-1]).write_bytes(b"x" * 100)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(ya.subprocess, "run", sahte_run)
    ya.create_review_montage(tmp_path / "video.mp4", "gorev", 45, bicim=ya.UZUN_BICIMI)
    vf = _vf(yakalanan["command"])

    assert "scale=480:270" in vf
    assert "scale=270:480" not in vf
    assert vf.count("eq(n") == ya.HAKEM_ORNEK_TAVANI


def test_uzun_izgara_serit_olmuyor():
    """45 kare 23x2'lik okunmaz bir serit olurdu; asil kusur buydu."""
    sutun, satir = ya.montaj_izgarasi(ya.HAKEM_ORNEK_TAVANI, dikey=False)

    assert sutun * satir >= ya.HAKEM_ORNEK_TAVANI
    assert sutun <= 4, f"{sutun} sutun cok genis, hakem okuyamaz"


def test_uzun_istem_ORNEKLEMI_soyluyor(monkeypatch):
    """⚠️ Soylenmezse hakem 12 karelik montaji 45 sahnelik senaryoyla
    eslestirmeye calisir ve "gorseller anlatimi takip etmiyor" der — kusur
    videoda degil, bizim ona verdigimiz eslemede olur."""
    istem = _istemi_yakala(monkeypatch, sahne=45, bicim=ya.UZUN_BICIMI)

    assert "12-frame chronological montage" in istem
    assert "horizontal documentary" in istem
    assert "vertical Short" not in istem
    assert "45 scenes" in istem
    assert "were not sampled" in istem
    # ⚠️ Shorts'a ozel "iki kare ayni sahne" kurali uzun kipte YANLIS olurdu.
    assert "frames per scene" not in istem
    assert "deliberate layout" not in istem


def test_uzun_kipte_TEKRAR_gercek_kusur(monkeypatch):
    """Uzun kipte her kare AYRI sahne, yani ayni gorsel iki karede gercekten
    tekrardir — Shorts'taki "kasitli" istisnasi burada gecerli degil."""
    istem = _istemi_yakala(monkeypatch, sahne=45, bicim=ya.UZUN_BICIMI)

    assert "ARE a real repetition defect" in istem


def test_HAKEM_KARESINDEN_SAHNE_ornekleme_uyuyor():
    """⚠️ Iki cevrim ust uste: montaj sirasi -> gercek kare -> sahne.
    Atlanirsa `kareyi_onar` her seferinde YANLIS sahneyi degistirir."""
    ornekler = ya.hakem_kareleri(45, ya.UZUN_BICIMI)

    # Hakemin "kare 1" dedigi sey orneklemin ilki, yani gercek sahne 1.
    assert ya.hakem_karesinden_sahne(1, 1, ornekler) == ornekler[0] == 1
    # "kare 12" ise orneklemin sonuncusu — 12. sahne DEGIL, 45. sahne.
    assert ya.hakem_karesinden_sahne(12, 1, ornekler) == ornekler[-1] == 45
    assert ya.hakem_karesinden_sahne(12, 1, ornekler) != 12


def test_SHORTS_eslemesi_orneklemsiz_DEGISMEDI():
    assert [ya.hakem_karesinden_sahne(k) for k in (1, 2, 3, 4)] == [1, 1, 2, 2]


def test_montaj_cagrisi_KARE_sayisini_geciyor():
    """⚠️ Baglanti testi — fonksiyon dogru olsa bile cagri eksikse kusur surer.

    Sahne sayisi gecilseydi montaj her sahnenin TAM ORTASINDAN kare
    alirdi, yani iki gorselin EK YERINDEN.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "len(plan.scenes) * KARE_YUVASI" in kaynak
