"""Görü modelinin okunamayan cevabi KOŞUMU OLDURMEMELI (DW-51).

⚠️ Olculdu (2026-08-16) — ayni gun IKI koşum bu yuzden oldu:

    06:13  json.decoder.JSONDecodeError: Expecting value: line 1 column 1
    14:15  RuntimeError: model bos cevap dondurdu

Ikisi de RET degil ÇÖKME: `run_cycle` yigin iziyle oluyor, uretim slotu
kayboluyor ve zamanlayici "HATA | cikis 1" yaziyor. 14:15 koşumu Terracotta
Army'yi ta hakem asamasina getirmisti — render bitmisti, ~25 dakikalik is
cope gitti.

Kusur modelin CIKTISINDA, girdide degil: ayni istem ikinci denemede
okunabilir JSON dondurebiliyor.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _istemci(cevaplar: list[str | None]):
    """Sirayla verilen govdeleri donduren sahte OpenAI istemcisi."""
    cagri = {"adet": 0}

    def create(**_k):
        govde = cevaplar[min(cagri["adet"], len(cevaplar) - 1)]
        cagri["adet"] += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=govde))]
        )

    istemci = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return istemci, cagri


def _hazirla(monkeypatch, tmp_path, cevaplar):
    istemci, cagri = _istemci(cevaplar)
    monkeypatch.setattr(ya, "INFERENCE_BACKEND", "openai")
    monkeypatch.setattr(ya, "_openai_client", lambda: (istemci, "kimi"))
    monkeypatch.setattr(ya, "_akil_yurutmeyi_kapat", lambda *_a, **_k: {})
    gorsel = tmp_path / "kare.jpg"
    gorsel.write_bytes(b"sahte-jpeg")
    return gorsel, cagri


def test_BOS_cevaptan_sonra_tekrar_deniyor(monkeypatch, tmp_path):
    """14:15 çökmesi — bos cevap."""
    gorsel, cagri = _hazirla(monkeypatch, tmp_path, ["", '{"skor": 82}'])

    sonuc = ya._vision_json({"soru": "x"}, gorsel)

    assert sonuc == {"skor": 82}
    assert cagri["adet"] == 2, "ilk bos cevaptan sonra tekrar denenmeli"


def test_BOZUK_JSON_sonrasi_tekrar_deniyor(monkeypatch, tmp_path):
    """06:13 çökmesi — JSON olmayan govde (`JSONDecodeError` ValueError'dir)."""
    gorsel, cagri = _hazirla(monkeypatch, tmp_path, ["ben bir JSON degilim", '{"skor": 75}'])

    assert ya._vision_json({"soru": "x"}, gorsel) == {"skor": 75}
    assert cagri["adet"] == 2


def test_ILK_denemede_calisirsa_tekrar_YOK(monkeypatch, tmp_path):
    """⚠️ Her deneme yuksek cozunurluklu bir gorü cagrisi — bosa harcanmamali."""
    gorsel, cagri = _hazirla(monkeypatch, tmp_path, ['{"skor": 90}'])

    ya._vision_json({"soru": "x"}, gorsel)

    assert cagri["adet"] == 1


def test_hepsi_duserse_ACIK_hata(monkeypatch, tmp_path):
    """Sessizce gecmemeli: kapi cevapsiz kalirsa video degerlendirilmemis olur."""
    gorsel, cagri = _hazirla(monkeypatch, tmp_path, [""])

    with pytest.raises(RuntimeError, match="okunabilir JSON vermedi"):
        ya._vision_json({"soru": "x"}, gorsel)

    assert cagri["adet"] == ya.GORU_JSON_DENEMESI
