"""Uretim artiklarinin silinmesi (DW-105).

⚠️ Bu modulun testleri agirlikli olarak NE SILINMEDIGINI kontrol ediyor.
Silme geri alinamaz; bir ara dosyanin sagkalmasi disk yer kaplar, bir kaydin
ya da teslim edilen videonun silinmesi kalicidir. Testlerin agirligi bu
asimetriyi yansitiyor.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import temizlik  # noqa: E402


@pytest.fixture
def depo(tmp_path, monkeypatch):
    """Gercek `storage/` yerine gecici bir agac — testler diske dokunuyor."""
    d = tmp_path / "storage"
    gorevler = d / "tasks"
    yerel = d / "local_videos"
    otomasyon = d / "youtube_automation"
    malzemeler = otomasyon / "commons_materials"
    incelemeler = otomasyon / "reviews"
    for yol in (gorevler, yerel, malzemeler, incelemeler):
        yol.mkdir(parents=True)

    monkeypatch.setattr(temizlik, "DEPO", d)
    monkeypatch.setattr(temizlik, "GOREVLER", gorevler)
    monkeypatch.setattr(temizlik, "YEREL_VIDEOLAR", yerel)
    monkeypatch.setattr(temizlik, "OTOMASYON", otomasyon)
    monkeypatch.setattr(temizlik, "MALZEMELER", malzemeler)
    monkeypatch.setattr(temizlik, "INCELEMELER", incelemeler)
    monkeypatch.setattr(temizlik, "DURUM", otomasyon / "state.json")
    monkeypatch.setattr(temizlik, "KILIT", otomasyon / "automation.lock")
    return d


def _gorev(depo, kimlik="gorev-1", *, url="https://youtube.com/shorts/abc"):
    g = depo / "tasks" / kimlik
    g.mkdir(parents=True, exist_ok=True)
    (g / "final-1.mp4").write_bytes(b"final")
    (g / "combined-1.mp4").write_bytes(b"combined")
    (g / "audio.mp3").write_bytes(b"audio")
    (g / "subtitle.srt").write_text("1\n", encoding="utf-8")
    (g / "script.json").write_text("{}", encoding="utf-8")
    durum = {
        "published": [
            {"url": url, "video_path": str(g / "final-1.mp4"), "task_id": kimlik}
        ]
    }
    (depo / "youtube_automation" / "state.json").write_text(
        json.dumps(durum), encoding="utf-8"
    )
    return g


# --- Silinmemesi gerekenler ----------------------------------------------


def test_nihai_video_ara_dosya_sayilmiyor(depo):
    """`final-1.mp4` TESLIM EDILEN URUN.

    Ara dosya temizligi ona hicbir kosulda dokunmamali — silinmesi ayri ve
    acik bir karar (`--videolar`), ve yalnizca kanit varken.
    """
    gorev = _gorev(depo)

    temizlik.uygula(temizlik.ara_dosyalar())

    assert (gorev / "final-1.mp4").exists()


def test_atif_kaydi_korunuyor(depo):
    """credits.json CC BY icin hukuki dayanak — gorsel degil KAYIT."""
    kosum = depo / "youtube_automation" / "commons_materials" / "2026-08-08-10"
    kosum.mkdir(parents=True)
    (kosum / "credits.json").write_text("[]", encoding="utf-8")
    (kosum / "scene-01.jpg").write_bytes(b"jpg")

    temizlik.uygula(temizlik.ara_dosyalar())

    assert (kosum / "credits.json").exists()
    assert not (kosum / "scene-01.jpg").exists()


def test_durum_dosyasi_korunuyor(depo):
    """state.json kaybi tekrar ureti ve kanca cesitliligini birden bozar."""
    _gorev(depo)

    temizlik.uygula(temizlik.ara_dosyalar())

    assert (depo / "youtube_automation" / "state.json").exists()


def test_su_an_uretilen_kosum_korunuyor(depo):
    """Yarim kalmis bir kosumun dosyalarini silmek uretimi bozar."""
    gorev = _gorev(depo, "aktif")

    temizlik.uygula(temizlik.ara_dosyalar(koru={"aktif"}))

    assert (gorev / "combined-1.mp4").exists()


# --- Silinmesi gerekenler ------------------------------------------------


def test_ara_surum_ve_sahne_kaynaklari_siliniyor(depo):
    """Olculdu (2026-08-08): 822 MB'in tamami bu uc kumede."""
    gorev = _gorev(depo)
    (depo / "local_videos" / "cli-material-x.jpg").write_bytes(b"jpg")
    (depo / "local_videos" / "cli-material-x.jpg.mp4").write_bytes(b"mp4")
    (depo / "youtube_automation" / "reviews" / "montaj.jpg").write_bytes(b"jpg")

    temizlik.uygula(temizlik.ara_dosyalar())

    assert not (gorev / "combined-1.mp4").exists()
    assert not (gorev / "audio.mp3").exists()
    assert not any((depo / "local_videos").iterdir())
    assert not any((depo / "youtube_automation" / "reviews").iterdir())


