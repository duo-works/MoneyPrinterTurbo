"""Turetme kolu reddedilince BASKA KONU planlamiyor.

⚠️ NEDEN VAR — olculdu 2026-08-21, canli koşum (`--turet --privacy public`).
Turetilmis Alhambra Shorts'u sorunsuz kuruldu ve render edildi:

    ℹ️ turetme: Alhambra … · pencere 0 · 6 sahne · 113 kelime
    kare duzeni [shorts]: 6 sahne × 2 yuva = 12 kare
    anlatim 39.26 sn · klip 1.22-5.39 sn

Sonra nihai hakemin goru cagrisi bos cevap dondurdu, `should_abandon_topic`
atesledi ve hat sunu yapti:

    ⚠️ deneme 1/5 reddedildi: … (7 sahne, 157 kelime, capa 'Sacsayhuaman')

Yani `--turet` Alhambra turetmesini birakip ALAKASIZ bir konu planladi ve
turetilmemis bir video yayinlamaya gidiyordu. Hicbir satirda "turetme
dustu" yazmiyordu; kullanicinin istedigi is ile hattin yaptigi is sessizce
ayristi.

⚠️ Kok sebep bu deponun imza kusuru: kurtarma yolu, planin NEREDEN
geldigini bilmeden davraniyor. Iki yeniden planlama noktasi da "bu konu
tutmadi, baska bir konu sec" diyor — ama turetmede BASKA KONU YOKTUR,
plan yayinlanmis tek bir uzun videodan kuruluyor.

Bu dosya iki noktayi da yurutuyor (kaynak hakemi reddi VE konuyu terk) ve
ayrica sirali kolun yeniden planlamayi SURDURDUGUNU kilitliyor — duzeltme
oraya sizarsa gercek bir gerileme olurdu.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _uzun_kayit() -> dict:
    """`turetme` modulunun kabul ettigi en kisa gercek uzun yayin kaydi."""
    sahneler = [
        {
            "sahne": sira,
            "terim": f"Alhambra detay {sira}",
            "kaynak_dosya": f"alhambra-{sira}.jpg",
            "kaynak_dosya_2": "",
            "gelen": f"alhambra-{sira}.jpg",
            "anlatim": (
                f"The {sira}th court held a shallow basin fed by a clay pipe. "
                f"Water crossed the terrace before it reached the garden below."
            ),
            "kelime": 24,
        }
        for sira in range(1, 13)
    ]
    return {
        "topic": "Alhambra Nasrid palaces and their water system",
        "visual_anchor": "Alhambra",
        "title": "Alhambra: Why a Dying Kingdom Built Its Greatest Palace",
        "url": "https://youtube.com/shorts/LCr4700P5OM",
        "bicim": "uzun",
        "sahne_sayisi": 12,
        "description": "aciklama",
        "tags": ["Alhambra", "Granada", "Nasrid"],
        "ruh_hali": "gorkemli",
        "sahneler": sahneler,
        "script": " ".join(s["anlatim"] for s in sahneler),
    }


def _hat(monkeypatch, tmp_path, *, review: ya.QualityReview, kaynak_reddi: bool):
    """Turetilmis plani hakem reddine kadar goturen en kisa gercek yol.

    Doner deger: `generate_content_plan` cagri sayaci (tek elemanli liste).
    """
    video = tmp_path / "final-1.mp4"
    video.write_bytes(b"x")

    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "LOCK_FILE", tmp_path / "automation.lock")
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        ya,
        "load_state",
        lambda: {"published": [], "rejected": [], "completed_slots": []},
    )
    monkeypatch.setattr(ya, "save_state", lambda _s: None)
    monkeypatch.setattr(ya.notion_kuyrugu, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(
        ya, "create_review_montage", lambda *_a, **_k: tmp_path / "m.jpg"
    )
    monkeypatch.setattr(ya, "review_video", lambda *_a, **_k: review)
    # Onarim yolunun menuye uzanmasini engelle: bu dosya onarimi degil
    # YENIDEN PLANLAMAYI olcuyor.
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k, **_: [])
    monkeypatch.setattr(ya, "refine_search_terms", lambda p, *_a, **_k: p)
    # Baslik cikarimi: turetme yalnizca bunu harciyor, testte sabitleniyor.
    monkeypatch.setattr(
        ya, "_json_completion", lambda *_a, **_k: {"title": "Alhambra water #Shorts"}
    )

    sayac = [0]

    def _sayan_plan(*_a, **_k):
        sayac[0] += 1
        raise ya.DistinctTopicUnavailableError("bu testte yeni konu uretilmemeli")

    monkeypatch.setattr(ya, "generate_content_plan", _sayan_plan)

    if kaynak_reddi:

        def _uretici(_p, _a, **_k):
            raise ya.SourceMaterialRejected(review, [])

    else:

        def _uretici(_p, _a, **_k):
            return ("gorev-1", video, tmp_path / "s.txt", [], 0)

    monkeypatch.setattr(ya, "run_generator", _uretici)
    return sayac


# Hakem "bu konuyu terk et" diyecek kadar dusuk: agir kusur var, yani
# `onarilabilir_mi` False, skor da esigin altinda.
_TERK_REVIEW = ya.QualityReview(
    False,
    60,
    88,
    ["Frame 4 shows the wrong century"],
    agir_kusurlar=["kare 4: donem uyusmuyor"],
)


@pytest.mark.parametrize("kaynak_reddi", [False, True])
def test_turetme_reddi_YENI_KONU_PLANLAMIYOR(
    monkeypatch, tmp_path, capsys, kaynak_reddi
):
    """⚠️ MUTASYON: `yeniden_planlanabilir` kapisini kaldirmak bunu duser.

    Iki yeniden planlama noktasi da yurutuluyor: kaynak hakemi reddi
    (`SourceMaterialRejected`) ve konuyu terk (`should_abandon_topic`).
    """
    sayac = _hat(monkeypatch, tmp_path, review=_TERK_REVIEW, kaynak_reddi=kaynak_reddi)

    sonuc = ya.run_cycle(dry_run=True, turet=(_uzun_kayit(), 0))

    assert sonuc["status"] == "rejected"
    assert sayac[0] == 0, (
        "turetme kolunda YENI KONU planlandi — canli koşumda Alhambra "
        "turetmesi birakilip Sacsayhuaman planlanmisti"
    )
    assert "türetme reddedildi" in capsys.readouterr().out, (
        "dusus SESSIZ olmamali: kullanicinin istedigi is yapilmadiysa "
        "bunu soyleyen bir satir olmali"
    )


def test_SIRALI_kol_yeniden_planlamayi_SURDURUYOR(monkeypatch, tmp_path):
    """⚠️ MUTASYON: kapiyi `turet` yerine kosulsuz yazmak bunu duser.

    Zamanlanmis uretim hatti bu koldan geciyor ve orada "konu tutmadi,
    baskasini sec" DOGRU davranis: konu havuzdan seciliyor, yani gercekten
    baska bir konu var. Turetmeye ozel duzeltmenin buraya sizmasi uretimi
    tek denemeye indirirdi.
    """
    sayac = _hat(monkeypatch, tmp_path, review=_TERK_REVIEW, kaynak_reddi=False)
    plan = ya.turetilmis_plani_kur(_uzun_kayit(), 0)
    monkeypatch.setattr(ya, "generate_content_plan", None)

    cagri = [0]

    def _sayan_plan(*_a, **_k):
        cagri[0] += 1
        return plan

    monkeypatch.setattr(ya, "generate_content_plan", _sayan_plan)

    ya.run_cycle(dry_run=True, kuyruktan=True, yedek_konu=True)

    assert sayac[0] == 0  # taklit degistirildi, eski sayac artmamali
    assert cagri[0] > 1, "sirali kolda ilk plan + en az bir yeniden planlama beklenir"
