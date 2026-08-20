"""Uzun videodan Shorts turetme — plan tarafi.

⚠️ Bu dosyanin merkezindeki test `test_turetilen_plan_SHORTS_KELIME_ARALIGINDA`.
Iki bicimin sahne yogunlugu uyusmuyor (uzun sahne ~42 kelime, Shorts tavani
150 kelime TOPLAM) ve turetme ancak dogru kesitle mumkun. O kesit olculdu;
test onu kilitliyor.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import turetme  # noqa: E402
from youtube_automation import SHORTS_BICIMI  # noqa: E402


def _sahne(no: int) -> dict:
    """Olculen uzun sahnesinin bicimi: IKI cumle, ~21 + ~20 kelime.

    Gercek dagilim (yayinlanan 28 sahnelik video): 27 sahne iki cumle, biri
    uc; ilk cumleler 14-29 kelime, ortalama 21,5.
    """
    ilk = " ".join(f"first{no}word{i}" for i in range(21))
    ikinci = " ".join(f"second{no}word{i}" for i in range(20))
    return {
        "sahne": no,
        # ⚠️ Capa terimin ICINDE: uzun plan `_ensure_visual_anchor`dan
        # geciyor, yani yayinlanmis kayitlarin terimleri ZATEN capali.
        # Turetme bu on kosula dayaniyor ve test onu gercek veriden aliyor.
        "terim": f"Herculaneum detay {no}",
        "kaynak_dosya": f"Dosya {no}.jpg",
        "kaynak_dosya_2": "",
        "gelen": f"Dosya {no}.jpg",
        "anlatim": f"{ilk}. {ikinci}.",
        "kelime": 41,
    }


@pytest.fixture
def uzun_kayit() -> dict:
    return {
        "slot": "2026-08-20-15",
        "status": "published",
        "bicim": "uzun",
        "topic": "Herculaneum",
        "visual_anchor": "Herculaneum",
        "title": "Why Did Herculaneum's Last 340 People Wait at the Shore?",
        "script": "MODELIN AYRI YAZDIGI SENARYO, anlatimlarla ayni degil.",
        "description": "A documentary about Herculaneum.",
        "tags": ["history", "rome", "archaeology"],
        "ruh_hali": "somber",
        "sahne_sayisi": 28,
        "sahneler": [_sahne(n) for n in range(1, 29)],
    }


def test_turetilen_plan_SHORTS_KELIME_ARALIGINDA(uzun_kayit):
    """⚠️ MUTASYON: `ilk_cumle` yerine tam `anlatim` kullanmak bunu duser.

    Olculdu (2026-08-20), yayinlanan 28 sahnelik videonun gercek sayilari:

        6 sahne x ilk cumle : 112-145 kelime  -> 23/23 pencere ARALIKTA
        6 sahne x tam sahne : ~250 kelime     -> tavan 150, hepsi RED

    Yani kesit dogru secilmezse turetme her seferinde kelime kapisinda
    olur ve sebep "model uzun yazdi" sanilir.
    """
    taban, tavan = SHORTS_BICIMI.kelime_araligi

    for sira in range(turetme.pencere_sayisi(28)):
        alanlar = turetme.turetilmis_plan_alanlari(uzun_kayit, sira)
        kelime = len(alanlar["script"].split())

        assert taban <= kelime <= tavan, f"pencere {sira}: {kelime} kelime"


def test_turetilen_sahne_sayisi_SHORTS_ARALIGINDA(uzun_kayit):
    taban, tavan = SHORTS_BICIMI.sahne_araligi
    alanlar = turetme.turetilmis_plan_alanlari(uzun_kayit, 0)

    assert taban <= len(alanlar["scenes"]) <= tavan


def test_her_sahne_KENDI_gorseliyle_geliyor(uzun_kayit):
    """⚠️ Alternatif tasarim (3 uzun sahne x 2 cumle) ayni kelime araligini
    tutuyordu ama 6 sahneye 3 dosya dusuyordu — ayni gorsel arka arkaya."""
    alanlar = turetme.turetilmis_plan_alanlari(uzun_kayit, 0)
    dosyalar = [s["kaynak_dosya"] for s in alanlar["scenes"]]

    assert len(set(dosyalar)) == len(dosyalar)
    assert all(dosyalar)


def test_sahne_anlatimi_TEK_CUMLE(uzun_kayit):
    alanlar = turetme.turetilmis_plan_alanlari(uzun_kayit, 0)

    for sahne in alanlar["scenes"]:
        assert len(turetme.cumleler(sahne["narration"])) == 1


def test_script_ANLATIMLARDAN_kuruluyor_kayittan_DEGIL(uzun_kayit):
    """⚠️ MUTASYON: `script`i kayittan kopyalamak bunu duser.

    Olculdu: uzun kayitta `script` (5.843 krkt) ile anlatimlarin birlesigi
    (7.242 krkt) AYNI DEGIL. Kopyalansaydi turetilen videonun SESI 28
    sahneyi, GORUNTUSU 6 sahneyi anlatirdi — ve fark sessiz olurdu.
    """
    alanlar = turetme.turetilmis_plan_alanlari(uzun_kayit, 0)

    assert alanlar["script"] != uzun_kayit["script"]
    assert alanlar["script"] == " ".join(s["narration"] for s in alanlar["scenes"])


def test_ikincil_dosya_BOS_komsudan_doldurulmuyor(uzun_kayit):
    """Eksik ikincil kusur DEGIL; komsudan doldurmak anlatim-gorsel
    uyusmazligini ELLE uretmek olurdu."""
    alanlar = turetme.turetilmis_plan_alanlari(uzun_kayit, 0)

    assert all(s["kaynak_dosya_2"] == "" for s in alanlar["scenes"])


def test_pencereler_ORTUSMUYOR(uzun_kayit):
    """⚠️ MUTASYON: pencereyi kaydirmali yapmak bunu duser."""
    gorulen: list[str] = []
    for sira in range(turetme.pencere_sayisi(28)):
        alanlar = turetme.turetilmis_plan_alanlari(uzun_kayit, sira)
        gorulen.extend(s["kaynak_dosya"] for s in alanlar["scenes"])

    assert len(set(gorulen)) == len(gorulen)


def test_pencere_sayisi_TAM_BOLUM(uzun_kayit):
    assert turetme.pencere_sayisi(28) == 4
    assert turetme.pencere_sayisi(6) == 1
    assert turetme.pencere_sayisi(5) == 0
    assert turetme.pencere_sayisi(0) == 0


def test_yetersiz_sahnede_SESSIZCE_kisa_plan_DONMUYOR(uzun_kayit):
    """Son pencere eksik kalirsa hata verilir; 4 sahnelik bir Shorts
    sessizce uretilmez (sahne tabani 6)."""
    with pytest.raises(ValueError):
        turetme.turetilmis_sahneler(uzun_kayit, 4)


def test_ALANI_EKSIK_kayittan_turetilmiyor(uzun_kayit):
    """⚠️ 2026-08-20'den ONCE yayinlanan uzun kayitlarda `description`,
    `tags` ve `ruh_hali` YOK. Sessizce eksik plan kurmak yerine kayit
    listeye HIC alinmiyor — sebep gorunur olsun."""
    assert turetme.plani_kurulabilir_mi(uzun_kayit) is True

    for alan in turetme.ZORUNLU_ALANLAR:
        eksik = {**uzun_kayit, alan: None}
        assert turetme.plani_kurulabilir_mi(eksik) is False, alan


def test_ruh_hali_ZORUNLU_DEGIL(uzun_kayit):
    """`ContentPlan.ruh_hali` varsayilani bos ve bos deger "muzigi havuzdan
    sec" demek — bugunku davranis, kusur degil."""
    assert turetme.plani_kurulabilir_mi({**uzun_kayit, "ruh_hali": ""}) is True


