"""Kaynak kontak sayfasi uzun formatta ORNEKLENIYOR.

⚠️ OLCULDU (2026-08-15, DOKUZUNCU Herculaneum koşumu, 46,2 dakika): plan
besinci denemede gecti, 45 gorsel indi, kaynak kapisi calisti ve model BOS
cevap dondurdu. 45 gorsel 4 sutuna dizilince kontak sayfasi 1600x3600
piksel oluyor; model o seritte hicbir seyi okuyamiyor.

⚠️ Cozum zaten depoda vardi: `hakem_kareleri` ayni dersi render SONRASI
hakem kapisinda ogrenmisti (`HAKEM_ORNEK_TAVANI` docstring'i: "45 karelik
bir videoda HER SAHNE DENETLENMIYOR"). Ders yalnizca o kapiya uygulanmis,
kaynak on-kapisi hic dokunulmamisti — `review_source_materials` `bicim`
parametresi bile almiyordu.

⚠️ NUMARALANDIRMA: hucrenin uzerine yazilan sayi hucrenin SIRASI degil
GERCEK sahne numarasi. Boylece hakem gercek sahne numarasini bildiriyor ve
`problem_scene_numbers` dogrudan `plan.scenes`e denk dusuyor — video
hakemindeki iki asamali cevrim (`hakem_karesinden_sahne`) burada gerekmiyor.
"""

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _dosyalar(tmp_path: Path, n: int) -> list[Path]:
    yollar = []
    for i in range(1, n + 1):
        p = tmp_path / f"sahne-{i:02d}.jpg"
        Image.new("RGB", (400, 300), (i * 5 % 255, 60, 90)).save(p)
        yollar.append(p)
    return yollar


# --- Orneklem secimi -------------------------------------------------------


def test_SHORTS_hic_orneklenmiyor(tmp_path):
    """⚠️ Olculerek kalibre edilmis bir kapinin gorus alani daraltilmaz."""
    dosyalar = _dosyalar(tmp_path, 16)

    assert ya.kaynak_ornegi(dosyalar, ya.SHORTS_BICIMI) == list(range(1, 17))


def test_uzun_formatta_TAVANA_iniyor(tmp_path):
    secilen = ya.kaynak_ornegi(_dosyalar(tmp_path, 45), ya.UZUN_BICIMI)

    assert len(secilen) <= ya.HAKEM_ORNEK_TAVANI


def test_ILK_ve_SON_her_zaman_iceride(tmp_path):
    """Kanca ve kapanis, videonun en cok izlenen iki ani."""
    secilen = ya.kaynak_ornegi(_dosyalar(tmp_path, 45), ya.UZUN_BICIMI)

    assert secilen[0] == 1
    assert secilen[-1] == 45


def test_tavan_altinda_TAMAMI_denetleniyor(tmp_path):
    secilen = ya.kaynak_ornegi(_dosyalar(tmp_path, 10), ya.UZUN_BICIMI)

    assert secilen == list(range(1, 11))


def test_ONARILAN_sahneler_her_zaman_iceride(tmp_path):
    """⚠️ Kapi bir sahneyi kusurlu bulup gorseli DEGISTIRILDIKTEN sonra sayfa
    yeniden uretiliyor. Duzgun orneklem o sahneyi disarida birakabilirdi ve
    hat gorseli degistirip degisikligin ise yarayip yaramadigina hic
    bakmamis olurdu."""
    secilen = ya.kaynak_ornegi(_dosyalar(tmp_path, 45), ya.UZUN_BICIMI, [7, 23, 31])

    assert {7, 23, 31} <= set(secilen)


def test_zorunlu_numaralar_SIRALI_kaliyor(tmp_path):
    secilen = ya.kaynak_ornegi(_dosyalar(tmp_path, 45), ya.UZUN_BICIMI, [31, 7])

    assert secilen == sorted(secilen)


