"""Baslik BICIMI tekrar ediyor mu — kanal sayfasina bakanin gordugu ilk sey.

⚠️ NEDEN — olculdu (2026-08-14, yayindaki 15 video):

    5/15  "The ... of ..." tamlamasi   (ilk bes video, ust uste)
    9/15  duz soru                     (son dokuz video, ust uste)
    SON 6 VIDEONUN 6'SI DA SORU, ucu "Why ..."

Yani kanal iki blok halinde tekrar ediyor. Konu tekrari icin kapi VAR
(`_recent_titles` tum gecmisi okuyor, 15/15 konu benzersiz), kanca ve
kapanis icin kapi VAR — ama BASLIK BICIMI icin hicbir kapi yoktu.

⚠️ BU KAPI SORU BICIMINI YASAKLAMAZ, CESITLENDIRIR. Soru bicimi KASITLI:
DW-104'te olculdu, baslik arama kutusuna yazilan ifadeye benzedigi olcude
bulunuyor. Onu kaldirmak bulunurlugu yikardi. Kapinin yasakladigi sey ust
uste AYNI soru kelimesi — "why/who/how/what/did" arasinda donmeye zorluyor.

⚠️ Hacim baglami: bu kapi 2026-08-14'te zamanlayici gunde ~4-5 videoya
cikarken kondu. YouTube'un "toplu uretilmis / tekrar eden icerik"
politikasi sikligi degil AYIRT EDILEBILIRLIGI olcuyor; hacim artarken
tekrar yuzeylerini kapatmak, hacmin kendisini kismaktan daha dogru kaldirac.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


# --- Bicim cikarma --------------------------------------------------------


def test_soru_kelimesi_bicimi_belirliyor():
    assert ya._baslik_bicimi("Why Did Endurance Sink in Antarctica? #Shorts") == "soru/why"
    assert ya._baslik_bicimi("Who Was Gotz von Berlichingen? #Shorts") == "soru/who"
    assert ya._baslik_bicimi("How Many Times Did Mehmed II Rule? #Shorts") == "soru/how"


def test_iki_nokta_sonrasi_soru_da_ayni_bicim():
    """⚠️ Olculdu: bu iki baslik gozle farkli gorunuyor, kalibi ayni.

    "Friedrich Hayek: Why Did He Win the Nobel Prize?"
    "Second Anglo-Dutch War: Why Did It End?"

    Ozel ad basta durdugu icin ham ilk kelime ayirt edici sanilirdi; ayirt
    edici olan iki noktadan SONRAKI soru kelimesi.
    """
    assert ya._baslik_bicimi("Friedrich Hayek: Why Did He Win the Nobel Prize? #Shorts") == "soru/why"
    assert ya._baslik_bicimi("Second Anglo-Dutch War: Why Did It End? #Shorts") == "soru/why"
    assert ya._baslik_bicimi("Piri Reis Map: Did It Show Antarctica? #Shorts") == "soru/did"


def test_tamlama_bicimi_ayri():
    assert ya._baslik_bicimi("The Ingenious Design of the Colosseum #Shorts") == "tamlama"
    assert ya._baslik_bicimi("The Wonders of Karnak Temple #Shorts") == "tamlama"


def test_siniflanamayan_baslik_diger():
    assert ya._baslik_bicimi("Secrets of the Viking Longship #Shorts") == "diger"
    assert ya._baslik_bicimi("") == "diger"


# --- Kapi -----------------------------------------------------------------


def test_ayni_soru_kelimesi_tekrar_sayiliyor():
    onceki = ["Why Did Endurance Sink in Antarctica? #Shorts"]

    assert ya._baslik_bicimi_tekrari("Altamira Cave: Why Was Its Art Called Fake? #Shorts", onceki)


def test_farkli_soru_kelimesi_geciyor():
    """Kapi soruyu degil AYNI soruyu yasakliyor."""
    onceki = ["Why Did Endurance Sink in Antarctica? #Shorts"]

    assert not ya._baslik_bicimi_tekrari("Who Was Gotz von Berlichingen? #Shorts", onceki)


def test_ust_uste_tamlama_da_tekrar():
    """Ilk bes videonun kusuru buydu — hepsi "The ... of ..."."""
    onceki = ["The Wonders of Karnak Temple #Shorts"]

    assert ya._baslik_bicimi_tekrari("The Ingenious Design of the Colosseum #Shorts", onceki)


def test_diger_bicimi_ASLA_engellenmiyor():
    """⚠️ "diger" bir kalip degil, siniflandiramadigimiz sey.

    Onu tekrar saymak, birbirinden tamamen farkli iki basligi yanlislikla
    reddederdi — kapinin uretimi bosuna yakmasi tam da kacindigimiz sey.
    """
    onceki = ["Secrets of the Viking Longship #Shorts"]

    assert not ya._baslik_bicimi_tekrari("Gold Under the Hill #Shorts", onceki)


def test_gecmis_yoksa_kapi_kapali():
    assert not ya._baslik_bicimi_tekrari("Why Did It End? #Shorts", [])


# --- Pencereler -----------------------------------------------------------


def test_baslik_penceresi_dar_tutuluyor():
    """⚠️ Baslik penceresi kanca/kapanistan KASITLI olarak dar.

    Genis pencere "son 40 videoda why kullanildi" derdi ve soru kelimesi
    havuzu (why/who/how/what/did/when/where) 7 taneyken uretimi kilitlerdi.
    Amac cesitlilik saglamak, bicimi tuketmek degil.
    """
    assert ya.BASLIK_BICIMI_PENCERESI == 3


def test_kanca_ve_kapanis_penceresi_GENISLETILDI():
    """⚠️ Olculdu (2026-08-14): 12 kayitlik pencere gunde 4 videoda 3 GUN,
    gunde 5 videoda 2,4 gun hafiza demek. Uc gun sonra donen bir kalip hic
    yakalanmiyordu. Ayda ~10 video uretilirken sorun degildi; zamanlayici
    hacmi 18 katina cikarinca pencere anlamsizlasti.

    Genisletmenin uretimi kilitleme riski YOK: yumusak kapilar yalnizca ilk
    uc denemede acik (`YUMUSAK_KAPI_DENEMESI = 3`), sonra kapaniyor.
    """
    assert ya.TEKRAR_PENCERESI >= 40

    import inspect

    # Sabit GERCEKTEN kullanilmali: 12 kalmis bir varsayilan, sabiti
    # buyutmeyi anlamsiz kilardi.
    assert "adet: int = TEKRAR_PENCERESI" in inspect.getsource(ya._son_kancalar)
    assert "adet: int = TEKRAR_PENCERESI" in inspect.getsource(ya._son_kapanislar)


# --- Hatta baglanti -------------------------------------------------------


def test_senaryo_kayda_yaziliyor():
    """⚠️ Olculdu: `script` alani kayitlarda HIC YOK.

    Kanca (ilk cumle) ve kapanis (son cumle) olculuyor, aradaki 4-8 cumle
    icin hicbir olcu yok — ve kaydedilmedigi icin GERIYE DONUK olcmek de
    mumkun degil. Once kaydet, kapiyi veri birikince kur: bu oturumda agir
    kusur kapisinda tam tersi yapildi ve olmayan bir alan uzerinden
    "olculdu" denmisti.
    """
    i = KAYNAK.index("record = {")
    govde = KAYNAK[i : KAYNAK.index('"quality": asdict(review)', i)]

    assert '"script": plan.script' in govde


def _plan_yaniti(baslik: str) -> dict:
    return {
        "topic": "konu",
        "visual_anchor": "Sutton Hoo",
        "title": baslik,
        "script": (
            "Sutton Hoo held a ship no one saw arrive. The mound covered an "
            "entire vessel and the timbers had rotted into the sand, leaving "
            "only their iron rivets in place. Diggers traced the hull by those "
            "rivets alone in nineteen thirty nine, working with brushes because "
            "a spade would have destroyed the outline they were following. "
            "Inside lay a helmet, a shield and gold shoulder clasps of "
            "astonishing work, along with silver bowls carried from the far "
            "eastern Mediterranean. No body was ever found in the chamber "
            "itself, and the acid soil may have taken it. "
            "Nobody has opened the second chamber yet."
        ),
        "scenes": [
            {"narration": f"sahne {i}", "search_term": f"Sutton Hoo detay {i}"}
            for i in range(1, 7)
        ],
        "description": "aciklama",
        "tags": ["a", "b", "c"],
    }


def test_kapi_YEDEK_KIPTE_gercekten_yuruyor(monkeypatch):
    """⚠️ Dali GERCEKTEN yuruten test — kaynak metninde dize aramak degil.

    Bu oturumda ayni sinif kusur uc uretim koşumunu oldurdu: dize dogruydu,
    calismayan sey cagri yoluydu. Ve koşumlarin tamamina yakini YEDEK kipte
    (`konu=None`) calisiyor, yani kapi orada calismazsa hic calismiyor.
    """
    tekrarlayan = "Why Did Endurance Sink in Antarctica? #Shorts"
    yanitlar = [
        _plan_yaniti(tekrarlayan),
        _plan_yaniti("Who Was Gotz von Berlichingen? #Shorts"),
    ]
    istemler: list[str] = []

    def sahte(system: str, user: str) -> dict:
        istemler.append(user)
        return yanitlar[min(len(istemler) - 1, len(yanitlar) - 1)]

    monkeypatch.setattr(ya, "_json_completion", sahte)
    monkeypatch.setattr(ya, "_son_basliklar", lambda: ["Altamira Cave: Why Was Its Art Called Fake?"])
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: [])

    plan = ya.generate_content_plan(konu=None)

    assert len(istemler) == 2, "ayni soru kelimesi REDDEDILMELIYDI"
    assert "title repeats" in istemler[1], "geri bildirim modele gitmeli"
    assert plan.title.startswith("Who Was")


def test_istemde_gecmis_bicimler_modele_veriliyor():
    """Yasaklamak yetmiyor, model gecmisini gormeli (DW-94'un dersi)."""
    assert "were already used on this channel" in KAYNAK
    assert "_son_basliklar()" in KAYNAK
