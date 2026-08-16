"""Dev gorsel URETIMI durdurmasin — zamanlayiciyi olduren cokme.

⚠️ OLCULDU (2026-08-16 03:08, `storage/youtube_automation/logs/
hata-20260816-030859.log`). Yigin izi birebir suydu:

    download_scene_materials -> _tekrar_mi -> gorsel_olcum.parmak_izi
    -> Image.open -> _decompression_bomb_check
    PIL.Image.DecompressionBombError: Image size (1283491230 pixels)
    exceeds limit of 178956970 pixels

Kusurun can alici yeri: `_tekrar_mi` ve `_izi_ekle` ZATEN `except OSError`
ile sarilmisti ve niyetleri dogruydu ("olcum hatasi uretimi durdurmaz").
Ama `DecompressionBombError` `OSError`den DEGIL dogrudan `Exception`dan
turuyor, yani o korumalarin hicbiri onu goremiyordu.

Bedeli olculdu: 15 Agu 03:41 - 16 Agu 03:08 arasi SEKIZ slotun sekizi de
yayin uretmedi; bunlarin dordu bu sinif cokme.
"""

import re
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gorsel_olcum  # noqa: E402
import wikimedia_materials as wm  # noqa: E402


# --- parmak_izi: hatayi OSError'e ceviriyor ---------------------------------


def test_DecompressionBombError_OSError_olarak_geliyor(tmp_path, monkeypatch):
    """⚠️ Testin can alici noktasi: cagri yerleri OSError yakaliyor."""
    yol = tmp_path / "dev.jpg"
    yol.write_bytes(b"sahte")

    def patlat(*_a, **_k):
        raise Image.DecompressionBombError("Image size (1283491230 pixels) exceeds limit")

    monkeypatch.setattr(gorsel_olcum.Image, "open", patlat)

    with pytest.raises(OSError):
        gorsel_olcum.parmak_izi(yol)


def test_bomba_hatasi_OSError_ALT_SINIFI_degil():
    """Kusurun kokeni — bu dogru kaldigi surece cevrim SART."""
    assert not issubclass(Image.DecompressionBombError, OSError)


def test_MAX_IMAGE_PIXELS_kapatilmadi():
    """⚠️ Kolay ama YANLIS duzeltme: sinir kalkarsa 1,28 gigapiksel
    gercekten cozulur ve birkac GB RAM yer.

    ⚠️ Aranan sey ATAMA, gecen kelime degil — ilk yazdigimda bu test kendi
    aciklama yorumumu yakalayip patladi.
    """
    for modul in (gorsel_olcum, wm):
        kaynak = Path(modul.__file__).read_text(encoding="utf-8")

        assert not re.search(r"^\s*Image\.MAX_IMAGE_PIXELS\s*=", kaynak, re.MULTILINE)

    # Calisma zamaninda da kapatilmamis olmali.
    assert Image.MAX_IMAGE_PIXELS is not None


# --- cagri yerleri: cokme yerine gecis --------------------------------------


def test_tekrar_mi_COKMUYOR(tmp_path, monkeypatch):
    """Cokmenin birebir yasandigi cagri yeri."""
    yol = tmp_path / "dev.jpg"
    yol.write_bytes(b"sahte")
    monkeypatch.setattr(
        gorsel_olcum,
        "parmak_izi",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("cok buyuk")),
    )

    # Onceki iz VAR — yoksa fonksiyon olcmeden False donerdi ve test bos gecerdi.
    assert wm._tekrar_mi(yol, [object()]) is False


def test_izi_ekle_COKMUYOR(tmp_path, monkeypatch):
    yol = tmp_path / "dev.jpg"
    yol.write_bytes(b"sahte")
    monkeypatch.setattr(
        gorsel_olcum,
        "parmak_izi",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("cok buyuk")),
    )
    izler: list = []

    wm._izi_ekle(yol, izler)

    assert izler == []


# --- ikinci kat: aday bile olmasin ------------------------------------------


def _sayfa(genislik: int, yukseklik: int) -> dict:
    return {
        "title": "File:Ornek.jpg",
        "imageinfo": [
            {
                "mime": "image/jpeg",
                "url": "https://example.invalid/o.jpg",
                "width": genislik,
                "height": yukseklik,
                "extmetadata": {"LicenseShortName": {"value": "CC0"}},
            }
        ],
    }


def test_gigapiksel_dosya_ADAY_OLAMIYOR():
    """Coken dosyanin gercek olcusu: 1.283.491.230 piksel."""
    adaylar = wm._puanli_adaylar([_sayfa(46000, 27900)], set(), "", "", wm.UZUN_ORANI)

    assert adaylar == []


def test_CALISAN_buyuk_taramalar_hala_geciyor():
    """⚠️ Sinir fazla dar olursa en iyi arsiv kaynagini eleriz.

    Ayni gunun koşumunda 99 ve 114 megapiksellik iki dosya SORUNSUZ
    kullanildi — PIL yalnizca uyari verdi.
    """
    for genislik, yukseklik in ((11520, 8640), (13100, 8726)):
        assert genislik * yukseklik < wm.AZAMI_PIKSEL
        assert wm._puanli_adaylar(
            [_sayfa(genislik, yukseklik)], set(), "", "", wm.UZUN_ORANI
        )


def test_sinir_PIL_patlama_noktasinin_ALTINDA():
    """Sinir PIL'in hata esigini gecerse `parmak_izi` yine patlardi."""
    assert wm.AZAMI_PIKSEL < 178_956_970


def test_ALT_sinir_bozulmadi():
    """720 tabani yerinde kalmali — ust sinir onun yerine gecmiyor."""
    assert wm._puanli_adaylar([_sayfa(640, 640)], set(), "", "", wm.UZUN_ORANI) == []
