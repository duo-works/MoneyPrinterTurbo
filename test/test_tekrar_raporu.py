"""`kanal_rapor.py --tekrar` — tekrari korkuyla degil OLCUMLE yonetmek.

⚠️ NEDEN. 2026-08-14'te zamanlayici kurulunca aylik cikti ~10'dan ~150'ye
cikti ve dogal soru soruldu: "YouTube'un toplu uretilmis icerik politikasi
bizi vurur mu, sikligi dusurelim mi?" Sikligi dusurmek yanlis kaldiractI —
politika sikligi degil AYIRT EDILEBILIRLIGI olcuyor. Dogru cevap, ayirt
edilebilirligi SUREKLI OLCMEK ve esige yaklasinca yavaslamak.

⚠️ Bu rapor API'siz calisiyor: veriyi `state.json`dan okuyor, Analytics'e
gitmiyor. Sebebi pratik — Analytics 2-3 gun gecikmeli ve OAuth tokeni
"Testing" kipinde 7 gunde bir oluyor; tekrar olcumunun bunlarin hicbirine
bagli olmamasi gerek.

Baslangic olcumu (2026-08-14, 15 video):
    kanca ortalama ortusme  %4,1   — 0/36 cift %60 esiginin ustunde
    benzersiz konu          15/15
    baslik bicimi           SON 6 VIDEONUN 6'SI DA SORU  <-- tek zayif yuzey
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kanal_rapor  # noqa: E402


def _kayit(baslik: str, kanca: str, kapanis: str) -> dict:
    return {"title": baslik, "hook": kanca, "kapanis": kapanis}


FARKLI = [
    _kayit(
        "Why Did Endurance Sink in Antarctica? #Shorts",
        "Endurance sailed into the ice, but never crossed Antarctica.",
        "Nobody has opened the second chamber yet.",
    ),
    _kayit(
        "Who Was Gotz von Berlichingen? #Shorts",
        "The Iron Hand was also a poet.",
        "The next seductive map deserves the same test.",
    ),
    _kayit(
        "The Wonders of Karnak Temple #Shorts",
        "Tycho Brahe measured the heavens without a telescope.",
        "Three more columns are still buried in the sand.",
    ),
]


def test_farkli_videolar_dusuk_ortusme_veriyor():
    veri = kanal_rapor.tekrar_raporu(FARKLI)

    assert veri["video"] == 3
    assert veri["kanca"]["ortalama_ortusme"] < 0.2
    assert veri["kanca"]["esigi_gecen"] == 0


def test_ayni_kapanis_yakalaniyor():
    """Kapi uretimde bunu engelliyor; rapor KACAN'i gormek icin var."""
    kayitlar = FARKLI + [
        _kayit(
            "How Did It Vanish? #Shorts",
            "A different opening entirely here.",
            "Nobody has opened the second chamber yet.",
        )
    ]

    veri = kanal_rapor.tekrar_raporu(kayitlar)

    assert veri["kapanis"]["esigi_gecen"] >= 1
    assert veri["kapanis"]["ortalama_ortusme"] > 0


def test_baslik_bicimi_serisi_olculuyor():
    """⚠️ Olculen asil kusur: ust uste ayni bicim.

    Dagilim tek basina yetmiyor — 15 videonun 9'u soru olabilir ve bu
    sorun olmayabilir; sorun ARDISIK ayni bicim. Bu yuzden en uzun seri
    ayrica olculuyor.
    """
    ustuste_soru = [
        _kayit("Why Did It End? #Shorts", "a b c", "x y z"),
        _kayit("Why Was It Called Fake? #Shorts", "d e f", "u v w"),
        _kayit("Why Did Endurance Sink? #Shorts", "g h i", "r s t"),
    ]

    veri = kanal_rapor.tekrar_raporu(ustuste_soru)

    assert veri["baslik_bicimi"]["en_uzun_seri"] == 3
    assert veri["baslik_bicimi"]["dagilim"]["soru/why"] == 3


def test_bicim_donusumu_seriyi_kiriyor():
    veri = kanal_rapor.tekrar_raporu(FARKLI)

    assert veri["baslik_bicimi"]["en_uzun_seri"] == 1


def test_bos_gecmiste_patlamiyor():
    veri = kanal_rapor.tekrar_raporu([])

    assert veri["video"] == 0
    assert veri["kanca"]["ortalama_ortusme"] == 0
    assert veri["baslik_bicimi"]["en_uzun_seri"] == 0


def test_tek_video_cift_uretmiyor():
    veri = kanal_rapor.tekrar_raporu(FARKLI[:1])

    assert veri["video"] == 1
    assert veri["kanca"]["esigi_gecen"] == 0


def test_eksik_alan_kaydi_atlaniyor():
    """Eski kayitlarda `kapanis` yok (14 Agu'dan once yazilmiyordu)."""
    kayitlar = FARKLI + [{"title": "Bir Sey #Shorts"}]

    veri = kanal_rapor.tekrar_raporu(kayitlar)

    assert veri["video"] == 4
    assert veri["kapanis"]["olculen"] == 3


def test_yazdirma_patlamiyor(capsys):
    kanal_rapor._tekrari_yazdir(kanal_rapor.tekrar_raporu(FARKLI))

    cikti = capsys.readouterr().out
    assert "kanca" in cikti.lower()


def test_KAPI_ve_RAPOR_ayni_cetveli_kullaniyor():
    """⚠️ Bu testin varlik sebebi gercek bir kusur.

    Ilk surumde `_kapanis_tekrari` kendi esigini (`0.6`) ve kendi kelime
    ayiklayicisini (`_normalize_topic`) kullaniyordu; `--tekrar` raporu ise
    `tekrar_olcusu`nunkileri. Iki sabit, iki ayiklayici — yani rapor
    "tekrar yok" derken kapi BASKA bir cetvelle calisiyordu ve tetik,
    engellenen seyden baskasini olcuyordu. Tam da `tekrar_olcusu`
    docstring'inin uyardigi sapma, birinci gunden.
    """
    import youtube_automation as ya
    import tekrar_olcusu

    assert ya.KAPANIS_ORTUSME_ORANI == tekrar_olcusu.ORTUSME_ESIGI

    # Ayni cift, iki yoldan: kapi tekrar demeliyse rapor da esigi gecmeli.
    a = "The archive still holds the rest of that fleet."
    b = "The vault still holds the rest of that hoard."

    assert ya._kapanis_tekrari(f"Bir sey oldu. {b}", [a])
    assert tekrar_olcusu.kelime_ortusmesi(a, b) >= tekrar_olcusu.ORTUSME_ESIGI


def test_siniflanmayan_bicimler_tekrar_sayilmiyor():
    """"Whose ...?" ve "Whom ...?" ayni kovaya duser ama ayni kalip degil."""
    import youtube_automation as ya

    assert ya._baslik_bicimi("Whose Tomb Was It? #Shorts") == "soru/diger"
    assert not ya._baslik_bicimi_tekrari(
        "Whom Did It Serve? #Shorts", ["Whose Tomb Was It? #Shorts"]
    )


def test_cli_tekrar_bayragi_var():
    kaynak = Path(kanal_rapor.__file__).read_text(encoding="utf-8")

    assert '"--tekrar"' in kaynak
    # ⚠️ API'siz calismali: yetkilendirme istemeden state.json'dan okuyor.
    assert "tekrar_raporu" in kaynak
