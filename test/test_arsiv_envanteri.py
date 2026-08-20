"""Plan istemine ARSIV MENUSU veriliyor — model neyi gosterebilecegini bilmeli.

⚠️ Olculdu (2026-08-13, Murad III). Sahne terimlerinin farkli olmasi zorunlu
kilininca (62c4d05) portre yigini bitti ama YENI bir kusur cikti: model bu
kez arsivde OLMAYAN seyler istedi — "Murad III Ottoman map", "Murad III
coin", "Murad III mausoleum". Arsivde harita da sikke de turbe de yoktu;
arama havuzdaki minyaturu dondurdu ve hakem "harita istedin, minyatur geldi"
diyerek skoru 38/67/33'e indirdi.

⚠️ Ikinci olcum (2026-08-14): envanter DOSYA ADI olarak verildiginde kusur
surdu. Sebep, adlarin cogunun hicbir sey soylememesi — Borobudur
kategorisinin ilki `20190415 151806b.jpg`, `500px photo (50204564).jpeg`,
`Ujung.jpg`. Ayni dosyalarin Commons aciklamasi ise kullanilabilir bilgi
tasiyor ("The clipper CUTTY SARK re-conditioned at anchor at Falmouth",
1922 sonrasi). Menu artik ACIKLAMA ve TARIH tasiyor; kapisi
`test_arsiv_alintisi.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402
import wikimedia_materials as wm  # noqa: E402


def _aday(baslik: str, aciklama: str = "", tarih: str = "") -> dict:
    return {"title": baslik, "aciklama": aciklama, "tarih": tarih}


def test_menu_dosya_aciklama_ve_tarih_tasiyor(monkeypatch):
    monkeypatch.setattr(
        wm,
        "arsiv_menusu",
        lambda _k, **_kw: [
            _aday("File:Tughra of Murad III.JPG", "Imperial monogram", "1593"),
            _aday("File:Berat 1593.jpg", "Decree on paper", "1593"),
        ],
    )

    assert ya.arsiv_envanteri("Murad III") == [
        {
            "dosya": "Tughra of Murad III.JPG",
            "gosterdigi": "Imperial monogram",
            "tarih": "1593",
        },
        {"dosya": "Berat 1593.jpg", "gosterdigi": "Decree on paper", "tarih": "1593"},
    ]


def _gravurlu_menu():
    return [
        _aday(
            "File:Herculaneum fresco of a priestess.jpg",
            "Wall painting of a priestess having her hair dressed",
            "1st century CE",
        ),
        _aday(
            "File:House of the Stags Cupids sawing 1773 Engraving by Lamborn.jpg",
            "Small painting of Cupids sawing, engraved plate",
            "1773",
        ),
    ]


def test_UZUN_menude_1773_gravuru_ELENIYOR(monkeypatch):
    """⚠️ HAT KENDI KENDISIYLE CELISIYORDU (olculdu 2026-08-19).

    Herculaneum menusunun 44 gorselinin 14'u 1773 gravuruydu. Arsiv-once
    kurali modele "menuden yaz" diyor, sonra model gravuru anlatinca
    `resmedilemez_kusuru` reddediyor — yani hat resmedilemez icerigi
    DAYATIP sonra onu reddediyordu.
    """
    monkeypatch.setattr(wm, "arsiv_menusu", lambda _k, **_kw: _gravurlu_menu())

    menu = ya.arsiv_envanteri("Gravur Denemesi Uzun", bicim=ya.UZUN_BICIMI)

    assert [g["dosya"] for g in menu] == ["Herculaneum fresco of a priestess.jpg"]


def test_SHORTS_menusunde_gravur_ELENMIYOR(monkeypatch):
    """⚠️ KAPI TESTI: kusur uzun formatta olculdu, Shorts kalibre edilmis."""
    monkeypatch.setattr(wm, "arsiv_menusu", lambda _k, **_kw: _gravurlu_menu())

    menu = ya.arsiv_envanteri("Gravur Denemesi Shorts", bicim=ya.SHORTS_BICIMI)

    assert len(menu) == 2


def test_kayit_kalibi_DAR_tutuluyor():
    """⚠️ Gevsek anahtar zarar verirdi — ayni gecenin `\\bAI\\b` dersi.

    Olculdu: `engrav|etching|lithograph|woodcut` Herculaneum'da 14/14'u
    yakaliyor, `plate|print|disegn|incis` SIFIR ekliyor. Yani gevsek
    anahtarin kazanci yok, kaybi var.
    """
    assert ya.kayit_gorseli_mi("Cupids 1773 Engraving by Lamborn.jpg", "")
    # Roma gumus TABAGI bir kayit gorseli DEGIL; "ustaca icatlar" sutunu
    # da matbaa/baski konularini tasiyor.
    assert not ya.kayit_gorseli_mi("Roman silver plate from Mildenhall.jpg", "")
    assert not ya.kayit_gorseli_mi("Gutenberg printing press replica.jpg", "")


def test_menu_yoksa_bos_donuyor(monkeypatch):
    """Menusu kurulamayan konuda uretim DURMAMALI."""
    monkeypatch.setattr(wm, "arsiv_menusu", lambda _k, **_kw: [])

    assert ya.arsiv_envanteri("Bilinmeyen Konu") == []


def test_ag_hatasi_uretimi_durdurmuyor(monkeypatch):
    """⚠️ Menu bir IYILESTIRME; cekilemezse hat eskisi gibi calismali.

    Plan asamasindayiz, yani elde henuz hicbir sey yok: burada patlamak
    butun koşumu bir 429 yuzunden coplerdi.
    """

    def patla(_k, **_kw):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(wm, "arsiv_menusu", patla)

    assert ya.arsiv_envanteri("Murad III") == []


def test_aciklama_kirpiliyor(monkeypatch):
    """Istem sinirsiz buyumemeli: 40 girdi x uzun aciklama isteme sigmaz."""
    monkeypatch.setattr(
        wm, "arsiv_menusu", lambda _k, **_kw: [_aday("File:X.jpg", "a" * 500, "b" * 200)]
    )

    girdi = ya.arsiv_envanteri("X")[0]

    assert len(girdi["gosterdigi"]) == ya.ACIKLAMA_SINIRI
    assert len(girdi["tarih"]) == 40


def test_bos_baslik_atlaniyor(monkeypatch):
    # ⚠️ Aciklamalar ICERIK tasimali: menu artik iceriksiz aciklamayi eliyor
    # (`aciklama_iceriksiz_mi`) ve bu testin konusu BASLIK, aciklama degil.
    ya._ENVANTER_ONBELLEGI.clear()
    monkeypatch.setattr(
        wm,
        "arsiv_menusu",
        lambda _k, **_kw: [
            _aday("", "Tomb of Qin Shihuang, 210 BC"),
            _aday("File:Gercek.jpg", "Tomb of Qin Shihuang, 210 BC"),
            {},
        ],
    )

    assert [g["dosya"] for g in ya.arsiv_envanteri("X")] == ["Gercek.jpg"]


def test_menu_isteme_giriyor(monkeypatch):
    """⚠️ Baglanti testi — fonksiyon dogru olsa bile isteme girmezse kusur surer."""
    yakalanan: dict = {}

    def sahte_cikarim(system: str, user: str, **_) -> dict:
        yakalanan["user"] = user
        raise RuntimeError("dur")

    monkeypatch.setattr(
        ya,
        "arsiv_envanteri",
        lambda _k, **_: [
            {
                "dosya": "Tughra of Murad III.JPG",
                "gosterdigi": "Imperial monogram",
                "tarih": "1593",
            }
        ],
    )
    monkeypatch.setattr(wm, "vikipedi_ozeti", lambda *_a, **_k: "Murad III was a sultan.")
    monkeypatch.setattr(ya, "_json_completion", sahte_cikarim)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])

    try:
        ya.generate_content_plan(konu="Murad III")
    except Exception:
        pass

    istem = yakalanan.get("user", "")
    assert "ARCHIVE MENU" in istem
    assert "Tughra of Murad III.JPG" in istem
    assert "Imperial monogram" in istem
    # ⚠️ Asil talimat: once goruntuyu sec, sonra cumleyi yaz.
    assert "source_file" in istem


def test_menu_yoksa_istem_bozulmuyor(monkeypatch):
    """Menu bos donerse blok hic eklenmemeli, istem gecerli kalmali."""
    yakalanan: dict = {}

    def sahte_cikarim(system: str, user: str, **_) -> dict:
        yakalanan["user"] = user
        raise RuntimeError("dur")

    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: [])
    monkeypatch.setattr(wm, "vikipedi_ozeti", lambda *_a, **_k: "Murad III was a sultan.")
    monkeypatch.setattr(ya, "_json_completion", sahte_cikarim)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])

    try:
        ya.generate_content_plan(konu="Murad III")
    except Exception:
        pass

    istem = yakalanan.get("user", "")
    assert "ARCHIVE MENU" not in istem
    assert "AUTHORITATIVE SOURCE" in istem


# --- Iceriksiz aciklama suzgeci (2026-08-17) ------------------------------


def test_ICERIKSIZ_aciklamali_dosya_menuye_GIRMIYOR(monkeypatch):
    """⚠️ Olculdu (11 ret, 16-17 Agu): en sik agir kusur `konuyla ilgisiz
    modern goruntu` (20 kez). Model dosyayi ACIKLAMAYA bakarak seciyor ve
    Terracotta Army menusunde ilk on girdinin ALTISI ayni kunyeydi:

        "2007. Complete indexed photo collection at WorldHistoryPics.com."

    Ne gosterdigini soylemeyen girdi kor secim demek.
    """
    ya._ENVANTER_ONBELLEGI.clear()
    monkeypatch.setattr(
        wm,
        "arsiv_menusu",
        lambda _k, **_kw: [
            _aday("File:Warrior 1.jpg", "2007. Complete indexed photo collection at WHP.com."),
            _aday("File:Warrior 2.jpg", "https://example.org/gallery"),
            _aday("File:Pit 1.jpg", "Tomb of Qin Shihuang, 210 BC, Qin, Lintong, Shaanxi."),
            _aday("File:Bos.jpg", ""),
            _aday("File:Kisa.jpg", "Xi'an"),
        ],
    )

    menu = ya.arsiv_envanteri("Terracotta Army")

    assert [g["dosya"] for g in menu] == ["Pit 1.jpg"]


def test_ICERIKLI_aciklama_KORUNUYOR(monkeypatch):
    """⚠️ Sinir bekcisi: suzgec kasten DAR. Menuyu kurutmak, ayni fonksiyon
    kapma kapisi oldugu icin (`run_cycle`) konuyu tumden elemek demek."""
    ya._ENVANTER_ONBELLEGI.clear()
    monkeypatch.setattr(
        wm,
        "arsiv_menusu",
        lambda _k, **_kw: [
            _aday("File:A.jpg", "Moai on Rapa Nui, fallen and broken at the quarry"),
            _aday("File:B.jpg", "Lantern slide; view of a moai with its face eroded"),
            _aday("File:C.jpg", "Aretas IV (reigned B.C. 9 - A.D. 40), builder of Al-Khazneh"),
        ],
    )

    menu = ya.arsiv_envanteri("Moai")

    assert len(menu) == 3, "icerik tasiyan aciklama elenmemeli"


def test_suzgec_dogrudan_olculuyor():
    """Kalibin kendisi — istemden bagimsiz."""
    for iceriksiz in (
        "2007. Complete indexed photo collection at WorldHistoryPics.com.",
        "https://commons.example/file",
        "www.example.com",
        "Own work",
        "",
        "Xi'an",
    ):
        assert ya.aciklama_iceriksiz_mi(iceriksiz), iceriksiz

    for icerikli in (
        "Tomb of Qin Shihuang, 210 BC, Qin, Lintong, Shaanxi.",
        "The clipper CUTTY SARK re-conditioned at anchor at Falmouth",
        "Lantern slide; view of a moai having fallen and broken",
    ):
        assert not ya.aciklama_iceriksiz_mi(icerikli), icerikli
