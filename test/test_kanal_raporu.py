"""Kanal analitigi — yukleme yolunu BOZMADAN okumali.

⚠️ NEDEN AYRI TOKEN. Analitik kapsamini `youtube_upload.SCOPES`e eklemek en
kolay yoldu ama tehlikeliydi: `get_authenticated_service` kapsam yetersizse
YENI BIR ONAY EKRANI aciyor (`flow.run_local_server`). Uretim koşumu arka
planda calisiyor, yani ilk yuklemede tarayici bekleyip suresiz kilitlenirdi
ve bunu ancak koşum olunce fark ederdik.

⚠️ NEDEN VAR. Kanalda 11 video, ~2.200 izlenme ve 1 abone; biri 709, digeri
5 izlenmis ve sebebi bilinmiyor. Hat bugune kadar hakem skorunu optimize
etti — "gorsel cumleye uyuyor mu" sorusunu. "Insan izliyor mu" sorusu hic
olculmedi.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kanal_rapor as kr  # noqa: E402
import youtube_upload as yu  # noqa: E402


def test_yukleme_kapsami_DEGISMEDI():
    """⚠️ Asil koruma: yukleme token'i analitik yuzunden gecersizlesmemeli."""
    assert "https://www.googleapis.com/auth/yt-analytics.readonly" not in yu.SCOPES
    assert set(yu.SCOPES) == {
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    }


def test_token_dosyalari_AYRI():
    """Ayni dosyaya yazsalardi biri digerinin kapsamini ezerdi."""
    assert kr.TOKEN_FILE != yu.TOKEN_FILE


def test_analitik_kapsami_okuma_ile_sinirli():
    """Rapor komutu hicbir sey degistirmemeli — yazma kapsami istenmiyor."""
    assert all(kapsam.endswith("readonly") for kapsam in kr.SCOPES), kr.SCOPES


def test_yetkisiz_kipte_BEKLEMIYOR(monkeypatch, tmp_path):
    """⚠️ Etkilesimsiz cagri onay ekrani acmamali, ACIK HATA vermeli.

    Arka planda calisan bir cagri `run_local_server`da suresiz beklerdi.
    """
    monkeypatch.setattr(kr, "TOKEN_FILE", str(tmp_path / "yok.json"))

    def acilmamali(*_a, **_k):
        raise AssertionError("etkilesimsiz kipte onay ekrani ACILMAMALI")

    monkeypatch.setattr(kr.InstalledAppFlow, "from_client_secrets_file", acilmamali)

    with pytest.raises(RuntimeError) as hata:
        kr.yetkilendir(etkilesimli=False)

    assert "--yetkilendir" in str(hata.value), "mesaj NE YAPILACAGINI soylemeli"


def test_rapor_kirilimlari_dolduruyor(monkeypatch):
    """Analitik cevabi rapor sozlugune dogru cevriliyor mu."""

    class _Sorgu:
        def __init__(self, yanit):
            self._yanit = yanit

        def execute(self):
            return self._yanit

    kanal_yaniti = {
        "columnHeaders": [{"name": "views"}, {"name": "subscribersGained"}],
        "rows": [[2186, 1]],
    }
    video_yaniti = {
        "columnHeaders": [
            {"name": "video"},
            {"name": "views"},
            {"name": "averageViewPercentage"},
        ],
        "rows": [["abc123", 709, 41.2], ["def456", 5, 12.0]],
    }
    trafik_yaniti = {"rows": [["SHORTS", 2100], ["YT_SEARCH", 86]]}
    yanitlar = iter([kanal_yaniti, video_yaniti, trafik_yaniti])

    class _Raporlar:
        def query(self, **_k):
            return _Sorgu(next(yanitlar))

    class _Analytics:
        def reports(self):
            return _Raporlar()

    class _Videolar:
        def list(self, **_k):
            return _Sorgu(
                {
                    "items": [
                        {"id": "abc123", "snippet": {"title": "Mehmed II"}},
                        {"id": "def456", "snippet": {"title": "Jacopo de' Pazzi"}},
                    ]
                }
            )

    class _YouTube:
        def videos(self):
            return _Videolar()

    monkeypatch.setattr(
        kr, "build", lambda ad, _s, credentials=None: _Analytics() if ad.endswith("Analytics") else _YouTube()
    )

    veri = kr.rapor(gun=28, creds=object())

    assert veri["kanal"]["views"] == 2186
    assert veri["kanal"]["subscribersGained"] == 1
    assert veri["videolar"][0]["baslik"] == "Mehmed II"
    assert veri["videolar"][0]["averageViewPercentage"] == 41.2
    assert veri["videolar"][1]["baslik"] == "Jacopo de' Pazzi"
    assert veri["trafik"][0] == {"kaynak": "SHORTS", "izlenme": 2100}


def test_tutunma_olcumu_isteniyor():
    """⚠️ Izlenme dagitimin SONUCU, tutunma SEBEBI. Sorgudan dusmemeli."""
    assert "averageViewPercentage" in kr.VIDEO_OLCUMLERI
    assert "subscribersGained" in kr.VIDEO_OLCUMLERI