def test_turetilebilir_yayinlar_EN_YENIDEN_eskiye(uzun_kayit):
    eski = {**uzun_kayit, "slot": "2026-08-19-15", "topic": "Petra"}
    state = {"published": [eski, uzun_kayit]}

    sonuc = turetme.turetilebilir_yayinlar(state)

    assert [k["topic"] for k in sonuc] == ["Herculaneum", "Petra"]


def test_turetilebilir_yayinlar_SHORTS_ve_YAYINLANMAMISI_atliyor(uzun_kayit):
    state = {
        "published": [
            {**uzun_kayit, "bicim": "shorts"},
            {**uzun_kayit, "status": "dry-run"},
            uzun_kayit,
        ]
    }

    assert len(turetme.turetilebilir_yayinlar(state)) == 1


def test_sonraki_pencere_KULLANILMISI_atliyor(uzun_kayit):
    """⚠️ MUTASYON: `turetildi` kaydini okumamak bunu duser — hat ayni
    pencereden her gun ayni Shorts'u uretirdi."""
    state = {
        "published": [
            uzun_kayit,
            {
                "bicim": "shorts",
                "status": "published",
                "turetildi": {"kimlik": turetme.turetme_kimligi(uzun_kayit, 0)},
            },
        ]
    }

    assert turetme.sonraki_pencere(state, uzun_kayit) == 1