def test_bosalan_bayt_raporlaniyor(depo):
    (depo / "local_videos" / "a.jpg").write_bytes(b"x" * 1000)

    assert temizlik.uygula(temizlik.ara_dosyalar()) == 1000


# --- Yayinlanmis video kopyasi -------------------------------------------


def test_yayinlanmis_video_silinebiliyor(depo):
    gorev = _gorev(depo, url="https://youtube.com/shorts/abc")

    assert temizlik.yayinlanmis_videolar() == [gorev / "final-1.mp4"]


def test_url_yoksa_video_kaliyor(depo):
    """⚠️ Kapali-hata: yuklendigine dair KANIT yoksa silinmez.

    "Muhtemelen yuklenmistir" diye silmek, geri getirilemeyecek tek seyi
    geri getirilemez bicimde silmek olurdu.
    """
    _gorev(depo, url="")

    assert temizlik.yayinlanmis_videolar() == []


def test_durum_dosyasi_yoksa_video_kaliyor(depo):
    (depo / "tasks" / "g").mkdir()
    (depo / "tasks" / "g" / "final-1.mp4").write_bytes(b"final")

    assert temizlik.yayinlanmis_videolar() == []


def test_depo_disindaki_yol_reddediliyor(depo, tmp_path):
    """state.json bozulsa bile depo disina cikilmamali."""
    disarida = tmp_path / "ev" / "onemli.mp4"
    disarida.parent.mkdir(parents=True)
    disarida.write_bytes(b"onemli")
    (depo / "youtube_automation" / "state.json").write_text(
        json.dumps({"published": [{"url": "https://x", "video_path": str(disarida)}]}),
        encoding="utf-8",
    )

    assert temizlik.yayinlanmis_videolar() == []
    assert disarida.exists()


def test_depo_disi_silme_hata_veriyor(depo, tmp_path):
    """`uygula` son savunma — hesaplama hatasi buraya kadar gelirse durur."""
    disarida = tmp_path / "ev" / "onemli.mp4"
    disarida.parent.mkdir(parents=True)
    disarida.write_bytes(b"onemli")

    with pytest.raises(temizlik.TemizlikHatasi, match="depo disi"):
        temizlik.uygula(temizlik.Plan(dosyalar=[disarida]))

    assert disarida.exists()


# --- Kosum sonrasi kanca -------------------------------------------------


def test_kosum_sonrasi_nihai_videoya_dokunmuyor(depo):
    """Otomatik yol yalnizca ara dosyalari alir — video kararini vermez."""
    gorev = _gorev(depo, "g1")

    temizlik.kosum_sonrasi_temizle("g1")

    assert (gorev / "final-1.mp4").exists()
    assert (gorev / "combined-1.mp4").exists(), "aktif kosum korunmali"


def test_kosum_sonrasi_onceki_kosumlari_temizliyor(depo):
    """Su anki kosum korunuyor, ONCEKILER gidiyor — diskte tek kosumluk artik."""
    eski = _gorev(depo, "eski")
    yeni = _gorev(depo, "yeni")

    temizlik.kosum_sonrasi_temizle("yeni")

    assert not (eski / "combined-1.mp4").exists(), "onceki kosum temizlenmeli"
    assert (yeni / "combined-1.mp4").exists(), "aktif kosum korunmali"
    assert (eski / "final-1.mp4").exists(), "video hicbir kosulda burada silinmez"


def test_kosum_sonrasi_malzeme_klasorunu_de_koruyor(depo):
    """Gorev kimligi ve kosum adi FARKLI — ikisi de korunmali.

    Gorev dizini `<uuid>`, malzeme dizini `<slot>-attempt-1`. Yalnizca biri
    gecilirse digerinin gorselleri montaja bakmadan silinir.
    """
    malzeme = depo / "youtube_automation" / "commons_materials" / "2026-08-08-18-attempt-1"
    malzeme.mkdir(parents=True)
    (malzeme / "scene-01.jpg").write_bytes(b"jpg")

    temizlik.kosum_sonrasi_temizle("uuid-1", "2026-08-08-18-attempt-1")

    assert (malzeme / "scene-01.jpg").exists()


def test_bozuk_durum_dosyasi_sessizce_gecilmiyor(depo):
    """Okunamayan state.json, "kayit yok" demek DEGIL — hata verilmeli."""
    (depo / "youtube_automation" / "state.json").write_text("{bozuk", encoding="utf-8")

    with pytest.raises(temizlik.TemizlikHatasi, match="okunamadi"):
        temizlik.yayinlanmis_videolar()
