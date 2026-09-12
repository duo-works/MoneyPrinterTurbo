"""Uretilemez aday kuyruga DONMEZ, `Yeni`ye doner; huni onu yeniden terfi ETMEZ (DW-140).

⚠️ OLCULDU (2026-09-12, 23:20 koşumu, $0,081, render yok). `Seçildi`deki War
of Jenkins' Ear "ayrik arz 8/8" ile terfi etmisti ama arsivin verdigi kareler
karikatur, bust ve kat planiydi; kaynak kapisi uc plani da render'a sokmadi:

    23:32  source_materials  Robert Walpole          45
    23:36  source_materials  Admiral Edward Vernon   45
    23:39  source_materials  Robert Walpole          35

Kopruden tek geri yol `adayi_birak` (→ `Seçildi`) oldugu icin aday kuyrukta
kaldi: 24 saat sonra ayni slotu yeniden yakacakti ve kaydi elle `Yeni`ye
cekmek kanal sahibine dusuyordu ("bu isi ben yapmak zorunda kalmayayim, kod
yapabilsin"). Uc parca:

  1. `aday_uretilemez_mi(reviews)` — koşum adayin hicbir planini render'a
     sokamadiysa (>= ASGARI_KAYNAK_REDDI kaynak reddi, baska asama yok);
  2. `run_cycle` `finally`: uretilemez aday `adayi_geri_cek`, digerleri
     eskisi gibi `adayi_birak`; kopru komutu yoksa `birak`a duser;
  3. `huni_besle.besle`: kaynak kapisinda dusmus `Yeni` aday ayrik-kare
     sayisiyla yeniden `Seçildi`ye tasinmaz — dongu burada kapaniyor.
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import huni_besle  # noqa: E402
import notion_kuyrugu as nk  # noqa: E402
import youtube_automation as ya  # noqa: E402

SRC = {"stage": "source_materials", "review": {"visual_alignment_score": 45}}
VID = {"stage": "video", "review": {"visual_alignment_score": 62}}
PLN = {"stage": "planning", "review": {"visual_alignment_score": 0}}

ORNEK = {
    "kimlik": "abc123",
    "baslik": "War of Jenkins' Ear",
    "sayfa_url": "https://notion.so/abc123",
    "onerilen_format": "Shorts",
    "dil": "en",
    "bosluk_skoru": 0.41,
    "talep": 24000,
}


# --- 1 · karar --------------------------------------------------------------


@pytest.mark.parametrize(
    ("reviews", "beklenen"),
    [
        ([], False),
        ([SRC], False),  # tek kaynak reddi PLANIN kusuru olabilir
        ([SRC, SRC], True),
        ([SRC, SRC, SRC], True),  # 23:20 koşumunun kendisi
        ([SRC, VID], False),  # render OLDU: kusur arsivde degil
        ([VID, VID], False),
        ([SRC, SRC, PLN], False),  # konu uretilemedi: baska bir kusur sinifi
        ([PLN, SRC, SRC], False),
    ],
)
def test_uretilemez_karari(reviews, beklenen):
    assert ya.aday_uretilemez_mi(reviews) is beklenen


def test_esik_ikiden_asagi_INMEZ():
    """Tek kaynak reddiyle `Yeni`ye cekmek, insanin secimini bir plan hatasina feda etmek."""
    assert ya.ASGARI_KAYNAK_REDDI >= 2


# --- 2 · run_cycle: uretilemez aday `Yeni`ye, digerleri kuyruga -------------


def _kaynak_reddi(*_a, **_k):
    raise ya.SourceMaterialRejected(
        ya.QualityReview(
            publishable=False,
            visual_alignment_score=45,
            subtitle_readability_score=100,
            issues=["Scene 1: political caricature, not the platform stones"],
            problem_scene_numbers=[1],
        )
    )


def _plan(capa: str = "Robert Walpole") -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="War of Jenkins' Ear",
        visual_anchor=capa,
        title="Jenkins' Ear #Shorts",
        script="s " * 100,
        scenes=[{"narration": f"sahne {i}", "search_term": f"{capa} detay {i}"} for i in range(1, 9)],
        description="d",
        tags=["history"],
    )


@pytest.fixture
def hat(monkeypatch, tmp_path):
    monkeypatch.setattr(ya, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(ya, "LOCK_FILE", tmp_path / "lock")
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(ya, "PLAN_KASASI", tmp_path / "kasa")
    monkeypatch.setattr(ya, "YTOTO_PATH", "/sahte/ytoto")
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda konu, **_k: [{"dosya": "x"}] * 40)
    aday = nk.Aday.sozlukten(ORNEK)
    monkeypatch.setattr(nk, "kuyrugu_oku", lambda **_kwargs: [aday])
    monkeypatch.setattr(nk, "adayi_kap", lambda *a, **k: None)
    cagri: dict[str, list] = {"geri_cek": [], "birak": []}
    monkeypatch.setattr(nk, "adayi_geri_cek", lambda a, **k: cagri["geri_cek"].append(k["gerekce"]))
    monkeypatch.setattr(nk, "adayi_birak", lambda a, **k: cagri["birak"].append(k["gerekce"]))
    return cagri


def test_her_plan_kaynak_kapisinda_dusunce_aday_YENIYE_cekiliyor(hat, monkeypatch):
    """23:20 koşumunun kendisi: uc plan, uc kaynak reddi, sifir render."""
    monkeypatch.setattr(ya, "generate_content_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(ya, "run_generator", _kaynak_reddi)

    sonuc = ya.run_cycle(kuyruktan=True, dry_run=True)

    assert sonuc["status"] == "rejected"
    assert len(hat["geri_cek"]) == 1, "uretilemez aday `Yeni`ye cekilmeli"
    assert hat["birak"] == [], "kuyruga geri konmamali"
    (gerekce,) = hat["geri_cek"]
    assert "kaynak kapısını geçmedi" in gerekce and "45" in gerekce


def test_render_olduysa_aday_KUYRUKTA_kaliyor(hat, monkeypatch):
    """Kaynak kapisini gecip hakemde dusen aday plan/hakem varyansi: eski davranis."""
    monkeypatch.setattr(ya, "generate_content_plan", lambda *a, **k: _plan())
    sayac = {"n": 0}

    def once_kaynak_sonra_render(*_a, **_k):
        sayac["n"] += 1
        if sayac["n"] == 1:
            _kaynak_reddi()
        raise RuntimeError("render tarafi bu testin konusu degil")

    monkeypatch.setattr(ya, "run_generator", once_kaynak_sonra_render)

    with pytest.raises(RuntimeError, match="render tarafi"):
        ya.run_cycle(kuyruktan=True, dry_run=True)

    # Tek kaynak reddi + beklenmedik istisna: uretilemez sayilMAZ.
    assert hat["geri_cek"] == []
    assert len(hat["birak"]) == 1


def test_planlama_hatasinda_aday_KUYRUKTA_kaliyor(hat, monkeypatch):
    monkeypatch.setattr(
        ya,
        "generate_content_plan",
        lambda *a, **k: (_ for _ in ()).throw(ya.DistinctTopicUnavailableError("yok")),
    )

    ya.run_cycle(kuyruktan=True, dry_run=True)

    assert hat["geri_cek"] == []
    assert len(hat["birak"]) == 1


# --- 2b · kopru: komut yoksa `birak`a dus -----------------------------------


@pytest.fixture
def sahte_kos(monkeypatch):
    cagrilar: list[list[str]] = []

    def kur(kodlar: dict[str, int]):
        def kos(komut, **_kwargs):
            cagrilar.append(komut)
            kod = kodlar.get(komut[2], 0)  # ["/sahte/ytoto", "aday", "<alt komut>", ...]
            return SimpleNamespace(
                returncode=kod, stdout="", stderr="unrecognized arguments" if kod else ""
            )

        monkeypatch.setattr(subprocess, "run", kos)
        monkeypatch.setattr(nk, "_ytoto_yolu", lambda _yol: "/sahte/ytoto")
        return cagrilar

    return kur


def test_geri_cek_komutu_gerekceyle_gidiyor(sahte_kos, capsys):
    cagrilar = sahte_kos({})
    aday = nk.Aday.sozlukten(ORNEK)

    nk.adayi_geri_cek(aday, gerekce="kaynak kapısı 3/3", ytoto_path="/sahte/ytoto")

    (komut,) = cagrilar
    assert komut[1:] == ["aday", "geri-cek", "abc123", "--not", "kaynak kapısı 3/3"]
    assert "kuyruktan çekildi" in capsys.readouterr().out


def test_kopru_komutu_yoksa_BIRAKa_dusuyor(sahte_kos, capsys):
    """Iki repo ayri sevk ediliyor; `geri-cek` canlida degilse aday mahsur kalmamali."""
    cagrilar = sahte_kos({"geri-cek": 2})
    aday = nk.Aday.sozlukten(ORNEK)

    nk.adayi_geri_cek(aday, gerekce="g", ytoto_path="/sahte/ytoto")

    assert [k[2] for k in cagrilar] == ["geri-cek", "birak"]
    assert "kuyruğa geri konuyor" in capsys.readouterr().out


def test_geri_cek_hata_firlatmiyor(sahte_kos):
    """`finally` icinde cagriliyor: temizlik adimi asil hatayi gizlememeli."""
    sahte_kos({"geri-cek": 1, "birak": 1})
    aday = nk.Aday.sozlukten(ORNEK)

    nk.adayi_geri_cek(aday, gerekce="g", ytoto_path="/sahte/ytoto")  # firlatmaz


# --- 3 · huni: kaynak kapisinda dusen aday yeniden terfi ETMEZ --------------


def _ret(baslik: str, stage: str = "source_materials") -> dict:
    return {
        "stage": stage,
        "slot": "2026-09-12-23",
        "kaynak": "huni",
        "aday_basligi": baslik,
        "topic": baslik,
        "visual_anchor": "Robert Walpole",
        "visual_alignment_score": 45,
        "rejected_at": "2026-09-12T23:32:27+03:00",
    }


def test_kaynak_retleri_sayiliyor():
    state = {"rejected": [_ret("War of Jenkins' Ear"), _ret("War of Jenkins' Ear"), _ret("Baska")]}
    assert ya.adayin_kaynak_retleri("War of Jenkins' Ear", state) == 2
    assert ya.adayin_kaynak_retleri("war of jenkins' ear", state) == 2, "buyuk/kucuk harf"
    assert ya.adayin_kaynak_retleri("Baska", state) == 1
    assert ya.adayin_kaynak_retleri("Yok", state) == 0


def test_video_asamasi_reddi_kaynak_reddi_SAYILMIYOR():
    state = {"rejected": [_ret("X", stage="video"), _ret("X", stage="video"), _ret("X", stage="planning")]}
    assert ya.adayin_kaynak_retleri("X", state) == 0


def test_huni_kaynak_kapisinda_dusen_adayi_terfi_ETMIYOR(monkeypatch, capsys):
    """Dongunun kapandigi yer: `Yeni`ye cekilen aday ayrik sayiyla geri gelmemeli."""
    yeni = [
        nk.Aday.sozlukten({**ORNEK, "kimlik": "jenkins", "baslik": "War of Jenkins' Ear"}),
        nk.Aday.sozlukten({**ORNEK, "kimlik": "temiz", "baslik": "Battle of Curuzú"}),
    ]
    state = {"rejected": [_ret("War of Jenkins' Ear"), _ret("War of Jenkins' Ear")], "published": []}
    monkeypatch.setattr(huni_besle, "takilanlari_kurtar", lambda kuru=False: [])
    monkeypatch.setattr(nk, "kuyrugu_oku", lambda **_k: [])  # Seçildi bos → eksik 6
    monkeypatch.setattr(huni_besle, "load_state", lambda: state)
    monkeypatch.setattr(huni_besle, "yeni_adaylar", lambda limit=120: yeni)
    monkeypatch.setattr(huni_besle, "_kullanilmis_capalar", lambda: [])
    monkeypatch.setattr(huni_besle, "uretilebilir_mi", lambda baslik: (True, 16))

    ozet = huni_besle.besle(kuru=True)

    assert ozet["terfi"] == ["Battle of Curuzú"]
    assert ("War of Jenkins' Ear", -2) in ozet["elenen"]
    assert "kaynak kapısında" in capsys.readouterr().out


def test_huni_kaynak_kapisi_kontrolu_AGA_CIKMIYOR(monkeypatch):
    """Elenen aday olcum tavanina sayilmamali — kontrol yerel (`state.json`)."""
    yeni = [nk.Aday.sozlukten({**ORNEK, "kimlik": "jenkins"})]
    state = {"rejected": [_ret("War of Jenkins' Ear"), _ret("War of Jenkins' Ear")], "published": []}
    monkeypatch.setattr(huni_besle, "takilanlari_kurtar", lambda kuru=False: [])
    monkeypatch.setattr(nk, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(huni_besle, "load_state", lambda: state)
    monkeypatch.setattr(huni_besle, "yeni_adaylar", lambda limit=120: yeni)
    monkeypatch.setattr(huni_besle, "_kullanilmis_capalar", lambda: [])
    olcum = []
    monkeypatch.setattr(huni_besle, "uretilebilir_mi", lambda baslik: olcum.append(baslik) or (True, 16))

    ozet = huni_besle.besle(kuru=True)

    assert olcum == [], "kaynak kapisinda dusen aday icin arsiv olculmemeli"
    assert ozet["olcum"] == 0


def test_tek_kaynak_reddi_terfiyi_ENGELLEMIYOR(monkeypatch):
    """Esik `ASGARI_KAYNAK_REDDI`: tek red planin kusuru olabilir, aday yine denenir."""
    yeni = [nk.Aday.sozlukten({**ORNEK, "kimlik": "jenkins"})]
    state = {"rejected": [_ret("War of Jenkins' Ear")], "published": []}
    monkeypatch.setattr(huni_besle, "takilanlari_kurtar", lambda kuru=False: [])
    monkeypatch.setattr(nk, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(huni_besle, "load_state", lambda: state)
    monkeypatch.setattr(huni_besle, "yeni_adaylar", lambda limit=120: yeni)
    monkeypatch.setattr(huni_besle, "_kullanilmis_capalar", lambda: [])
    monkeypatch.setattr(huni_besle, "uretilebilir_mi", lambda baslik: (True, 16))

    assert huni_besle.besle(kuru=True)["terfi"] == ["War of Jenkins' Ear"]


def test_kaydin_kendisi_json_kalibinda(tmp_path):
    """`state.json` kaydi bu testlerin varsaydigi alanlari tasiyor mu — gercek kayitla."""
    gercek = Path("/Users/mirzasaribiyik/Projects/MoneyPrinterTurbo/storage/youtube_automation/state.json")
    if not gercek.exists():
        pytest.skip("canli state yok")
    s = json.loads(gercek.read_text(encoding="utf-8"))
    kaynak = [r for r in s["rejected"] if r.get("stage") == "source_materials" and r.get("aday_basligi")]
    if not kaynak:
        pytest.skip("kaynak asamasi kaydi yok")
    assert ya.adayin_kaynak_retleri(kaynak[-1]["aday_basligi"], s) >= 1
