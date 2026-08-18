"""Videolar arasi tekrar — huni kipinde de kapali, ama uretimi olduracak kadar degil.

Iki ayri sey kilitleniyor:

1. **Capa ve acilis kalibi huni kipinde de kontrol ediliyor.** Konu
   benzerligi atlanmaya devam ediyor (konuyu insan ve olculmus talep verisi
   sectI) ama capa ayni arsivi, ayni kalip ayni videoyu uretiyor. Gecmis
   acilislar isteme ZATEN veriliyordu ve model yine tekrarladi — bu
   oturumun tekrar eden dersi (DW-87).

2. ⚠️ **Kapilar KATMANLI.** Olculdu (2026-08-13, Sutton Hoo koşumu):
   yumusak kapilar bes denemeyi tuketince kosum
   `DistinctTopicUnavailableError` ile oldu ve o saat icin HIC video
   uretilmedi. Kalite tercihini kovalarken uretimin kendisini kaybetmek,
   duzeltilmesi istenen istikrarsizligin ta kendisi.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


# --- Kanca kalibi ---------------------------------------------------------


ONCEKILER = ["Mehmed II did not rule once.", "The Colosseum swallowed 50,000 people."]


def test_ayni_kalip_farkli_ozne_yakalaniyor():
    """⚠️ Asil kusur: cumleler farkli ama kalip ayni.

    "Mehmed II did not rule once" ile "Murad III did not take the throne"
    farkli cumleler; kanal ust uste bunlari yayinlarsa izleyici ayni videoyu
    izliyormus gibi hissediyor (DW-94).
    """
    assert ya._kanca_tekrari("Murad III did not take the throne quietly. Devam.", ONCEKILER)


def test_tek_kelimelik_ozne_de_calisiyor():
    """⚠️ Ozne SABIT UZUNLUKTA DEGIL: "Mehmed II" iki, "Cleopatra" tek kelime.

    Ilk surum sabit sayida kelime atiyordu ve bu yuzden kalibi kaciriyordu.
    """
    assert ya._kanca_tekrari("Cleopatra did not die the way the story says. Devam.", ONCEKILER)


def test_farkli_kalip_gecebiliyor():
    assert not ya._kanca_tekrari("Sutton Hoo held a ship no one saw arrive. Devam.", ONCEKILER)


def test_gecmis_yoksa_kapi_kapali():
    assert not ya._kanca_tekrari("Anything at all here. Devam.", [])


def test_cok_kisa_acilis_patlamiyor():
    assert not ya._kanca_tekrari("Gold.", ONCEKILER)
    assert not ya._kanca_tekrari("", ONCEKILER)


# --- Katmanli kapilar -----------------------------------------------------


def test_yumusak_kapilar_son_denemelerde_gevsiyor():
    """⚠️ Bu testin konusu: uretimi kaybetmemek.

    Gecerli bir plan bulunduysa, yumusak kapilar yuzunden hicbir video
    uretmemektense o plan render'a gonderilir. Kalite kapisi (skor + agir
    kusur) zaten arkada duruyor.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def generate_content_plan(")
    govde = kaynak[i : kaynak.index("def refine_search_terms(", i)]

    assert "YUMUSAK_KAPI_DENEMESI" in govde

    # ⚠️ BOSLUKLARDAN BAGIMSIZ karsilastirma. Onceki hali cagrinin tek
    # satirda durdugunu varsayiyordu ve `alinti_kusuru`ya bir argüman
    # eklenip satir sarinca kirildi — kusur kodda degil, testin kodu okuma
    # bicimindeydi. Bicimlendirici satiri istedigi yerden bolebilmeli.
    def bosluksuz(metin: str) -> str:
        return re.sub(r"\s+", "", metin)

    assert bosluksuz("yumusak_kapilar_acik and (kusur := alinti_kusuru(plan, konu") in (
        bosluksuz(govde)
    )
    # ⚠️ KAPILAR TASINDI (2026-08-18): kanca/baslik/kapanis/acilis/dengesi
    # artik `yumusak_kapi_kusurlari` icinde TEK GECISTE degerlendiriliyor.
    # KORUNAN OZELLIK AYNI ve asil onemli olan o: toplu cagri da
    # `yumusak_kapilar_acik` korumasi altinda, yani son denemelerde gevsiyor.
    assert bosluksuz("yumusak_kapilar_acik and (yumusak := yumusak_kapi_kusurlari(") in (
        bosluksuz(govde)
    )


def test_dogrulama_HER_denemede_zorunlu():
    """Ust katman gevsememeli: gecersiz plan hicbir denemede gecmemeli."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def generate_content_plan(")
    govde = kaynak[i : kaynak.index("def refine_search_terms(", i)]
    # ⚠️ Capa DONGU GOVDESI olmali: "yumusak_kapilar_acik" dongunun
    # oncesinde de geciyor (sabit tanimi ve gerekce yorumu) ve ilk gecisi
    # aramak testi yanlis yerden olcuyor.
    dongu = govde[govde.index("for deneme in range(1, 6):") :]
    # ⚠️ CAGRILAN ADI DEGISTI (2026-08-18): `validate_content_plan` yerine
    # `plan_kusurlari` — dongu artik TUM kusurlari birden geri besliyor.
    # Bu testin korudugu ozellik degismedi: dogrulama yumusak kapilardan
    # ONCE ve KOSULSUZ calismali.
    dogrulama = dongu.index("plan_kusurlari(")
    ilk_yumusak_kapi = dongu.index("if yumusak_kapilar_acik")

    assert dogrulama < ilk_yumusak_kapi, "dogrulama yumusak kapilardan ONCE ve kosulsuz olmali"


def test_huni_kipinde_capa_tekrari_kontrol_ediliyor():
    """Konu benzerligi atlaniyor ama capa atlanmiyor."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def generate_content_plan(")
    govde = kaynak[i : kaynak.index("def refine_search_terms(", i)]
    huni_dali = govde[govde.index("if konu:") :]

    assert "is_duplicate_visual_anchor" in huni_dali
    # ⚠️ IDDIA GUCLENDI, ZAYIFLAMADI (2026-08-18). Eski hali `_kanca_tekrari`
    # dizesini "ilk `if konu:`den sonra" ariyordu — ama o ilk eslesme
    # govdenin en basinda, yani test pratikte "govdede bir yerde geciyor mu"
    # diyordu. Kanca kapisi zaten `if konu:` dalinin DISINDA ve KOSULSUZ
    # calisiyordu (huni kipinde de, yedek kipte de).
    #
    # Artik dogru sey olculuyor: kapi toplu yumusak gecise tasindi ve o gecis
    # huni dalindan ONCE, kosulsuz calisiyor.
    dongu = govde[govde.index("for deneme in range(1, 6):") :]
    assert dongu.index("yumusak_kapi_kusurlari(") < dongu.index("\n        if konu:")
    toplayici = kaynak[kaynak.index("def yumusak_kapi_kusurlari(") :]
    assert "_kanca_tekrari(" in toplayici[: toplayici.index("\ndef ", 10)]
