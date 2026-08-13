"""Konu KISI mi (Wikidata P31 = Q5) — uretim sirasini belirleyen sinyal.

⚠️ Olculdu (2026-08-13). Yayinlanan 12 videonun kaydinda konu sinifi ile
hakem kusuru arasinda temiz ayrim var:

    anit / yer / nesne   skor 70-90, kusur  0-3
    kisi biyografisi     skor 68-84, kusur 9-11

Sebep kisinin kendisi degil ARSIVI: kisi kategorileri portre yigini.

⚠️ Bu sinyale UCUZ ALTERNATIFLER denendi ve UCU DE ELENDI (bu dosyanin
varlik sebebi budur — ileride "daha ucuzu vardi" diye geri donulmesin):
  · dosya adi turu    → Kolezyum'un adlari anlamsiz, kazanani elerdi
  · algisal benzerlik → kaybeden 0,50-0,54 / kazanan 0,51-0,63, ayrismiyor
  · ton yayilimi      → Dholavira (85 puan, 0 kusur) 0,004 ile en dusugu
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402


def _onbellekleri_temizle():
    wm._QID_ONBELLEGI.clear()
    wm._KISI_ONBELLEGI.clear()
    wm._KATEGORI_ONBELLEGI.clear()


def _yanit(govde: dict):
    class Sahte:
        def json(self):
            return govde

    return Sahte()


def _ag(monkeypatch, *, qid: str | None, p31: list[str] | None):
    """Wikipedia→QID ve Wikidata→P31 cagrilarini taklit eder."""
    cagrilar: list[str] = []

    def sahte(url, **kwargs):
        params = kwargs.get("params") or {}
        if params.get("action") == "query":
            cagrilar.append("qid")
            sayfa = {"pageprops": {"wikibase_item": qid}} if qid else {}
            return _yanit({"query": {"pages": [sayfa]}})
        cagrilar.append(params.get("property", "?"))
        if p31 is None:
            return _yanit({"claims": {}})
        return _yanit(
            {
                "claims": {
                    "P31": [
                        {"mainsnak": {"datavalue": {"value": {"id": kimlik}}}}
                        for kimlik in p31
                    ]
                }
            }
        )

    monkeypatch.setattr(wm, "_get_with_retry", sahte)
    return cagrilar


def test_insan_true_donuyor(monkeypatch):
    _onbellekleri_temizle()
    _ag(monkeypatch, qid="Q8556", p31=["Q5"])

    assert wm.kisi_mi("Murad III") is True


def test_insan_olmayan_false_donuyor(monkeypatch):
    _onbellekleri_temizle()
    _ag(monkeypatch, qid="Q10285", p31=["Q839954", "Q41176"])

    assert wm.kisi_mi("Colosseum") is False


def test_birden_cok_p31_arasinda_insan_varsa_true(monkeypatch):
    """Bir oge hem "insan" hem baska bir sey olabilir."""
    _onbellekleri_temizle()
    _ag(monkeypatch, qid="Q1", p31=["Q215627", "Q5"])

    assert wm.kisi_mi("X") is True


def test_qid_yoksa_none(monkeypatch):
    """⚠️ None "kisi degil" DEMEK DEGIL — cagiran taraf ayirt etmeli."""
    _onbellekleri_temizle()
    _ag(monkeypatch, qid=None, p31=None)

    assert wm.kisi_mi("Bilinmeyen") is None


def test_p31_yoksa_none(monkeypatch):
    _onbellekleri_temizle()
    _ag(monkeypatch, qid="Q1", p31=None)

    assert wm.kisi_mi("X") is None


def test_ag_hatasi_none_donuyor_patlamiyor(monkeypatch):
    """⚠️ Siniflandirma bir IYILESTIRME; ag hatasi uretimi durdurmamali."""
    _onbellekleri_temizle()

    def patla(*_a, **_k):
        raise requests.ConnectionError("kopuk")

    monkeypatch.setattr(wm, "_get_with_retry", patla)

    assert wm.kisi_mi("Murad III") is None


def test_onbellek_ikinci_cagriyi_aga_cikarmiyor(monkeypatch):
    """Kuyruk taramasi her aday icin cagriyi tekrarlamamali."""
    _onbellekleri_temizle()
    cagrilar = _ag(monkeypatch, qid="Q1", p31=["Q5"])

    wm.kisi_mi("X")
    ilk = len(cagrilar)
    wm.kisi_mi("X")

    assert len(cagrilar) == ilk


def test_kategori_ile_qid_adimi_paylasiliyor(monkeypatch):
    """`commons_kategorisi` ve `kisi_mi` ayni QID cagrisini iki kez yapmamali."""
    _onbellekleri_temizle()
    cagrilar: list[str] = []

    def sahte(url, **kwargs):
        params = kwargs.get("params") or {}
        if params.get("action") == "query":
            cagrilar.append("qid")
            return _yanit({"query": {"pages": [{"pageprops": {"wikibase_item": "Q1"}}]}})
        if params.get("property") == "P373":
            return _yanit({"claims": {"P373": [{"mainsnak": {"datavalue": {"value": "Kat"}}}]}})
        return _yanit({"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}})

    monkeypatch.setattr(wm, "_get_with_retry", sahte)

    wm.commons_kategorisi("X")
    wm.kisi_mi("X")

    assert cagrilar.count("qid") == 1, "QID adimi onbellekten gelmeliydi"
