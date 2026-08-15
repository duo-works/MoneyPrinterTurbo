"""Kapanis — izleyicinin geri gelip gelmeyecegini belirleyen cumle.

⚠️ NEDEN — olculdu (2026-08-14, YouTube Analytics). 1.115 izlenme, **1
abone** (%0,09) ve trafigin %96'si Shorts akisi. Yani DAGITIM CALISIYOR,
donusum calismiyor: video sonuna kadar gelen izleyici kanalin ne yaptigini
ogrenmeden kayiyor. Tutunma egrisi videonun sonunda %31-36'ya iniyor ve o
ana kadar hicbir yerde bir sebep verilmiyordu.

⚠️ Kapanis kapisinin kancadan FARKLI bir riski var: "geri gelmek icin sebep
ver" talimati modeli dogal olarak her videoda AYNI cumleye itiyor. Ust uste
ayni kapanis, seri kimligi degil reklam kusagi olur — bu yuzden tekrar
kontrolu kancadaki `_kalip_iskeleti` ile ortak.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


ONCEKI = [
    "The archive still holds the rest of that fleet.",
    "Another sealed room waits under the same hill.",
]


def test_kapanis_son_cumleyi_aliyor():
    metin = "Birinci cumle. Ikinci cumle. Son soz burada."

    assert ya.kapanis(metin) == "Son soz burada."


def test_tek_cumlelik_metin_patlamiyor():
    assert ya.kapanis("Tek cumle.") == "Tek cumle."
    assert ya.kapanis("") == ""
    assert ya.kapanis("   ") == ""


def test_ozne_degisse_de_AYNI_cumle_yakalaniyor():
    """⚠️ Asil kusur: ozne degisiyor, cumle ayni kaliyor.

    ⚠️ Kancanin kalip olcusu burada CALISMIYOR ve sebebi ogretici:
    `_kalip_iskeleti` bastaki buyuk harfli diziyi atiyor. Kancada ozne ozel
    ad oldugu icin dogru sonuc veriyor; kapanislarda ise yalnizca "The"
    atiliyor ve ayirt edici isim kalibin icinde kaliyor. Bu yuzden olcu
    kelime ortusmesi.
    """
    senaryo = "Bir sey oldu. The vault still holds the rest of that hoard."

    assert ya._kapanis_tekrari(senaryo, ONCEKI)


def test_gercekten_farkli_kapanis_geciyor():
    senaryo = "Bir sey oldu. Nobody has opened the second chamber yet."

    assert not ya._kapanis_tekrari(senaryo, ONCEKI)


def test_gecmis_yoksa_kapi_kapali():
    assert not ya._kapanis_tekrari("Bir sey oldu. Herhangi bir kapanis.", [])


def test_cok_kisa_kapanis_patlamiyor():
    assert not ya._kapanis_tekrari("Gold.", ONCEKI)
    assert not ya._kapanis_tekrari("", ONCEKI)


# --- Hatta baglanti -------------------------------------------------------


def test_kapanis_kayda_yaziliyor():
    """⚠️ Yazilmazsa `_son_kapanislar` hep bos doner ve kapi hicbir seyi engellemez."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("record = {")
    govde = kaynak[i : kaynak.index('"quality": asdict(review)', i)]

    assert '"kapanis": kapanis(plan.script)' in govde


def _plan_yaniti(kapanis_cumlesi: str) -> dict:
    return {
        "topic": "konu",
        "visual_anchor": "Sutton Hoo",
        "title": "Sutton Hoo: What Was Buried There? #Shorts",
        # ⚠️ 80-120 kelime olmali. Ilk surumu 73 kelimeydi ve dogrulama
        # kapanis kapisindan ONCE dusuyordu: test kapiyi hic yuruttemeden
        # gecmis gibi gorunuyordu.
        "script": (
            "Sutton Hoo held a ship no one saw arrive. The mound covered an "
            "entire vessel and the timbers had rotted into the sand, leaving "
            "only their iron rivets in place. Diggers traced the hull by those "
            "rivets alone in nineteen thirty nine, working with brushes because "
            "a spade would have destroyed the outline they were following. "
            "Inside lay a helmet, a shield and gold shoulder clasps of "
            "astonishing work, along with silver bowls carried from the far "
            "eastern Mediterranean. No body was ever found in the chamber "
            "itself, and the acid soil may have taken it. " + kapanis_cumlesi
        ),
        "scenes": [
            {"narration": f"sahne {i}", "search_term": f"Sutton Hoo detay {i}"}
            for i in range(1, 7)
        ],
        "description": "aciklama",
        "tags": ["a", "b", "c"],
    }


def test_kapi_YEDEK_KIPTE_de_calisiyor(monkeypatch):
    """⚠️ ASIL KOSUL — ve bu kapinin ilk halinde YOKTU.

    Kapi `if konu:` dalinin icindeydi, yani yalnizca huni kipinde. Ama
    zamanlayici kurulunca koşumlarin tamamina yakini YEDEK kipte calisiyor
    (kuyruk neredeyse her zaman bos, `konu=None`) — yani gunde 4-6 video
    ureten kipte tekrar kontrolu hic isletilmiyordu.

    ⚠️ Bu test dali GERCEKTEN yuruttuyor. Kaynak metninde dize aramak bunu
    goremezdi: dize DOGRUYDU, calismayan sey cagri yoluydu. Ayni sinif kusur
    bu oturumda uc uretim koşumunu oldurdu.
    """
    tekrarlayan = "The archive still holds the rest of that fleet."
    yanitlar = [_plan_yaniti(tekrarlayan), _plan_yaniti("Nobody has opened the second chamber yet.")]
    istemler: list[str] = []

    def sahte(system: str, user: str, **_) -> dict:
        istemler.append(user)
        return yanitlar[min(len(istemler) - 1, len(yanitlar) - 1)]

    monkeypatch.setattr(ya, "_json_completion", sahte)
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [tekrarlayan])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: [])

    plan = ya.generate_content_plan(konu=None)

    assert len(istemler) == 2, "tekrarlayan kapanis REDDEDILMELIYDI"
    assert "closing line repeats" in istemler[1], "geri bildirim modele gitmeli"
    assert plan.script.endswith("Nobody has opened the second chamber yet.")


