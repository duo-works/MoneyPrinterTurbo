"""Kapilamayan aday koşumu OLDURMEZ, atlanir.

⚠️ Olculdu (2026-08-14, canli Notion). Veritabani sorgu indeksi bayat
kalabiliyor: `Durum = Seçildi` filtresi, sayfasi okununca `Elendi` gorunen
adaylari donduruyordu — Talaat Pasha ve Murad III, ikisi de saatler once
elenmis konular. Dogrudan sorulunca her ikisi icin de TEK sayfa var ve
durumu `Elendi`, yani mukerrer kayit degil indeks gecikmesi; birkac dakika
icinde ayni filtre 2 sayfadan 1'e dustu.

Eski kod `adaylar[0]`i alip kapiyor, kapayamazsa butun koşumu dusuruyordu.
Saat basi calisan bir zamanlayicida bu, bayat TEK bir kayit yuzunden
uretimin tamamen durmasi demek — ve gercekten de zamanlayici betigi ilk
denemede tam bu yuzden dustu.

⚠️ "Kapmadan uretme" guvencesi KORUNUYOR: kapilamayan aday uretilmiyor,
yalnizca atlaniyor. Tehlikeli olan tersi.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notion_kuyrugu  # noqa: E402
import youtube_automation as ya  # noqa: E402


def _aday(baslik: str) -> notion_kuyrugu.Aday:
    return notion_kuyrugu.Aday(
        kimlik=f"id-{baslik}",
        baslik=baslik,
        sayfa_url="",
        onerilen_format=None,
        dil=None,
        bosluk_skoru=None,
        talep=None,
    )


def _hat(monkeypatch, adaylar, kapilamayanlar, menuler=None):
    kapilan: list[str] = []

    def sahte_kap(aday, **_k):
        if aday.baslik in kapilamayanlar:
            raise notion_kuyrugu.KopruHatasi(
                f"aday kapilamadi ({aday.baslik}): durum 'Elendi', beklenen 'Seçildi'"
            )
        kapilan.append(aday.baslik)

    # ⚠️ Envanter TAKLIT EDILMELI: kapma artik olcumden geciyor ve gercek
    # `arsiv_envanteri` aga cikardi. Varsayilan bol (40), yani bu dosyanin
    # asil konusu — bayat kayit — olcumden etkilenmiyor.
    olculen = menuler or {}
    monkeypatch.setattr(
        ya,
        "arsiv_envanteri",
        lambda konu, **_k: [{"dosya": f"{konu}-{i}"} for i in range(olculen.get(konu, 40))],
    )
    monkeypatch.setattr(notion_kuyrugu, "kuyrugu_oku", lambda **_k: list(adaylar))
    monkeypatch.setattr(notion_kuyrugu, "adayi_kap", sahte_kap)
    monkeypatch.setattr(
        ya, "load_state", lambda: {"published": [], "rejected": [], "completed_slots": []}
    )
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    return kapilan


def test_bayat_aday_atlaniyor_sonraki_kapiliyor(monkeypatch):
    """Asil kosul: bayat kayit koşumu oldurmemeli."""
    kapilan = _hat(
        monkeypatch,
        [_aday("Talaat Pasha"), _aday("Gercek Aday")],
        kapilamayanlar={"Talaat Pasha"},
    )

    def dur(*_a, **_k):
        raise RuntimeError("PLAN ASAMASINA ULASILDI")

    monkeypatch.setattr(ya, "generate_content_plan", dur)

    try:
        ya.run_cycle(kuyruktan=True)
    except RuntimeError as hata:
        assert "ULASILDI" in str(hata)
    else:
        raise AssertionError("plan asamasina gecilmeliydi")

    assert kapilan == ["Gercek Aday"], "bayat aday atlanip sonraki kapilmaliydi"


def test_hicbiri_kapilamazsa_bayraksiz_DURUYOR(monkeypatch):
    """⚠️ Varsayilan davranis degismiyor: kuyruga bagliyim diyen hat, konu uydurmaz."""
    _hat(
        monkeypatch,
        [_aday("Talaat Pasha"), _aday("Murad III")],
        kapilamayanlar={"Talaat Pasha", "Murad III"},
    )

    sonuc = ya.run_cycle(kuyruktan=True)

    assert sonuc["status"] == "no-candidate"
    assert "Konu uydurulmadi" in sonuc["reason"]


def test_hicbiri_kapilamazsa_yedek_kipe_dusuluyor(monkeypatch, capsys):
    """Bayrak verilmisse slot bosa gitmemeli."""
    _hat(
        monkeypatch,
        [_aday("Talaat Pasha")],
        kapilamayanlar={"Talaat Pasha"},
    )

    def dur(*_a, **_k):
        raise RuntimeError("YEDEK KIPE ULASILDI")

    monkeypatch.setattr(ya, "generate_content_plan", dur)

    try:
        ya.run_cycle(kuyruktan=True, yedek_konu=True)
    except RuntimeError as hata:
        assert "ULASILDI" in str(hata)
    else:
        raise AssertionError("yedek kipe gecilmeliydi")

    cikti = capsys.readouterr().out
    assert "aday atlandı" in cikti, "atlama SESSIZ olmamali"
    assert "yedek konu kipi" in cikti


# --- Arsivi yetmeyen aday (2026-08-16) -----------------------------------


def test_ARSIVI_YETMEYEN_aday_KAPILMIYOR(monkeypatch, capsys):
    """⚠️ Olculdu (2026-08-16, iki koşum arka arkaya): `Ernst Hanfstaengl`
    `Secildi`de duruyordu ve uretim onu her slotta kuyrugun basinda buldu;
    18:00 ve 18:57 koşumlarinin ALTI denemesi de yandi (ikisi tam render).

        Ernst Hanfstaengl  menu  8   <- konu
        Franz Hanfstaengl  menu 40   <- DEDESI, 19. yy fotografcisi

    Uretim arsivi zengin olan dedeyi capa secti; bir fotografcinin Commons
    kategorisi kendi resimleriyle degil CEKTIGI kisilerle dolu oldugu icin
    hakem her karede baskasini gordu ("anlatilan kisi degil").

    ⚠️ Huni terfide olcuyordu ama kuyruga BASKA yollardan da aday giriyor
    (insan elle `Secildi` yapabiliyor, takilan aday kurtarilabiliyor), yani
    tuketen uc de olcmek zorunda.

    ⚠️ ESIK 2026-08-18'DE 12'DEN 6'YA INDI, yani ustteki 8 dosyalik Ernst
    ARTIK GECIYOR (bkz. `test_ESKI_ESIKTE_engellenen_aday_artik_geciyor`).
    Bu testin korudugu sey bir SAYI degil, kapinin VARLIGI: gercekten
    yetersiz bir arsiv hala atlanmali. Gerekce `arsiv_videoyu_tasir`da.

    ⚠️ HIPOTEZ, dogrulanmadi: capa ikamesini eski esigin KENDISI tetiklemis
    olabilir — model 12 dosyalik bir capa bulmak zorundaydi, Ernst 8
    veriyordu, dede 40. Esik 6'ya indigine gore o baski kalkti. Dogrulanacagi
    yer canli koşum: Ernst kapildiginda capa yine dedeye kayiyor mu.
    """
    kapilan = _hat(
        monkeypatch,
        [_aday("Ernst Hanfstaengl"), _aday("Tipasa")],
        kapilamayanlar=set(),
        menuler={"Ernst Hanfstaengl": 3},
    )

    def dur(*_a, **_k):
        raise RuntimeError("PLAN ASAMASINA ULASILDI")

    monkeypatch.setattr(ya, "generate_content_plan", dur)

    try:
        ya.run_cycle(kuyruktan=True)
    except RuntimeError as hata:
        assert "ULASILDI" in str(hata)
    else:
        raise AssertionError("plan asamasina gecilmeliydi")

    assert kapilan == ["Tipasa"], "arzi yetmeyen aday atlanip sonraki kapilmali"
    assert "arşiv menüsü 3" in capsys.readouterr().out, "atlama SESSIZ olmamali"


def test_ESKI_ESIKTE_engellenen_aday_artik_geciyor(monkeypatch):
    """⚠️ Gerilemenin YONU: 6-11 arasi menu ARTIK KAPILMALI.

    Canli olculdu (2026-08-18): kuyruktaki 6 adaydan biri (Ernst
    Hanfstaengl, menu 8) yalnizca eski 12 esigi yuzunden atlaniyordu.
    8 dosya 6 sahneye ayri birincil verir.
    """
    kapilan = _hat(
        monkeypatch,
        [_aday("Ernst Hanfstaengl")],
        kapilamayanlar=set(),
        menuler={"Ernst Hanfstaengl": 8},
    )

    def dur(*_a, **_k):
        raise RuntimeError("PLAN ASAMASINA ULASILDI")

    monkeypatch.setattr(ya, "generate_content_plan", dur)

    try:
        ya.run_cycle(kuyruktan=True)
    except RuntimeError:
        pass

    assert kapilan == ["Ernst Hanfstaengl"], "8 dosyalik aday artik kapilmali"


def test_arsivi_YETEN_aday_engellenMIYOR(monkeypatch):
    """⚠️ Sinir bekcisi: esik TAM degerde engellememeli."""
    kapilan = _hat(
        monkeypatch,
        [_aday("Tipasa")],
        kapilamayanlar=set(),
        # ⚠️ Sinir artik SAHNE BASINA BIR gorsel (6), yuva sayisi degil.
        menuler={"Tipasa": 6},
    )

    def dur(*_a, **_k):
        raise RuntimeError("PLAN ASAMASINA ULASILDI")

    monkeypatch.setattr(ya, "generate_content_plan", dur)

    try:
        ya.run_cycle(kuyruktan=True)
    except RuntimeError:
        pass

    assert kapilan == ["Tipasa"]


def test_arzi_yetmeyen_TEK_aday_yedek_kipe_dusuruyor(monkeypatch, capsys):
    """Slot bosa gitmemeli: yedek capa havuzu saglikli (50 uygun capa)."""
    _hat(
        monkeypatch,
        [_aday("Ernst Hanfstaengl")],
        kapilamayanlar=set(),
        menuler={"Ernst Hanfstaengl": 3},
    )

    def dur(*_a, **_k):
        raise RuntimeError("YEDEK KIPE ULASILDI")

    monkeypatch.setattr(ya, "generate_content_plan", dur)

    try:
        ya.run_cycle(kuyruktan=True, yedek_konu=True)
    except RuntimeError as hata:
        assert "ULASILDI" in str(hata)
    else:
        raise AssertionError("yedek kipe gecilmeliydi")

    assert "yedek konu kipi" in capsys.readouterr().out


def test_kapilan_aday_uretime_giriyor(monkeypatch):
    """Kapma basariliysa davranis eskisi gibi: o aday uretilir."""
    kapilan = _hat(monkeypatch, [_aday("Saglam Aday")], kapilamayanlar=set())
    yakalanan: dict = {}

    def yakala(*_a, **kwargs):
        yakalanan.update(kwargs)
        raise RuntimeError("dur")

    monkeypatch.setattr(ya, "generate_content_plan", yakala)

    try:
        ya.run_cycle(kuyruktan=True)
    except RuntimeError:
        pass

    assert kapilan == ["Saglam Aday"]
    assert yakalanan.get("konu") == "Saglam Aday"
