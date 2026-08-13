"""Oznesi kaydin kendisi olan anlatim — hicbir arsiv gorseli bunu gosteremez.

Olculdu (2026-08-13): Ibn Saud koşumunda uretilen 8 sahnenin 2'si buydu ve
o sahnelere zorunlu olarak alakasiz gorsel geldi; hakem 69/54/31 verdi.
Talaat Pasha koşumlarinda da ayni kalip vardi. Kusur konuda degil METINDE:
model konuyu yeterince bilmeyince olgu yerine kayit hakkinda dolgu yaziyor.

Kapsam bilerek dar — istem tarihsel belirsizligi baska yerde acikca serbest
birakiyor. Asagidaki ikinci obek o siniri kilitliyor: genis bir yasak
dogrulama-yeniden deneme dongusunu kilitlerdi.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(*anlatimlar: str) -> ya.ContentPlan:
    """Yalnizca anlatimlari degisen, gerisi gecerli bir plan."""
    return ya.ContentPlan(
        topic="Ibn Saud",
        visual_anchor="Ibn Saud",
        script=(
            "Ibn Saud did not begin as king. In 1902 he crossed the desert and took "
            "Riyadh back with forty men, climbing the wall of the fort before dawn. "
            "His recorded titles included Emir, Sultan, and King of Nejd, each one "
            "won separately. He took Hejaz in 1925 and held both crowns at once for "
            "seven years. On 23 September 1932 he proclaimed Saudi Arabia, and in "
            "1945 Roosevelt received him aboard the USS Quincy. He ruled until his "
            "death in 1953. The kingdom began on a date, but the authority behind it "
            "took thirty years to build and never carried a single name."
        ),
        description="d",
        tags=["a", "b", "c"],
        title="Who Was Ibn Saud? #Shorts",
        # ⚠️ Terimler farkli: ayni terimi tekrarlayan plan artik
        # dogrulamadan gecmiyor (portre yigini kusuru, 2026-08-13). Bu
        # dosyanin konusu ANLATIM, terimler yalnizca gecerli olsun diye var.
        scenes=[
            {"narration": anlatim, "search_term": f"Ibn Saud {ayrinti}"}
            for anlatim, ayrinti in zip(
                anlatimlar,
                ("portrait", "Riyadh fort", "desert camp", "signed treaty",
                 "USS Quincy meeting", "Nejd banner", "royal court", "later years"),
                strict=False,
            )
        ],
    )


# --- yakalanmasi gerekenler: oznesi kayit/ozet/video olan cumleler ---


@pytest.mark.parametrize(
    "anlatim",
    [
        "No one can reconstruct every transition from this summary alone.",
        "The record here does not name each turning point.",
        "This account cannot list every title he held.",
        "The surviving detail cannot be reconstructed from this summary alone.",
        "The video does not name each turning point.",
        # ⚠️ Model ayni ailenin yeni ifadesini buldu (Mehmed II, 2. deneme).
        "Why it ended is not known from the evidence given.",
        "His motive is unclear from the information provided.",
    ],
)
def test_kayit_hakkindaki_cumle_yakalaniyor(anlatim):
    assert ya.resmedilemez_kusuru(anlatim) != ""


def test_belirsizligin_kendisi_degil_kaynak_eki_yakalaniyor():
    """⚠️ Bu testin ozu bir AYRIM.

    "Why it ended is not known" TEK BASINA mesru: Fatih'in 1446'da tahttan
    inisinin sebebi gercekten tartismali ve bu, dunya hakkinda durust bir
    belirsizlik — anlatimin en iyi yaptigi seylerden biri. Kusurlu olan
    "from the evidence given" eki, cunku ozneyi dunyadan MODELE VERILEN
    METNE kaydiriyor.

    Kalip belirsizligi yasaklamaya baslarsa bu test duser.
    """
    assert ya.resmedilemez_kusuru("Why it ended is not known.") == ""
    assert ya.resmedilemez_kusuru("Why it ended is not known from the evidence given.") != ""


def test_mesaj_ne_yapilacagini_soyluyor():
    """Dogrulama hatasi modele geri besleniyor; kurali tekrarlamak donguyu kirmiyor."""
    kusur = ya.resmedilemez_kusuru("No one can reconstruct every transition.")

    assert "replace the sentence" in kusur
    assert "concrete" in kusur


# --- yakalanMAmasi gerekenler: dunya hakkindaki durust belirsizlik ---


@pytest.mark.parametrize(
    "anlatim",
    [
        "His body was never found.",
        "Locals still claim the tunnel runs under the hill.",
        "The Inca told of a city that moved.",
        "Historians still argue about who fired first.",
        "He never explained the decision to anyone.",
        "The treaty text was burned in 1922.",
    ],
)
def test_dunya_hakkindaki_belirsizlik_serbest(anlatim):
    """⚠️ Bu obek sinirin bekcisi.

    Istem tarihsel belirsizligi acikca SERBEST birakiyor ve iyi tarih
    anlatimi bunu gerektiriyor. Yasak genisletilirse burasi kirilir — ve
    her yeniden dogrulama bir cikarim koşumu demek.
    """
    assert ya.resmedilemez_kusuru(anlatim) == ""


# --- dogrulayiciya bagli mi ---


def test_plan_dogrulamasi_resmedilemez_sahneyi_reddediyor():
    plan = _plan(
        "In 1902 he took Riyadh with forty men.",
        "The record here does not name each turning point.",
        "He proclaimed the kingdom on 23 September 1932.",
        "He held the crowns of Nejd and Hejaz at once.",
        "Roosevelt met him aboard the USS Quincy in 1945.",
        "He ruled until his death in 1953.",
    )

    with pytest.raises(ValueError, match="scene 2"):
        ya.validate_content_plan(plan)


def test_temiz_plan_geciyor():
    plan = _plan(
        "In 1902 he took Riyadh with forty men.",
        "His first title was Emir of Nejd.",
        "He proclaimed the kingdom on 23 September 1932.",
        "He held the crowns of Nejd and Hejaz at once.",
        "Roosevelt met him aboard the USS Quincy in 1945.",
        "He ruled until his death in 1953.",
    )

    ya.validate_content_plan(plan)


def test_istem_de_kurali_soyluyor():
    """Kod zorluyor, istem duzeltilecek metin sayisini azaltiyor (DW-87 dersi)."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "NEVER WRITE A SENTENCE WHOSE SUBJECT IS THE RECORD ITSELF" in kaynak


