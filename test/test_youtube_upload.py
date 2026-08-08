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


KANAL = "UCtest0000000000000000"


class SahteKanallar:
    def __init__(self, kimlik=KANAL, ad="Test Kanal"):
        self.kimlik = kimlik
        self.ad = ad
        self.cagrildi = False

    def list(self, **_kwargs):
        self.cagrildi = True
        return self

    def execute(self):
        if self.kimlik is None:
            return {"items": []}
        return {"items": [{"id": self.kimlik, "snippet": {"title": self.ad}}]}


class SahteServis:
    def __init__(self, kanal_kimligi=KANAL):
        self.videolar = SahteVideolar()
        self.kanallar = SahteKanallar(kanal_kimligi)

    def videos(self):
        return self.videolar

    def channels(self):
        return self.kanallar


def _yukle(tmp_path, monkeypatch=None, servis=None, **kwargs):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")
    servis = servis or SahteServis()
    with (
        patch.object(youtube_upload, "get_authenticated_service", return_value=servis),
        patch.object(youtube_upload, "MediaFileUpload", lambda *a, **k: object()),
        patch.dict(os.environ, {youtube_upload.KANAL_ORTAM_ANAHTARI: KANAL}),
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


# --- Gorunurluk alanlari (DW-104) ----------------------------------------


def test_dil_alanlari_gonderiliyor(tmp_path):
    """⚠️ Ikisi de bostu. Dil belirtilmeyince YouTube basligi ve aciklamayi
    hangi dilde arayana eslestirecegini TAHMIN etmek zorunda kaliyor.

    Kanal Ingilizce uretiyor; `kanal.py` profilinde `varsayilan_dil="en"`
    yaziliydi ama MPT yukleyicisi bu bilgiyi hic gondermiyordu.
    """
    snippet = _yukle(tmp_path)["snippet"]

    assert snippet["defaultLanguage"] == "en"
    assert snippet["defaultAudioLanguage"] == "en", "konusmanin dili ayri alan"


def test_kategori_egitim(tmp_path):
    """Onceden "22" (People & Blogs) gidiyordu — vlog kumesi.

    Bu kanal belgesel tarzi tarih anlatiyor; 27 (Education) icerigin ne
    oldugunu dogru soyluyor.
    """
    assert _yukle(tmp_path)["snippet"]["categoryId"] == "27"


def test_dil_ve_kategori_cagirandan_gecilebilir(tmp_path):
    """Kanal ileride baska dile acilirsa varsayilan kilit olmamali."""
    govde = _yukle(tmp_path, language="tr", category_id="22")

    assert govde["snippet"]["defaultLanguage"] == "tr"
    assert govde["snippet"]["categoryId"] == "22"


# --- Kanal dogrulamasi (DW-104) ------------------------------------------


def _dogrula(servis, beklenen):
    """⚠️ `beklenen_kanal` YAMANIYOR, ortam degiskeni degil.

    Ortami temizlemek yetmiyordu: fonksiyon ortam bos olunca makinedeki
    config.toml'a dusuyor ve test, calistigi makinenin ayarina gore sonuc
    veriyordu — gercek kanal ayarlandigi anda "ayar yok" testi dustu.
    """
    with patch.object(youtube_upload, "beklenen_kanal", return_value=beklenen):
        return youtube_upload.kanali_dogrula(servis)


def test_readonly_kapsami_isteniyor():
    """`upload` kapsami tek basina `channels.list(mine=True)`i 403 yapiyor.

    Kapsam listesi daraltilirsa dogrulama calisma aninda patlar — testin
    kapsami kilitlemesi bu yuzden.
    """
    assert "https://www.googleapis.com/auth/youtube.readonly" in youtube_upload.SCOPES
    assert "https://www.googleapis.com/auth/youtube.upload" in youtube_upload.SCOPES


def test_yanlis_kanala_yukleme_engelleniyor(tmp_path):
    """Olculdu (2026-08-05): token paylasilan dosyaya yazilinca yanlis kanala
    baglandi ve video yanlis kanala gitti. O gun bunu yakalayan bir sey yoktu.
    """
    servis = SahteServis("UCbaskakanal000000000")

    with pytest.raises(youtube_upload.YanlisKanalHatasi, match="yanlis kanala bagli"):
        _dogrula(servis, KANAL)


def test_hedef_kanal_ayarsizsa_yukleme_yapilmiyor():
    """⚠️ Kapali-hata. "Ayar yoksa dogrulamayi atla" davranisi, korumayi tam da
    en cok gerekli oldugu anda (ilk kurulum, token tazelendi) kapatirdi.
    """
    servis = SahteServis()

    with pytest.raises(youtube_upload.YanlisKanalHatasi, match="ayarli degil"):
        _dogrula(servis, "")


def test_kanalsiz_hesap_yakalaniyor():
    """Google hesabi var ama kanali yok — `items` bos doner, IndexError degil
    anlasilir hata verilmeli."""
    servis = SahteServis(None)

    with pytest.raises(youtube_upload.YanlisKanalHatasi, match="kanali yok"):
        _dogrula(servis, KANAL)


def test_dogru_kanalda_gecis_var():
    servis = SahteServis()

    assert _dogrula(servis, KANAL) == (KANAL, "Test Kanal")


def test_dogrulama_yukleme_yoluna_bagli(tmp_path):
    """Baglanti testi — `kanali_dogrula` tek basina dogru olsa bile
    `upload_video` onu cagirmazsa koruma yok.

    Mutasyon dersi (DW-97): izole dogruluk yetmiyor.
    """
    servis = SahteServis()
    _yukle(tmp_path, servis=servis)

    assert servis.kanallar.cagrildi, "yuklemeden once kanal olculmeli"


def test_dogrulama_insert_ten_once_calisiyor(tmp_path):
    """Sira onemli: once yukleyip sonra dogrulamak videoyu yanlis kanala koyar."""
    servis = SahteServis("UCbaskakanal000000000")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")

    with (
        patch.object(youtube_upload, "get_authenticated_service", return_value=servis),
        patch.object(youtube_upload, "MediaFileUpload", lambda *a, **k: object()),
        patch.dict(os.environ, {youtube_upload.KANAL_ORTAM_ANAHTARI: KANAL}),
        pytest.raises(youtube_upload.YanlisKanalHatasi),
    ):
        youtube_upload.upload_video(str(video), "T", "A", ["history"], "private")

    assert servis.videolar.insert_cagrisi is None, "hicbir sey yuklenmemeli"


def test_ortam_degiskeni_config_i_geciyor(monkeypatch):
    """Zamanlanmis hat kanali ortamdan verebilmeli — config.toml tek kanala kilitli."""
    monkeypatch.setenv(youtube_upload.KANAL_ORTAM_ANAHTARI, "UCortam0000000000000")

    assert youtube_upload.beklenen_kanal() == "UCortam0000000000000"
