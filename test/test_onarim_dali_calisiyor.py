"""Onarim dali GERCEKTEN calisiyor — cagri yeri, mocklanmis fonksiyon degil.

⚠️ NEDEN VAR — olculdu (2026-08-14). `kareyi_onar` cagrisina `konu` diye var
olmayan bir degisken yazmistim. Fonksiyonun kendi birim testleri yesildi
(onlar fonksiyonu monkeypatch'liyor), baglanti testi de yesildi (o kaynak
metninde dize ariyor). Dal yalnizca hakem "reddet" dedikten SONRA
calistigi icin kusur ancak URETIMDE ortaya cikti: uc koşum sirayla video
render etti ve tam o satirda `NameError` ile coktu.

Bu test dalin kendisini yuruttuyor: `run_cycle` video reddine kadar
gotuuruluyor ve onarimin calistigi dogrulaniyor. Bir daha ayni sinif kusur
uretime kadar gidemez.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan() -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Roman dodecahedrons",
        visual_anchor="Roman Dodecahedron",
        title="baslik #Shorts",
        # ⚠️ Gercek uzunlukta: `refine_search_terms` yedek yola dusunce plani
        # yeniden dogruluyor ve kisa bir metin testi kendi kusuruyla dusurur.
        script=(
            "Roman dodecahedrons appear across the northwestern provinces and nobody "
            "agrees what they were for. Each one carries twelve pierced faces and a "
            "knob at every corner, cast in bronze with unusual care. Soldiers carried "
            "them, farmers buried them, and no ancient writer ever wrote their name "
            "down. Some were found in coin hoards, which suggests they were valuable "
            "enough to hide. Surveying instrument, knitting frame, calendar, gaming "
            "piece: every explanation fits a few examples and fails on the rest. More "
            "than a hundred survive today and the question remains open."
        ),
        scenes=[
            {
                "narration": f"sahne {sira}",
                "search_term": f"Roman Dodecahedron detay {sira}",
                "kaynak_dosya": f"eski-{sira}.jpg",
            }
            for sira in range(1, 9)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def _hat(monkeypatch, tmp_path):
    """Video reddine kadar giden en kisa gercek yol."""
    plan = _plan()
    video = tmp_path / "final-1.mp4"
    video.write_bytes(b"x")

    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "LOCK_FILE", tmp_path / "automation.lock")
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        ya, "load_state", lambda: {"published": [], "rejected": [], "completed_slots": []}
    )
    monkeypatch.setattr(ya, "save_state", lambda _s: None)
    monkeypatch.setattr(ya.notion_kuyrugu, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(ya, "generate_content_plan", lambda *_a, **_k: plan)
    # ⚠️ Bes ogeli: son oge `tam_dolan_sahne` telemetrisi (kac sahnede iki
    # AYRI arsiv gorseli bulundu). Taklit imzayi takip etmezse `run_cycle`
    # acilirken patlar — tam da bu dosyanin yakalamak icin var oldugu kusur.
    monkeypatch.setattr(
        ya, "run_generator", lambda p, a: ("gorev-1", video, tmp_path / "s.txt", [], 0)
    )
    monkeypatch.setattr(ya, "create_review_montage", lambda *_a, **_k: tmp_path / "m.jpg")
    # Gorsel skor 80'in USTUNDE: `should_abandon_topic` False doner, yani
    # akis onarim daline girer. Agir kusur yayini engelliyor.
    monkeypatch.setattr(
        ya,
        "review_video",
        lambda *_a, **_k: ya.QualityReview(
            False, 89, 88, ["Frame 6 shows the wrong object"],
            agir_kusurlar=["kare 6: konuyla ilgisiz modern goruntu"],
        ),
    )
    # Menude birden fazla kullanilmamis dosya: uc deneme boyunca onarim
    # calisabilsin (tek girdi olursa ikinci denemede menu tukenir ve akis
    # yedek yola duser — o zaman test onarimi degil yedegi olcer).
    monkeypatch.setattr(
        ya,
        "arsiv_envanteri",
        lambda _k, **_: [
            {"dosya": f"YENI-{i}.jpg", "gosterdigi": "dogru nesne", "tarih": "1900"}
            for i in range(1, 5)
        ],
    )
    secim = iter([f"YENI-{i}.jpg" for i in range(1, 5)])
    # ⚠️ `n` SAHNE numarasi, kare degil. Hakem "kare 6" diyor ve sahne
    # basina iki kare oldugu icin (`KARE_YUVASI`) bu SAHNE 3 demek.
    # 2026-08-14'e kadar burada 6 yaziyordu; kare duzeni degisince taklit
    # var olmayan bir sahneyi secmeye calisti, onarim hicbir seyi
    # degistirmedi ve akis sessizce yedek yola dustu.
    monkeypatch.setattr(
        ya,
        "_json_completion",
        lambda s, u: {"picks": [{"n": ya.kareden_sahneye(6), "source_file": next(secim)}]},
    )
    return plan


def test_onarim_dali_NameError_vermeden_calisiyor(monkeypatch, tmp_path, capsys):
    """⚠️ Asil kosul: uc uretim koşumunu olduren kusur tam da buydu."""
    plan = _hat(monkeypatch, tmp_path)

    sonuc = ya.run_cycle(kuyruktan=True, yedek_konu=True, dry_run=True)

    assert sonuc["status"] == "rejected"
    # "kare 6" -> sahne 3 -> dizide 2. sira.
    assert plan.scenes[ya.kareden_sahneye(6) - 1]["kaynak_dosya"].startswith(
        "YENI-"
    ), "bozuk karenin gorseli degismeliydi"
    # Uc denemenin ucunde de onarim calisti: dal her turda yuruttuluyor.
    assert capsys.readouterr().out.count("kare onarımı") == 3


def test_onarim_temiz_kareye_dokunmuyor(monkeypatch, tmp_path):
    plan = _hat(monkeypatch, tmp_path)

    ya.run_cycle(kuyruktan=True, yedek_konu=True, dry_run=True)

    assert plan.scenes[0]["kaynak_dosya"] == "eski-1.jpg"
