"""Lisans kabulu — PD/CC0 ve CC BY evet, CC BY-SA hayir.

Bu bir hukuki sinir; testler o sinirin kodda tuttugunu dogrular.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402
from youtube_automation import format_commons_credits  # noqa: E402


@pytest.mark.parametrize(
    "lisans",
    ["Public domain", "PD-old-70", "CC0", "cc0 1.0", "PUBLIC DOMAIN"],
)
def test_kosulsuz_lisanslar_kabul(lisans):
    assert wm.is_safe_license(lisans)
    assert wm.kullanilabilir_lisans(lisans)


@pytest.mark.parametrize("lisans", ["CC BY 2.0", "CC BY 4.0", "cc by 3.0"])
def test_atif_lisanslari_kabul(lisans):
    """Olculdu: bunlar reddedilirken gercek fotograflarin %78'i eleniyordu."""
    assert wm.atif_gerektiren(lisans)
    assert wm.kullanilabilir_lisans(lisans)
    assert not wm.is_safe_license(lisans), "kosulsuz degil, atif istiyor"


@pytest.mark.parametrize(
    "lisans",
    ["CC BY-SA 4.0", "CC BY-SA 2.0", "cc by-sa 3.0", "CC BY-SA", "Share Alike 1.0"],
)
def test_share_alike_reddediliyor(lisans):
    """⚠️ Metin tuzagi: "cc by-sa 4.0" metni "cc by" ICERIYOR.

    Naif bir `in` kontrolu share-alike'i de gecirirdi. Share-alike turev eseri
    ayni lisansa zorluyor; bu videonun tamaminin CC BY-SA olmasi anlamina
    gelebilir ve baskalarinin videoyu alip kullanmasina kapi acar. Kullanici
    kararı: PD/CC0 + CC BY.
    """
    assert wm.paylasimli_lisans(lisans)
    assert not wm.atif_gerektiren(lisans), f"{lisans} atif lisansi sayilmamali"
    assert not wm.kullanilabilir_lisans(lisans), f"{lisans} KABUL EDILMEMELI"


@pytest.mark.parametrize("lisans", ["", "Fair use", "All rights reserved", "GFDL"])
def test_bilinmeyen_lisans_reddediliyor(lisans):
    assert not wm.kullanilabilir_lisans(lisans)


def test_lisans_kontrolu_secime_bagli():
    """Fonksiyon dogru olsa bile secim onu cagirmazsa sinir tutmaz."""
    kaynak = Path(wm.__file__).read_text(encoding="utf-8")
    # ⚠️ SABIT UZUNLUKTA DILIM ALMA. Onceki hali `i : i + 3000` idi ve
    # `_puanli_adaylar`a yorum eklenince dilim lisans kontrolune ULASAMADI;
    # test kod bozulmadan patladi (bu sinif kirilma bu depoda dorduncu kez).
    # Dilim, secimin gercekten kullandigi fonksiyonun SONUNA kadar gidiyor.
    i = kaynak.index("def select_candidate(")
    j = kaynak.index("\ndef ", kaynak.index("def _puanli_adaylar("))
    govde = kaynak[i:j]

    assert "kullanilabilir_lisans(license_name)" in govde


# --- Atif metni ----------------------------------------------------------


def test_atif_sanatci_ve_lisansi_yaziyor():
    """CC BY icin atif hukuki zorunluluk — ad ve lisans gorunmeli."""
    metin = format_commons_credits(
        [
            {
                "source_url": "https://commons.wikimedia.org/wiki/File:A.jpg",
                "artist": "Jane Doe",
                "license": "CC BY 4.0",
            }
        ]
    )

    assert "Jane Doe" in metin
    assert "CC BY 4.0" in metin
    assert "https://commons.wikimedia.org/wiki/File:A.jpg" in metin


def test_baslik_serbestlik_iddia_etmiyor():
    """Baslik "public domain / CC0" diyordu; CC BY varken bu YANLIS bir iddia."""
    metin = format_commons_credits(
        [{"source_url": "https://x/A.jpg", "artist": "", "license": "CC BY 2.0"}]
    )

    assert "public domain" not in metin.splitlines()[0].lower()
    assert "cc0" not in metin.splitlines()[0].lower()


def test_hepsi_kamu_maliysa_baslik_bunu_soyluyor():
    metin = format_commons_credits(
        [{"source_url": "https://x/A.jpg", "title": "File:A.jpg", "license": "Public domain"}]
    )

    assert "public domain" in metin.splitlines()[0].lower()


def test_ayni_kaynak_bir_kez_yaziliyor():
    metin = format_commons_credits(
        [
            {"source_url": "https://x/A.jpg", "title": "File:A.jpg", "license": "CC0"},
            {"source_url": "https://x/A.jpg", "title": "File:A.jpg", "license": "CC0"},
        ]
    )

    assert metin.count("•") == 1


