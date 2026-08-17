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
Mortimer menu 0, Franz Count of Meran 3, Henry Macandrew 3).

⚠️ O ELENMENIN SEBEBI 2026-08-17'de OLCULDU ve buradaki ilk teshis
("huni KISI konulari seciyor ve kisilerin arsiv arzi yok") YANLIS cikti.
Kuyrugun tamami olculdugunde sinif ile esik arasinda anlamli fark yoktu:

    yer/nesne   12+ gecen  25%      kisi   12+ gecen  24%

Yani kisi olmak tek basina eleme sebebi degil; `sinifa_gore_sirala` zaten
kisiyi sona atiyordu, dolayisiyla terfi eden aday kisi de OLMUYORDU —
hic terfi olmuyordu. Asil sebep PENCEREYDI (asagidaki testlerin basligi).
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
        menuler={"Ernst Hanfstaengl": 20},
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


def test_URETILEMEYEN_takilan_aday_KURTARILMIYOR(monkeypatch):
    """⚠️ Kurtarma bir TERFIDIR, ayni kapidan gecmeli.

    Olculdu (2026-08-16 aksami): kosulsuz kurtarilan `Ernst Hanfstaengl`
    `Secildi`ye geri kondu ve 18:00 slotunun UC denemesini de yakti (biri tam
    render). Konunun kendi menusu 8, kapi 12; uretim ise arsivi zengin olan
    DEDESINI (`Franz Hanfstaengl`, menu 40, 19. yy fotografcisi) capa secti ve
    hakem her karede baskasini gordu (Wagner, Rietschel, Ludwig II).
    """
    _hazirla(
        monkeypatch,
        mevcut=[_aday("Dolu", "d1")] * 6,
        yeni=[],
        menuler={"Ernst Hanfstaengl": 8},
        takilan=[_aday("Ernst Hanfstaengl", "takili-1")],
    )
    birakilan: list[str] = []
    monkeypatch.setattr(
        notion_kuyrugu,
        "adayi_birak",
        lambda aday, **_k: birakilan.append(aday.baslik),
    )

    huni_besle.besle()

    assert birakilan == [], "kapiyi gecemeyen aday kuyrugun basina konmamali"


