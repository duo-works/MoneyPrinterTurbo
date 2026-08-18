"""Kod degisince ESKI redler adayi sogutmamali.

⚠️ NEDEN VAR — soguma sessiz bir varsayim tasiyor: "ayni aday, ayni kosullar,
ayni sonuc". Varsayim bir KOD DEGISIKLIGI reddin sebebini ortadan kaldirinca
BOZULUYOR ve soguma bir koruma degil bir ENGEL oluyor: duzeltilmis bir kusur
yuzunden aday 24 saat daha bekliyor.

⚠️ Olculdu 2026-08-18: `Secildi` kuyrugunda 6 aday vardi ve uretim koşumu
UCUNU birden sogumada buldu (King Philip's War 7,1 sa · Cemal Bajá 11,9 sa ·
Köktürk 16,0 sa). Redlerinin sebepleri o gece kapanmisti:

    #43 (`49826ee`)  esik alti render artik konuyu yakmiyor, onariliyor
    #44 (`e9f681b`)  kucuk arsivde ikinci gorsel artik isteniyor
    #46 (`bd5953a`)  arsiv esigi 12 -> 6

Yani kuyruk, ARTIK GECERLI OLMAYAN redler yuzunden kuruydu ve koşum yedek
kipe dusuyordu.

⚠️ KAYITLAR SILINMIYOR. `state["rejected"]` bir denetim izi ve bu oturumda
birden fazla teshis ondan cikti (aday basligi eslesmesi, skor dagilimi,
yeniden planlamanin yazi-tura oldugu). Damga yalnizca SOGUMANIN penceresini
daraltiyor.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

BOLGE = ZoneInfo(ya.TIMEZONE_NAME)


def _an(saat_once: float) -> str:
    return (datetime.now(BOLGE) - timedelta(hours=saat_once)).isoformat()


def _durum(*, red_saat_once: float, damga_saat_once: float | None = None) -> dict:
    durum = {
        "rejected": [
            {
                "stage": "video",
                "kaynak": "huni",
                "aday_basligi": "Köktürk",
                "topic": "Köktürk",
                "rejected_at": _an(red_saat_once),
            }
        ]
    }
    if damga_saat_once is not None:
        durum["soguma_gecerlilik"] = _an(damga_saat_once)
    return durum


# --- Damga yokken eski davranis ---------------------------------------------


def test_DAMGA_YOKKEN_davranis_AYNI():
    """⚠️ Varsayilan degismemeli: damga yoksa soguma eskisi gibi calisir."""
    durum = _durum(red_saat_once=2)

    assert ya.aday_sogumada_mi("Köktürk", durum) > 0


def test_damga_BOZUKSA_soguma_KAPANMIYOR():
    """⚠️ Bozuk bir damga sogumayi tamamen kapatirsa, tek bir elle duzenleme
    #38'in kapattigi dongunun tamamini geri acardi."""
    durum = _durum(red_saat_once=2)
    durum["soguma_gecerlilik"] = "bu bir tarih degil"

    assert ya.aday_sogumada_mi("Köktürk", durum) > 0


# --- Damga isini yapiyor ----------------------------------------------------


def test_damgadan_ESKI_red_sogutmuyor():
    """Asil is: red 2 saat once, damga 1 saat once -> aday SERBEST."""
    durum = _durum(red_saat_once=2, damga_saat_once=1)

    assert ya.aday_sogumada_mi("Köktürk", durum) == 0
    assert ya.adayin_son_reddi("Köktürk", durum) is None


def test_damgadan_YENI_red_HALA_sogutuyor():
    """⚠️ Sinir bekcisi: sifirlama gecmisi siliyor, GELECEGI degil. Damgadan
    sonraki bir red yine 24 saat sogutmali, yoksa #38'in kapattigi dongu
    (reddedilen aday kuyrugun basina donuyor) geri acilirdi."""
    durum = _durum(red_saat_once=1, damga_saat_once=2)

    assert ya.aday_sogumada_mi("Köktürk", durum) > 0


