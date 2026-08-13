"""Kuyruk bosken slot bosa gitmesin — ama geri dusus SESSIZ OLMASIN.

⚠️ Buradaki denge onemli. `run_cycle`'daki eski yorum hakliydi: sessiz geri
dusus, "kuyruga bagliyim" sanan ama kendi konusunu ureten bir hat demek ve
bu hic baglanmamis olmaktan kotudur, cunku fark edilmiyor. Bu yuzden geri
dusus:

  · yalnizca `--yedek-konu` verilirse calisir (varsayilan davranis AYNI),
  · kaydina `kaynak: yedek` yazar ve stdout'a basar.

Neden degerli: olculdu (2026-08-13), model-secimli anit/yer konulari 70-90
skor ve 0-3 kusurla gecti; ayni donemde huniden gelen kisi konulari 68-84
ve 9-11 kusur aldi.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _bos_kuyruk(monkeypatch):
    monkeypatch.setattr(ya.notion_kuyrugu, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(ya, "load_state", lambda: {"published": [], "rejected": [], "completed_slots": []})


def test_bayraksiz_davranis_degismiyor(monkeypatch):
    """⚠️ Varsayilan AYNI kalmali: bayrak yoksa kosum durur."""
    _bos_kuyruk(monkeypatch)

    sonuc = ya.run_cycle(kuyruktan=True)

    assert sonuc["status"] == "no-candidate"
    assert "Konu uydurulmadi" in sonuc["reason"]


def test_bayrakla_uretime_devam_ediliyor(monkeypatch, capsys):
    """Bayrak verilince kuyruk bos olsa da kosum ilerler."""
    _bos_kuyruk(monkeypatch)

    def dur(*_a, **_k):
        raise RuntimeError("plan asamasina ULASILDI")

    # Kilit `finally` icinde `LOCK_FILE.unlink(missing_ok=True)` ile
    # birakiliyor; ayri bir serbest birakma fonksiyonu yok.
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "generate_content_plan", dur)

    try:
        ya.run_cycle(kuyruktan=True, yedek_konu=True)
    except RuntimeError as hata:
        assert "ULASILDI" in str(hata), "yedek kipte plan asamasina gecilmeliydi"
    else:
        raise AssertionError("kosum durmamaliydi")


def test_geri_dusus_sessiz_degil(monkeypatch, capsys):
    """⚠️ Bu testin konusu: fark edilebilirlik.

    Eski tasarim geri dususe bilerek izin vermiyordu cunku sessiz olurdu.
    Izin veriyorsak, gorunur olmak zorunda.
    """
    _bos_kuyruk(monkeypatch)
    # Kilit `finally` icinde `LOCK_FILE.unlink(missing_ok=True)` ile
    # birakiliyor; ayri bir serbest birakma fonksiyonu yok.
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(
        ya, "generate_content_plan", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("dur"))
    )

    try:
        ya.run_cycle(kuyruktan=True, yedek_konu=True)
    except RuntimeError:
        pass

    assert "yedek konu kipi" in capsys.readouterr().out


def test_kaynak_alani_kayda_yaziliyor():
    """Arayuz ve rapor `kaynak` ile kirilim yapiyor; alan kaydin parcasi olmali."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert '"kaynak": kaynak' in kaynak
    assert kaynak.count('"kaynak": kaynak') >= 3, "yayin ve iki red kaydinda da olmali"


def test_red_kayitlari_slot_tasiyor():
    """⚠️ 120 reddedilmis kaydin hicbiri zaman dilimiyle iliskilendirilemiyordu."""
    # ⚠️ Capa `state.setdefault("rejected"` — `"stage": "source_materials"`
    # iki yerde geciyor ve ilki bellekteki `reviews` listesi, kalici kayit
    # degil. Yanlis capa testi yesil/kirmizi acisindan yaniltir.
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    capa = 'state.setdefault("rejected", []).append('
    yerler = []
    konum = kaynak.find(capa)
    while konum != -1:
        yerler.append(konum)
        konum = kaynak.find(capa, konum + 1)

    assert len(yerler) == 2, f"iki kalici red kaydi bekleniyordu, {len(yerler)} bulundu"
    for konum in yerler:
        govde = kaynak[konum : konum + 900]
        assert '"slot": slot' in govde, "her kalici red kaydi slot tasimali"
        assert '"kaynak": kaynak' in govde


def test_cli_bayragi_hatta_bagli():
    """Baglanti testi — bayrak tanimlansa bile `run_cycle`a gecmezse islevsiz."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert '"--yedek-konu"' in kaynak
    assert "yedek_konu=args.yedek_konu" in kaynak