def test_KURU_kipte_takilan_aday_birakilmiyor(monkeypatch):
    """`--kuru` hicbir kosulda Notion'a yazmamali."""
    _hazirla(
        monkeypatch,
        mevcut=[_aday("Dolu", "d1")] * 6,
        yeni=[],
        menuler={"Ernst Hanfstaengl": 20},
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


# --- Pencere ve olcum tavani (2026-08-17) ---------------------------------
#
# ⚠️ Dosyanin basindaki tesis "huni KISI konulari seciyor" diyordu. Olculdu
# ve YANLIS cikti: `sinifa_gore_sirala` kisiyi zaten sona atiyor, yani terfi
# eden aday kisi olmuyordu — hic terfi olmuyordu.
#
# Asil sebep PENCERE: kesme ytoto okumasinda (`--limit`), siralama yalnizca
# okunan dilimin icinde yer degistiriyor. `Yeni` kuyrugunun tamami (100 aday)
# olculdugunde esigi gecen 12 aday cikti ve 12'sinin de ham sirasi 40'in
# OTESINDEYDI (Ignatius of Loyola #87 menu 40, H. G. Wells #88 menu 35,
# King Philip's War #57 menu 16). Huni her koşumda listenin uretilemeyen
# basini tarayip 0 terfiyle donuyordu.


def test_PENCERE_ytotoya_gecen_limit(monkeypatch):
    """Genisletilen pencere OKUMAYA yansimali; yoksa hicbir sey degismez."""
    yakalanan: dict = {}

    class _Sonuc:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def sahte_kos(args, **_k):
        yakalanan["args"] = args
        return _Sonuc()

    monkeypatch.setattr(huni_besle.subprocess, "run", sahte_kos)
    monkeypatch.setattr(huni_besle.notion_kuyrugu, "_ytoto_yolu", lambda _p: "ytoto")
    monkeypatch.setattr(notion_kuyrugu, "sinifa_gore_sirala", lambda a: a)

    huni_besle.yeni_adaylar()

    assert "--limit" in yakalanan["args"]
    limit = yakalanan["args"][yakalanan["args"].index("--limit") + 1]
    assert limit == str(huni_besle.PENCERE)
    assert huni_besle.PENCERE > 40, "40'lik pencere olculen 12 adayin hicbirini gormuyordu"


def test_TAVAN_dolunca_ilerideki_aday_gorulmuyor(monkeypatch):
    """Tavanin ne yaptigini durust yaziyor: koruma bedava DEGIL.

    Tavani dolduracak kadar kotu aday varsa ilerideki iyi aday O KOŞUMDA
    kaciriliyor. Kabul edilen takas: besleme HER uretim slotunda kosuyor,
    yani kayip bir slotluk gecikme; tavansiz hal ~12 dakikalik besleme, yani
    uretimin kendisinin gecikmesi.
    """
    kotu = [_aday(f"Kotu{i}", f"k{i}") for i in range(huni_besle.OLCUM_TAVANI)]
    iyi = _aday("King Philip's War", "iyi")
    menuler = {f"Kotu{i}": 1 for i in range(len(kotu))}
    menuler["King Philip's War"] = 16

    secilenler = _hazirla(
        monkeypatch, mevcut=[], yeni=kotu + [iyi], menuler=menuler
    )

    ozet = huni_besle.besle()

    assert ozet["terfi"] == []
    assert ozet["tavana_carpti"] is True
    assert ozet["olcum"] == huni_besle.OLCUM_TAVANI
    assert secilenler == []


def test_tavan_ICINDEKI_iyi_aday_terfi_ediyor(monkeypatch):
    """Tavan ELEME DEGIL sinir: altinda kalan ayni dizilim terfi etmeli."""
    kotu = [_aday(f"Kotu{i}", f"k{i}") for i in range(huni_besle.OLCUM_TAVANI - 1)]
    iyi = _aday("King Philip's War", "iyi")
    menuler = {f"Kotu{i}": 1 for i in range(len(kotu))}
    menuler["King Philip's War"] = 16

    _hazirla(monkeypatch, mevcut=[], yeni=kotu + [iyi], menuler=menuler)

    ozet = huni_besle.besle()

    assert ozet["terfi"] == ["King Philip's War"]
    assert ozet["tavana_carpti"] is False


def test_BENZERLIK_elemesi_tavana_SAYILMIYOR(monkeypatch):
    """⚠️ `is_duplicate_visual_anchor` aga gitmiyor — tavan AG maliyeti icin.

    Benzerlik elemesini saymak, uzun bir 'benzeri uretilmis' serisinin
    tavani bosa doldurup gercek adaylari gormemesi demek olurdu.
    """
    benzer = [_aday("Palmyra", f"p{i}") for i in range(60)]
    iyi = _aday("King Philip's War", "iyi")

    _hazirla(
        monkeypatch,
        mevcut=[],
        yeni=benzer + [iyi],
        menuler={"King Philip's War": 16},
        kullanilmis=["Palmyra"],
    )

    ozet = huni_besle.besle()

    assert ozet["terfi"] == ["King Philip's War"], (
        "60 benzerlik elemesi aga gitmiyor, tavani doldurmamali"
    )
    assert ozet["olcum"] == 1, "yalnizca gercek olcum sayilmali"
    assert ozet["tavana_carpti"] is False


def test_tavan_dolunca_SESSIZ_kesilmiyor(monkeypatch, capsys):
    """'Kuyruk kuru' ile 'kuyrugu tarayamadim' ayni gorunmemeli."""
    kotu = [_aday(f"Kotu{i}", f"k{i}") for i in range(huni_besle.OLCUM_TAVANI + 5)]

    _hazirla(
        monkeypatch,
        mevcut=[],
        yeni=kotu,
        menuler={f"Kotu{i}": 1 for i in range(len(kotu))},
    )

    huni_besle.besle()

    assert "ölçüm tavanı" in capsys.readouterr().out


def test_olcum_TEMBEL_kalmali(monkeypatch):
    """Eksik kadar terfi bulununca olcum DURMALI — tavan bunu bozmamali."""
    yeni = [_aday(f"Iyi{i}", f"i{i}") for i in range(20)]

    _hazirla(
        monkeypatch,
        mevcut=[_aday("Var", "v1")] * 3,
        yeni=yeni,
        menuler={f"Iyi{i}": 20 for i in range(20)},
    )

    ozet = huni_besle.besle()

    assert len(ozet["terfi"]) == 3, "eksik 3, fazlasi terfi etmemeli"
    assert ozet["olcum"] == 3, "gereginden fazla Commons cagrisi yapilmamali"
