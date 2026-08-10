"""Kaynak incelemesi dusunce ONCE arsiv denenir, sonra AI (DW-118).

⚠️ Olculdu (2026-08-10): arsivi tekrar deneyen blok
`not AI_VISUAL_FALLBACK_ENABLED` kosuluna bagliydi. Yedek uretimde ACIK
oldugu icin o blok uretimde OLU KODDU: kaynak incelemesi dustugunde hat
arsivde daha iyi bir arama hic denemeden dogruca `ai-refinement`'a gidiyordu.

Sonucu o gecenin videolarinda gorunuyor — Scanagatta 6/6 sahne AI. Kanal
sahibinin geri bildirimi "AI resim biraz cok, internetten bulup uretmeye
calis daha cok"; asil kaldirac buydu.

Testler iki seyi tutuyor: arsiv gercekten once deneniyor mu, ve arsiv
yeterse AI hic cagrilmiyor mu.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402
from youtube_automation import (  # noqa: E402
    ContentPlan,
    QualityReview,
    SourceMaterialRejected,
    run_generator,
)

SAHNE_SAYISI = 7


def _plan() -> ContentPlan:
    return ContentPlan(
        topic="The forgotten rescue that changed history",
        visual_anchor="historic rescue",
        title="The Rescue History Almost Forgot #Shorts",
        script=" ".join(["history"] * 95),
        scenes=[
            {
                "narration": f"Scene {index}",
                "search_term": f"historic rescue scene {index}",
            }
            for index in range(1, SAHNE_SAYISI + 1)
        ],
        description="A remarkable true story.\n\n#Shorts #History",
        tags=["Shorts", "History", "Amazing Facts"],
    )


class RenderaUlasildi(Exception):
    """Kalite kapisi GECILDI isareti.

    ⚠️ Testler render'i calistirmiyor: render gercek goruntu dosyalari,
    seslendirme ve ffmpeg ister — hicbiri bu testin konusu degil. Kapinin
    gecildigini kanitlamanin ucuz ve kesin yolu, render'in ilk adiminda
    taninabilir bir istisna firlatmak.
    """


def _hazirla(monkeypatch, tmp_path, incelemeler, arsiv_indirme):
    """Yedek ACIK — uretimdeki hal."""
    monkeypatch.setattr("youtube_automation.AI_VISUAL_FALLBACK_ENABLED", True)
    monkeypatch.setattr("youtube_automation.download_scene_materials", arsiv_indirme)
    monkeypatch.setattr(
        "youtube_automation.create_source_montage",
        lambda *_args, **_kwargs: tmp_path / "sources.jpg",
    )
    sira = iter(incelemeler)
    monkeypatch.setattr(
        "youtube_automation.review_source_materials", lambda *_, **__: next(sira)
    )
    # Kapiyi gectikten sonraki adimlar (dikeye cevirme, seslendirme suresi,
    # render) bu testin konusu degil; ilki gercek dosya ister.
    monkeypatch.setattr(
        "youtube_automation.dikeye_uydur_hepsi", lambda dosyalar, _hedef: dosyalar
    )
    monkeypatch.setattr("youtube_automation.anlatim_suresi", lambda _metin: 30.0)
    monkeypatch.setattr("youtube_automation.muzik_sec", lambda *_a, **_k: "")

    def render(*_a, **_k):
        raise RenderaUlasildi

    monkeypatch.setattr("youtube_automation.subprocess.run", render)


def test_arsiv_yeterse_ai_hic_cagrilmiyor(monkeypatch, tmp_path):
    """Asil kosul: arsiv sahneyi kurtardiysa AI'ya hic gidilmez."""
    plan = _plan()
    ilk = [tmp_path / f"commons-{i}.jpg" for i in range(1, SAHNE_SAYISI + 1)]
    cagrilar: list[int] = []

    def arsiv(_konu, sahneler, *_a, **_k):
        cagrilar.append(len(sahneler))
        if len(sahneler) == SAHNE_SAYISI:
            return ilk, [{"title": f"File:c{i}.jpg", "scene": i} for i in range(1, 8)]
        # Revize edilmis terimlerle ikinci tur: yalnizca sorunlu sahneler.
        return (
            [tmp_path / f"arsiv-duzeltme-{i}.jpg" for i in range(len(sahneler))],
            [{"title": f"File:d{i}.jpg"} for i in range(len(sahneler))],
        )

    ai_cagrildi: list[str] = []
    monkeypatch.setattr(
        "youtube_automation.generate_ai_scene_materials",
        lambda *a, **k: ai_cagrildi.append("cagrildi") or [],
    )
    _hazirla(
        monkeypatch,
        tmp_path,
        [
            QualityReview(False, 60, 100, ["Commons mismatch"], ["yeni terim"], [3]),
            QualityReview(True, 95, 100, [], []),
        ],
        arsiv,
    )

    # Kapi gecildi: hat render'a ulasti.
    with pytest.raises(RenderaUlasildi):
        run_generator(plan, 1)

    assert cagrilar == [SAHNE_SAYISI, 1], "arsiv sorunlu sahne icin tekrar denenmedi"
    assert ai_cagrildi == [], "arsiv yettigi halde AI cagrildi"


