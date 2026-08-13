"""Sahnenin alintiladigi dosya GERCEKTEN indiriliyor mu.

⚠️ Kapinin (`youtube_automation.alinti_kusuru`) tek basina degeri yok: plan
menuden dogru dosyayi secse bile indirici aramaya devam ederse sahne yine
baska bir gorselle doluyor ve kusur aynen suruyor.

Olculdu (2026-08-14): senaryo once yazilip arsiv sonra arandiginda hakem 12
kosumun 12'sinde ayni gerekceyi yazdi — "dogru konu, YANLIS an". Anlatim
artik SECILEN dosyanin gosterdigi seyin uzerine yaziliyor, yani baska bir
gorsel "yakin" degil yanlis olur.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402


def _sayfa(ad: str, url: str, *, en=1000, boy=1400, aciklama="") -> dict:
    return {
        "title": ad,
        "imageinfo": [
            {
                "mime": "image/jpeg",
                "url": url,
                "descriptionurl": f"https://commons.wikimedia.org/wiki/{ad}",
                "width": en,
                "height": boy,
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "ImageDescription": {"value": aciklama},
                },
            }
        ],
    }


def _hat(monkeypatch, havuz, *, aramadan=None):
    aramalar: list[str] = []

    def sahte_arama(query, *_a, **_k):
        aramalar.append(query)
        return list(aramadan or [])

    monkeypatch.setattr(wm, "search_commons", sahte_arama)
    monkeypatch.setattr(wm, "commons_kategorisi", lambda _k: "Kategori")
    monkeypatch.setattr(wm, "kategori_gorselleri", lambda *_a, **_k: list(havuz))
    monkeypatch.setattr(wm, "download_met_scene_material", lambda *_a, **_k: None)
    monkeypatch.setattr(wm, "_tekrar_mi", lambda *_a, **_k: False)
    monkeypatch.setattr(wm, "_izi_ekle", lambda *_a, **_k: None)
    monkeypatch.setattr(wm, "_download", lambda url, hedef, **_k: hedef.write_bytes(b"x" * 20_000))
    return aramalar


def test_alintilanan_dosya_aramanin_onune_geciyor(monkeypatch, tmp_path):
    """Asil kosul: hat BASKA bir gorseli daha uygun bulsa bile alinti kazanir.

    ⚠️ `baska.jpg` havuzda ONCE geliyor: `_kategori_adaylari` esitlikte
    sirayla puanladigi icin, alinti calismasaydi sahneye O girerdi. Sira
    boyle kurulmazsa test kendiliginden gecer ve hicbir sey kilitlemez.
    """
    havuz = [_sayfa("File:baska.jpg", "u2"), _sayfa("File:secilen.jpg", "u1")]
    _hat(monkeypatch, havuz, aramadan=[_sayfa("File:aramadan.jpg", "u3")])

    _dosyalar, kunyeler = wm.download_scene_materials(
        "Konu",
        [{"narration": "n", "search_term": "Konu detay", "kaynak_dosya": "secilen.jpg"}],
        tmp_path,
        visual_anchor="Konu",
    )

    assert kunyeler[0]["title"] == "File:secilen.jpg"


def test_alinti_tuttuysa_hic_aranmiyor(monkeypatch, tmp_path):
    """Sahnenin gorseli zaten SECILMIS; aramak onu degistirmek olurdu."""
    aramalar = _hat(monkeypatch, [_sayfa("File:secilen.jpg", "u1")])

    wm.download_scene_materials(
        "Konu",
        [{"narration": "n", "search_term": "Konu detay", "kaynak_dosya": "secilen.jpg"}],
        tmp_path,
        visual_anchor="Konu",
    )

    assert aramalar == [], f"alinti tuttugu halde arama yapildi: {aramalar}"


def test_met_alinti_varken_denenmiyor(monkeypatch, tmp_path):
    denendi: list[int] = []
    _hat(monkeypatch, [_sayfa("File:secilen.jpg", "u1")])
    monkeypatch.setattr(
        wm,
        "download_met_scene_material",
        lambda *_a, **_k: (denendi.append(1), None)[1],
    )

    wm.download_scene_materials(
        "Konu",
        [{"narration": "n", "search_term": "Konu detay", "kaynak_dosya": "secilen.jpg"}],
        tmp_path,
        visual_anchor="Konu",
    )

    assert denendi == []


def test_kategoride_olmayan_alinti_tek_istekle_getiriliyor(monkeypatch, tmp_path):
    """Menu kategoriden VE aramadan besleniyor; aramadan gelen secim havuzda yok."""
    _hat(monkeypatch, [_sayfa("File:baska.jpg", "u1")])
    monkeypatch.setattr(
        wm, "dosya_sayfasi", lambda ad: _sayfa(f"File:{ad}", "u-tek")
    )

    _dosyalar, kunyeler = wm.download_scene_materials(
        "Konu",
        [{"narration": "n", "search_term": "Konu detay", "kaynak_dosya": "uzak.jpg"}],
        tmp_path,
        visual_anchor="Konu",
    )

    assert kunyeler[0]["title"] == "File:uzak.jpg"


def test_havuzdaki_EKSIK_kayit_dosyayi_dusurmuyor(monkeypatch, tmp_path):
    """⚠️ Alintilarin %61'ini kaybettiren kusur — olculdu (2026-08-14).

    MediaWiki `categorymembers` istegi `imageinfo`yu ISTEK BASINA
    siniriyor ve yaklasik ilk 50 dosyadan sonrasini BOS donduruyor. Angkor
    Wat kategorisinde uyelerin %90'i boyle geldi. Havuzdaki bos kayit
    suzgecten elenince sahne aramaya dusuyor ve BASKA bir gorsel geliyordu;
    hakemin sikayet ettigi 11 sahnenin 10'u tam da bunlardi.
    """
    eksik = {"title": "File:secilen.jpg", "imageinfo": [{}]}
    _hat(monkeypatch, [eksik, _sayfa("File:baska.jpg", "u2")])
    monkeypatch.setattr(
        wm, "dosya_sayfasi", lambda ad: _sayfa(f"File:{ad}", "u-tam")
    )

    _dosyalar, kunyeler = wm.download_scene_materials(
        "Konu",
        [{"narration": "n", "search_term": "Konu detay", "kaynak_dosya": "secilen.jpg"}],
        tmp_path,
        visual_anchor="Konu",
    )

    assert kunyeler[0]["title"] == "File:secilen.jpg", "eksik kayit dosyayi dusurmemeli"


def test_alinti_bulunamazsa_zincir_devam_ediyor(monkeypatch, tmp_path):
    """⚠️ Alinti bir GARANTI degil ILK TERCIH.

    Dosya silinmis olabilir. Bu yuzden dusmek yerine eski zincir calismali —
    yoksa tek bir kayip dosya butun koşumu oldururdu.
    """
    _hat(monkeypatch, [_sayfa("File:havuzdan.jpg", "u1")])
    monkeypatch.setattr(wm, "dosya_sayfasi", lambda _ad: None)

    dosyalar, kunyeler = wm.download_scene_materials(
        "Konu",
        [{"narration": "n", "search_term": "Konu detay", "kaynak_dosya": "yok.jpg"}],
        tmp_path,
        visual_anchor="Konu",
    )

    assert dosyalar[0] is not None
    assert kunyeler[0]["title"] == "File:havuzdan.jpg"


def test_alinti_yoksa_eski_davranis(monkeypatch, tmp_path):
    """Menusu olmayan konularda hat eskisi gibi calismali."""
    aramalar = _hat(
        monkeypatch, [], aramadan=[_sayfa("File:aramadan.jpg", "u1", aciklama="Konu")]
    )

    _dosyalar, kunyeler = wm.download_scene_materials(
        "Konu",
        [{"narration": "n", "search_term": "Konu detay"}],
        tmp_path,
        visual_anchor="Konu",
    )

    assert aramalar, "alinti yokken arama calismali"
    assert kunyeler[0]["title"] == "File:aramadan.jpg"


def test_alinti_lisans_kapisindan_gecmek_zorunda(monkeypatch, tmp_path):
    """Menu suzgeci atlatilamamali: model paylasimli lisansli bir dosya secerse
    indirici onu KABUL ETMEMELI (CC BY-SA videoyu yeniden lisanslardi)."""
    sayfa = _sayfa("File:paylasimli.jpg", "u1")
    sayfa["imageinfo"][0]["extmetadata"]["LicenseShortName"] = {"value": "CC BY-SA 4.0"}
    _hat(monkeypatch, [sayfa, _sayfa("File:temiz.jpg", "u2")])

    _dosyalar, kunyeler = wm.download_scene_materials(
        "Konu",
        [{"narration": "n", "search_term": "Konu detay", "kaynak_dosya": "paylasimli.jpg"}],
        tmp_path,
        visual_anchor="Konu",
    )

    assert kunyeler[0]["title"] == "File:temiz.jpg"