# --- Blok kisaligi (DW-104) ----------------------------------------------


def test_kamu_mali_gorseller_baglanti_tasimiyor():
    """⚠️ Uzunluk bir bicim tercihi degil, atif sozlesmesinin sonucu.

    Olculdu (2026-08-08): uc kamu mali gorsel, aciklamaya 1216 karakterlik bir
    yuzde-kodlu adres duvari koydu. Kamu mali / CC0 icin atif hukuki
    zorunluluk DEGIL, dolayisiyla baglanti da zorunlu degil — baslik ve
    sanatci kaynagi zaten gosteriyor. Blok 201 karaktere indi.
    """
    metin = format_commons_credits(
        [
            {
                "source_url": "https://commons.wikimedia.org/wiki/File:A.jpg",
                "title": "File:Masonry of the Chaco and other ruins.jpg",
                "license": "Public domain",
            }
        ]
    )

    assert "https://" not in metin
    assert "Masonry of the Chaco and other ruins" in metin


def test_lisans_bilinmiyorsa_baglanti_yaziliyor():
    """Kosul "CC BY mi" degil "serbest DEGIL mi".

    Bilinmeyen bir lisansi serbest saymak, atifi tam da emin olmadigimiz yerde
    atlamak olurdu. Yon asimetrik: gereksiz atif zarar vermiyor, eksik atif
    lisans ihlali.
    """
    metin = format_commons_credits(
        [{"source_url": "https://x/B.jpg", "title": "File:B.jpg", "license": "bilinmiyor"}]
    )

    assert "https://x/B.jpg" in metin


def test_kitap_kunyesi_baslikta_gorunmuyor():
    """Ham Commons adi izleyiciye arsiv kimligi ve baski atolyesi gosteriyordu."""
    metin = format_commons_credits(
        [
            {
                "source_url": "https://x/C.jpg",
                "title": (
                    "File:Pottery found at the Publo Hungo Pavie. R. H. delt. P.S. "
                    "Duval's Lith. Steam Press. Philada. (to accompany) Reports of the "
                    "secretary (IA dr pottery-found-0380036).jpg"
                ),
                "license": "Public domain",
            }
        ]
    )

    assert "Pottery found at the Publo Hungo Pavie" in metin
    for kunye in ("delt", "Duval", "Steam Press", "(IA", ".jpg"):
        assert kunye not in metin, f"kunye parcasi kaldi: {kunye}"


def test_okunmayacak_kadar_uzun_sanatci_dusuruluyor():
    """Commons bu alani kitap kunyesinden alinca isim degil isim LISTESI geliyor:
    "Johnston, Joseph E. Marcy, R. B. Simpson. James H. Whiting, W.H.C. Kern,
    Richard H., 1821-1853". Okunmayan bir satir atif islevi gormuyor.
    """
    uzun = "Johnston, Joseph E. Marcy, R. B. Simpson. James H. Whiting, W.H.C. Kern, Richard H., 1821-1853"
    metin = format_commons_credits(
        [{"source_url": "https://x/D.jpg", "title": "File:D.jpg", "license": "CC0", "artist": uzun}]
    )

    assert "Johnston" not in metin


def test_cc_by_de_uzun_sanatci_dusurulmuyor_kisaltiliyor():
    """⚠️ Kamu maliyla ayni davranmak ATIF IHLALI olurdu.

    CC BY'de eser sahibinin adi lisansin acikca istedigi unsur. Uzun diye
    dusurmek, baglanti ve lisans adi yazilmis ama ADI yazilmamis bir atif
    uretirdi — yani gecersiz bir atif.
    """
    uzun = "Johnston, Joseph E. Marcy, R. B. Simpson. James H. Whiting, W.H.C. Kern"
    metin = format_commons_credits(
        [
            {
                "source_url": "https://x/F.jpg",
                "title": "File:F.jpg",
                "license": "CC BY 4.0",
                "artist": uzun,
            }
        ]
    )

    assert "Johnston" in metin, "CC BY'de sanatci yazilmali"
    assert "CC BY 4.0" in metin
    assert "https://x/F.jpg" in metin


def test_kisa_sanatci_korunuyor():
    metin = format_commons_credits(
        [
            {
                "source_url": "https://x/E.jpg",
                "title": "File:Colosseum in Rome.jpg",
                "license": "CC0",
                "artist": "Diliff",
            }
        ]
    )

    assert "Diliff" in metin


def test_kaynak_yoksa_bos_doner():
    assert format_commons_credits([]) == ""
    assert format_commons_credits([{"source_url": ""}]) == ""


def test_sanatci_bilinmiyorsa_baglanti_yine_yaziliyor():
    metin = format_commons_credits(
        [{"source_url": "https://x/B.jpg", "artist": "", "license": ""}]
    )

    assert "https://x/B.jpg" in metin
