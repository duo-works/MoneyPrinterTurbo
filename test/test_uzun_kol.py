"""Zamanlanmis UZUN KOL — 00:05 slotu uzun video uretebiliyor mu.

⚠️ NEDEN VAR. 2026-08-22'ye kadar hattin uzun kolu YOKTU: `--uzun` hicbir
betikte gecmiyordu, 31 yayinin 2'si uzundu ve ikisi de ELLE uretilmisti.
Kol baglanirken uc ayri bloker olculdu ve ucu de "kapi, tuketicinin
kullandigindan baska bir sayiyi olcuyor" ailesinden:

    1. `ikinci_gorsel_istenebilir` global KARE_YUVASI=2 okuyordu, oysa
       `UZUN_BICIMI.kare_yuvasi = 1` -> kapi 28 sahne icin 56 dosya
       istiyordu ve havuzun EN ZENGIN sekiz capasi da dusuyordu.
    2. Kapma kapisi uzun kolda `ASGARI_SAHNE_ARZI` = 6 varsayiyordu, oysa
       uzun video 24-28 sahne -> menusu 6 dosyalik aday kapiliyor ve plan
       asamasinda kesin reddedilip slotu yakiyordu.
    3. Uzun kol basarisiz olunca SHORTS'A dusuyordu — kanal sahibinin
       karari bunu yasakliyor ("uzun israr et"): 00:05 slotu uzun-ya-da-hic.

⚠️ Testler METNE CAKILMIYOR, kodu KOSTURUYOR. Bu dosyanin kardesi
`test_uzun_hat.py` baglanti testi oldugu icin metne bakiyor ve tam bu
turda iki testi yalnizca ifade degistigi icin dustu.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _menu(n: int) -> list[dict[str, str]]:
    return [{"dosya": f"{i:03d}.jpg", "gosterdigi": "x"} for i in range(n)]


def _bos_durum() -> dict[str, list]:
    return {"published": [], "rejected": [], "completed_slots": []}


# --- §1 · `ikinci_gorsel_istenebilir` yuvayi PARAMETRE aliyor --------------


def test_uzun_menusu_49_YETIYOR():
    """Alhambra'nin birebir sayisi: 49 girdi, 28 sahne, sahne basina TEK kare.

    ⚠️ Mutasyon: `yuva`yi global `KARE_YUVASI`ye geri sabitlemek bu testi
    dusurur — 49 < 56 olur ve capa yine secilmez.
    """
    assert ya.ikinci_gorsel_istenebilir(_menu(49), 28, yuva=1)


def test_ayni_menu_SHORTS_yuvasiyla_YETMIYOR():
    """Ayni menu, ayni sahne sayisi, yalnizca yuva 2: olcut gercekten
    `yuva`dan geliyor mu — yoksa hep mi `True` donuyor."""
    assert not ya.ikinci_gorsel_istenebilir(_menu(49), 28, yuva=2)


def test_VARSAYILAN_yuva_shorts_yuvasi():
    """⚠️ REGRESYON KILIDI. `yuva` gecmeyen her cagiran bugunku davranisi
    almali; varsayilani 1 yapmak Shorts'ta ikinci gorsel baskisini
    sessizce kaldirirdi (kapattigi gerileme `alinti_kusuru`de olculmus).

    Mutasyon: varsayilani 1 yapmak bu testi dusurur.
    """
    assert not ya.ikinci_gorsel_istenebilir(_menu(11), 6)
    assert ya.ikinci_gorsel_istenebilir(_menu(12), 6)


def test_yedek_capa_UZUN_bicimin_yuvasini_geciriyor(monkeypatch):
    """⚠️ Asil bloker buydu: `_yedek_capa_sec` kapiyi cagirirken bicimin
    yuvasini gecirmezse uzun kipte HICBIR capa secilmiyor.

    Mutasyon: `yuva=bicim.kare_yuvasi`yi kaldirmak bu testi dusurur.
    """
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda *_a, **_k: _menu(49))
    monkeypatch.setattr(ya, "ayrik_arz_yeter_mi", lambda *_a, **_k: True)

    secilen = ya._yedek_capa_sec(
        ["Alhambra"],
        bicim=ya.UZUN_BICIMI,
        envanter_sinir=ya.envanter_siniri(ya.UZUN_BICIMI),
        sahne_sayisi=None,
    )

    assert secilen == "Alhambra"


def test_yedek_capa_SHORTS_ta_hala_ELIYOR(monkeypatch):
    """Regresyon kilidi: Shorts'ta 11 girdilik menu 6 sahneye yetmiyor."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda *_a, **_k: _menu(11))
    monkeypatch.setattr(ya, "ayrik_arz_yeter_mi", lambda *_a, **_k: True)

    secilen = ya._yedek_capa_sec(
        ["Alhambra"],
        bicim=ya.SHORTS_BICIMI,
        envanter_sinir=ya.envanter_siniri(ya.SHORTS_BICIMI),
        sahne_sayisi=6,
    )

    assert secilen == ""