def test_pencereler_BITINCE_None(uzun_kayit):
    state = {
        "published": [
            uzun_kayit,
            *[
                {
                    "bicim": "shorts",
                    "status": "published",
                    "turetildi": {"kimlik": turetme.turetme_kimligi(uzun_kayit, n)},
                }
                for n in range(4)
            ],
        ]
    }

    assert turetme.sonraki_pencere(state, uzun_kayit) is None


def test_turetme_kimligi_UZUN_VIDEOYA_ozgu(uzun_kayit):
    """Iki farkli uzun videonun 0. penceresi ayni kimligi ALMAMALI."""
    baska = {**uzun_kayit, "slot": "2026-08-21-15"}

    assert turetme.turetme_kimligi(uzun_kayit, 0) != turetme.turetme_kimligi(baska, 0)


def test_ilk_cumle_bos_girdide_PATLAMIYOR():
    assert turetme.ilk_cumle("") == ""
    assert turetme.ilk_cumle(None) == ""
    assert turetme.cumleler("") == []


# --- youtube_automation'a baglanma ----------------------------------------


import json as _json  # noqa: E402
from unittest.mock import patch  # noqa: E402

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def test_turetilmis_plan_TEK_cikarim_cagrisi(uzun_kayit):
    """Plan sifir cikarim; yalnizca BASLIK bir cagri harciyor.

    ⚠️ MUTASYON: plani `generate_content_plan`e havale etmek bunu duser —
    sayac 1'de kalmazdi.
    """
    cagrilar = []

    def sahte(system, user, **kwargs):
        cagrilar.append(user)
        return {"title": "Why Did 340 Wait at the Shore?"}

    with patch.object(ya, "_json_completion", sahte):
        plan = ya.turetilmis_plani_kur(uzun_kayit, 0, onceki_basliklar=[])

    assert len(cagrilar) == 1
    assert plan.title == "Why Did 340 Wait at the Shore? #Shorts"
    assert len(plan.scenes) == turetme.TURETME_SAHNE_SAYISI


def test_baslik_cikarimi_DUSERSE_kosum_olmuyor(uzun_kayit):
    """⚠️ MUTASYON: `except`i kaldirmak bunu duser.

    Zayif bir baslik, yayinlanmamis bir videodan iyidir — ve determinist
    yol zaten olculdu: dort pencerenin biri iyi baslik veriyor.
    """

    def patlayan(system, user, **kwargs):
        raise RuntimeError("kota doldu")

    with patch.object(ya, "_json_completion", patlayan):
        plan = ya.turetilmis_plani_kur(uzun_kayit, 0, onceki_basliklar=[])

    assert plan.title.endswith("#Shorts")
    assert len(plan.title) < 70


def test_baslikta_SHORTS_etiketi_garanti(uzun_kayit):
    """Model etiketi unutursa ekleniyor: `#Shorts` olmadan YouTube videoyu
    Shorts akisina koymayabilir."""
    with patch.object(
        ya, "_json_completion", lambda s, u, **k: {"title": "Bir Baslik"}
    ):
        plan = ya.turetilmis_plani_kur(uzun_kayit, 0, onceki_basliklar=[])

    assert plan.title == "Bir Baslik #Shorts"


