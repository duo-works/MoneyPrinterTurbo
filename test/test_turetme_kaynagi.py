"""Turetme, uzun videonun INDIRILMIS karelerini yeniden kullaniyor mu.

⚠️ NEDEN VAR — olculdu 2026-08-21. Turetme kareyi dosya ADIYLA yeniden
cozuyordu ve teslim yolu adin yarisini tutmuyor: yayinlanmis dokuz videonun
103 sahnesinde istenen dosyanin teslim orani **%48** (ayni 49, FARKLI 54).
Sonuc, turetilen Shorts'un hakemin ONAYLADIGI karelerle degil her koşumda
yeniden atilan bir zarla uretilmesiydi.

Olculen zincir: uzun videonun kareleri arasinda yakin-ikiz cift var ->
turetme ikisini de cagiriyor -> `_tekrar_mi` ikincisini dusuruyor -> sahne
arama yedegine dusuyor -> Nasrid su altyapisi anlatimina HACLI BIR CAN
KULESI geliyor. O koşum 45 aldi (esik 75).

Dosyayi yeniden kullanmak zincirin tamamini kaldiriyor: indirme yok, parmak
izi elemesi yok, arama yedegi yok.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import turetme  # noqa: E402
import youtube_automation as ya  # noqa: E402


def _kayit(ad: str = "alhambra", sahne: int = 12) -> dict:
    return {
        "bicim": "uzun",
        "status": "published",
        "turetme_kaynagi": ad,
        "sahneler": [{"sahne": n} for n in range(1, sahne + 1)],
    }


def _depo(kok: Path, ad: str = "alhambra", *, kareler: int = 12) -> Path:
    dizin = kok / ad
    dizin.mkdir(parents=True)
    for n in range(1, kareler + 1):
        (dizin / f"sahne-{n:02d}.jpg").write_bytes(f"kare{n}".encode())
    (dizin / turetme.KAYNAK_KUNYESI).write_text(
        json.dumps(
            [
                {"scene": n, "title": f"File:Dosya {n}.jpg"}
                for n in range(1, kareler + 1)
            ]
        ),
        encoding="utf-8",
    )
    return dizin


# ====================================================== okuma tarafi


def test_pencere_SAKLANMIS_dosyalari_veriyor(tmp_path):
    """⚠️ MUTASYON: `hazir_kareler`i hep None dondurmek bunu duser."""
    _depo(tmp_path)

    cikti = turetme.hazir_kareler(_kayit(), 1, tmp_path)

    assert cikti is not None
    assert [d.name for d, _ in cikti] == [f"sahne-{n:02d}.jpg" for n in range(7, 13)]
    assert [k["title"] for _, k in cikti] == [
        f"File:Dosya {n}.jpg" for n in range(7, 13)
    ]


def test_TEK_kare_eksikse_HIC_kullanilmiyor(tmp_path):
    """⚠️ MUTASYON: eksik kareyi atlayip devam etmek bunu duser.

    Yarim yeniden kullanim en kotu secenek: bazi kareler yayinlanmis
    videodan, bazilari yeniden atilan zardan gelir ve ciktida hangisinin
    nereden geldigi GORUNMEZ. Ya hepsi, ya hicbiri.
    """
    dizin = _depo(tmp_path)
    (dizin / "sahne-09.jpg").unlink()

    assert turetme.hazir_kareler(_kayit(), 1, tmp_path) is None
    # Eksigin OLMADIGI pencere etkilenmiyor.
    assert turetme.hazir_kareler(_kayit(), 0, tmp_path) is not None


@pytest.mark.parametrize("alan", ["", None])
def test_kayitta_kaynak_YOKSA_None(tmp_path, alan):
    """20 Ağu oncesi kayitlar bu alani tasimiyor — yedek yol calismali."""
    _depo(tmp_path)
    kayit = _kayit()
    kayit["turetme_kaynagi"] = alan

    assert turetme.hazir_kareler(kayit, 0, tmp_path) is None


def test_kunye_BOZUKSA_kareler_yine_kullaniliyor(tmp_path):
    """Atif duser ama video DOGRU olur; kunyesizlik yeniden kullanimi
    engellememeli."""
    dizin = _depo(tmp_path)
    (dizin / turetme.KAYNAK_KUNYESI).write_text("bu json degil", encoding="utf-8")

    cikti = turetme.hazir_kareler(_kayit(), 0, tmp_path)

    assert cikti is not None and len(cikti) == 6
    assert all(kunye == {} for _, kunye in cikti)


# ====================================================== yazma tarafi


def _plan(sahne: int = 8) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Alhambra Nasrid palaces",
        visual_anchor="Alhambra",
        title="baslik",
        script="metin",
        scenes=[
            {"narration": f"s{n}", "search_term": f"t{n}"} for n in range(1, sahne + 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def test_kareler_HAM_haliyle_saklaniyor(tmp_path, monkeypatch, capsys):
    """Saklanan sey `scene-NN.jpg` — formata uydurulmus kare DEGIL.

    Kaynak yatay, turetme dikey; uydurma islemi turetme kosumunda yeniden
    yapiliyor. Ham dosya her iki formati da besliyor.
    """
    monkeypatch.setattr(ya, "TURETME_KAYNAGI", tmp_path / "depo")
    malzeme = tmp_path / "malzeme"
    malzeme.mkdir()
    for n in range(1, 9):
        (malzeme / f"scene-{n:02d}.jpg").write_bytes(f"ham{n}".encode())
        (malzeme / f"dikey-{n:02d}.jpg").write_bytes(b"uydurulmus")

    ad = ya.turetme_kaynagini_yaz(_plan(), malzeme, [{"scene": 1, "title": "x"}])

    hedef = tmp_path / "depo" / ad
    assert sorted(p.name for p in hedef.glob("*.jpg")) == [
        f"sahne-{n:02d}.jpg" for n in range(1, 9)
    ]
    assert (hedef / "sahne-03.jpg").read_bytes() == b"ham3"
    assert (hedef / turetme.KAYNAK_KUNYESI).exists()
    assert "türetme kaynağı" in capsys.readouterr().out


def test_eksik_kare_YAYINI_bozmuyor(tmp_path, monkeypatch):
    """Saklama bir IYILESTIRME; dusmesi yayinlanmis videoyu bozmamali."""
    monkeypatch.setattr(ya, "TURETME_KAYNAGI", tmp_path / "depo")
    malzeme = tmp_path / "malzeme"
    malzeme.mkdir()
    (malzeme / "scene-01.jpg").write_bytes(b"tek")

    ad = ya.turetme_kaynagini_yaz(_plan(), malzeme, [])

    assert (tmp_path / "depo" / ad / "sahne-01.jpg").exists()


def test_SAKLAMA_budamayi_CAGIRIYOR(tmp_path, monkeypatch):
    """⚠️ MUTASYON: `turetme_kaynagini_yaz` icindeki `_turetme_kaynagini_buda()`
    cagrisini silmek bunu duser.

    ⚠️ NEDEN AYRI BIR TEST: budamanin KENDISINI olcen test
    (`test_depo_TAVANDA_budaniyor`) fonksiyonu DOGRUDAN cagiriyor, yani
    saklamanin onu kullandigini soylemiyor. Mutasyon calistirildi ve tam
    bu bosluktan kacti — bu oturumda ayni bosluk `TURETME_BICIMI`nde de
    yasandi. Depo, budanmazsa sinirsiz buyur.
    """
    kok = tmp_path / "depo"
    monkeypatch.setattr(ya, "TURETME_KAYNAGI", kok)
    monkeypatch.setattr(ya, "TURETME_KAYNAGI_TAVANI", 1)
    malzeme = tmp_path / "malzeme"
    malzeme.mkdir()
    (malzeme / "scene-01.jpg").write_bytes(b"ham")
    kok.mkdir()
    eski = kok / "cok-eski-video"
    eski.mkdir()
    (eski / "sahne-01.jpg").write_bytes(b"x")

    ya.turetme_kaynagini_yaz(_plan(1), malzeme, [])

    assert not eski.exists(), "saklama budamayi cagirmadi — depo sinirsiz buyur"


def test_depo_TAVANDA_budaniyor(tmp_path, monkeypatch):
    """⚠️ MUTASYON: budamayi kaldirmak bunu duser.

    Sinirsiz buyuyen hicbir dizin "gecici" degildir; ustelik bu dizin
    `temizlik.ara_dosyalar`in dort kokunun disinda, yani baska hicbir sey
    onu kucultmuyor.
    """
    kok = tmp_path / "depo"
    monkeypatch.setattr(ya, "TURETME_KAYNAGI", kok)
    monkeypatch.setattr(ya, "TURETME_KAYNAGI_TAVANI", 2)
    kok.mkdir()
    for i, ad in enumerate(("eski-1", "eski-2", "eski-3")):
        d = kok / ad
        d.mkdir()
        (d / "sahne-01.jpg").write_bytes(b"x")
        import os

        os.utime(d, (1000 + i, 1000 + i))

    ya._turetme_kaynagini_buda(tavan=2)

    assert sorted(p.name for p in kok.iterdir()) == ["eski-2", "eski-3"]


# ====================================================== BAGLANTI
#
# ⚠️ NEDEN AYRI: bu oturumda bir mutasyon tam bu bosluktan kacti. Sabitin
# DEGERINI olcen test, hattin onu KULLANDIGINI soylemiyor. Asagidakiler
# `run_cycle`i gercekten yurutup cagriyi yakaliyor.


def _yayin_hatti(monkeypatch, tmp_path, *, bicim):
    """`run_cycle`i YAYINA kadar goturur."""
    plan = _plan(6)
    video = tmp_path / "final-1.mp4"
    video.write_bytes(b"x")
    malzeme = tmp_path / "malzeme"
    malzeme.mkdir()
    for n in range(1, 7):
        (malzeme / f"scene-{n:02d}.jpg").write_bytes(f"ham{n}".encode())

    monkeypatch.setattr(ya, "TURETME_KAYNAGI", tmp_path / "depo")
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "LOCK_FILE", tmp_path / "automation.lock")
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path / "logs")
    # ⚠️ Durum REFERANSLA tutuluyor: `run_cycle` kaydi bu sozluge ekliyor.
    # `save_state` taklidini dinlemek kirilgandi — yayin kaydinin yazildigi
    # an ile son `save_state` cagrisi ayni olmak zorunda degil.
    durum: dict = {"published": [], "rejected": [], "completed_slots": []}
    monkeypatch.setattr(ya, "load_state", lambda: durum)
    monkeypatch.setattr(ya, "save_state", lambda _s: None)
    monkeypatch.setattr(ya.notion_kuyrugu, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(ya, "generate_content_plan", lambda *_a, **_k: plan)
    monkeypatch.setattr(
        ya,
        "run_generator",
        lambda _p, _a, **_k: ("gorev-1", video, tmp_path / "s.txt", [], 0, malzeme),
    )
    monkeypatch.setattr(
        ya, "create_review_montage", lambda *_a, **_k: tmp_path / "m.jpg"
    )
    monkeypatch.setattr(
        ya,
        "review_video",
        lambda *_a, **_k: ya.QualityReview(True, 92, 90, [], agir_kusurlar=[]),
    )
    monkeypatch.setattr(ya.temizlik, "kosum_sonrasi_temizle", lambda *_a: 0)
    return durum


def test_UZUN_yayin_kareleri_SAKLIYOR(monkeypatch, tmp_path):
    """⚠️ MUTASYON: `turetme_kaynagini_yaz` cagrisini kaldirmak bunu duser.

    Cagri olmadan depo hic olusmaz ve turetme sonsuza dek yedek yola —
    kareyi adiyla yeniden cozmeye — duser. Olculen teslim orani %48.
    """
    _yayin_hatti(monkeypatch, tmp_path, bicim=ya.UZUN_BICIMI)

    # ⚠️ Kayit DONEN degerden okunuyor: `dry_run` state'e yazmiyor
    # (`if not dry_run: state.setdefault("published", ...)`), ama kaydi
    # kurup donduruyor. Alanin varligini olcmek icin yayin gerekmiyor.
    kayit = ya.run_cycle(
        dry_run=True, bicim=ya.UZUN_BICIMI, konu_override="Alhambra Nasrid palaces"
    )

    assert kayit["status"] == "dry-run"
    ad = kayit["turetme_kaynagi"]
    assert ad, "kayitta turetme kaynagi yok — turetme kareleri bulamaz"
    hedef = tmp_path / "depo" / ad
    assert sorted(p.name for p in hedef.glob("*.jpg")) == [
        f"sahne-{n:02d}.jpg" for n in range(1, 7)
    ]


def test_SHORTS_yayini_SAKLAMIYOR(monkeypatch, tmp_path):
    """⚠️ MUTASYON: `if not bicim.dikey` kosulunu kaldirmak bunu duser.

    Turetmenin kaynagi UZUN video. Shorts'un karelerini saklamak depoyu
    gunde alti kez doldurup uzun videonunkini tavandan tasirdi — yani
    ozelligi sessizce kapatirdi.
    """
    _yayin_hatti(monkeypatch, tmp_path, bicim=ya.SHORTS_BICIMI)

    kayit = ya.run_cycle(
        dry_run=True, bicim=ya.SHORTS_BICIMI, kuyruktan=True, yedek_konu=True
    )

    assert kayit["turetme_kaynagi"] == ""
    assert not (tmp_path / "depo").exists()


def test_turet_dali_HAZIR_KARELERI_ureticiye_geciriyor(monkeypatch, tmp_path):
    """⚠️ MUTASYON: `hazir_kareler=hazir_kareler` argumanini dusurmek bunu
    duser — ve dususu SESSIZ olurdu: video yine uretilir, sadece kareleri
    kaynak videodan farkli olur.
    """
    _depo(tmp_path / "depo", "alhambra", kareler=12)
    kaynak_kayit = {
        "bicim": "uzun",
        "status": "published",
        "turetme_kaynagi": "alhambra",
        "topic": "Alhambra",
        "visual_anchor": "Alhambra",
        "title": "Alhambra",
        "script": "metin",
        "description": "aciklama",
        "tags": ["a", "b", "c"],
        "sahneler": [
            {
                "sahne": n,
                "terim": f"Alhambra detay {n}",
                "kaynak_dosya": f"d{n}.jpg",
                "kaynak_dosya_2": "",
                "gelen": f"File:d{n}.jpg",
                "anlatim": "Bir cumle burada duruyor. Ikinci cumle de var.",
            }
            for n in range(1, 13)
        ],
    }
    _yayin_hatti(monkeypatch, tmp_path, bicim=ya.SHORTS_BICIMI)
    monkeypatch.setattr(
        ya, "_json_completion", lambda *_a, **_k: {"title": "Alhambra #Shorts"}
    )

    gorulen: dict = {}

    def _uretici(_p, _a, **kw):
        gorulen.update(kw)
        return (
            "gorev-1",
            tmp_path / "final-1.mp4",
            tmp_path / "s.txt",
            [],
            0,
            tmp_path,
        )

    monkeypatch.setattr(ya, "run_generator", _uretici)

    ya.run_cycle(dry_run=True, turet=(kaynak_kayit, 0))

    hazir = gorulen.get("hazir_kareler")
    assert hazir is not None, "turetme kolu saklanmis kareleri ureticiye gecirmedi"
    assert [d.name for d, _ in hazir] == [f"sahne-{n:02d}.jpg" for n in range(1, 7)]


def test_kaynak_YOKKEN_turetme_SESSIZCE_devam_ETMIYOR(monkeypatch, tmp_path, capsys):
    """Yedek yol calisir ama GORUNUR olur.

    ⚠️ MUTASYON: uyari satirini silmek bunu duser. Kareyi adiyla yeniden
    cozmek olculen %48 teslim orani demek — yani cikan Shorts kaynak
    videodan gorsel olarak sapar. Bu bir kusur degil ama bilinmeden
    gecilmemeli.
    """
    kaynak_kayit = {
        "bicim": "uzun",
        "status": "published",
        "turetme_kaynagi": "",
        "topic": "Alhambra",
        "visual_anchor": "Alhambra",
        "title": "Alhambra",
        "script": "metin",
        "description": "aciklama",
        "tags": ["a", "b", "c"],
        "sahneler": [
            {
                "sahne": n,
                "terim": f"Alhambra detay {n}",
                "kaynak_dosya": f"d{n}.jpg",
                "kaynak_dosya_2": "",
                "gelen": f"File:d{n}.jpg",
                "anlatim": "Bir cumle burada duruyor. Ikinci cumle de var.",
            }
            for n in range(1, 13)
        ],
    }
    _yayin_hatti(monkeypatch, tmp_path, bicim=ya.SHORTS_BICIMI)
    monkeypatch.setattr(
        ya, "_json_completion", lambda *_a, **_k: {"title": "Alhambra #Shorts"}
    )

    ya.run_cycle(dry_run=True, turet=(kaynak_kayit, 0))

    assert "türetme kaynağı yok" in capsys.readouterr().out