# --- §2 · Kapma kapisi BICIMIN kendi tabanini goruyor ----------------------


def _kapma_gereken(monkeypatch, *, bicim, sahne_sayisi):
    """`run_cycle`in kapma kapisina GERCEKTEN gecirdigi sahne sayisi."""
    gorulen: list[int | None] = []

    class _Aday:
        baslik = "Test Konusu"

    monkeypatch.setattr(ya, "load_state", _bos_durum)
    monkeypatch.setattr(ya.notion_kuyrugu, "kuyrugu_oku", lambda **_k: [_Aday()])
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)

    def _kapi(_baslik, _state, *, bicim=None, sahne_sayisi=None):
        gorulen.append(sahne_sayisi)
        return ya.KapmaKarari(False, "test", "arsiv")

    monkeypatch.setattr(ya, "aday_kapilabilir_mi", _kapi)

    ya.run_cycle(kuyruktan=True, bicim=bicim, sahne_sayisi=sahne_sayisi)
    return gorulen


def test_UZUN_kolda_kapma_kapisi_24_istiyor(monkeypatch):
    """⚠️ Uzun kolda `--sahne-sayisi` CLI'da yasak, yani deger None geliyor
    ve kapi `ASGARI_SAHNE_ARZI` = 6'ya dusuyordu: menusu 6 dosyalik aday
    28 SAHNELIK bir video icin kapilabilir sayiliyordu.

    Mutasyon: `bicim.sahne_araligi[0]` yerine `ASGARI_SAHNE_ARZI` koymak
    bu testi dusurur.
    """
    assert _kapma_gereken(monkeypatch, bicim=ya.UZUN_BICIMI, sahne_sayisi=None) == [24]


def test_SHORTS_kolunda_kapma_kapisi_DEGISMEDI(monkeypatch):
    """Regresyon kilidi: `uret.sh` her Shorts koşumunda `--sahne-sayisi`
    geciyor, yani `or` dali hic calismamali."""
    assert _kapma_gereken(monkeypatch, bicim=ya.SHORTS_BICIMI, sahne_sayisi=8) == [8]


def test_SHORTS_ta_sahne_sayisi_yoksa_UZUN_tabani_UYGULANMIYOR(monkeypatch):
    """⚠️ Mutasyon kilidi: uzun tabani (24) Shorts'a da uygulamak bu testi
    dusurur — Shorts'un kendi tabani 6."""
    assert _kapma_gereken(monkeypatch, bicim=ya.SHORTS_BICIMI, sahne_sayisi=None) == [6]


# --- §3a · Uzun kol SHORTS'A DUSMUYOR -------------------------------------


