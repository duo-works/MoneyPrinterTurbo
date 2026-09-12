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


# --- METIN yolu: ayni ders, ikinci yol -----------------------------------
#
# ⚠️ Yukaridaki duzeltme 2026-08-16'da YALNIZCA gorü yoluna uygulandi. Metin
# yolu tek bir bos cevapta cökmeye devam etti ve 17 Agu 12:35 koşumunu ayni
# istisna oldurdu:
#
#     RuntimeError: model bos cevap dondurdu
#       ...run_cycle -> generate_content_plan -> _json_completion
#
# O koşum plani uc kez kurmus, Tikal arsivini indirmis ve iki kez render'a
# kadar gitmisti. Cozum depoda hazir duruyordu, buraya uygulanmamisti.


def test_METIN_bos_cevaptan_sonra_tekrar_deniyor(monkeypatch, tmp_path):
    _, cagri = _hazirla(monkeypatch, tmp_path, ["", '{"topic": "x"}'])

    assert ya._json_completion("sistem", "kullanici") == {"topic": "x"}
    assert cagri["adet"] == 2, "ilk bos cevaptan sonra tekrar denenmeli"


def test_METIN_bozuk_JSON_sonrasi_tekrar_deniyor(monkeypatch, tmp_path):
    _, cagri = _hazirla(monkeypatch, tmp_path, ["<html>502</html>", '{"topic": "y"}'])

    assert ya._json_completion("sistem", "kullanici") == {"topic": "y"}
    assert cagri["adet"] == 2


def test_METIN_ilk_denemede_calisirsa_tekrar_YOK(monkeypatch, tmp_path):
    _, cagri = _hazirla(monkeypatch, tmp_path, ['{"topic": "z"}'])

    ya._json_completion("sistem", "kullanici")

    assert cagri["adet"] == 1


def test_METIN_hepsi_duserse_ACIK_hata(monkeypatch, tmp_path):
    """⚠️ Sessizce bos sozluk DONMEMELI: cagiran taraf plani uretilmis sanip
    bos bir videoyu isleme sokardi."""
    _, cagri = _hazirla(monkeypatch, tmp_path, [""])

    with pytest.raises(RuntimeError):
        ya._json_completion("sistem", "kullanici")

    assert cagri["adet"] == ya.METIN_JSON_DENEMESI


# --- `null` govde: sozluk degilse yeniden deneme ---------------------------
#
# ⚠️ Olculdu (2026-09-12, 18:38 tetigi, iki koşum): `_json_govdesi` sozluk
# disi govdeyi (`null`) sessizce geciriyordu ve ikincil gorsel denetimi iki
# kez "'NoneType' object has no attribute 'get'" ile ATLANDI — o dal
# sarmalanmisti. Birincil kaynak kapisi ve hakem sarmalanmamis: ayni govde
# orada ODENMIS render'i cökerterek atardi.


def test_null_govde_SOZLUK_degil_diye_patliyor():
    with pytest.raises(ValueError, match="NoneType"):
        ya._json_govdesi("null")
    with pytest.raises(ValueError, match="list"):
        ya._json_govdesi("[1, 2]")
    with pytest.raises(ValueError, match="str"):
        ya._json_govdesi('"duz metin"')


def test_hata_mesaji_govdenin_basini_tasiyor():
    """Bir sonraki sefer sebep tahmin degil olcum olsun."""
    with pytest.raises(ValueError, match=r"\[1, 2, 3\]"):
        ya._json_govdesi("```json\n[1, 2, 3]\n```")


def test_null_govde_GORU_yolunda_yeniden_deneniyor(monkeypatch, tmp_path, capsys):
    """Ikincil denetimi iki kez atlatan govde: artik AttributeError degil, tekrar."""
    gorsel, cagri = _hazirla(monkeypatch, tmp_path, ["null", '{"visual_alignment_score": 80}'])

    assert ya._vision_json({"soru": "x"}, gorsel) == {"visual_alignment_score": 80}
    assert cagri["adet"] == 2
    assert "görü yanıtı okunamadı (deneme 1/" in capsys.readouterr().out


def test_null_govde_METIN_yolunda_yeniden_deneniyor(monkeypatch, tmp_path):
    _, cagri = _hazirla(monkeypatch, tmp_path, ["null", '{"topic": "x"}'])

    assert ya._json_completion("sistem", "kullanici") == {"topic": "x"}
    assert cagri["adet"] == 2


def test_ikincil_denetim_null_govdeyle_ATLANMIYOR(monkeypatch, tmp_path):
    """Bugunku satirin kendisi: `ikincil gorsel denetimi atlandi: 'NoneType'...`.
    Ikinci denemede okunabilir cevap gelince kapi CALISIYOR ve sahneyi dusuruyor."""
    _, cagri = _hazirla(
        monkeypatch,
        tmp_path,
        ["null", '{"visual_alignment_score": 60, "issues": ["kare 2"], "problem_scene_numbers": [2], "frames": []}'],
    )
    monkeypatch.setattr(ya, "create_source_montage", lambda *_a, **_k: tmp_path / "kare.jpg")
    (tmp_path / "kare.jpg").write_bytes(b"sahte-jpeg")
    plan = ya.ContentPlan(
        topic="Ephesus library",
        visual_anchor="Ephesus",
        title="t",
        script="s",
        scenes=[{"narration": f"c{i}", "search_term": f"Ephesus {i}"} for i in range(1, 4)],
        description="d",
        tags=["a"],
    )

    dusen = ya.ikincil_gorselleri_denetle(plan, [None, tmp_path / "kare.jpg", tmp_path / "kare.jpg"], 1)

    assert dusen == [2]
    assert cagri["adet"] == 2
