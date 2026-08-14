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


def test_kapi_plan_donguSUNE_bagli():
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def generate_content_plan(")
    govde = kaynak[i : kaynak.index("def refine_search_terms(", i)]

    assert "_kapanis_tekrari(plan.script, onceki_kapanislar)" in govde
    # Gecmis kapanislar isteme de veriliyor: yalnizca reddetmek donguyu
    # tuketir, modelin gecmisini gormesi tek denemede duzeltir (DW-94).
    assert "_son_kapanislar()" in govde


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
