"""Kuyruk kendini besliyor — `Yeni` -> olcum -> `Secildi`.

⚠️ NEDEN VAR — olculdu (2026-08-14). Uretim iki kez durdu, ikisinde de
sebep hattin kendisi degil BESLENMEMESIYDI:

    `Secildi` kuyrugu      1-2 aday    (uretim buradan besleniyor)
    `Yeni` kuyrugu       100+ aday     (bekliyor, kimse tasimiyor)
    yedek capa havuzu      KALAN 0     -> "could not generate a
                                          sufficiently distinct topic"

⚠️ TERFI KOR OLMAMALI. Adayi arsiv arzina bakmadan tasimak kuyrugu
doldurur ama uretimi duzeltmez: konu uretilemezse koşum yine bos doner,
ustelik bu kez bir uretim slotu yakarak. Ilk canli kuru koşumda tam bunun
kanitI cikti — `Yeni` kuyrugundaki 40 adayin 40'i elendi (Rogelio
Mortimer menu 0, Franz Count of Meran 3, Henry Macandrew 3): huni KISI
konulari seciyor ve kisilerin arsiv arzi yok.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import huni_besle  # noqa: E402
import notion_kuyrugu  # noqa: E402


def _aday(baslik: str, kimlik: str = "k1") -> notion_kuyrugu.Aday:
    return notion_kuyrugu.Aday(
        kimlik=kimlik,
        baslik=baslik,
        sayfa_url="https://notion.example/x",
        onerilen_format="shorts",
        dil="en",
        bosluk_skoru=1.0,
        talep=5000,
    )


def _hazirla(monkeypatch, *, mevcut, yeni, menuler, kullanilmis=(), takilan=()):
    # ⚠️ Sahte kuyruk DURUMA duyarli olmali: `takilanlari_kurtar` ayni
    # fonksiyonu `durum="Üretiliyor"` ile cagiriyor. Durumu yok sayan bir
    # sahte, `Secildi` adaylarini "takilmis" sanip serbest biraktiriyordu.
    monkeypatch.setattr(
        notion_kuyrugu,
        "kuyrugu_oku",
        lambda **k: list(takilan if k.get("durum") == "Üretiliyor" else mevcut),
    )
    monkeypatch.setattr(huni_besle, "yeni_adaylar", lambda *_a, **_k: list(yeni))
    monkeypatch.setattr(huni_besle, "_kullanilmis_capalar", lambda: list(kullanilmis))
    monkeypatch.setattr(
        huni_besle.wikimedia_materials,
        "arsiv_menusu",
        lambda konu, sinir=40: [{"dosya": f"{konu}-{i}.jpg"} for i in range(menuler.get(konu, 0))],
    )
    secilenler: list[str] = []

    class _Sonuc:
        returncode = 0
        stderr = ""

    def sahte_kos(args, **_k):
        if args[1:3] == ["aday", "sec"]:
            secilenler.append(args[3])
        return _Sonuc()

    monkeypatch.setattr(huni_besle.subprocess, "run", sahte_kos)
    monkeypatch.setattr(huni_besle.notion_kuyrugu, "_ytoto_yolu", lambda _p: "ytoto")
    return secilenler


def test_arz_yeterse_TERFI_ediliyor(monkeypatch):
    secilen = _hazirla(
        monkeypatch,
        mevcut=[],
        yeni=[_aday("Alhambra", "a1")],
        menuler={"Alhambra": 30},
    )

    ozet = huni_besle.besle()

    assert ozet["terfi"] == ["Alhambra"]
    assert secilen == ["a1"], "Notion'a terfi cagrisi gitmeli"


def test_ARZ_YETMEZSE_terfi_YOK(monkeypatch):
    """⚠️ Asil kosul: kuyrugu doldurmak yetmez, URETILEBILIR doldurmali."""
    secilen = _hazirla(
        monkeypatch,
        mevcut=[],
        yeni=[_aday("Henry Macandrew", "a1")],
        menuler={"Henry Macandrew": 3},
    )

    ozet = huni_besle.besle()

    assert ozet["terfi"] == []
    assert secilen == [], "uretilemeyen konu Notion'a yazilmamali"


def test_esik_KARE_YUVASINA_bagli():
    """Iki yerde ayri sayi tutmak, kuyrugun kabul ettigi konunun havuzun
    reddettigi konu olmasi demek olurdu."""
    assert huni_besle.ASGARI_MENU == 6 * huni_besle.KARE_YUVASI == 12


def test_uretilmis_konuya_benzer_aday_atlaniyor(monkeypatch):
    secilen = _hazirla(
        monkeypatch,
        mevcut=[],
        yeni=[_aday("Great Sphinx", "a1")],
        menuler={"Great Sphinx": 40},
        kullanilmis=["Great Sphinx"],
    )

    assert huni_besle.besle()["terfi"] == []
    assert secilen == []


def test_kuyruk_DOLUYSA_hic_dokunulmuyor(monkeypatch):
    secilen = _hazirla(
        monkeypatch,
        mevcut=[_aday(f"k{i}", f"i{i}") for i in range(huni_besle.HEDEF_DERINLIK)],
        yeni=[_aday("Alhambra", "a1")],
        menuler={"Alhambra": 40},
    )

    ozet = huni_besle.besle()

    assert ozet["eksik"] == 0
    assert secilen == [], "dolu kuyrugu doldurmaya calismamali"


def test_yalnizca_EKSIK_kadar_terfi(monkeypatch):
    monkeypatch.setattr(huni_besle, "HEDEF_DERINLIK", 3)
    secilen = _hazirla(
        monkeypatch,
        mevcut=[_aday("var", "v1")],
        yeni=[_aday(f"Konu{i}", f"a{i}") for i in range(5)],
        menuler={f"Konu{i}": 40 for i in range(5)},
    )

    huni_besle.besle()

    assert len(secilen) == 2, "3 hedef - 1 mevcut = 2"


def test_kuru_kip_NOTIONA_yazmiyor(monkeypatch):
    secilen = _hazirla(
        monkeypatch,
        mevcut=[],
        yeni=[_aday("Alhambra", "a1")],
        menuler={"Alhambra": 40},
    )

    ozet = huni_besle.besle(kuru=True)

    assert ozet["terfi"] == ["Alhambra"], "kuru kipte de olcum raporlanmali"
    assert secilen == [], "kuru kipte Notion'a yazilmamali"


def test_menu_hatasi_koşumu_oldurmuyor(monkeypatch):
    """Ag hatasi tek adayi atlatmali, butun beslemeyi degil."""
    _hazirla(monkeypatch, mevcut=[], yeni=[_aday("X", "a1")], menuler={})

    def patlat(*_a, **_k):
        raise RuntimeError("ag koptu")

    monkeypatch.setattr(huni_besle.wikimedia_materials, "arsiv_menusu", patlat)

    assert huni_besle.besle()["terfi"] == []


def test_terfi_hatasi_digerlerini_engellemiyor(monkeypatch):
    """Bir aday terfi edemezse kalanlar denenmeli."""
    monkeypatch.setattr(notion_kuyrugu, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(
        huni_besle, "yeni_adaylar", lambda *_a, **_k: [_aday("A", "a1"), _aday("B", "a2")]
    )
    monkeypatch.setattr(huni_besle, "_kullanilmis_capalar", lambda: [])
    monkeypatch.setattr(
        huni_besle.wikimedia_materials, "arsiv_menusu", lambda k, sinir=40: [{}] * 40
    )
    monkeypatch.setattr(huni_besle.notion_kuyrugu, "_ytoto_yolu", lambda _p: "ytoto")
    gecen: list[str] = []

    class _Sonuc:
        def __init__(self, kod):
            self.returncode = kod
            self.stderr = "olmadi"

    def sahte(args, **_k):
        if args[3] == "a1":
            return _Sonuc(1)
        gecen.append(args[3])
        return _Sonuc(0)

    monkeypatch.setattr(huni_besle.subprocess, "run", sahte)

    ozet = huni_besle.besle()

    assert gecen == ["a2"]
    assert ozet["terfi"] == ["B"]


def test_TAKILAN_aday_kurtariliyor(monkeypatch):
    """⚠️ Olculdu (2026-08-16): `Ernst Hanfstaengl` 10 GUNDUR `Uretiliyor`da,
    `Video URL` bos. 6 Agustos'ta bir koşum kapip sonra olmus ve `adayi_birak`
    hic cagrilmamis. Kuyruk yalnizca `Secildi` okudugu icin o aday bir daha
    gorunmuyordu — sessiz kayip.

    Zaman damgasi gerekmiyor: besleyici uretimden ONCE ve ayni kilit altinda
    koşuyor, yani bu noktada `Uretiliyor` duran her kayit OKSUZ."""
    _hazirla(
        monkeypatch,
        mevcut=[_aday("Dolu", "d1")] * 6,
        yeni=[],
        menuler={},
        takilan=[_aday("Ernst Hanfstaengl", "takili-1")],
    )
    birakilan: list[str] = []
    monkeypatch.setattr(
        notion_kuyrugu,
        "adayi_birak",
        lambda aday, **_k: birakilan.append(aday.baslik),
    )

    huni_besle.besle()

    assert birakilan == ["Ernst Hanfstaengl"]


def test_KURU_kipte_takilan_aday_birakilmiyor(monkeypatch):
    """`--kuru` hicbir kosulda Notion'a yazmamali."""
    _hazirla(
        monkeypatch,
        mevcut=[_aday("Dolu", "d1")] * 6,
        yeni=[],
        menuler={},
        takilan=[_aday("Ernst Hanfstaengl", "takili-1")],
    )
    birakilan: list[str] = []
    monkeypatch.setattr(
        notion_kuyrugu,
        "adayi_birak",
        lambda aday, **_k: birakilan.append(aday.baslik),
    )

    huni_besle.besle(kuru=True)

    assert birakilan == []


def test_takilan_taranamazsa_besleme_SURUYOR(monkeypatch):
    """⚠️ Kurtarma bir IYILESTIRME; beslemeyi dusuremez."""
    _hazirla(
        monkeypatch,
        mevcut=[],
        yeni=[_aday("Karnak", "a1")],
        menuler={"Karnak": 20},
    )

    def patla(**k):
        if k.get("durum") == "Üretiliyor":
            raise RuntimeError("Notion kopuk")
        return []

    monkeypatch.setattr(notion_kuyrugu, "kuyrugu_oku", patla)

    assert huni_besle.besle()["terfi"] == ["Karnak"]