def _uzun_kosum(monkeypatch, plan_hatasi):
    """Uzun kolda plan uretimi `plan_hatasi` ile duserse ne oluyor."""
    denenen: list[str] = []

    monkeypatch.setattr(ya, "load_state", _bos_durum)
    monkeypatch.setattr(ya.notion_kuyrugu, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "save_state", lambda _d: None)
    monkeypatch.setattr(ya, "_yedek_capa_sec", lambda *_a, **_k: "Petra")

    def _plan(*_a, **kwargs):
        denenen.append(kwargs["bicim"].ad)
        raise plan_hatasi

    monkeypatch.setattr(ya, "generate_content_plan", _plan)

    sonuc = ya.run_cycle(kuyruktan=True, yedek_konu=True, bicim=ya.UZUN_BICIMI)
    return sonuc, denenen


def test_uzun_format_uygun_degilse_SHORTS_DENENMIYOR(monkeypatch):
    """⚠️ KANAL SAHIBININ KARARI: "uzun israr et" — 00:05 slotu uzun-ya-da-hic.

    Eski davranis `denenecek = [bicim, SHORTS_BICIMI]` ile Shorts'a
    dusuyordu; uzun slottan Shorts cikmasi, istenen sey ile uretilen seyin
    sessizce ayrismasi demekti.

    Mutasyon: listeye `SHORTS_BICIMI`i geri eklemek bu testi dusurur.
    """
    sonuc, denenen = _uzun_kosum(
        monkeypatch, ya.UzunFormatUygunDegilError("arsiv ince")
    )

    assert denenen == [ya.UZUN_BICIMI.ad], f"Shorts denendi: {denenen}"
    assert sonuc["status"] == "rejected"


def test_uzun_format_uygun_degilse_GERCEK_SEBEP_kayda_geciyor(monkeypatch):
    """⚠️ Shorts'a gecmemek, SESSIZCE olmek anlamina gelmemeli — ve "kayit
    var mi" sormak YETMIYOR.

    Olculdu (mutasyon M9): `planlama_hatasi` atamasini kaldirip `continue`
    demek kaydin VARLIGINI degistirmiyor, cunku dongu bitince akis yine
    `plan is None` daline duşuyor. Degisen sey kaydin GEREKCESI: gercek
    sebep ("arsivde 12 gorsel var") yerine jenerik "hicbir bicim icin plan
    uretilemedi" yaziliyor.

    Yani kusur gorunmez degil, YANLIS ADLANDIRILMIS oluyor — deponun imza
    kusurunun rapor tarafindaki hali. Test bu yuzden ozgun mesaji ariyor.
    """
    sonuc, _ = _uzun_kosum(
        monkeypatch, ya.UzunFormatUygunDegilError("arsivde 12 gorsel var")
    )

    kayitlar = sonuc.get("reviews") or []
    planlama = [k for k in kayitlar if k.get("stage") == "planning"]
    assert planlama, sonuc

    notlar = " ".join(planlama[0]["review"]["issues"])
    assert "arsivde 12 gorsel var" in notlar, (
        f"gercek sebep kayda gecmiyor, jenerik mesaj yazilmis: {notlar!r}"
    )


def test_konu_yoksa_HAVUZ_CAPASI_konu_oluyor(monkeypatch):
    """⚠️ Eski davranis burada `bicim = SHORTS_BICIMI` diyordu. Yeni davranis
    konuyu havuzdan SABITLIYOR — `--konu`nun sagladigi kosulun aynisi.

    Mutasyon: capa sabitlemeyi kaldirip Shorts'a dusmek bu testi dusurur.
    """
    gorulen: list[str | None] = []

    monkeypatch.setattr(ya, "load_state", _bos_durum)
    monkeypatch.setattr(ya.notion_kuyrugu, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "save_state", lambda _d: None)
    monkeypatch.setattr(ya, "_yedek_capa_sec", lambda *_a, **_k: "Petra")

    def _plan(*_a, **kwargs):
        gorulen.append(kwargs.get("konu"))
        raise ya.DistinctTopicUnavailableError("dur")

    monkeypatch.setattr(ya, "generate_content_plan", _plan)

    ya.run_cycle(kuyruktan=True, yedek_konu=True, bicim=ya.UZUN_BICIMI)

    assert gorulen == ["Petra"]