def test_kapi_HUNI_kipinde_de_calisiyor(monkeypatch):
    tekrarlayan = "The archive still holds the rest of that fleet."
    yanitlar = [_plan_yaniti(tekrarlayan), _plan_yaniti("Nobody has opened the second chamber yet.")]
    istemler: list[str] = []

    def sahte(system: str, user: str, **_) -> dict:
        istemler.append(user)
        return yanitlar[min(len(istemler) - 1, len(yanitlar) - 1)]

    monkeypatch.setattr(ya, "_json_completion", sahte)
    monkeypatch.setattr(ya, "_son_kapanislar", lambda: [tekrarlayan])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: [])
    monkeypatch.setattr(ya.wikimedia_materials, "vikipedi_ozeti", lambda *_a, **_k: "")

    ya.generate_content_plan(konu="Sutton Hoo")

    assert len(istemler) == 2, "huni kipinde de reddedilmeliydi"


def test_istem_stok_cagriyi_YASAKLIYOR():
    """⚠️ "Subscribe" demek en kolay yol ve tam da istemedigimiz sey.

    Ayni cumle her videoda tekrarlanirsa izleyici onu reklam olarak gorur;
    kanal kimligi degil gurultu olur.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "END ON A REASON TO COME BACK" in kaynak
    assert 'never write "subscribe"' in kaynak


def test_seri_imzasi_aciklamanin_BASINDA():
    """YouTube aciklamanin yalnizca ilk satirlarini katlanmamis gosteriyor."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert 'description = f"{SERI_IMZASI}\\n\\n{plan.description}"' in kaynak
    assert "Shemz" in ya.SERI_IMZASI
