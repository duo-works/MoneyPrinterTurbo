"""Ikincil gorsel render ONCESI denetleniyor.

⚠️ OLCULDU (2026-08-17, 01 slotu, IKI koşumun IKISINDE de). Kaynak kapisi
(`review_source_materials`) calisiyordu ama yalnizca BIRINCIL gorselleri
goruyordu. Ikincil gorsel kapidan SONRA iniyor ve hicbir denetimden gecmeden
videonun yarisini dolduruyordu:

    Palmyra    kaynak kontak sayfasi 6/6 TEMIZ. Alti agir kusurun ALTISI da
               ikincil gorsel alan sahnelere dustu (3 ve 5).
               `ikincil/scene-05b.jpg` askeri hava ussunde bayrakli cocuklar
               (20. yy), `scene-04b.jpg` deveye binmis modern turist.
    Gobekli    tek agir kusur "kare 12" = 6. sahne. `scene-06b.jpg` bir
               PowerPoint slaydi: "Legacy of Strong Female Symbols in
               Anatolia", MO 9500 - MS 110.

Teshis tam da iki sayfanin KARSILASTIRILMASIYLA yapildi (birincil temiz,
ikincil bozuk), o yuzden montaj dosya adi ayrisiyor — bkz.
`test_montaj_birincil_sayfayi_EZMIYOR`.

⚠️ Kok neden `wikimedia_materials.ikincil_gorseller`in esleme yedegi: aday
bulunamayinca `_kategori_adaylari(...)[0]` aliniyor — kategori havuzunun ILK
dosyasi, alaka kontrolu YOK. Oradaki varsayim ("kategori uyeligi ozneyi
garanti eder") yalnizca YER icin dogru: Commons'in Palmyra kategorisi
Palmyra'nin modern turist fotograflarini da icerir.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(sahne_sayisi: int = 6) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Palmyra",
        visual_anchor="Palmyra",
        title="Palmyra",
        script="...",
        scenes=[
            {"narration": f"cumle {i}", "search_term": f"terim {i}"}
            for i in range(1, sahne_sayisi + 1)
        ],
        description="",
        tags=[],
    )


def _gorseller(tmp_path: Path, numaralar: list[int], toplam: int = 6) -> list[Path | None]:
    """Sahne-indeksli liste: ikincili olmayan sahne None."""
    ikincil: list[Path | None] = [None] * toplam
    for n in numaralar:
        yol = tmp_path / f"scene-{n:02d}b.jpg"
        Image.new("RGB", (400, 300), (n * 30 % 255, 80, 120)).save(yol)
        ikincil[n - 1] = yol
    return ikincil


@pytest.fixture
def kapi(monkeypatch):
    """Denetimi yakalar; gercek gorü cagrisi yapilmaz."""
    gorulen: dict = {}

    def kur(sorunlu: list[int]):
        def sahte(plan, montaj, *, secilen=None, bicim=None):
            gorulen["secilen"] = secilen
            gorulen["montaj"] = montaj
            return ya.QualityReview(
                publishable=True,
                visual_alignment_score=75,
                subtitle_readability_score=100,
                problem_scene_numbers=list(sorunlu),
            )

        monkeypatch.setattr(ya, "review_source_materials", sahte)
        return gorulen

    return kur


# --- Dusurme davranisi ----------------------------------------------------


def test_isaretlenen_ikincil_DUSURULUYOR(tmp_path, kapi):
    """Palmyra sahnesi: 5. sahnenin ikincili hava ussu fotografiydi."""
    kapi([5])
    ikincil = _gorseller(tmp_path, [3, 4, 5])

    assert ya.ikincil_gorselleri_denetle(_plan(), ikincil, attempt=1) == [5]


def test_temiz_ikincil_KORUNUYOR(tmp_path, kapi):
    """⚠️ Sinir bekcisi: denetim iyi ikincilleri silerse gorsel ritmi
    (`kare_yerlesimi` gerekcesi) coker ve kanal sahibinin sikayeti geri
    gelir — "fotograflar cok uzun sure kaliyor ekranda"."""
    kapi([])
    ikincil = _gorseller(tmp_path, [3, 4, 5])

    assert ya.ikincil_gorselleri_denetle(_plan(), ikincil, attempt=1) == []


def test_ikincil_yoksa_CAGRI_YAPILMIYOR(tmp_path, monkeypatch):
    """Bos sayfa icin gorü cagrisi bosa para ve bosa saniye."""
    def patla(*_a, **_k):
        raise AssertionError("ikincil yokken denetim cagrilmamali")

    monkeypatch.setattr(ya, "review_source_materials", patla)

    assert ya.ikincil_gorselleri_denetle(_plan(), [None] * 6, attempt=1) == []


def test_SAHNE_numaralari_korunuyor(tmp_path, kapi):
    """⚠️ `create_source_montage` hucreyi `material_files[numara - 1]` diye
    okuyor. Sikistirilmis liste ([03b, 04b, 05b]) verilseydi hakem 3 derken
    1. hucreyi gorurdu ve YANLIS sahne dusurulurdu."""
    gorulen = kapi([])
    ya.ikincil_gorselleri_denetle(_plan(), _gorseller(tmp_path, [3, 4, 5]), attempt=1)

    assert gorulen["secilen"] == [3, 4, 5]


def test_alakasiz_numara_YOK_SAYILIYOR(tmp_path, kapi):
    """Hakem ikincili olmayan bir sahneyi isaretlerse dusurecek sey yok."""
    kapi([1, 2, 5])
    ikincil = _gorseller(tmp_path, [3, 4, 5])

    assert ya.ikincil_gorselleri_denetle(_plan(), ikincil, attempt=1) == [5]


# --- Kapi bir IYILESTIRME, on kosul degil ---------------------------------


def test_hata_uretimi_DURDURMUYOR(tmp_path, monkeypatch, capsys):
    """⚠️ Ayni gerekce `arsiv_envanteri`de: tek bir 429 butun koşumu
    coplememeli. Denetim dusunce hat bugunku davranisina doner."""
    def patla(*_a, **_k):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(ya, "review_source_materials", patla)

    assert ya.ikincil_gorselleri_denetle(
        _plan(), _gorseller(tmp_path, [3]), attempt=1
    ) == []
    assert "atlandi" in capsys.readouterr().out


# --- Adli kayit -----------------------------------------------------------


def test_montaj_birincil_sayfayi_EZMIYOR(tmp_path, kapi):
    """⚠️ Teshis tam da iki sayfayi karsilastirarak yapildi: birincil kontak
    sayfasi TEMIZDI, bozukluk ikincildeydi. Ayni dosya adi kullanilsaydi o
    karsilastirma bir daha hic yapilamazdi."""
    gorulen = kapi([])
    ya.ikincil_gorselleri_denetle(_plan(), _gorseller(tmp_path, [3]), attempt=1)

    assert "-ikincil" in gorulen["montaj"].name


def test_montaj_eki_varsayilan_olarak_KAPALI(tmp_path):
    """Birincil sayfanin adi degismemeli — geriye donuk kayit okunabilir kalsin."""
    dosya = tmp_path / "a.jpg"
    Image.new("RGB", (400, 300), "blue").save(dosya)

    yol = ya.create_source_montage([dosya], attempt=1, konu="Palmyra")

    assert "-ikincil" not in yol.name