def test_baslik_istemine_SON_BASLIKLAR_veriliyor(uzun_kayit):
    """⚠️ Turetilen Shorts'lar ayni uzun videodan geliyor: ayni konu, ayni
    gun, ust uste iki baslik. Bicim tekrari riski BURADA en yuksek."""
    gorulen = {}

    def sahte(system, user, **kwargs):
        gorulen.update(_json.loads(user))
        return {"title": "T"}

    with patch.object(ya, "_json_completion", sahte):
        ya.turetilmis_plani_kur(uzun_kayit, 0, onceki_basliklar=["Why Did X?"])

    assert gorulen["recent_titles"] == ["Why Did X?"]


def _yayin_kaydi_blogu() -> str:
    i = KAYNAK.index('"published_at": datetime.now(')
    return KAYNAK[i - 4000 : i]


def test_yayin_kaydi_TURETME_IZINI_yaziyor():
    """⚠️ MUTASYON: `turetildi` alanini silmek bunu duser.

    Yazilmazsa `turetme.sonraki_pencere` kullanilmis pencereyi goremez ve
    hat her gun AYNI Shorts'u uretir — sessizce, cunku her koşum kendi
    icinde basarili olur.
    """
    blok = _yayin_kaydi_blogu()

    assert '"turetildi": (' in blok
    assert "turetme.turetme_kimligi(turet[0], turet[1])" in blok


def test_yayin_kaydi_PLANI_KURMAYA_YETEN_alanlari_yaziyor():
    """⚠️ MUTASYON: uc alandan birini silmek bunu duser.

    Olculdu: bunlar olmadan `state.json`dan `ContentPlan` yeniden
    KURULAMIYOR ve turetme her seferinde yeni bir plan cikarimi yapardi —
    turetmenin butun ucuzlugu oradan geliyor.
    """
    blok = _yayin_kaydi_blogu()

    assert '"description": plan.description,' in blok
    assert '"tags": plan.tags,' in blok
    assert '"ruh_hali": plan.ruh_hali,' in blok


def test_turet_KONU_KAYNAKLARIYLA_birlikte_kullanilamiyor():
    """Sessizce birini yok saymak, kullanicinin istedigini sandigi seyden
    baskasini uretirdi."""
    i = KAYNAK.index("if args.uzun or args.konu or args.from_notion:")

    assert "--turet ile --uzun/--konu/--from-notion" in KAYNAK[i : i + 400]


def test_turetme_kolu_PLAN_URETMIYOR():
    """⚠️ MUTASYON: `denenecek = []` satirini kaldirmak bunu duser —
    turetilmis plan kurulur, sonra `generate_content_plan` onu EZERDI."""
    i = KAYNAK.index("if turet is not None:")
    blok = KAYNAK[i : i + 1200]

    assert "denenecek = []" in blok
    assert "plan = turetilmis_plani_kur(kaynak_kayit, pencere)" in blok
    assert 'kaynak = "turetme"' in blok


def test_turetilen_plan_SHORTS_PLAN_KAPILARINI_geciyor(uzun_kayit):
    """⚠️ BU DOSYANIN EN DEGERLI TESTI — kesitin gercek sinavi.

    Diger testler tek tek olcut kilitliyor (kelime, sahne, dosya); bu test
    turetilen plani hattin KENDI kapisindan geciriyor (`plan_kusurlari`,
    ~23 kapi). Gercek yayinlanan kayitla da kosuldu (2026-08-20): dort
    pencerenin DORDU de kusursuz gecti.

    ⚠️ Kapi listesi buyudugunde bu test onu KENDILIGINDEN olcer. Turetme
    yolu `generate_content_plan`i atladigi icin kapilar orada calismiyor;
    calismayan bir kapinin turetilen videoyu koruyup korumadigi ancak
    boyle gorulur.
    """
    for sira in range(turetme.pencere_sayisi(28)):
        alanlar = turetme.turetilmis_plan_alanlari(uzun_kayit, sira)
        plan = ya.ContentPlan(
            title="Why Did They Wait at the Shore? #Shorts", **alanlar
        )

        kusurlar = ya.plan_kusurlari(plan, bicim=ya.SHORTS_BICIMI, konu=plan.topic)

        assert kusurlar == [], f"pencere {sira}: {kusurlar}"
