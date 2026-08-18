"""Kucuk arsivde ikinci gorsel HEP-YA-HIC degil, KISMI isteniyor.

⚠️ NEDEN VAR — olculdu 2026-08-18, son sekiz render'in kare duzeni:

    [A,A]  24 sahne   ·   [AB,AB]  6   ·   [A,B]  5

Yani sahnelerin ~%69'u AYNI gorseli iki yuvada gosteriyor. Ustelik o
gorselin %68'i `GaussianBlur(radius=40)` dolgu, cunku her 16:9 arsiv
fotografi bant yoluna dusuyor (`AZAMI_KIRPMA = 0.35`, 16:9'un kirpmasi
~0,68). Hakem de bunu boyle yaziyor: "frames 9-10 are identical images",
"heavily blurred/green gradient with no discernible content".

Sebep `_menu_talimati`nin ucuncu daliydi: menu 12 girdi veremiyorsa
(olculen menu boylari — Notre Dame 5 · Newgrange 7 · Sigiriya 8 ·
Hadrian's Wall 11 · Sacsayhuaman 11) istem HER sahne icin ikinci gorseli
YASAKLIYORDU. Oysa 8 girdili bir menude 6 birincil + 2 ikincil pekala
secilebilir.

⚠️ `ikinci_gorsel_istenebilir` KALDIRILMADI ve bu onemli: kapattigi
gerileme gercek (2026-08-14). Model imkansiz talebi karsilamak icin dosya
tekrar ediyordu, `alinti_kusuru` PLANIN TAMAMINI reddediyordu ve bes deneme
yaniyordu. Kismi dal o baskiyi ACIKCA kaldiriyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402
import youtube_automation as ya  # noqa: E402


def _menu(adet: int) -> list[dict[str, str]]:
    return [
        {"dosya": f"{i}.jpg", "gosterdigi": f"{i} gorseli", "tarih": "1900"}
        for i in range(adet)
    ]


# --- Istemin uc dali --------------------------------------------------------


def test_menu_BOL_ise_her_sahneye_ikinci_gorsel_isteniyor():
    """Eski davranis korunuyor: 12 girdi, 6 sahne."""
    metin = ya._menu_talimati(_menu(12), 6)

    assert "ALSO pick a SECOND entry for each scene" in metin


def test_menu_KUCUK_ama_ARTAN_varsa_KISMI_isteniyor():
    """⚠️ ASIL DUZELTME. Sigiriya'nin menusu 8, sahne 6 — iki sahne ikinci
    gorsel alabilir. Eskiden sifir aliyordu."""
    metin = ya._menu_talimati(_menu(8), 6)

    assert "This archive is small: 8 usable images for 6 scenes" in metin
    assert "Leave source_file_2 empty for every scene" not in metin


def test_kismi_dal_BIRINCILLERIN_farkli_olmasini_ONCELIKLI_tutuyor():
    """⚠️ Gerilemenin kapisi burasi: model ikinci gorseli tutturmak icin
    BIRINCIL dosyayi tekrar ederse `alinti_kusuru` plani tumden reddeder."""
    metin = ya._menu_talimati(_menu(8), 6)

    assert "must still be a DIFFERENT entry" in metin
    assert "comes first" in metin


def test_kismi_dal_TEKRARA_zorlamiyor():
    """Model "bulamazsan bos birak" iznini acikca gormeli."""
    metin = ya._menu_talimati(_menu(8), 6)

    assert "leave source_file_2 empty when nothing distinct is left" in metin


def test_menu_ARTAN_VERMIYORSA_ikinci_gorsel_hic_istenmiyor():
    """6 sahne icin 6 girdi: artan yok, kismi dal da anlamsiz."""
    metin = ya._menu_talimati(_menu(6), 6)

    assert "Leave source_file_2 empty for every scene" in metin
    assert "This archive is small" not in metin


def test_UZUN_kipte_ikinci_gorsel_hic_istenmiyor():
    """⚠️ `kare_yuvasi == 1` — istenirse model menunun iki katini bosa
    tuketir ve ekranda hicbir sey degismez."""
    metin = ya._menu_talimati(_menu(40), 30, bicim=ya.UZUN_BICIMI)

    assert "each scene shows exactly one picture" in metin
    assert "This archive is small" not in metin


# --- Algisal tekrar elemesi -------------------------------------------------
#
# ⚠️ NEDEN VAR: `used_titles` yalnizca BASLIK esitligini yakaliyor. Ayni
# fotografin baska adla duran kopyasini gormuyor — birincil yolda bu koruma
# zaten vardi (`_tekrar_mi`), ikincil yol ondan HIC gecmiyordu. Kismi dal
# ikinci gorseli daha sik istedigi icin risk buyudu.


def _tedarik_kur(monkeypatch, tmp_path, izler_haritasi):
    """`ikincil_gorseller`i aga cikmadan kosturur.

    `izler_haritasi`: dosya adi -> sahte parmak izi. Ayni iz = ayni fotograf.
    """
    monkeypatch.setattr(
        wm, "_alinti_adayi",
        lambda alinti, *_a, **_k: {
            "url": f"http://x/{alinti}",
            "title": alinti,
            "mime": "image/jpeg",
            "source_url": "http://x",
            "license": "CC0",
            "artist": "yok",
        },
    )

    def _sahte_indir(url, hedef):
        hedef.write_bytes(b"x")

    monkeypatch.setattr(wm, "_download", _sahte_indir)
    monkeypatch.setattr(
        wm.gorsel_olcum, "parmak_izi", lambda yol: izler_haritasi.get(Path(yol).name, yol.name)
    )
    monkeypatch.setattr(
        wm.gorsel_olcum, "benzerlik", lambda a, b: 1.0 if a == b else 0.0
    )
    return tmp_path


def test_BIRINCILIN_kopyasi_olan_ikincil_ELENIYOR(monkeypatch, tmp_path):
    """Ayni fotograf, farkli ad. Sahne [A, A]'ya doner — dogru sonuc, cunku
    ayni resmi iki yuvada gostermek zaten kacinmak istedigimiz sey."""
    birincil = tmp_path / "scene-01.jpg"
    birincil.write_bytes(b"x")
    _tedarik_kur(monkeypatch, tmp_path, {"scene-01.jpg": "AYNI", "scene-01b.jpg": "AYNI"})

    dosyalar, krediler = wm.ikincil_gorseller(
        [{"kaynak_dosya_2": "kopya.jpg", "search_term": "t"}],
        tmp_path / "ikincil",
        [],
        birincil_dosyalar=[birincil],
    )

    assert dosyalar == [None]
    assert krediler == [], "elenen gorsel kunyeye girmemeli"
    assert not (tmp_path / "ikincil" / "scene-01b.jpg").exists(), "dosya silinmeliydi"


def test_FARKLI_ikincil_kabul_ediliyor(monkeypatch, tmp_path):
    birincil = tmp_path / "scene-01.jpg"
    birincil.write_bytes(b"x")
    _tedarik_kur(monkeypatch, tmp_path, {"scene-01.jpg": "A", "scene-01b.jpg": "B"})

    dosyalar, krediler = wm.ikincil_gorseller(
        [{"kaynak_dosya_2": "baska.jpg", "search_term": "t"}],
        tmp_path / "ikincil",
        [],
        birincil_dosyalar=[birincil],
    )

    assert dosyalar[0] is not None
    assert len(krediler) == 1, "kabul edilen gorselin kunyesi ZORUNLU (CC BY atif)"


def test_IKI_IKINCIL_birbirinin_kopyasi_olamaz(monkeypatch, tmp_path):
    """Secilen her ikincil de ize ekleniyor; yoksa iki sahne ayni resmi alir."""
    b1, b2 = tmp_path / "s1.jpg", tmp_path / "s2.jpg"
    b1.write_bytes(b"x")
    b2.write_bytes(b"x")
    _tedarik_kur(
        monkeypatch,
        tmp_path,
        {"s1.jpg": "A", "s2.jpg": "B", "scene-01b.jpg": "C", "scene-02b.jpg": "C"},
    )

    dosyalar, _ = wm.ikincil_gorseller(
        [
            {"kaynak_dosya_2": "x.jpg", "search_term": "t"},
            {"kaynak_dosya_2": "y.jpg", "search_term": "t"},
        ],
        tmp_path / "ikincil",
        [],
        birincil_dosyalar=[b1, b2],
    )

    assert dosyalar[0] is not None
    assert dosyalar[1] is None, "ikinci sahne birincinin kopyasini aldi"


def test_birincil_VERILMEZSE_eski_davranis(monkeypatch, tmp_path):
    """⚠️ Parametre istege bagli: webui ve testler ayni fonksiyonu cagiriyor,
    varsayilan davranis degismemeli."""
    _tedarik_kur(monkeypatch, tmp_path, {})

    dosyalar, _ = wm.ikincil_gorseller(
        [{"kaynak_dosya_2": "x.jpg", "search_term": "t"}], tmp_path / "ikincil", []
    )

    assert dosyalar[0] is not None


def test_OLCUM_DUSERSE_mesru_aday_elenmiyor(monkeypatch, tmp_path):
    """⚠️ `_tekrar_mi` okunamayan dosyada False donuyor — mesru bir adayi
    elemek, tekrari kacirmaktan daha kotu."""
    birincil = tmp_path / "scene-01.jpg"
    birincil.write_bytes(b"x")
    _tedarik_kur(monkeypatch, tmp_path, {})

    def _patla(_yol):
        raise OSError("okunamadi")

    monkeypatch.setattr(wm.gorsel_olcum, "parmak_izi", _patla)

    dosyalar, _ = wm.ikincil_gorseller(
        [{"kaynak_dosya_2": "x.jpg", "search_term": "t"}],
        tmp_path / "ikincil",
        [],
        birincil_dosyalar=[birincil],
    )

    assert dosyalar[0] is not None


def test_hat_BIRINCILLERI_geciriyor():
    """Baglanti testi: parametre eklenip cagriya gecmezse islevsiz."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "birincil_dosyalar=list(material_files)" in kaynak
