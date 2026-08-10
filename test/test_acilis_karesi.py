"""1. sahne genis planla acilmaz (DW-121).

⚠️ Olculdu (2026-08-10, Chaco Canyon'un ilk 11 saati — kanalin ilk gercek
izleyici verisi): 374 goruntuleme, trafigin %97,3'u Shorts akisi. YouTube
videoyu DAGITIYOR, sorun erisim degil.

Asil sayi: izleyicilerin %73'u IZLEMEDEN geciyor, %27'si kaliyor. Kalanlar
iyi izliyor — 33 saniyelik videoda ortalama 0:20, yani %61. Govde tutuyor,
ACILIS tutmuyor.

Sebep kodda bulundu: `kare_dili` listeyi sahne numarasina gore donduruyordu
ve `KARE_DILI[0]` "a wide establishing shot with the subject small in a large
landscape". Yani her videonun 1. sahnesi, tanim geregi, oznenin minicik
oldugu genis bir plan. Canyon'un ilk 3 saniyesi tam boyle: mavi saat, sonuk,
figur kadrajin kucuk bir noktasi.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def test_birinci_sahne_genis_plan_almiyor():
    """Asil kosul — olculen kusur buydu."""
    kadraj = ya.kare_dili(1, "Chaco Canyon")
    assert kadraj != ya.KARE_DILI[0]
    assert "wide establishing shot" not in kadraj
    assert "subject small" not in kadraj


def test_acilis_her_konuda_yakin_ve_okunakli():
    for kadraj in ya.ACILIS_KARELERI:
        assert "wide establishing" not in kadraj
        assert "subject small" not in kadraj


def test_acilis_konuya_gore_degisiyor():
    """Tekdüzelik acilista olusmasin: butun videolar ayni kareyle acilmamali."""
    konular = [
        "Chaco Canyon",
        "Franziska Scanagatta",
        "William Hardham",
        "Jacopo de' Pazzi",
        "Anita Florence Hemmings",
        "Mary Ritter Beard",
        "Nazca Lines",
        "Antikythera Mechanism",
    ]
    secilenler = {ya.kare_dili(1, konu) for konu in konular}
    assert len(secilenler) >= 3, f"acilis cesitliligi zayif: {secilenler}"


def test_acilis_ayni_konuda_kararli():
    """⚠️ `hash()` degil crc32 — kosum tekrar uretilebilmeli."""
    assert ya.kare_dili(1, "Chaco Canyon") == ya.kare_dili(1, "Chaco Canyon")


def test_diger_sahneler_eski_donusumu_koruyor():
    """Duzeltme yalnizca 1. sahneyi degistirmeli; cesitlilik dongusu kalmali."""
    for sahne in range(2, 11):
        assert ya.kare_dili(sahne, "Chaco Canyon") == ya.KARE_DILI[(sahne - 1) % 10]


def test_konu_verilmezse_eski_davranis():
    """Eski cagrilar ve testler bozulmamali."""
    assert ya.kare_dili(1) == ya.KARE_DILI[0]


def test_acilis_kadraji_prompta_bagli():
    """Liste dogru olsa bile prompta girmezse kusur surer."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    assert "kare_dili(index, plan.topic)" in kaynak