# --- Kaptiyon anlatimi (2026-08-14) --------------------------------------


def test_gorseli_anlatan_cumle_reddediliyor():
    """⚠️ Ailenin UCUNCU bicimi, arsiv menusuyle BIRLIKTE geldi.

    Olculdu (2026-08-14, menunun ilk canli plani): model artik elindeki
    dosyayi bildigi icin onu tarif etmeye basladi — "An 1871 image shows the
    fast vessel", "Another image shows her carrying full sail", "One later
    port photograph may show Sydney". Alt yazi kaptiyona donuyor: izleyici
    seyrettigi seyin hikayesini degil dosyanin tarifini dinliyor.
    """
    for cumle in (
        "An 1871 image shows the fast vessel created for his line.",
        "Another image shows her carrying full sail before 1916.",
        "One later port photograph may show Sydney.",
        "This engraving depicts the harbour at dawn.",
    ):
        assert ya.resmedilemez_kusuru(cumle), cumle


def test_gorsel_hakkindaki_OLGU_mesru_kaliyor():
    """⚠️ Kalip kasten DAR: dunya hakkinda bir olgu anlatmak serbest."""
    for cumle in (
        "The photograph was taken in Sydney Harbour in 1885.",
        "The painting hung in the shipowner's office until the fire.",
        "The plate records the king's name in three scripts.",
    ):
        assert ya.resmedilemez_kusuru(cumle) == "", cumle
