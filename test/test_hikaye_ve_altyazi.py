"""Konu yonu (hikaye/efsane) ve altyazi bicimi.

Ikisi de prompt/parametre sozlesmesi oldugu icin testler metne bakiyor:
kusur bir davranis degil bir CUMLE ya da BAYRAK.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def _sistem_yonergesi() -> str:
    """⚠️ Eskiden prompt KAYNAK METNINDEN dilimleniyordu:

        i = KAYNAK.index("You are the editorial producer")
        return KAYNAK[i : KAYNAK.index('\"\"\"', i)]

    Prompt iki sabite ayrilinca (DW-105: kanal kimligi + sozlesme) o dilim
    ilkinde bitti ve 11 test dustu — hicbiri gercek bir kusur degildi.
    Artik modele giden metnin KENDISI okunuyor.
    """
    return ya.editoryal_sistem_yonergesi()


# --- Altyazi bicimi (DW-103) ---------------------------------------------


def test_siyah_serit_kapali():
    """Kullanici istegi: metin dogrudan goruntunun uzerinde dursun (DW-103).

    ⚠️ 17 Agu'da bu karar YENIDEN soruldu ve KORUNDU. Altyazi kapisi 7
    render'in dordunde dusuyordu ve kodda hazir bir ara yol vardi — metin
    genisliginde, %55 saydam, yuvarlatilmis kutu
    (`--rounded-subtitle-background`, seritten farkli). Kanal sahibine
    acikca soruldu, REDDETTI: zemin yok, kontur kalinlastirilacak.

    ⚠️ Pencereyle dilimleme BIRAKILDI: gerekce yorumlari buyuyunce bayrak
    1400 karakterlik pencerenin disina tasti ve test, kod DOGRU oldugu halde
    dustu. Artik kaynagin tamami taraniyor — hem daha saglam hem daha genis
    bir guvence. Tirnakli arama `--no-...` icindeki alt dizeye TAKILMAZ.
    """
    assert '"--no-subtitle-background-enabled"' in KAYNAK
    assert '"--subtitle-background-enabled"' not in KAYNAK
    assert '"--rounded-subtitle-background"' not in KAYNAK


def test_kontur_serit_yerine_okunabilirligi_sagliyor():
    """Serit kalkinca beyaz metni acik zeminde ayakta tutan tek sey kontur.

    ⚠️ 5 -> 7 (2026-08-17). Olculdu: altyazi kapisi 7 render'in DORDUNDE
    dustu (65, 70, 72, 78; kapi 80) ve hakem her seferinde ayni gerekceyi
    yazdi — "white text lacks sufficient contrast against cloudy skies",
    "light text on light paper background". Kontur 5 yetmiyordu.

    ⚠️ Serit yine ACILMADI: kanal sahibine 17 Agu'da acikca soruldu ve yari
    saydam kutu secenegi de REDDEDILDI (bkz. `test_siyah_serit_kapali`).

    ⚠️ 7 bir TAVAN: 56px fontta ~%12,5 ve ustu harflerin ic bosluklarini
    kapatmaya baslar. Harfler bozulursa 6'ya INILIR, yukari cikilmaz.
    """
    i = KAYNAK.index('"--stroke-width"')
    govde = KAYNAK[i : i + 60]

    assert '"7"' in govde, "serit yokken kontur kalinlastirilmali"


def test_metin_beyaz_kontur_siyah():
    assert '"--text-fore-color",\n        "#FFFFFF"' in KAYNAK
    assert '"--stroke-color",\n        "#000000"' in KAYNAK


# --- Konu yonu: hikaye, nesne tarifi degil -------------------------------


def test_hikaye_anlatimi_isteniyor():
    """Olculdu (2026-08-07, DW-103): eski yonerge ansiklopedi maddesi
    uretiyordu.

        eski: "Machu Picchu: Architectural Marvel of the Inca"
              "Nestled high in the Andes, Machu Picchu is a stunning
               testament to Inca engineering."

        yeni: "The Legend of Machu Picchu's Lost Treasure"
              "In the 16th century, as Spanish conquistadors invaded Peru,
               the Incas sought to protect their wealth..."
    """
    yonerge = _sistem_yonergesi()

    assert "TELL A STORY, DO NOT DESCRIBE AN OBJECT" in yonerge
    assert "legend or myth" in yonerge
    assert "still unsolved" in yonerge
    assert "Name people, dates, and outcomes" in yonerge


def test_efsane_efsane_olarak_isaretleniyor():
    """Efsaneyi gercek gibi sunmak hem yaniltici hem az etkili."""
    yonerge = _sistem_yonergesi()

    assert "say plainly that it is a legend" in yonerge
    assert "separate it from the archaeological record" in yonerge


def test_olay_yasagi_kaldirildi():
    """⚠️ Eski kisit hattin YALNIZCA arsiv fotografi bulabildigi doneme aitti.

    "Belirli bir tarihsel an isteme" kurali, o anin gorseli bulunamayacagi
    icin vardi. AI gorsel yedegi calisir hale gelince (DW-97) kisit gecersiz
    kaldi ama prompt'ta durmaya devam ediyordu — ve tam da kullanicinin
    istedigi hikaye anlatimini engelliyordu.
    """
    yonerge = _sistem_yonergesi()

    assert "Do not require" not in yonerge or "a specific historical moment" not in yonerge
    assert "Avoid war rescues, named battles" not in yonerge


def test_olcu_ve_teknik_detay_geri_plana_atildi():
    """Boyut ve insaat teknigi anlatimi videoyu ansiklopediye cevirir."""
    yonerge = _sistem_yonergesi()

    assert "single supporting sentence at most" in yonerge


def test_dogruluk_kisiti_korunuyor():
    """Hikaye serbestligi, uydurma serbestligi DEGIL."""
    yonerge = _sistem_yonergesi()

    assert "truthful about what is known" in yonerge
    assert "uncertain claims" in yonerge, "belirsiz iddia yasagi durmali"