def test_capa_SABITLENEMEZSE_kosum_DURUYOR(monkeypatch):
    """⚠️ Garantinin kendisi: capa yoksa modele SERBEST konu urettirilmiyor.

    Konusuz uzun plan 2.000 kelimeyi hafizadan yazar (DW-114) ve uydurma
    uzun formatta kelime SAYISIYLA olcekleniyor.

    Mutasyon: bos capada plan uretimine devam etmek bu testi dusurur.
    """
    monkeypatch.setattr(ya, "load_state", _bos_durum)
    monkeypatch.setattr(ya.notion_kuyrugu, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "_yedek_capa_sec", lambda *_a, **_k: "")

    def _patlat(*_a, **_k):
        raise AssertionError("capa yokken plan uretilmemeliydi")

    monkeypatch.setattr(ya, "generate_content_plan", _patlat)

    sonuc = ya.run_cycle(kuyruktan=True, yedek_konu=True, bicim=ya.UZUN_BICIMI)

    assert sonuc["status"] == "no-candidate"
    assert "uydurulmadi" in sonuc["reason"]


def test_uygun_capalar_TEK_KAYNAK(monkeypatch):
    """⚠️ Liste iki yerde geziliyor (`generate_content_plan` yedek dali ve
    `run_cycle` uzun kolu). Iki ayri kurulum, biri `engellenen_capalar`i
    okumazsa yakilmis capayi yeniden secerdi.

    Mutasyon: `uygun_capalar`i baypas edip havuzu dogrudan gezmek bu testi
    dusurur.
    """
    monkeypatch.setattr(ya, "EDITORIAL_ANCHOR_POOL", ["Petra", "Alhambra"])
    monkeypatch.setattr(ya, "engellenen_capalar", lambda _s: ["Petra"])

    assert ya.uygun_capalar({}) == ["Alhambra"]


# --- §3b · CLI yasagi DARALDI, kalkmadi -----------------------------------


def _cli(monkeypatch, argv):
    """`main()`i gercekten koşturur; `run_cycle`a ULASILDI mi doner."""
    ulasildi: list[dict] = []
    monkeypatch.setattr(sys, "argv", ["youtube_automation.py", *argv])
    monkeypatch.setattr(
        ya, "run_cycle", lambda **kwargs: ulasildi.append(kwargs) or {"status": "ok"}
    )
    ya.main()
    return ulasildi


def test_uzun_YEDEK_KONU_kabul_ediliyor(monkeypatch):
    """⚠️ Mutasyon: yasagi geri koymak (`or args.yedek_konu`yu silmek) bu
    testi dusurur — `parser.error` `SystemExit` atar."""
    ulasildi = _cli(monkeypatch, ["--uzun", "--yedek-konu"])

    assert len(ulasildi) == 1
    assert ulasildi[0]["yedek_konu"] is True
    assert ulasildi[0]["bicim"] is ya.UZUN_BICIMI


def test_uzun_KONUSUZ_hala_REDDEDILIYOR(monkeypatch):
    """⚠️ Yasak KALKMADI: uc konu kaynagindan hicbiri yoksa hata veriyor."""
    with pytest.raises(SystemExit) as hata:
        _cli(monkeypatch, ["--uzun"])

    assert hata.value.code == 2


def test_uzun_SAHNE_SAYISI_yasagi_DURUYOR(monkeypatch):
    """⚠️ Regresyon kilidi: sahne sayisi deneyi Shorts koluna ait ve uzun
    kolda `uret.sh` bu bayragi GECMEMELI."""
    with pytest.raises(SystemExit) as hata:
        _cli(monkeypatch, ["--uzun", "--yedek-konu", "--sahne-sayisi", "8"])

    assert hata.value.code == 2
