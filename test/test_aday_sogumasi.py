"""Reddedilen Notion adayi kuyrugun BASINA donmemeli (#38).

⚠️ NEDEN VAR — olculdu (2026-08-17), `state.json`. Kuyruk kipli 12 reddin
SEKIZI tek bir adaydaydi:

    8  King Philip's War    <- uc ayri slot; 14:00 slotu tek basina alti deneme
    4  Ernst Hanfstaengl

Dongu kapaliydi: `adayi_birak` adayi `Seçildi`ye geri cekiyor, `adaylari_getir`
`Boşluk skoru` DESCENDING siraliyor, skor degismedigi icin aday tam da geldigi
yere donuyor. Red bir sonuc dogurmuyordu.

⚠️ ERTELEME, ELEME DEGIL. Bu dosyanin korudugu asil sey bu: insanin
`Seçildi`ye aldigi aday sessizce cope atilamaz. Arsiv zamanla degisiyor —
bugun 8 dosyasi olan konunun yarin 40 dosyasi olabilir. `RET_DENEME_BUTCESI`
CAPA duzeyinde kalici kapatir; burasi ADAY duzeyinde yalnizca bekletir.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

TZ = ZoneInfo(ya.TIMEZONE_NAME)
SIMDI = datetime(2026, 8, 18, 12, 0, tzinfo=TZ)


def _red(baslik: str, *, saat_once: float, **fazlasi) -> dict:
    return {
        "aday_basligi": baslik,
        "rejected_at": (SIMDI - timedelta(hours=saat_once)).isoformat(),
        **fazlasi,
    }


def test_yeni_reddedilen_aday_SOGUMADA():
    durum = {"rejected": [_red("King Philip's War", saat_once=8)]}

    kalan = ya.aday_sogumada_mi("King Philip's War", durum, simdi=SIMDI)

    assert kalan > 0
    assert round(kalan, 1) == 16.0, "24 saatlik sogumanin 8'i gecmisti"


def test_sure_dolunca_aday_GERI_GELIYOR():
    """⚠️ Planin baglayici kisiti: erteleme, kalici eleme degil."""
    durum = {"rejected": [_red("King Philip's War", saat_once=25)]}

    assert ya.aday_sogumada_mi("King Philip's War", durum, simdi=SIMDI) == 0.0


def test_sinirda_TAM_24_saat_gecmis_aday_geri_geliyor():
    durum = {"rejected": [_red("Sinir Konusu", saat_once=24)]}

    assert ya.aday_sogumada_mi("Sinir Konusu", durum, simdi=SIMDI) == 0.0


def test_hic_reddedilmemis_aday_sogumada_DEGIL():
    durum = {"rejected": [_red("Baska Konu", saat_once=1)]}

    assert ya.aday_sogumada_mi("King Philip's War", durum, simdi=SIMDI) == 0.0


def test_EN_SON_red_sayiliyor_ilk_red_degil():
    """Alti denemeli bir slotta ilk red 6 saat once, sonuncusu 1 saat once."""
    durum = {
        "rejected": [
            _red("King Philip's War", saat_once=6),
            _red("King Philip's War", saat_once=1),
            _red("King Philip's War", saat_once=4),
        ]
    }

    kalan = ya.aday_sogumada_mi("King Philip's War", durum, simdi=SIMDI)

    assert round(kalan, 1) == 23.0, "en son red esas alinmaliydi"


def test_yayinlanan_aday_sogumaya_GIRMIYOR():
    """`published` okunmuyor: yayin bir basarisizlik degil."""
    durum = {
        "published": [{"aday_basligi": "Ellora Caves", "slot": "2026-08-17-21"}],
        "rejected": [],
    }

    assert ya.aday_sogumada_mi("Ellora Caves", durum, simdi=SIMDI) == 0.0


def test_buyuk_kucuk_harf_ve_bosluk_farki_ESLESMEYI_BOZMUYOR():
    durum = {"rejected": [_red("King Philip's War", saat_once=2)]}

    assert ya.aday_sogumada_mi("  king philip's WAR ", durum, simdi=SIMDI) > 0


# --- Gecis koprusu: `aday_basligi` alani 2026-08-17'de eklendi ---------------


def test_ESKI_kayit_huni_kaynakliysa_topic_uzerinden_eslesiyor():
    """⚠️ 235 eski kayitta `aday_basligi` YOK. Kuyruk kipinde model konuyu
    bazen aynen birakiyor ve `topic` aday basligina esitleniyor."""
    durum = {
        "rejected": [
            {
                "kaynak": "huni",
                "topic": "King Philip's War",
                "rejected_at": (SIMDI - timedelta(hours=3)).isoformat(),
            }
        ]
    }

    assert ya.aday_sogumada_mi("King Philip's War", durum, simdi=SIMDI) > 0


def test_ESKI_kayit_MODEL_kaynakliysa_topic_koprusu_CALISMIYOR():
    """⚠️ Yedek kipte `topic` modelin yazdigi cumle, bir Notion adayi degil.
    Koprüyü oraya da acmak, alakasiz adaylari sogutmak olurdu."""
    durum = {
        "rejected": [
            {
                "kaynak": "model",
                "topic": "Hadrian's Wall",
                "rejected_at": (SIMDI - timedelta(hours=1)).isoformat(),
            }
        ]
    }

    assert ya.aday_sogumada_mi("Hadrian's Wall", durum, simdi=SIMDI) == 0.0


def test_kopru_EKSIK_esleseceğini_biliyor_ve_bu_bilincli():
    """Hanfstaengl'in dort reddinde model konuyu yeniden yazmis; hicbiri aday
    basligina esit degil. Bulanik eslesme YANLIS adaylari soguturdu."""
    durum = {
        "rejected": [
            {
                "kaynak": "huni",
                "topic": (
                    "Ernst Hanfstaengl's defection from Nazi Germany and "
                    "later work for FDR"
                ),
                "rejected_at": (SIMDI - timedelta(hours=1)).isoformat(),
            }
        ]
    }

    assert ya.aday_sogumada_mi("Ernst Hanfstaengl", durum, simdi=SIMDI) == 0.0


# --- Dayaniklilik: soguma bir IYILESTIRME, uretimi dusuremez -----------------


def test_bozuk_zaman_damgasi_kosumu_DUSURMUYOR():
    durum = {
        "rejected": [
            {"aday_basligi": "Bozuk Kayit", "rejected_at": "dun aksam"},
            _red("Bozuk Kayit", saat_once=2),
        ]
    }

    assert ya.aday_sogumada_mi("Bozuk Kayit", durum, simdi=SIMDI) > 0


def test_zaman_damgasi_YOKSA_kayit_atlaniyor():
    durum = {"rejected": [{"aday_basligi": "Damgasiz"}]}

    assert ya.aday_sogumada_mi("Damgasiz", durum, simdi=SIMDI) == 0.0


def test_bos_baslik_hicbir_seyle_ESLESMIYOR():
    """Aksi halde `aday_basligi` bos olan her kayit her adayi soguturdu."""
    durum = {"rejected": [{"aday_basligi": "", "rejected_at": SIMDI.isoformat()}]}

    assert ya.aday_sogumada_mi("", durum, simdi=SIMDI) == 0.0
    assert ya.aday_sogumada_mi("Herhangi Bir Konu", durum, simdi=SIMDI) == 0.0


def test_saat_dilimsiz_damga_patlamiyor():
    """Eski kayitlarin bir kisminda damga naif olabilir; karsilastirma
    `TypeError` vermemeli."""
    naif = (SIMDI - timedelta(hours=2)).replace(tzinfo=None)
    durum = {"rejected": [{"aday_basligi": "Naif", "rejected_at": naif.isoformat()}]}

    assert ya.aday_sogumada_mi("Naif", durum, simdi=SIMDI) > 0


def test_soguma_suresi_BIR_GUNU_kapsiyor():
    """⚠️ Deger gerekceli: 24 saat bir gunun butun slotlarini kapsiyor, aday
    ertesi gun kendiliginden geri geliyor. Kisaltmak dongusu geri acar."""
    assert ya.ADAY_SOGUMA_SAATI == 24


# --- Kapi GERCEKTEN bagli mi: `run_cycle` uzerinden -------------------------
#
# ⚠️ Yukaridaki testlerin hicbiri kapinin BAGLI oldugunu gostermiyor; hepsi
# fonksiyonu dogrudan cagiriyor. Bu depoda "fonksiyon dogru, cagri yolu kopuk"
# sinifi kusur uc uretim koşumunu oldurdu (`test_onarim_dali_calisiyor.py`).
# Asagisi kuyruk dongusunun kendisini yurutuyor.


def _kuyruk_hatti(monkeypatch, tmp_path, adaylar, durum):
    kapilanlar: list[str] = []
    olculenler: list[str] = []

    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "LOCK_FILE", tmp_path / "automation.lock")
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(ya, "load_state", lambda: durum)
    monkeypatch.setattr(ya, "save_state", lambda _s: None)
    monkeypatch.setattr(
        ya.notion_kuyrugu, "kuyrugu_oku", lambda **_k: list(adaylar)
    )

    def _kap(aday, **_k):
        kapilanlar.append(aday.baslik)

    def _envanter(capa, **_k):
        olculenler.append(capa)
        return [
            {"dosya": f"{capa}-{i}.jpg", "gosterdigi": "nesne", "tarih": "1900"}
            for i in range(1, 20)
        ]

    monkeypatch.setattr(ya.notion_kuyrugu, "adayi_kap", _kap)
    monkeypatch.setattr(ya, "arsiv_envanteri", _envanter)
    monkeypatch.setattr(ya.notion_kuyrugu, "adayi_birak", lambda *_a, **_k: None)

    # ⚠️ PLANLAMA HER KOSULDA KESILIYOR — testin gecmesi icin degil, HERMETIK
    # olmasi icin. Olculdu: bu yama once yoktu ve mutasyon denemesinde
    # (kapiyi devre disi birakip testin dustugunu gormek) koşum ASILDI:
    # kapi calismayinca akis adayi kapip gercek `generate_content_plan`e
    # giriyor, o da aga cikiyor. Yani testin "gecmesi" kapinin calismasina
    # BAGLIYDI ve kapi bozuldugunda temiz bir hata yerine donma veriyordu.
    # Bir kapiyi test eden dosya, kapi bozuldugunda ANLASILIR sekilde
    # dusmeli.
    monkeypatch.setattr(
        ya,
        "generate_content_plan",
        lambda *_a, **_k: (_ for _ in ()).throw(
            ya.DistinctTopicUnavailableError("planlama testin kapsami disinda")
        ),
    )
    return kapilanlar, olculenler


def _aday(baslik: str):
    return ya.notion_kuyrugu.Aday(
        kimlik=f"kimlik-{baslik}",
        baslik=baslik,
        sayfa_url="",
        onerilen_format=None,
        dil="en",
        bosluk_skoru=80.0,
        talep=None,
    )


def test_SOGUMADAKI_aday_run_cycle_icinde_KAPILMIYOR(monkeypatch, tmp_path, capsys):
    durum = {
        "rejected": [
            {
                "aday_basligi": "King Philip's War",
                "rejected_at": ya.datetime.now(TZ).isoformat(),
            }
        ],
        "published": [],
        "completed_slots": [],
    }
    kapilanlar, _ = _kuyruk_hatti(
        monkeypatch, tmp_path, [_aday("King Philip's War")], durum
    )

    sonuc = ya.run_cycle(kuyruktan=True, dry_run=True)

    assert kapilanlar == [], "sogumadaki aday kapilmamaliydi"
    assert sonuc["status"] == "no-candidate"
    assert "soğumada" in sonuc["reason"], "gerekce kuyrugu BOS gibi gosteremez"
    assert "King Philip's War" in sonuc["reason"]
    assert "soğumada" in capsys.readouterr().out


def test_soguma_kapisi_AGDAN_OKUMADAN_once_eliyor(monkeypatch, tmp_path):
    """⚠️ Sira onemli: menu olcumu `arsiv_envanteri` ile agdan okuyor.
    Sogumadaki adayi once olcup sonra atlamak bos yere ag trafigi demek."""
    durum = {
        "rejected": [
            {
                "aday_basligi": "King Philip's War",
                "rejected_at": ya.datetime.now(TZ).isoformat(),
            }
        ],
        "published": [],
        "completed_slots": [],
    }
    _, olculenler = _kuyruk_hatti(
        monkeypatch, tmp_path, [_aday("King Philip's War")], durum
    )

    ya.run_cycle(kuyruktan=True, dry_run=True)

    assert olculenler == [], "sogumadaki aday icin arsiv OKUNMAMALIYDI"


def test_sogumadaki_aday_ATLANIP_sonrakine_geciliyor(monkeypatch, tmp_path):
    """Asil kazanc: soguma kuyrugu durdurmuyor, SIRADAKINE geciriyor."""
    durum = {
        "rejected": [
            {
                "aday_basligi": "King Philip's War",
                "rejected_at": ya.datetime.now(TZ).isoformat(),
            }
        ],
        "published": [],
        "completed_slots": [],
    }
    kapilanlar, _ = _kuyruk_hatti(
        monkeypatch,
        tmp_path,
        [_aday("King Philip's War"), _aday("Ellora Caves")],
        durum,
    )
    ya.run_cycle(kuyruktan=True, dry_run=True)

    assert kapilanlar == ["Ellora Caves"], "soguyan atlanip sonraki kapilmaliydi"


def test_PLANLAMA_dusunce_de_aday_sogumaya_giriyor(monkeypatch, tmp_path):
    """⚠️ SOGUMANIN UCUNCU CIKIS YOLU — olculdu (2026-08-18), canli koşumda.

    Soguma `state["rejected"]` okuyor. Plan uretilemeden dusen yol ise
    yalnizca `reviews`e yaziyordu, yani aday HIC sogumuyordu ve ertesi
    koşumda gene kuyrugun basindaydi.

    Canli ornek: 01:10 koşumu `Orkhon Yazıtları`ni kapti, bes denemenin dordu
    "capa arzi yetersiz" ile yandi (konu arsiv fakiri) ve `rejected` bos
    kaldi. Video ve kaynak asamalari icin ayni kusur bir tur once
    kapatilmisti; bu ucuncu yol atlanmisti.
    """
    durum = {"rejected": [], "published": [], "completed_slots": []}
    yazilan: list[dict] = []
    monkeypatch.setattr(ya, "save_state", lambda s: yazilan.append(s))
    _kuyruk_hatti(monkeypatch, tmp_path, [_aday("Orkhon Yazıtları")], durum)

    sonuc = ya.run_cycle(kuyruktan=True)

    assert sonuc["status"] == "rejected"
    kayitlar = durum.get("rejected", [])
    assert kayitlar, "planlama reddi kayda gecmeliydi"
    assert kayitlar[-1]["aday_basligi"] == "Orkhon Yazıtları"
    assert kayitlar[-1]["stage"] == "planning"
    assert ya.aday_sogumada_mi("Orkhon Yazıtları", durum) > 0, "aday sogumaliydi"


def test_planlama_reddi_CAPA_YAKMIYOR(monkeypatch, tmp_path):
    """⚠️ Kayitta capa BOS: plan hic kurulamadi, gecerli bir capa yok.

    Bos capa `engellenen_capalar`a girmemeli — aksi halde planlama hatasi
    sessizce bir capayi omur boyu yasaklardi.
    """
    durum = {"rejected": [], "published": [], "completed_slots": []}
    monkeypatch.setattr(ya, "save_state", lambda _s: None)
    _kuyruk_hatti(monkeypatch, tmp_path, [_aday("Orkhon Yazıtları")], durum)

    ya.run_cycle(kuyruktan=True)

    assert durum["rejected"][-1]["visual_anchor"] == ""
    assert ya.engellenen_capalar(durum) == []


def test_DRY_RUN_planlama_reddini_KAYDETMIYOR(monkeypatch, tmp_path):
    """Kuru koşum durumu kirletmemeli; diger iki kayit yolu da boyle."""
    durum = {"rejected": [], "published": [], "completed_slots": []}
    monkeypatch.setattr(ya, "save_state", lambda _s: None)
    _kuyruk_hatti(monkeypatch, tmp_path, [_aday("Orkhon Yazıtları")], durum)

    ya.run_cycle(kuyruktan=True, dry_run=True)

    assert durum["rejected"] == []


def test_SOGUMAMIS_aday_normal_kapiliyor(monkeypatch, tmp_path):
    """Kapinin yalnizca soguyanlari eledigini gosteren karsit ornek."""
    durum = {
        "rejected": [
            {
                "aday_basligi": "King Philip's War",
                "rejected_at": (
                    ya.datetime.now(TZ) - timedelta(hours=30)
                ).isoformat(),
            }
        ],
        "published": [],
        "completed_slots": [],
    }
    kapilanlar, _ = _kuyruk_hatti(
        monkeypatch, tmp_path, [_aday("King Philip's War")], durum
    )
    ya.run_cycle(kuyruktan=True, dry_run=True)

    assert kapilanlar == ["King Philip's War"], "30 saat gecmisti, kapilmaliydi"