def test_arsiv_yetmezse_ai_devraliyor(monkeypatch, tmp_path):
    """AI kaldirilmiyor, yalnizca SON careye tasiniyor."""
    plan = _plan()
    ilk = [tmp_path / f"commons-{i}.jpg" for i in range(1, SAHNE_SAYISI + 1)]

    def arsiv(_konu, sahneler, *_a, **_k):
        if len(sahneler) == SAHNE_SAYISI:
            return ilk, [{"title": f"File:c{i}.jpg", "scene": i} for i in range(1, 8)]
        raise ya.MaterialsUnavailableError("arsiv bu sahneyi besleyemiyor")

    ai_cagrilari: list[dict] = []

    def ai(*_a, **kwargs):
        ai_cagrilari.append(kwargs)
        return [tmp_path / "ai-3.png"]

    monkeypatch.setattr("youtube_automation.generate_ai_scene_materials", ai)
    _hazirla(
        monkeypatch,
        tmp_path,
        [
            QualityReview(False, 60, 100, ["Commons mismatch"], ["yeni terim"], [3]),
            QualityReview(False, 62, 100, ["hala kotu"], []),
        ],
        arsiv,
    )

    with pytest.raises(SourceMaterialRejected):
        run_generator(plan, 1)

    assert len(ai_cagrilari) == 1, "arsiv dustugu halde AI devralmadi"


def test_arsiv_yanlis_sayida_donerse_kosum_dusmuyor(monkeypatch, tmp_path):
    """⚠️ Bu yol artik HER kosumda calisiyor; sayi uyusmazligi cokme sebebi olmamali.

    Eskiden `strict=True` zip dogrudan ValueError firlatiyor ve butun videoyu
    dusuruyordu. Arsiv yardimci bir yol — basarisizligi AI'ya devretmeli.
    """
    plan = _plan()
    ilk = [tmp_path / f"commons-{i}.jpg" for i in range(1, SAHNE_SAYISI + 1)]

    def arsiv(_konu, sahneler, *_a, **_k):
        # Ikinci turda 1 sahne istendi ama 7 dosya donuyor — uyumsuz.
        return ilk, [{"title": f"File:c{i}.jpg", "scene": i} for i in range(1, 8)]

    monkeypatch.setattr(
        "youtube_automation.generate_ai_scene_materials",
        lambda *a, **k: [tmp_path / "ai-3.png"],
    )
    _hazirla(
        monkeypatch,
        tmp_path,
        [
            QualityReview(False, 60, 100, ["Commons mismatch"], ["yeni terim"], [3]),
            QualityReview(False, 62, 100, ["hala kotu"], []),
        ],
        arsiv,
    )

    # Cokme degil, duzgun bir red bekleniyor.
    with pytest.raises(SourceMaterialRejected):
        run_generator(plan, 1)


def test_arsiv_blogu_artik_yedek_bayragina_bagli_degil():
    """Kaynakta kosul gercekten kaldirilmis mi."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    assert "if not AI_VISUAL_FALLBACK_ENABLED and (" not in kaynak
