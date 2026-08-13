"""Ayni arsiv gorselinin iki sahnede kullanilmasi (DW-109).

⚠️ Olculdu (2026-08-09, Library of Alexandria kosumu): sahne 3 ve sahne 7
AYNI gravurdu — "The Great Library of Alexandria - Colorized.jpg" ile
"Ancientlibraryalex.jpg". Algisal benzerlik 0,836. Kullanicinin sikayeti
birebir buydu: "bir resmi birden fazla kez kullanmissin".

`used_titles` bunu yakalayamiyordu cunku dosya adlari tamamen farkli.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gorsel_olcum  # noqa: E402
import wikimedia_materials as wm  # noqa: E402


def _gorsel(yol: Path, *, tohum: int, renkli: bool = False) -> Path:
    """Tekrarlanabilir bir desen — `tohum` ayni ise gorsel de ayni.

    ⚠️ Desen BLOK BLOK rastgele: ilk surum duz zemin uzerine birkac dikdortgen
    ciziyordu ve farkli tohumlar bile 0,86 benzerlik veriyordu — zeminin
    kendisi baskin. Parmak izi 16x16'ya indirdigi icin desenin o olcekte de
    ayrisiyor olmasi gerekiyor.

    `renkli` ayni deseni farkli renklerle uretir: gercek vakada oldugu gibi
    (renklendirilmis gravur) parmak izinin renge duyarsiz oldugunu gosterir.
    """
    import random

    rastgele = random.Random(tohum)
    im = Image.new("RGB", (400, 600))
    ciz = ImageDraw.Draw(im)
    for gy in range(0, 600, 25):
        for gx in range(0, 400, 25):
            koyu = rastgele.random() < 0.5
            if renkli:
                # ⚠️ Renkler parlaklik yapisini KORUMALI: gercek bir
                # renklendirme gravurun koyu/acik duzenini bozmaz, uzerine
                # renk katar. Ilk surumde koyu bloklar kirmiziya, aciklar
                # maviye boyaniyordu; ikisinin gri karsiligi neredeyse esitti,
                # desen kayboluyordu ve test kendi fixture'i yuzunden dusuyordu.
                renk = (120, 20, 20) if koyu else (245, 230, 150)
            else:
                renk = (25, 25, 25) if koyu else (235, 235, 235)
            ciz.rectangle([gx, gy, gx + 25, gy + 25], fill=renk)
    im.save(yol)
    return yol


# --- Olcum ----------------------------------------------------------------


def test_renklendirilmis_kopya_yakalaniyor(tmp_path):
    """⚠️ Gercek vakanin ozu: ayni gravur, biri renklendirilmis.

    Parmak izi griye cevirdigi icin renk farki onu gizleyemiyor.
    """
    a = _gorsel(tmp_path / "a.png", tohum=5)
    b = _gorsel(tmp_path / "b.png", tohum=5, renkli=True)

    oran = gorsel_olcum.benzerlik(
        gorsel_olcum.parmak_izi(a), gorsel_olcum.parmak_izi(b)
    )

    assert oran >= gorsel_olcum.ARSIV_TEKRAR_ESIGI


def test_farkli_gorseller_tekrar_sayilmiyor(tmp_path):
    a = _gorsel(tmp_path / "a.png", tohum=3)
    b = _gorsel(tmp_path / "b.png", tohum=91)

    oran = gorsel_olcum.benzerlik(
        gorsel_olcum.parmak_izi(a), gorsel_olcum.parmak_izi(b)
    )

    assert oran < gorsel_olcum.ARSIV_TEKRAR_ESIGI


def test_esik_olculen_iki_tekrari_da_kapsiyor():
    """⚠️ Esik VERIDEN secildi, tahminle degil.

    0,836 ayni gravur; 0,734 ayni sutunun iki fotografi. Sonraki cift 0,578 —
    aradaki bosluk genis, 0,75 ikisini de yakalayip mesru gorsellerden uzak
    duruyor.
    """
    assert gorsel_olcum.ARSIV_TEKRAR_ESIGI <= 0.734, "ayni sutunun iki fotografi kacar"
    assert gorsel_olcum.ARSIV_TEKRAR_ESIGI > 0.578, "mesru gorseller elenir"


def test_olcum_hatasi_adayi_elemiyor(tmp_path):
    """Okunamayan dosya yuzunden MESRU bir adayi elemek, tekrari kacirmaktan kotu."""
    bozuk = tmp_path / "bozuk.png"
    bozuk.write_bytes(b"resim degil")
    saglam = _gorsel(tmp_path / "a.png", tohum=1)

    assert wm._tekrar_mi(bozuk, [gorsel_olcum.parmak_izi(saglam)]) is False


def test_ilk_sahne_her_zaman_geciyor(tmp_path):
    assert wm._tekrar_mi(_gorsel(tmp_path / "a.png", tohum=1), []) is False


# --- Hatta baglanti -------------------------------------------------------


def _sahte_arama(
    tmp_path, monkeypatch, adaylar: list[dict], *, europeana=None
) -> list[str]:
    """`search_commons` ve `_download` yamanir; indirilen dosyalar uretilir.

    ⚠️ Europeana da yamaniyor. Yamanmazsa bu testler CANLI AGA cikar: tekrar
    yedegi artik Europeana'dan SONRA calisiyor (2026-08-13), yani butun
    adaylar kopya cikinca kod once Europeana'ya gidiyor. Ayni tuzak
    `test_gorsel_cesitliligi.py`'de de not edilmisti.
    """
    indirilen: list[str] = []

    monkeypatch.setattr(wm, "search_commons", lambda *_a, **_k: list(adaylar))
    monkeypatch.setattr(
        wm, "download_europeana_scene_material", europeana or (lambda *_a, **_k: None)
    )

    def sahte_secim(pages, kullanilan, **_k):
        for sayfa in pages:
            if sayfa["title"] not in kullanilan:
                return sayfa
        return None

    monkeypatch.setattr(wm, "select_candidate", sahte_secim)

    def sahte_indir(url, hedef):
        indirilen.append(url)
        _gorsel(hedef, tohum=int(url))

    monkeypatch.setattr(wm, "_download", sahte_indir)
    monkeypatch.setattr(wm, "download_met_scene_material", lambda *_a, **_k: None)
    return indirilen


def _aday(url: str, ad: str) -> dict:
    return {
        "title": ad,
        "url": url,
        "mime": "image/png",
        "source_url": f"https://commons.wikimedia.org/wiki/{ad}",
        "license": "Public domain",
        "artist": "x",
    }


def test_ayni_gorsel_ikinci_sahnede_kullanilmiyor(tmp_path, monkeypatch):
    """⚠️ Asil kusur. Iki sahne, aday listesinde ayni gorsel iki farkli adla.

    Eski davranis: ikisi de secilirdi (basliklar farkli). Yeni davranis:
    ikinci sahne farkli olan uc numarali adayi alir.
    """
    _sahte_arama(
        tmp_path,
        monkeypatch,
        [
            _aday("5", "File:Ayni gravur.png"),
            _aday("5", "File:Ayni gravur - Colorized.png"),
            _aday("91", "File:Bambaska bir gorsel.png"),
        ],
    )

    dosyalar, krediler = wm.download_scene_materials(
        "Alexandria",
        [{"search_term": "library"}, {"search_term": "scrolls"}],
        tmp_path,
        kismi=True,
    )

    assert len(dosyalar) == 2
    izler = [gorsel_olcum.parmak_izi(d) for d in dosyalar]

    assert gorsel_olcum.benzerlik(izler[0], izler[1]) < gorsel_olcum.ARSIV_TEKRAR_ESIGI
    assert krediler[1]["title"] == "File:Bambaska bir gorsel.png"


def test_baska_aday_yoksa_benzer_gorsel_yine_kullaniliyor(tmp_path, monkeypatch):
    """⚠️ Yumusak kapi: delik birakmak, benzer gorselden DAHA kotu.

    Sahne bos kalirsa ya AI dolgusu devreye girer (para) ya da video eksik
    kalir. Elde baska bir sey yokken tekrari kabul etmek dogru taviz.
    """
    _sahte_arama(
        tmp_path,
        monkeypatch,
        [
            _aday("5", "File:Ayni gravur.png"),
            _aday("5", "File:Ayni gravur - Colorized.png"),
        ],
    )

    dosyalar, _ = wm.download_scene_materials(
        "Alexandria",
        [{"search_term": "library"}, {"search_term": "scrolls"}],
        tmp_path,
        kismi=True,
    )

    assert dosyalar[1] is not None, "sahne bos birakilmamali"


def test_tekrar_yedeginden_once_europeana_deneniyor(tmp_path, monkeypatch):
    """⚠️ Sira kusuru (2026-08-13). `yedek` TANIMI GEREGI bilinen bir kopya:
    yalnizca `_tekrar_mi` dallarinda ataniyor. Eskiden Europeana'dan ONCE
    calisiyor, `selected`i dolduruyor ve ucuncu kaynagin kapisini hic
    actirmiyordu — bilinen kopya, hic denenmemis kaynaga tercih ediliyordu.

    Olculdu (Mehmed II koşumu): hakem "kare 2 ve 3 ayni, kare 6 ve 7 ayni"
    yazdi, gorsel skoru 56. Tekrar o koşumda kalan tek baskin kusurdu.
    """
    eu_yol = tmp_path / "europeana.png"

    def sahte_europeana(_queries, *, scene_number, target_dir, used_ids, **_k):
        _gorsel(eu_yol, tohum=777)
        return eu_yol, {
            "scene": scene_number,
            "title": "Europeana: bambaska gorsel",
            "europeana_id": "/1/eu-1",
            "source_url": "https://europeana.eu/item/1",
            "license": "Public domain",
            "artist": "x",
        }

    _sahte_arama(
        tmp_path,
        monkeypatch,
        [
            _aday("5", "File:Ayni gravur.png"),
            _aday("5", "File:Ayni gravur - Colorized.png"),
        ],
        europeana=sahte_europeana,
    )

    dosyalar, krediler = wm.download_scene_materials(
        "Alexandria",
        [{"search_term": "library"}, {"search_term": "scrolls"}],
        tmp_path,
        kismi=True,
    )

    assert krediler[1]["title"] == "Europeana: bambaska gorsel", (
        "ikinci sahne Commons kopyasini degil Europeana'daki yeni gorseli almali"
    )
    izler = [gorsel_olcum.parmak_izi(d) for d in dosyalar]
    assert gorsel_olcum.benzerlik(izler[0], izler[1]) < gorsel_olcum.ARSIV_TEKRAR_ESIGI


def test_europeana_bos_donerse_tekrar_yedegi_yine_calisiyor(tmp_path, monkeypatch):
    """Sira degisti ama YUMUSAK KAPI duruyor — son care hala kopya koymak.

    Bu testin ikizi `test_baska_aday_yoksa_benzer_gorsel_yine_kullaniliyor`;
    burada ayrica Europeana'nin GERCEKTEN sorulduğu kilitleniyor, yoksa
    sira duzeltmesi sessizce geri alinabilir.
    """
    soruldu: list[int] = []

    def bos_europeana(_queries, *, scene_number, **_k):
        soruldu.append(scene_number)
        return None

    _sahte_arama(
        tmp_path,
        monkeypatch,
        [
            _aday("5", "File:Ayni gravur.png"),
            _aday("5", "File:Ayni gravur - Colorized.png"),
        ],
        europeana=bos_europeana,
    )

    dosyalar, _ = wm.download_scene_materials(
        "Alexandria",
        [{"search_term": "library"}, {"search_term": "scrolls"}],
        tmp_path,
        kismi=True,
    )

    assert soruldu == [2], "kopya yedegine dusmeden once Europeana sorulmali"
    assert dosyalar[1] is not None, "son care olarak kopya yine konmali"


def test_tekrar_kontrolu_indirmeden_sonra(tmp_path, monkeypatch):
    """Benzerlik pikselden olculuyor — baslikla ya da URL'yle bilinemez.

    Bu yuzden aday indirilmeden karar verilemez; test o siranin korundugunu
    kilitliyor.
    """
    indirilen = _sahte_arama(
        tmp_path,
        monkeypatch,
        [
            _aday("5", "File:Bir.png"),
            _aday("5", "File:Iki.png"),
            _aday("91", "File:Uc.png"),
        ],
    )

    wm.download_scene_materials(
        "Alexandria",
        [{"search_term": "a"}, {"search_term": "b"}],
        tmp_path,
        kismi=True,
    )

    assert indirilen.count("5") >= 2, "elenen aday da indirilmis olmali"


def test_esik_tek_yerde():
    """Iki modul ayni esigi kullanmali; kopyalanirsa sessizce ayrisir."""
    kaynak = Path(wm.__file__).read_text(encoding="utf-8")

    assert "gorsel_olcum.ARSIV_TEKRAR_ESIGI" in kaynak
    assert "0.75" not in kaynak, "esik burada kopyalanmamali"


def test_dairesel_import_yok():
    """⚠️ `gorsel_olcum` bu yuzden ayri modul.

    `wikimedia_materials` olcume ihtiyac duyuyor ama `youtube_automation`
    zaten onu import ediyor; olcum orada kalsaydi dairesel import olurdu.
    """
    kaynak = Path(gorsel_olcum.__file__).read_text(encoding="utf-8")

    assert "import youtube_automation" not in kaynak
    assert "import wikimedia_materials" not in kaynak


@pytest.mark.parametrize("ad", ["parmak_izi", "ton_yayilimi"])
def test_youtube_automation_ayni_uygulamayi_kullaniyor(ad):
    """Iki kopya uygulama zamanla ayrisir; olcumler ayni sayiyi vermeli."""
    import youtube_automation as ya

    esler = {"parmak_izi": ya._parmak_izi, "ton_yayilimi": ya.ton_yayilimi}

    assert esler[ad] is getattr(gorsel_olcum, ad)