def test_damga_ADAY_AYIRT_ETMIYOR():
    """Sifirlama toptan: bir kod degisikligi butun adaylarin kosullarini
    degistirir, tek bir adayinkini degil."""
    durum = {
        "soguma_gecerlilik": _an(1),
        "rejected": [
            {"kaynak": "huni", "aday_basligi": ad, "rejected_at": _an(2)}
            for ad in ("Köktürk", "Cemal Bajá", "King Philip's War")
        ],
    }

    for ad in ("Köktürk", "Cemal Bajá", "King Philip's War"):
        assert ya.aday_sogumada_mi(ad, durum) == 0, f"{ad} hala sogumada"


def test_ESKI_KAYITLAR_silinmiyor():
    """⚠️ Denetim izi korunmali: bu oturumda uc teshis `rejected`ten cikti."""
    durum = _durum(red_saat_once=2, damga_saat_once=1)

    ya.aday_sogumada_mi("Köktürk", durum)

    assert len(durum["rejected"]) == 1, "kayit silinmis"


# --- Capa butcesi de damgayi okuyor -----------------------------------------
#
# ⚠️ NEDEN — olculdu 2026-08-18, sogumayi sifirladiktan HEMEN SONRA.
# `King Philip's War` kuyruktan cekildi (yani soguma sifirlamasi calisti) ama
# BES DENEMESININ IKISI capa engeline carpti:
#
#     deneme 1  capa daha once kullanilmis: 'Metacom'
#     deneme 3  capa daha once kullanilmis: 'Mount Hope'
#
# Adayin sekiz eski reddi tam bu iki capada birikmisti (`RET_DENEME_BUTCESI`
# = 3). Yani soguma sifirlansa bile aday kendi dogal capalarini kullanamiyor
# ve "yanan adayi yeniden dene" fiilen imkansiz kaliyordu.


def _capa_durumu(*, red_saat_once: float, damga_saat_once: float | None = None) -> dict:
    durum = {
        "published": [],
        "rejected": [
            {"visual_anchor": "Metacom", "rejected_at": _an(red_saat_once)}
            for _ in range(ya.RET_DENEME_BUTCESI)
        ],
    }
    if damga_saat_once is not None:
        durum["soguma_gecerlilik"] = _an(damga_saat_once)
    return durum


def test_damga_YOKKEN_capa_butcesi_ESKISI_GIBI():
    durum = _capa_durumu(red_saat_once=5)

    assert "Metacom" in ya.engellenen_capalar(durum)


def test_damgadan_ESKI_redler_capayi_YAKMIYOR():
    """⚠️ Asil is: eski kodla yanmis capa yeniden denenebilmeli."""
    durum = _capa_durumu(red_saat_once=5, damga_saat_once=1)

    assert "Metacom" not in ya.engellenen_capalar(durum)


def test_damgadan_YENI_redler_capayi_HALA_yakiyor():
    """⚠️ Sinir bekcisi: sifirlama gecmisi siliyor, GELECEGI degil."""
    durum = _capa_durumu(red_saat_once=1, damga_saat_once=2)

    assert "Metacom" in ya.engellenen_capalar(durum)


def test_YAYINLANAN_capa_damgadan_ETKILENMIYOR():
    """⚠️ Tekrar politikasi bir kod degisikligiyle gecersizlesmez: ayni konu
    iki kez yayinlanmamali."""
    durum = {
        "soguma_gecerlilik": _an(1),
        "published": [{"visual_anchor": "Colosseum", "published_at": _an(50)}],
        "rejected": [],
    }

    assert "Colosseum" in ya.engellenen_capalar(durum)


# --- CLI --------------------------------------------------------------------


def test_bayrak_URETIM_YAPMADAN_cikiyor():
    """⚠️ Bakim islemi, koşum secenegi degil: ayni komut uretim de yapsaydi
    her sifirlama bir slot harcardi."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("if args.sogumayi_sifirla:") :][:900]

    assert 'state["soguma_gecerlilik"] = simdi.isoformat()' in govde
    assert "save_state(state)" in govde
    assert "return" in govde, "sifirlamadan sonra uretime devam etmemeli"


def test_bayrak_TANIMLI_ve_parse_ediliyor():
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert '"--sogumayi-sifirla"' in kaynak
    assert "args.sogumayi_sifirla" in kaynak


def test_sifirlama_URETIMDEN_ONCE_calisiyor():
    """`run_cycle` cagrisindan once donmeli."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert kaynak.index("if args.sogumayi_sifirla:") < kaynak.index("result = run_cycle(")
