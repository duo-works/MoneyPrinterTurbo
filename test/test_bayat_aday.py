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


def _hat(monkeypatch, adaylar, kapilamayanlar):
    kapilan: list[str] = []

    def sahte_kap(aday, **_k):
        if aday.baslik in kapilamayanlar:
            raise notion_kuyrugu.KopruHatasi(
                f"aday kapilamadi ({aday.baslik}): durum 'Elendi', beklenen 'Seçildi'"
            )
        kapilan.append(aday.baslik)

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
