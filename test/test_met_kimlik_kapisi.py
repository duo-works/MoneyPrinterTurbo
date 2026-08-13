"""Met'te capa, nesnenin NE OLDUGUNDA aranir; NE ZAMANDAN oldugunda degil.

⚠️ Olculdu (2026-08-13): "Tutankhamun" capasiyla `The Viceroy's Boat, Tomb
of Huy` kapiyi GECIYORDU — bambaska bir mezarin duvar resmi. Sebep genis
kanit kumesi: Huy, Tutankhamun DONEMINDE yasadigi icin `reign` ve `period`
alanlari capayi tasiyor ve nesne "ayni cagdan" diye geciyordu.

Hakemin bu oturumda onlarca kez yazdigi kusur tam da bu: "somebody else
sharing the same medal, uniform, institution or era".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import met_materials as mm  # noqa: E402


def _nesne(**alanlar) -> dict:
    temel = {
        "objectID": alanlar.pop("objectID", 1),
        "isPublicDomain": True,
        "primaryImage": "https://x/a.jpg",
        "objectURL": "https://metmuseum.org/1",
        "title": "",
        "objectName": "",
    }
    temel.update(alanlar)
    return temel


def test_donem_alanindaki_capa_YETMIYOR():
    """⚠️ Gercek vaka: Huy'un mezari, Tutankhamun'un saltanatindan."""
    nesneler = [
        _nesne(
            objectID=1,
            title="The Viceroy's Boat, Tomb of Huy",
            objectName="Facsimile painting",
            reign="reign of Tutankhamun",
            period="New Kingdom",
        )
    ]

    secilen = mm.select_met_candidate(nesneler, set(), "Tutankhamun", required_anchor="Tutankhamun")

    assert secilen is None, "donem alani capayi tasisa da nesne gecmemeli"


def test_baslikta_capa_varsa_geciyor():
    nesneler = [
        _nesne(
            objectID=2,
            title="Inscribed Linen Sheet from Tutankhamun's Embalming Cache",
            objectName="Linen",
        )
    ]

    secilen = mm.select_met_candidate(nesneler, set(), "Tutankhamun", required_anchor="Tutankhamun")

    assert secilen is not None
    assert secilen["id"] == 2


def test_nesne_adinda_capa_varsa_geciyor():
    nesneler = [_nesne(objectID=3, title="Fragment", objectName="Tutankhamun statuette")]

    secilen = mm.select_met_candidate(nesneler, set(), "Tutankhamun", required_anchor="Tutankhamun")

    assert secilen is not None


def test_etikette_capa_varsa_geciyor():
    """Etiketler nesnenin KIMLIGINI tasiyor, donemi degil."""
    nesneler = [
        _nesne(
            objectID=4,
            title="Statuette",
            objectName="Statuette",
            tags=[{"term": "Tutankhamun"}],
        )
    ]

    secilen = mm.select_met_candidate(nesneler, set(), "Tutankhamun", required_anchor="Tutankhamun")

    assert secilen is not None


def test_genis_kanit_SORGU_puanlamasinda_kaliyor():
    """⚠️ Daraltma yalnizca KIMLIK kapisinda.

    Donem, hanedan, teknik ve sanatci sorgu eslesmesinde hala degerli;
    orada baglam bilgisi, kimlik kapisinda ise yaniltici.
    """
    # ⚠️ Sinir bir sonraki FONKSIYONA baglaniyor, karakter sayisina degil:
    # sabit pencere araya eklenen her yorumla daraliyor ve testi kendi
    # kusuru yuzunden dusuruyor (bu oturumda iki kez oldu).
    kaynak = Path(mm.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def select_met_candidate(")
    govde = kaynak[i : kaynak.index("def search_met(", i)]

    assert "kimlik_terimleri" in govde
    assert "query_terms & evidence_terms" in govde, "sorgu puanlamasi genis kumede kalmali"