def test_gecersiz_zorunlu_numara_ELENIYOR(tmp_path):
    """Sinir disi numara `material_files[n-1]`de IndexError verirdi."""
    secilen = ya.kaynak_ornegi(_dosyalar(tmp_path, 20), ya.UZUN_BICIMI, [0, 99, -3])

    assert all(1 <= n <= 20 for n in secilen)


# --- Kontak sayfasi --------------------------------------------------------


def test_sayfa_yalnizca_SECILEN_kareleri_tasiyor(tmp_path):
    dosyalar = _dosyalar(tmp_path, 45)
    secilen = ya.kaynak_ornegi(dosyalar, ya.UZUN_BICIMI)

    montaj = ya.create_source_montage(dosyalar, 1, "Herculaneum", secilen=secilen)

    with Image.open(montaj) as im:
        genislik, yukseklik = im.size
    satir = (len(secilen) + 3) // 4
    assert (genislik, yukseklik) == (4 * 400, satir * 300)


def test_ORNEKLENMEYEN_sayfa_eskisi_gibi(tmp_path):
    """Shorts yolu birebir ayni kalmali."""
    dosyalar = _dosyalar(tmp_path, 16)

    montaj = ya.create_source_montage(dosyalar, 1, "konu")

    with Image.open(montaj) as im:
        assert im.size == (4 * 400, 4 * 300)


def test_45_kare_okunabilir_boyutta_kaliyor(tmp_path):
    """⚠️ Dokuzuncu koşumu olduren sayi: 1600x3600 piksel."""
    dosyalar = _dosyalar(tmp_path, 45)
    secilen = ya.kaynak_ornegi(dosyalar, ya.UZUN_BICIMI)

    montaj = ya.create_source_montage(dosyalar, 1, "Herculaneum", secilen=secilen)

    with Image.open(montaj) as im:
        assert im.size[1] <= 1200, "sayfa hakemin okuyamayacagi kadar uzun"


# --- Isteme giden sahneler -------------------------------------------------


def test_isteme_YALNIZCA_gorunen_sahneler_gidiyor(tmp_path, monkeypatch):
    """45 sahnenin tamamini verip 12 kare gostermek, modelden goremedigi 33
    kare hakkinda hukum istemek olurdu."""
    yakalanan: dict = {}

    def sahte_goru(prompt, _montaj, **_):
        yakalanan.update(prompt)
        return {"visual_alignment_score": 90, "issues": [], "problem_scene_numbers": []}

    monkeypatch.setattr(ya, "_vision_json", sahte_goru)
    plan = ya.ContentPlan(
        topic="Herculaneum",
        visual_anchor="Herculaneum",
        title="baslik",
        script="metin",
        scenes=[
            {"narration": f"sahne {i}", "search_term": f"Herculaneum detay {i}"}
            for i in range(1, 46)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )

    ya.review_source_materials(plan, tmp_path / "yok.jpg", secilen=[1, 12, 45])

    assert [s["n"] for s in yakalanan["scenes"]] == [1, 12, 45]


def test_istem_numaralarin_ATLAYABILECEGINI_soyluyor(tmp_path, monkeypatch):
    """⚠️ Bu cumle olmazsa model numaralari 1'den yeniden sayar ve
    bildirdigi her numara YANLIS sahneyi gosterir."""
    yakalanan: dict = {}

    def sahte_goru(prompt, _montaj, **_):
        yakalanan.update(prompt)
        return {"visual_alignment_score": 90, "issues": [], "problem_scene_numbers": []}

    monkeypatch.setattr(ya, "_vision_json", sahte_goru)
    plan = ya.ContentPlan(
        topic="konu",
        visual_anchor="capa",
        title="baslik",
        script="metin",
        scenes=[{"narration": "a", "search_term": "capa detay"}],
        description="aciklama",
        tags=["a", "b", "c"],
    )

    ya.review_source_materials(plan, tmp_path / "yok.jpg")

    yonerge = yakalanan["instructions"]
    assert "number printed on each image is its scene number" in yonerge
    assert "never its position on the sheet" in yonerge
