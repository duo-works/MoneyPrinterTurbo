"""Kanca cesitliligi — ayni acilis tekrar tekrar kullanilmamali.

Olculdu (2026-08-06, DW-94): uretilen 6 videonun 4'u birebir "Did you know..."
ile basladi. Prompt zaten "merak boslugu yarat" diyordu; yasak tek basina
yetmiyor, model kendi gecmisini gormeli.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__)


def test_ilk_cumle_ayikliyor():
    metin = "The Colosseum swallowed 50,000 people in ten minutes. Built in AD 80, it..."

    assert ya.kanca(metin) == "The Colosseum swallowed 50,000 people in ten minutes."


def test_tek_cumlelik_metinde_tamami_doner():
    assert ya.kanca("A single sentence with no period") == "A single sentence with no period"


def test_bos_metin_coksuyor_degil():
    assert ya.kanca("   ") == ""


def test_yasak_kaliplar_promptta_sayiliyor():
    """Kusur bir davranis degil bir CUMLE oldugu icin testi de cumleye bakiyor."""
    kaynak = KAYNAK.read_text(encoding="utf-8")
    i = kaynak.index("You are the editorial producer")
    sistem = kaynak[i : i + 4000]

    assert "Did you know" in sistem, "yasak kalip acikca anilmali"
    assert "Have you ever wondered" in sistem
    assert "Imagine a world" in sistem
    assert "could belong to no other video" in sistem


def test_yayinlanan_kancalar_okunuyor(monkeypatch):
    monkeypatch.setattr(
        ya,
        "load_state",
        lambda: {
            "published": [
                {"hook": "Birinci acilis."},
                {"hook": "Ikinci acilis."},
                {"topic": "kancasiz eski kayit"},
            ],
            "rejected": [{"hook": "Reddedilen acilis."}],
        },
    )

    kancalar = ya._son_kancalar()

    assert kancalar == ["Birinci acilis.", "Ikinci acilis."]
    assert "Reddedilen acilis." not in kancalar, "reddedilen video kanca yasaklamamali"


def test_kanca_listesi_sinirli(monkeypatch):
    """Prompt sinirsiz uzayamaz; en yeniler tutulur."""
    monkeypatch.setattr(
        ya,
        "load_state",
        lambda: {"published": [{"hook": f"Acilis {i}."} for i in range(30)]},
    )

    kancalar = ya._son_kancalar(adet=12)

    assert len(kancalar) == 12
    assert kancalar[-1] == "Acilis 29.", "en yeni kayit listede olmali"


def test_uretilen_kayda_kanca_yaziliyor():
    """Kaydedilmezse `_son_kancalar` hep bos doner ve kalip hic kirilmaz."""
    kaynak = KAYNAK.read_text(encoding="utf-8")
    i = kaynak.index("record = {")
    # ⚠️ Sinir bir sonraki ALANA baglaniyor, karakter sayisina degil: sabit
    # pencere (800) araya eklenen her alanla daraliyor ve testi KENDI kusuru
    # yuzunden dusuruyor. Bu oturumda ucuncu kez oldu — `sahne_sayisi` alani
    # eklenince pencere `"hook"`u disarida birakti.
    govde = kaynak[i : kaynak.index('"quality": asdict(review)', i)]

    assert '"hook": kanca(plan.script)' in govde


def test_gecmis_kancalar_prompta_ekleniyor():
    kaynak = KAYNAK.read_text(encoding="utf-8")

    assert "_son_kancalar()" in kaynak
    assert "do not reuse their sentence pattern" in kaynak
