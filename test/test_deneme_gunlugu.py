"""Her REDDEDILEN deneme iz birakmali — yalnizca sonuncusu degil.

⚠️ OLCULDU (2026-08-15, sekizinci Herculaneum koşumu): koşum 8,6 dakika
surdu, bes deneme de reddedildi ve geriye TEK satir bilgi kaldi:

    "5 denemede gecerli plan uretilemedi; son kusur: ... 48 sahne"

Diger dort denemenin neye taktigi kayboldu. Uzun format koşumlari 10-50
dakika suruyor; teshis edilemeyen her koşum yeni bir koşum demek.

⚠️ YUMUSAK KAPILAR daha da korduler: `alinti_kusuru`, kanca/kapanis/baslik
tekrari ve capa tekrari `son_kusur`u HIC yazmiyordu. Bes deneme bunlardan
duserse nihai mesaj eski bir dogrulama kusurunu ya da "bilinmiyor"
gosteriyordu — yani teshisi YANLIS yone gonderiyordu.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _dongu_govdesi() -> str:
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def generate_content_plan(") :]
    return govde[: govde.index("\ndef ", 10)]


def test_dogrulama_kusuru_DENEME_NUMARASIYLA_yaziliyor():
    govde = _dongu_govdesi()

    assert 'f"⚠️ deneme {deneme}/5 reddedildi:' in govde


def test_dogrulama_kusuru_OLCULERI_de_yaziyor():
    """Sahne sayisi, kelime sayisi ve capa — bir sonraki adimi bunlar belirliyor."""
    govde = _dongu_govdesi()

    assert "len(plan.scenes)} sahne" in govde
    assert "len(plan.script.split())} kelime" in govde
    assert "plan.visual_anchor!r}" in govde


def test_HER_yumusak_kapi_son_kusuru_yaziyor():
    """⚠️ Genelleyen test: bir kapi unutulursa o kapinin reddi gorunmez olur.

    Dongudeki her `continue`den once ya `son_kusur` atanmali ya da o dal
    plani KABUL etmeli. Sayim, kapi eklendiginde bu testin de guncellenmesini
    zorunlu kilar.
    """
    govde = _dongu_govdesi()

    assert govde.count("son_kusur = ") >= 6


def test_yumusak_kapi_redleri_de_YAZDIRILIYOR():
    govde = _dongu_govdesi()

    assert govde.count("deneme {deneme}/5 reddedildi") >= 6


def test_son_kusur_NIHAI_mesaja_giriyor():
    """Kapilar `son_kusur` yazmasa nihai mesaj yaniltirdi."""
    govde = _dongu_govdesi()

    assert "son kusur: {son_kusur or 'bilinmiyor'}" in govde


def test_alinti_kapisi_kusuru_ETIKETLI():
    """Hangi kapinin reddettigi mesajdan anlasilmali."""
    govde = _dongu_govdesi()

    assert re.search(r'son_kusur = f?"alinti kapisi:', govde)
