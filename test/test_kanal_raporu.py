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
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kanal_rapor as kr  # noqa: E402
import youtube_upload as yu  # noqa: E402

TMP = tempfile.mkdtemp(prefix="kanal-rapor-test-")


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


# --- Telefondan onay ------------------------------------------------------


def test_telefon_akisi_PKCE_dogrulayicisini_saklıyor(monkeypatch, tmp_path):
    """⚠️ Iki adim AYRI SURECLERDE calisiyor.

    `code_verifier` ilk adimda uretiliyor; diske yazilmazsa ikinci adim
    jetonu alamaz. Telefon akisinin tek kirilgan noktasi bu.
    """
    durum_dosyasi = tmp_path / "durum.json"
    monkeypatch.setattr(kr, "AKIS_DURUM_FILE", str(durum_dosyasi))

    class _Akis:
        redirect_uri = None
        code_verifier = "gizli-dogrulayici"

        def authorization_url(self, **_k):
            return "https://accounts.google.com/o/oauth2/auth?x=1", "durum-abc"

    monkeypatch.setattr(
        kr.InstalledAppFlow, "from_client_secrets_file", classmethod(lambda cls, *a, **k: _Akis())
    )

    baglanti = kr.telefon_baglantisi()

    assert baglanti.startswith("https://accounts.google.com/")
    import json as _json

    kayit = _json.loads(durum_dosyasi.read_text(encoding="utf-8"))
    assert kayit["code_verifier"] == "gizli-dogrulayici"
    assert kayit["state"] == "durum-abc"
    assert kayit["redirect_uri"] == kr.TELEFON_REDIRECT
    # Icinde PKCE dogrulayicisi var: baskasi okuyamamali.
    assert oct(durum_dosyasi.stat().st_mode)[-3:] == "600"


def test_tamamla_durum_yoksa_ACIK_hata(monkeypatch, tmp_path):
    monkeypatch.setattr(kr, "AKIS_DURUM_FILE", str(tmp_path / "yok.json"))

    with pytest.raises(RuntimeError) as hata:
        kr.telefon_tamamla("http://localhost:8765/?code=x")

    assert "--yetkilendir-telefon" in str(hata.value)


def test_onceki_izinler_jetona_EKLENMIYOR():
    """⚠️ Olculdu (2026-08-14) ve canli olarak yakalandi.

    `include_granted_scopes="true"` acikken Google, ayni istemciye daha
    once verilmis izinleri de jetona ekledi: donen jeton `youtube.upload`
    ve `youtube.force-ssl` tasiyordu — video silip duzenleyebilen bir
    yetki, "rapor okuma" komutunun icinde.

    ⚠️ Daha sinsisi: `credentials.scopes` yalnizca ISTENEN iki readonly
    kapsami gosteriyordu. Gercek kapsam ancak Google'in `tokeninfo` ucuna
    sorulunca goruldu — yani yerel nesneye bakarak dogrulanamiyor.
    """
    yakalanan: dict = {}

    class _Akis:
        redirect_uri = None
        code_verifier = "v"

        def authorization_url(self, **kwargs):
            yakalanan.update(kwargs)
            return "https://accounts.google.com/o/oauth2/auth", "durum"

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(kr, "AKIS_DURUM_FILE", str(Path(TMP) / "durum.json"))
        monkeypatch.setattr(
            kr.InstalledAppFlow,
            "from_client_secrets_file",
            classmethod(lambda cls, *a, **k: _Akis()),
        )
        kr.telefon_baglantisi()
    finally:
        monkeypatch.undo()

    # ⚠️ Davranis kontrolu, metin degil: yorumda gecen bir sozcuk testi
    # yanlis yerden gecirir/dusurur.
    assert "include_granted_scopes" not in yakalanan, yakalanan
    assert yakalanan.get("access_type") == "offline", "yenileme jetonu sart"


def test_telefon_redirect_localhost():
    """⚠️ Desktop istemcide yalnizca localhost/127.0.0.1 kabul ediliyor.

    LAN adresi yazmak (telefonun Mac'e ulasabilmesi icin) cazip ama Google
    onu reddeder; bu yuzden donus adresini KOPYALAMA yolu secildi.
    """
    assert kr.TELEFON_REDIRECT.startswith("http://localhost")


def test_tutunma_olcumu_isteniyor():
    """⚠️ Izlenme dagitimin SONUCU, tutunma SEBEBI. Sorgudan dusmemeli."""
    assert "averageViewPercentage" in kr.VIDEO_OLCUMLERI
    assert "subscribersGained" in kr.VIDEO_OLCUMLERI
