"""youtube_upload.py — beyan, gizlilik ve token korumalari.

Bu dosya DW-84 ile acildi: `youtube_upload.py`'nin hic testi yoktu ve icindeki
uc deger dogrudan YouTube'a giden beyanlar. Ag'a veya tarayiciya cikilmiyor.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_upload  # noqa: E402


class SahteYukleme:
    def __init__(self):
        self.adim = 0

    def next_chunk(self):
        self.adim += 1
        return None, {"id": "vid123"}


class SahteVideolar:
    def __init__(self):
        self.insert_cagrisi = None

    def insert(self, **kwargs):
        self.insert_cagrisi = kwargs
        return SahteYukleme()


class SahteServis:
    def __init__(self):
        self.videolar = SahteVideolar()

    def videos(self):
        return self.videolar


def _yukle(tmp_path, **kwargs):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")
    servis = SahteServis()
    with (
        patch.object(youtube_upload, "get_authenticated_service", return_value=servis),
        patch.object(youtube_upload, "MediaFileUpload", lambda *a, **k: object()),
    ):
        youtube_upload.upload_video(
            str(video),
            kwargs.pop("title", "Baslik"),
            kwargs.pop("description", "Aciklama"),
            kwargs.pop("tags", ["history"]),
            kwargs.pop("privacy_status", "private"),
            **kwargs,
        )
    return servis.videolar.insert_cagrisi["body"]


def test_sentetik_medya_beyani_gonderiliyor(tmp_path):
    """Bu hat videoyu LLM senaryosu + TTS ses ile uretiyor, yani icerik sentetik.

    Beyan eksikti (DW-84). YouTube gercekci sentetik/degistirilmis medya icin
    aciklama istiyor; gonderilmemesi uyum riski. Varsayilan True cunku bu hattin
    urettigi HER video sentetik.
    """
    govde = _yukle(tmp_path)

    assert govde["status"]["containsSyntheticMedia"] is True


def test_sentetik_olmayan_icerik_acikca_gecilebilir(tmp_path):
    """Istisna mumkun olmali ama acik bir karar olmali — sessiz varsayilan degil."""
    govde = _yukle(tmp_path, contains_synthetic_media=False)

    assert govde["status"]["containsSyntheticMedia"] is False


def test_gizlilik_cagirandan_geliyor(tmp_path):
    """`youtube_automation.py` privacy'yi acikca geciyor; o yol degismedi."""
    govde = _yukle(tmp_path, privacy_status="public")

    assert govde["status"]["privacyStatus"] == "public"


def test_cli_varsayilani_private():
    """Elle cagirmada varsayilan yayin olmamali.

    Varsayilan "public" idi. PRD'nin "v1'de OLMAYACAKLAR" listesinde "otomatik
    yayin karari" var; elle bir komutta bayragi unutmanin cezasi "yayinda"
    olmamali. Yon asimetrik: erken yayinlanan videoyu geri almak izlenme ve
    oneri sinyali kaybi, gec yayinlanani yayinlamak bir tik.
    """
    ayristirici_varsayilani = None
    with patch.object(sys, "argv", ["youtube_upload.py", "v.mp4", "--title", "T"]):
        with patch.object(youtube_upload, "upload_video") as sahte:
            youtube_upload.main()
            ayristirici_varsayilani = sahte.call_args[0][4]

    assert ayristirici_varsayilani == "private"


def test_token_dosyasi_yalnizca_sahibine_okunur(tmp_path, monkeypatch):
    """Icinde refresh token var — 0644 birakmak ssh anahtarini acikta birakmak gibi."""
    token = tmp_path / "youtube_token.json"
    monkeypatch.setattr(youtube_upload, "TOKEN_FILE", str(token))
    creds = MagicMock()
    creds.to_json.return_value = "{}"

    youtube_upload._token_yaz(creds)

    assert os.stat(token).st_mode & 0o777 == 0o600


def test_kapsam_eksikse_eski_token_kullanilmaz(tmp_path, monkeypatch):
    """`Credentials.valid` kapsam kontrol etmiyor — `has_scopes` ayri metot.

    SCOPES ileride genisletilirse (or. analytics icin readonly) diskteki eski
    token gecerli gorunmeye devam eder ve hata calisma aninda 403 olarak,
    cagri yerinde patlar.
    """
    token = tmp_path / "youtube_token.json"
    token.write_text("{}", encoding="utf-8")
    gizli = tmp_path / "client_secret.json"
    gizli.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(youtube_upload, "TOKEN_FILE", str(token))
    monkeypatch.setattr(youtube_upload, "CLIENT_SECRET_FILE", str(gizli))

    dar = MagicMock(valid=True, expired=False)
    dar.has_scopes.return_value = False
    yeni = MagicMock()
    yeni.to_json.return_value = "{}"
    akis = MagicMock()
    akis.run_local_server.return_value = yeni

    with (
        patch.object(youtube_upload.Credentials, "from_authorized_user_file", return_value=dar),
        patch.object(
            youtube_upload.InstalledAppFlow, "from_client_secrets_file", return_value=akis
        ),
        patch.object(youtube_upload, "build") as sahte_build,
    ):
        youtube_upload.get_authenticated_service()

    akis.run_local_server.assert_called_once()
    assert sahte_build.call_args[1]["credentials"] is yeni


def test_yenileme_basarisizsa_tarayici_akisina_dusulur(tmp_path, monkeypatch):
    """`RefreshError` yakalanmazsa zamanlanmis gorev en sik hatta oluyor.

    Onay ekrani "Testing" durumundayken refresh token 7 gunde doluyor, yani bu
    yol haftada bir geciliyor.
    """
    token = tmp_path / "youtube_token.json"
    token.write_text("{}", encoding="utf-8")
    gizli = tmp_path / "client_secret.json"
    gizli.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(youtube_upload, "TOKEN_FILE", str(token))
    monkeypatch.setattr(youtube_upload, "CLIENT_SECRET_FILE", str(gizli))

    bayat = MagicMock(valid=False, expired=True, refresh_token="abc")
    bayat.has_scopes.return_value = True
    bayat.refresh.side_effect = youtube_upload.RefreshError("iptal edilmis")

    yeni = MagicMock()
    yeni.to_json.return_value = '{"yeni": true}'
    akis = MagicMock()
    akis.run_local_server.return_value = yeni

    with (
        patch.object(youtube_upload.Credentials, "from_authorized_user_file", return_value=bayat),
        patch.object(
            youtube_upload.InstalledAppFlow, "from_client_secrets_file", return_value=akis
        ),
        patch.object(youtube_upload, "build"),
    ):
        youtube_upload.get_authenticated_service()

    akis.run_local_server.assert_called_once()
    assert token.read_text(encoding="utf-8") == '{"yeni": true}'


@pytest.mark.parametrize("alan", ["privacyStatus", "selfDeclaredMadeForKids", "containsSyntheticMedia"])
def test_status_alanlari_eksiksiz(tmp_path, alan):
    """Uc beyan da her yuklemede gonderilmeli — biri dusunce sessizce kayboluyor."""
    assert alan in _yukle(tmp_path)["status"]
