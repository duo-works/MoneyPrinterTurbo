"""Her yuva kendi suresini alir — gorsel, anlattigi cumleyle ayni anda.

⚠️ NEDEN VAR — olculdu (2026-08-18, Cemal Pasha, YAYINLANMIS video, gorsel 75).
`klip_suresi` sesi kare sayisina ESIT boluyordu. Cumleler esit degilse gorsel,
anlattigi cumleden kayiyor ve kayma video boyunca birikiyor:

    sahne   gorsel ekranda   cumlesi soyleniyor   kayma
    s2       6,4-12,8         7,9-16,3            cumle 3,5 sn tasiyor
    s3      12,8-19,2        16,6-24,2            gorsel 3,8 sn ONCE
    s4      19,2-25,6        24,5-27,4            gorsel 5,3 sn ONCE

Kelime sayilari [23, 25, 24, 7, 7, 19].

`ANLATIM_DENGESI` kapisi (#49) kaymayi SINIRLIYOR; buradaki degisiklik
KAYNAGINI kaldiriyor. Ikisi birlikte calisiyor.

⚠️ UC TUZAK — ucu de bu deponun daha once yandigi siniftan ve her biri ayri
sinaniyor:

  1. `combine_videos` klipleri `max_clip_duration`a gore YENIDEN KIRPIYOR
     (`video.py`, `if clip.duration > max_clip_duration`). Skaler, listenin
     AZAMISI olmali; ortalama verilseydi uzun yuvalar sessizce kesilirdi.
  2. Toplam sure sesin ALTINA duserse MPT acigi bastan bir klibi TEKRAR
     ederek kapatiyor ve video 1. sahnenin tekrariyla bitiyor
     (`klip_suresi` docstring'inde olculmus gerileme).
  3. Zoom Δ'si sureyle olcekleniyordu (`clip_duration * 0.03`), yani farkli
     sureli klipler farkli olcekte bitiyor ve sahne sinirinda sicrama
     olusuyordu — donusumlu kipin kapatmak icin var oldugu kusur.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402
from app.services import video as vd  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")

# Cemal Pasha'nin GERCEK sahne kelime sayilari.
CEMAL = [23, 25, 24, 7, 7, 19]


def _plan(*kelime_sayilari: int) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="capa",
        title="baslik",
        script=" ".join(["kelime"] * sum(kelime_sayilari)),
        scenes=[
            {"narration": " ".join(["kelime"] * n), "search_term": "t"}
            for n in kelime_sayilari
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


# --- Orantililik ------------------------------------------------------------


def test_sureler_KELIME_SAYISIYLA_orantili():
    sureler = ya.klip_sureleri(37.63, _plan(*CEMAL))

    # Sahne basina iki yuva; sahnenin payi iki yuvanin toplami.
    sahne_paylari = [sureler[i] + sureler[i + 1] for i in range(0, len(sureler), 2)]
    en_uzun, en_kisa = max(sahne_paylari), min(sahne_paylari)

    # Kelime orani 25/7 = 3,57; sure orani da ona yakin olmali.
    assert 3.0 < en_uzun / en_kisa < 4.0, sahne_paylari


def test_ESIT_anlatimda_ESIT_sure():
    """⚠️ SON YUVA HARIC — `KLIP_PAYI` orada toplaniyor, gerekce asagida."""
    sureler = ya.klip_sureleri(40.0, _plan(20, 20, 20, 20))

    assert len(set(sureler[:-1])) == 1, sureler


def test_sahnenin_IKI_YUVASI_esit():
    """Iki yuva cogu zaman ayni goruntu ([A,A]) ya da ayni yapistirmanin iki
    yarisi; ayri surelerin anlatimda karsiligi yok.

    ⚠️ SON SAHNE haric: `KLIP_PAYI` artigi son yuvaya ekleniyor.
    """
    sureler = ya.klip_sureleri(37.63, _plan(*CEMAL))

    for i in range(0, len(sureler) - 2, 2):
        assert sureler[i] == sureler[i + 1]


# --- Pay SONA toplaniyor ----------------------------------------------------
#
# ⚠️ Bu bir DAVRANIS KARARI, test duzeltmesi degil. Ilk surumde `KLIP_PAYI`
# butun sahnelere dagitiliyordu ve %2'lik uzama video boyunca BIRIKIYORDU:
# 30. saniyede %2 = 0,6 sn. Olculdu (Cemal Pasha, gercek altyazi zamanlari):
#
#     esit sure          en buyuk kayma 4,40 sn   <- yayinlanan videonun hali
#     pay dagitilmis     en buyuk kayma 1,65 sn
#     pay sona toplanmis en buyuk kayma 1,10 sn


def test_PAY_son_yuvada():
    sureler = ya.klip_sureleri(40.0, _plan(20, 20, 20, 20))

    assert sureler[-1] > sureler[0], "pay son yuvaya eklenmemis"


def test_ILK_n_eksi_1_klip_sesten_KISA():
    """⚠️ `KLIP_PAYI`nin IKINCI kosulu: ilk n-1 klibin toplami sesi GECERSE
    dongu sure dolunca kirilir ve SON SAHNE videoya hic girmez."""
    ses = 37.63
    sureler = ya.klip_sureleri(ses, _plan(*CEMAL))

    assert sum(sureler[:-1]) <= ses, (
        f"ilk n-1 klip {sum(sureler[:-1]):.2f} sn, ses {ses} sn — son sahne dusebilir"
    )


def test_yuva_sayisi_KARE_sayisina_esit():
    sureler = ya.klip_sureleri(37.63, _plan(*CEMAL))

    assert len(sureler) == len(CEMAL) * ya.KARE_YUVASI


# --- Tuzak 2: cycle-tekrari ------------------------------------------------


def test_TOPLAM_sesten_kisa_DEGIL():
    """⚠️ Nobetci: toplam sesin altina duserse MPT bastan bir klibi TEKRAR
    ediyor ve video 1. sahnenin tekrariyla bitiyor."""
    for ses in (20.0, 37.63, 50.8, 120.0):
        sureler = ya.klip_sureleri(ses, _plan(*CEMAL))

        assert sum(sureler) >= ses * ya.KLIP_PAYI - 0.2, (
            f"ses {ses}: toplam {sum(sureler):.2f} < {ses * ya.KLIP_PAYI:.2f}"
        )


def test_COK_dengesiz_planda_bile_toplam_korunuyor():
    """⚠️ Taban (`ASGARI_YUVA_SURESI`) yalnizca YUKARI calisir, yani toplami
    kucultemez. Yumusak kapi asildiginda plan cok dengesiz gelebilir."""
    sureler = ya.klip_sureleri(40.0, _plan(60, 2, 2, 2))

    assert sum(sureler) >= 40.0 * ya.KLIP_PAYI - 0.2


def test_asgari_yuva_suresi_UYGULANIYOR():
    sureler = ya.klip_sureleri(40.0, _plan(100, 1))

    assert min(sureler) >= ya.ASGARI_YUVA_SURESI


# --- Geri dusme -------------------------------------------------------------


def test_ANLATIM_YOKSA_esit_sureye_donuyor():
    """Orantilamak icin bilgi yok; duz bolusum bugunku davranis."""
    plan = _plan(10, 10)
    for sahne in plan.scenes:
        sahne["narration"] = ""

    sureler = ya.klip_sureleri(40.0, plan)

    assert len(set(sureler)) == 1
    assert len(sureler) == 2 * ya.KARE_YUVASI


def test_SES_OLCULEMEZSE_kelimeden_tahmin():
    """⚠️ `anlatim_suresi` agdan cekiyor ve hatayi yutup 0.0 donuyor."""
    sureler = ya.klip_sureleri(0.0, _plan(*CEMAL))

    assert all(s > 0 for s in sureler)
    assert sum(sureler) > 20, sureler


# --- Tuzak 1: combine_videos yeniden kirpiyor -------------------------------


def test_skaler_LISTENIN_AZAMISI_olarak_geciyor():
    """⚠️ `combine_videos` klipleri `--video-clip-duration`a gore kirpiyor.
    Ortalama verilseydi uzun yuvalar sessizce kesilirdi."""
    govde = KAYNAK[KAYNAK.index("    yuva_sureleri = klip_sureleri(") :][:1200]

    assert "klip = max(yuva_sureleri)" in govde


def test_uzunluk_UYUSMAZSA_liste_KULLANILMIYOR():
    """⚠️ Yanlis hizalanmis sureler, esit surelerden KOTUDUR: kayma o zaman
    rastgele olur ve teshis edilemez."""
    govde = KAYNAK[KAYNAK.index("    yuva_sureleri = klip_sureleri(") :][:1200]

    assert "if len(yuva_sureleri) != len(material_files):" in govde
    assert "yuva_sureleri = []" in govde


# --- Tuzak 3: zoom Δ ---------------------------------------------------------


def test_DONUSUMLU_zoomda_delta_SUREDEN_BAGIMSIZ():
    """⚠️ Δ sureyle olcekleniyorsa farkli sureli klipler farkli olcekte biter
    ve sahne sinirinda sicrama olusur."""
    kaynak = Path(vd.__file__).read_text(encoding="utf-8")

    assert "DONUSUMLU_ZOOM_ORANI" in kaynak
    assert "if donusumlu_zoom" in kaynak[kaynak.index("buyume = ") : kaynak.index("buyume = ") + 200]


def test_DUZ_zoom_davranisi_DEGISMEDI():
    """⚠️ Webui ayni servisi kullaniyor; duz kipte oran eskisi gibi sureyle
    olcekleniyor."""
    kaynak = Path(vd.__file__).read_text(encoding="utf-8")

    assert "bu_klip_suresi * 0.03" in kaynak


# --- Zincir: cagiran ve cagrilan -------------------------------------------


def test_preprocess_LISTE_kabul_ediyor():
    assert vd._yuva_suresi([3.0, 4.0, 5.0], 0) == 3.0
    assert vd._yuva_suresi([3.0, 4.0, 5.0], 2) == 5.0


def test_liste_KISA_kalirsa_son_deger_tekrarlaniyor():
    """Eksik sure yuzunden uretimin durmasi, biraz kaymis bir kareden kotu."""
    assert vd._yuva_suresi([3.0, 4.0], 9) == 4.0


def test_SKALER_hala_calisiyor():
    """⚠️ Webui ve eski cagiranlar etkilenmemeli."""
    assert vd._yuva_suresi(4.0, 7) == 4.0


def test_BOS_liste_PATLAMIYOR():
    assert vd._yuva_suresi([], 0) > 0


def test_cli_bayragi_TANIMLI_ve_eslenmis():
    """⚠️ Zincirin kopabilecegi yer: bayrak tanimlanip eslemeye eklenmezse
    argparse onu alir ama `VideoParams`a HIC gecmez — CLI'da gorunur,
    videoda gorunmez (`test_zoom_yonu.py` ayni dersi kaydediyor)."""
    kaynak = (Path(vd.__file__).resolve().parent.parent.parent / "cli.py").read_text(
        encoding="utf-8"
    )

    assert '"--video-clip-durations"' in kaynak
    assert '"video_clip_durations"' in kaynak


def test_task_katmani_LISTEYI_geciriyor():
    kaynak = Path(vd.__file__).resolve().parent.joinpath("task.py").read_text(
        encoding="utf-8"
    )

    assert "params.video_clip_durations or params.video_clip_duration" in kaynak


def test_sema_alani_var():
    from app.models.schema import VideoParams

    assert VideoParams(video_subject="konu").video_clip_durations is None


def test_komut_yuva_surelerini_GECIRIYOR():
    assert '"--video-clip-durations",' in KAYNAK


def test_GERCEK_renderda_sureler_UYGULANIYOR(tmp_path):
    """⚠️ Kaynakta dize aramak KODUN CALISTIGINI KANITLAMAZ — bu deponun
    tekrar eden hata sinifi (`ee886ab`, `ACILIS_KARELERI`). Burada gorseller
    gercekten klibe cevriliyor ve klip sureleri ffprobe ile olculuyor.
    """
    import os
    import shutil

    from app.models.schema import MaterialInfo
    from app.utils import utils

    kaynak = Path(__file__).resolve().parent / "resources" / "1.png"
    if not kaynak.exists():
        import pytest

        pytest.skip("test gorseli yok")

    istenen = [4.12, 1.25, 3.41]
    yerel = utils.storage_dir("local_videos", create=True)
    hedef = os.path.join(yerel, "yuva-suresi-testi.png")
    shutil.copy2(kaynak, hedef)

    malzemeler = []
    for _ in istenen:
        m = MaterialInfo()
        m.url = os.path.basename(hedef)
        m.provider = "local"
        malzemeler.append(m)

    sonuc = vd.preprocess_video(
        malzemeler, clip_duration=istenen, zoom=True, donusumlu_zoom=True
    )

    assert len(sonuc) == len(istenen)
    # ⚠️ Ayni kaynak dosyadan uretiliyorlar; ayri cikti sart (#48).
    assert len({m.url for m in sonuc}) == len(istenen), "klipler birbirini ezmis"

    for beklenen, mat in zip(istenen, sonuc):
        cikti = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", mat.url],
            capture_output=True, text=True, check=True, timeout=60,
        )
        olculen = float(cikti.stdout.strip())
        # Tolerans kare hizindan: 30 fps'te bir kare 0,033 sn.
        assert abs(olculen - beklenen) < 0.15, (
            f"istenen {beklenen} sn, olculen {olculen:.2f} sn"
        )


def test_cli_ayristirici_BOS_listeyi_reddediyor():
    """Sessizce bos donen bir ayristirici, sureler hic uygulanmadan videoyu
    uretirdi ve kusur ancak bitmis videoda gorunurdu."""
    kok = Path(vd.__file__).resolve().parent.parent.parent
    sonuc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import cli; "
         "import argparse\n"
         "try:\n"
         "    cli._pozitif_ondalik_listesi(',,')\n"
         "except argparse.ArgumentTypeError:\n"
         "    print('RED')\n" % str(kok)],
        capture_output=True, text=True, timeout=120,
    )

    assert "RED" in sonuc.stdout, sonuc.stderr
