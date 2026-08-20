"""Kapak (thumbnail) uretimi — `kapak.py` ve yukleyiciye baglanmasi.

⚠️ Bu dosyanin cogu testi bir OLCUME dayaniyor, zevke degil: kapak
YouTube oneri akisinda ~210x118 piksele iniyor (1280x720'nin altida biri).
"Guzel gorunuyor" olcutu o boyutta anlamsiz; testler bu yuzden metnin
KAPLADIGI ALANI ve puntonun tabanini olcuyor.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kapak  # noqa: E402
import youtube_upload  # noqa: E402


@pytest.fixture
def kare(tmp_path):
    """1920x1080 duz bir kare — hattin urettigi olcunun aynisi."""
    yol = tmp_path / "kare.png"
    Image.new("RGB", (1920, 1080), (90, 80, 70)).save(yol)
    return yol


def test_kapak_YOUTUBE_olcusunde_ve_sinirin_altinda(kare, tmp_path):
    hedef = kapak.kapak_uret(kare, "340 waited here", tmp_path / "k.jpg")

    with Image.open(hedef) as im:
        assert im.size == (1280, 720)
        assert im.format == "JPEG"
    # YouTube siniri 2 MB; asilirsa `kapak_bas` kapagi sessizce atlar.
    assert os.path.getsize(hedef) < 2 * 1024 * 1024


def test_metin_blogu_YUKSEKLIK_BUTCESINI_asmiyor():
    """⚠️ MUTASYON: `YAZI_YUKSEKLIK_PAYI` kosulu `_punto_sec`ten kaldirilinca duser.

    Olculdu (2026-08-20): butce yokken "340 WAITED HERE" iki satira bolunup
    296 px kapliyor ve kapagin oznesinin — iskeletlerin — uzerine oturuyordu.
    Butce tek satira dusurup 150 px'e indiriyor.
    """
    butce = kapak.KAPAK_YUKSEKLIGI * kapak.YAZI_YUKSEKLIK_PAYI
    pay = int(kapak.KAPAK_GENISLIGI * kapak.KENAR_PAYI)

    for metin in (
        "340 WAITED HERE",
        "WHY DID THEY WAIT",
        "THE LAST DAY OF A ROMAN TOWN",
    ):
        font, satirlar = kapak._punto_sec(metin, kapak.KAPAK_GENISLIGI - 2 * pay)
        yukseklik = kapak._satir_yuksekligi(font.size) * len(satirlar)

        assert yukseklik <= butce, f"{metin!r}: {yukseklik} px > butce {butce}"


def test_kisa_yazi_TEK_SATIRDA_kaliyor():
    """Butcenin gorunur sonucu: kisa ibare bolunmuyor, buyuk basiliyor."""
    pay = int(kapak.KAPAK_GENISLIGI * kapak.KENAR_PAYI)

    font, satirlar = kapak._punto_sec(
        "340 WAITED HERE", kapak.KAPAK_GENISLIGI - 2 * pay
    )

    assert satirlar == ["340 WAITED HERE"]
    assert font.size >= 100, "kisa ibare kucuk olcekte okunacak kadar buyuk basilmali"


def test_hicbir_satir_KENAR_PAYINA_tasmiyor():
    pay = int(kapak.KAPAK_GENISLIGI * kapak.KENAR_PAYI)
    band = kapak.KAPAK_GENISLIGI - 2 * pay

    font, satirlar = kapak._punto_sec(
        "WHY DID HERCULANEUM'S LAST 340 PEOPLE WAIT", band
    )

    assert all(font.getlength(s) <= band for s in satirlar)


def test_punto_TABANIN_altina_inmiyor():
    """⚠️ Cok uzun metinde punto tabanda DURUR, sonsuza kadar kuculmez.

    Kucuk olcekte 58 px'in altı okunmuyor; cozum puntoyu ezmek degil metni
    kisaltmak (`yaziyi_kisalt` / plan modelinin `kapak_yazisi` alani).
    """
    pay = int(kapak.KAPAK_GENISLIGI * kapak.KENAR_PAYI)

    font, _ = kapak._punto_sec("WORD " * 60, kapak.KAPAK_GENISLIGI - 2 * pay)

    assert font.size >= kapak.EN_KUCUK_PUNTO


def test_kontur_ORAN_olarak_tasiniyor(kare, tmp_path):
    """⚠️ MUTASYON: konturu sabit piksele cevirmek bu testi dusurur.

    Altyazidaki oran 56 px puntoda 7 px = %12,5. Kapak puntosu otomatik
    kuculdugu icin MUTLAK deger tasinamaz: 58 px puntoda 7 px kontur harfi
    yutar, 132 px puntoda gorunmez kalir.
    """
    assert kapak.KONTUR_ORANI == pytest.approx(7 / 56)

    # Cizim yolu gercekten orani kullaniyor mu — `text` cagrisi yakalanir.
    cagrilar = []
    gercek = kapak.ImageDraw.Draw

    class Yakalayici:
        def __init__(self, im):
            self._ic = gercek(im)

        def text(self, *a, **k):
            cagrilar.append(k)
            return self._ic.text(*a, **k)

    with patch.object(kapak.ImageDraw, "Draw", Yakalayici):
        kapak.kapak_uret(kare, "340 waited here", tmp_path / "k.jpg")

    assert cagrilar, "hic metin cizilmedi"
    for k in cagrilar:
        beklenen = max(2, round(k["font"].size * kapak.KONTUR_ORANI))
        assert k["stroke_width"] == beklenen


def test_KUTU_YOK_beyaz_metin_siyah_kontur(kare, tmp_path):
    """DW-103 karari: altyazida kutu yok; kapak ayni gorsel dili kullaniyor."""
    cagrilar = []
    gercek = kapak.ImageDraw.Draw

    class Yakalayici:
        def __init__(self, im):
            self._ic = gercek(im)

        def text(self, *a, **k):
            cagrilar.append(k)
            return self._ic.text(*a, **k)

        def __getattr__(self, ad):
            # Kutu cizilseydi `rectangle`/`rounded_rectangle` buradan gecerdi.
            raise AssertionError(f"kapakta {ad!r} cizimi yok olmali (kutu yasagi)")

    with patch.object(kapak.ImageDraw, "Draw", Yakalayici):
        kapak.kapak_uret(kare, "340 waited here", tmp_path / "k.jpg")

    assert all(k["fill"] == (255, 255, 255) for k in cagrilar)
    assert all(k["stroke_fill"] == (0, 0, 0) for k in cagrilar)


def test_yazisiz_kapak_da_URETILIYOR(kare, tmp_path):
    """Yazisiz kapak, kapaksiz videodan iyidir — YouTube aksi halde rastgele
    bir kare seciyor."""
    hedef = kapak.kapak_uret(kare, "", tmp_path / "k.jpg")

    with Image.open(hedef) as im:
        assert im.size == (1280, 720)


def test_kirpma_EN_BOY_bozmuyor(tmp_path):
    """Kare 16:9 degilse ORTADAN kirpilir; sikistirilmaz."""
    kaynak = tmp_path / "kare.png"
    im = Image.new("RGB", (1000, 1000), (10, 10, 10))
    # Ortaya ayirt edici bir bant koyulur; sikistirma olsaydi oran degisirdi.
    for y in range(480, 520):
        for x in range(1000):
            im.putpixel((x, y), (250, 250, 250))
    im.save(kaynak)

    hedef = kapak.kapak_uret(kaynak, "", tmp_path / "k.jpg")

    with Image.open(hedef) as cikti:
        assert cikti.size == (1280, 720)
        # Bant hala DIKEY ORTADA: kirpma simetrik.
        orta = cikti.getpixel((640, 360))
        assert min(orta) > 200


def test_yaziyi_kisalt_kisa_basligi_DEGISTIRMIYOR():
    assert kapak.yaziyi_kisalt("Why Did They Wait?") == "Why Did They Wait?"


def test_yaziyi_kisalt_iki_noktali_baslikta_SIGAN_yariyi_seciyor():
    """⚠️ Uzun yariyi degil SIGAN yariyi secer — bkz. `yaziyi_kisalt`.

    Iki yon de olculuyor: soru yarisi sigiyorsa O secilir (merak kancasi),
    sigmiyorsa konu adina dusulur — kapak baglamsiz kalmaz.
    """
    baslik = "Köktürk: What Happened to Their Writing?"

    assert kapak.yaziyi_kisalt(baslik, en_cok=35) == "What Happened to Their Writing?"
    assert kapak.yaziyi_kisalt(baslik, en_cok=20) == "Köktürk"


def test_yaziyi_kisalt_KELIME_sinirinda_kesiyor():
    kisa = kapak.yaziyi_kisalt(
        "Why Did Herculaneum's Last 340 People Wait at the Shore?"
    )

    assert len(kisa) <= 42
    # Kelime ortasindan kesilmedi.
    assert "Why Did Herculaneum's Last 340 People Wait".startswith(kisa)
    assert not kisa.endswith(" ")


def test_font_BOLD_ve_depoda_var():
    assert kapak.KAPAK_FONTU.exists()
    assert "Bold" in kapak.KAPAK_FONTU.name


# --- yukleyiciye baglanma -------------------------------------------------


class SahteKapaklar:
    def __init__(self):
        self.cagri = None

    def set(self, **kwargs):
        self.cagri = kwargs
        return self

    def execute(self):
        return {"ok": True}


def test_kapak_bas_thumbnails_set_CAGIRIYOR(tmp_path):
    """⚠️ MUTASYON: `upload_video`dan `kapak_bas` cagrisini silmek bunu dusurmez —
    onu `test_upload_video_kapagi_BAGLIYOR` yakalar. Bu test cagrinin
    SEKLINI kilitliyor (`videoId` + `media_body`)."""
    kapak_dosyasi = tmp_path / "k.jpg"
    kapak_dosyasi.write_bytes(b"x" * 100)
    kapaklar = SahteKapaklar()

    class Servis:
        def thumbnails(self):
            return kapaklar

    with patch.object(youtube_upload, "MediaFileUpload", lambda *a, **k: "MEDYA"):
        sonuc = youtube_upload.kapak_bas(Servis(), "VID123", str(kapak_dosyasi))

    assert sonuc is True
    assert kapaklar.cagri == {"videoId": "VID123", "media_body": "MEDYA"}


def test_kapak_bas_HATA_yutuyor_yukleme_dusmuyor(tmp_path):
    """⚠️ Yon asimetrik: cagri geldiginde video ZATEN yayinda.

    Istisna disari sizarsa koşum `state.json`a yazmadan olur ve yayinlanmis
    video KAYITSIZ kalir — kapaksizliktan cok daha pahali bir kusur.
    """
    kapak_dosyasi = tmp_path / "k.jpg"
    kapak_dosyasi.write_bytes(b"x" * 100)

    class Patlayan:
        def thumbnails(self):
            raise RuntimeError("kota doldu")

    assert youtube_upload.kapak_bas(Patlayan(), "VID", str(kapak_dosyasi)) is False


class SayanServis:
    """API'ye gidildi mi diye SAYAR, `raise` ETMEZ.

    ⚠️ Burasi bir kez yanlis yazildi ve mutasyon testi yakaladi: sahte servis
    `AssertionError` firlatiyordu, `kapak_bas`in genis `except Exception`i onu
    YUTUYORDU ve test 2 MB kontrolu silinince bile geciyordu. Yani testin
    kapisi, olcmek istedigi seyden baskasini olcuyordu — deponun imza kusuru,
    bu kez test tarafinda.
    """

    def __init__(self):
        self.cagri_sayisi = 0

    def thumbnails(self):
        self.cagri_sayisi += 1
        raise RuntimeError("cagrilmamaliydi")


def test_kapak_bas_2MB_ustunu_ATLIYOR(tmp_path):
    """⚠️ MUTASYON: boyut kontrolunu kaldirmak bunu duser."""
    buyuk = tmp_path / "k.jpg"
    buyuk.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    servis = SayanServis()

    assert youtube_upload.kapak_bas(servis, "VID", str(buyuk)) is False
    assert servis.cagri_sayisi == 0, "2 MB ustu kapak icin API cagrilmamali"


def test_kapak_bas_dosya_YOKSA_API_cagirmiyor(tmp_path):
    servis = SayanServis()

    assert youtube_upload.kapak_bas(servis, "VID", None) is False
    assert youtube_upload.kapak_bas(servis, "VID", str(tmp_path / "yok.jpg")) is False
    assert servis.cagri_sayisi == 0


def test_upload_video_kapagi_BAGLIYOR(tmp_path):
    """⚠️ MUTASYON: `upload_video` icindeki `kapak_bas` cagrisini silmek bunu duser.

    Kapak uretilip yuklenmemesi en sinsi kusur olurdu: dosya diskte var,
    log temiz, YouTube yine kendi karesini secer ve kimse fark etmez.
    """
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")
    kapak_dosyasi = tmp_path / "k.jpg"
    kapak_dosyasi.write_bytes(b"x" * 100)
    gorulen = {}

    class SahteIstek:
        def next_chunk(self):
            return None, {"id": "VID999"}

    class SahteVideolar:
        def insert(self, **kwargs):
            return SahteIstek()

    class SahteKanallar:
        def list(self, **kwargs):
            return self

        def execute(self):
            return {"items": [{"id": "UC_TEST", "snippet": {"title": "Kanal"}}]}

    class Servis:
        def videos(self):
            return SahteVideolar()

        def channels(self):
            return SahteKanallar()

    def sahte_kapak_bas(youtube, video_id, kapak_yolu):
        gorulen["video_id"] = video_id
        gorulen["kapak"] = kapak_yolu
        return True

    with (
        patch.object(
            youtube_upload, "get_authenticated_service", return_value=Servis()
        ),
        patch.object(youtube_upload, "MediaFileUpload", lambda *a, **k: object()),
        patch.object(youtube_upload, "kapak_bas", sahte_kapak_bas),
        patch.dict(os.environ, {youtube_upload.KANAL_ORTAM_ANAHTARI: "UC_TEST"}),
    ):
        youtube_upload.upload_video(
            str(video), "T", "A", ["history"], "private", kapak_yolu=str(kapak_dosyasi)
        )

    assert gorulen == {"video_id": "VID999", "kapak": str(kapak_dosyasi)}


def test_kota_maliyeti_YAZILI():
    """⚠️ 6 yukleme x (1600 + 50) = 9.900 / 10.000. Tavan 6'da SABIT.

    Sayi koda yazili olmasa yukleme tavanini buyutmek sessizce kotayi
    asardi; asildiginda `videos.insert` 403 doner ve gunun kalan yayinlari
    dusler.
    """
    assert youtube_upload.KAPAK_KOTA_MALIYETI == 50
    assert 6 * (1600 + youtube_upload.KAPAK_KOTA_MALIYETI) <= 10_000
