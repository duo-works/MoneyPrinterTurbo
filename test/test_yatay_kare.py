"""Yatay (16:9) render yolu — uzun formatin kare hazirligi.

⚠️ NEDEN AYRI BIR YATAY FONKSIYON YAZILMADI: parlaklik tabani
(`karanligi_ac`) kare hazirlama govdesinin ICINDE ve her sahne karesi
oradan geciyor. Catallansaydi yatay koldaki karanlik kareler sessizce
acilmadan kalirdi — ayni uyari `dikeye_yapistir` docstring'inde de var.
Bu yuzden `dikeye_uydur` artik `kareye_uydur`in ince bir sarmalayicisi.
"""

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _gorsel(yol: Path, en: int, boy: int) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (en, boy), (120, 120, 120)).save(yol, format="JPEG", quality=92)
    return yol


def _olcu(yol: Path) -> tuple[int, int]:
    with Image.open(yol) as g:
        return g.size


# --- Kare olcusu ve oran ---------------------------------------------------


def test_bicim_basina_kare_olcusu():
    assert (
        ya.kare_olcusu(ya.SHORTS_BICIMI)
        == (ya.SHORTS_EN, ya.SHORTS_BOY)
        == (1080, 1920)
    )
    assert ya.kare_olcusu(ya.UZUN_BICIMI) == (ya.UZUN_EN, ya.UZUN_BOY) == (1920, 1080)


def test_uzun_bicim_16_9():
    """⚠️ Dikey kalirsa YouTube videoyu Shorts sayar ve IZLENME SAATI YAZMAZ."""
    assert ya.en_boy_orani(ya.UZUN_BICIMI) == "16:9"
    assert ya.en_boy_orani(ya.SHORTS_BICIMI) == "9:16"


# --- Kare hazirlama --------------------------------------------------------


def test_yatay_hedef_1920x1080_uretiyor(tmp_path):
    kaynak = _gorsel(tmp_path / "k.jpg", 1600, 900)
    hedef = ya.kareye_uydur(kaynak, tmp_path / "h.jpg", en=ya.UZUN_EN, boy=ya.UZUN_BOY)

    assert _olcu(hedef) == (1920, 1080)


def test_dikey_sarmalayici_DEGISMEDI(tmp_path):
    kaynak = _gorsel(tmp_path / "k.jpg", 1600, 900)
    hedef = ya.dikeye_uydur(kaynak, tmp_path / "h.jpg")

    assert _olcu(hedef) == (1080, 1920)


def test_16_9_fotograf_yatayda_KIRPILMIYOR():
    """⚠️ Uzun formatin arsiv arzina uymasinin sebebi bu: dikey hedefte ayni
    fotograf %68 kirpilip bulanik bant yoluna duserdi."""
    kirpma = ya.kirpma_orani(1600, 900, ya.UZUN_EN, ya.UZUN_BOY)

    assert kirpma < 0.01, f"16:9 kaynak yatayda kirpilmamali, {kirpma:.2%} kirpildi"
    assert ya.kirpma_orani(1600, 900) > ya.AZAMI_KIRPMA, "dikeyde bant yolu beklenirdi"


def test_portre_fotograf_yatayda_BANT_yoluna_dusuyor(tmp_path):
    """Kural ayni, yon ters: yatayda sorun cikaran gorsel DIKEY olan."""
    portre = _gorsel(tmp_path / "p.jpg", 900, 1600)

    assert ya.bant_ister(portre, hedef_en=ya.UZUN_EN, hedef_boy=ya.UZUN_BOY)
    assert not ya.bant_ister(portre)

    hedef = ya.kareye_uydur(portre, tmp_path / "h.jpg", en=ya.UZUN_EN, boy=ya.UZUN_BOY)
    assert _olcu(hedef) == (1920, 1080), "bant yolunda da hedef kare dolmali"


def test_PARLAKLIK_TABANI_yatay_kolda_da_uygulaniyor(tmp_path, monkeypatch):
    """⚠️ Catallanmis bir yatay fonksiyon yazilsaydi kaybolacak olan sey."""
    cagrildi: list[str] = []
    gercek = ya.gorsel_olcum.karanligi_ac

    def izle(gorsel):
        cagrildi.append("evet")
        return gercek(gorsel)

    monkeypatch.setattr(ya.gorsel_olcum, "karanligi_ac", izle)
    kaynak = _gorsel(tmp_path / "k.jpg", 1600, 900)
    ya.kareye_uydur(kaynak, tmp_path / "h.jpg", en=ya.UZUN_EN, boy=ya.UZUN_BOY)

    assert cagrildi, "yatay kare parlaklik tabanindan gecmedi"


# --- Kare yerlesimi --------------------------------------------------------


def test_uzun_kipte_SAHNE_BASINA_TEK_kare(tmp_path):
    """⚠️ EN KRITIK DEGISMEZ: `klip_suresi` sesi KARE sayisina boluyor.
    Uzun kolda da `[A, A]` uretilseydi her karenin suresi yariya iner ve
    sessizce baska bir video cikardi."""
    birincil = [_gorsel(tmp_path / f"b{i}.jpg", 1600, 900) for i in range(5)]

    kareler, tam_dolan = ya.kare_yerlesimi(
        birincil, [None] * 5, tmp_path / "cikti", bicim=ya.UZUN_BICIMI
    )

    assert len(kareler) == len(birincil) * ya.UZUN_BICIMI.kare_yuvasi == 5
    assert tam_dolan == 0
    assert all(_olcu(k) == (1920, 1080) for k in kareler)


def test_uzun_kipte_IKINCI_GORSEL_kare_sayisini_DEGISTIRMIYOR(tmp_path):
    """Ikincil dosya verilse bile uzun kolda sahne basina tek kare kalir."""
    birincil = [_gorsel(tmp_path / f"b{i}.jpg", 1600, 900) for i in range(4)]
    ikincil = [_gorsel(tmp_path / f"i{i}.jpg", 1600, 900) for i in range(4)]

    kareler, _ = ya.kare_yerlesimi(
        birincil, ikincil, tmp_path / "cikti", bicim=ya.UZUN_BICIMI
    )

    assert len(kareler) == 4


def test_SHORTS_yerlesimi_DEGISMEDI(tmp_path):
    birincil = [_gorsel(tmp_path / f"b{i}.jpg", 1600, 900) for i in range(3)]

    kareler, tam_dolan = ya.kare_yerlesimi(birincil, [None] * 3, tmp_path / "cikti")

    assert len(kareler) == 3 * ya.KARE_YUVASI == 6
    assert tam_dolan == 0
    assert all(_olcu(k) == (1080, 1920) for k in kareler)


def test_yapistirma_uzun_kipte_HIC_kullanilmiyor(tmp_path, monkeypatch):
    """Alt alta yapistirma 16:9'u DIKEY kareye sigdirmak icin vardi."""

    def patlat(*_a, **_k):
        raise AssertionError("uzun formatta dikeye_yapistir cagrilmamali")

    monkeypatch.setattr(ya, "dikeye_yapistir", patlat)
    birincil = [_gorsel(tmp_path / f"b{i}.jpg", 1600, 900) for i in range(3)]
    ikincil = [_gorsel(tmp_path / f"i{i}.jpg", 1600, 900) for i in range(3)]

    ya.kare_yerlesimi(birincil, ikincil, tmp_path / "cikti", bicim=ya.UZUN_BICIMI)


# --- Kare -> sahne eslemesi ------------------------------------------------


def test_uzun_kipte_kare_i_SAHNE_i():
    """⚠️ Sabit 2'ye bolunseydi hakemin 30. karede gordugu kusur 15. sahneyi
    onartirdi — her onarim yanlis sahneye giderdi ve kimse fark etmezdi."""
    assert [ya.kareden_sahneye(k, 1) for k in (1, 2, 3, 30, 45)] == [1, 2, 3, 30, 45]


def test_SHORTS_eslemesi_DEGISMEDI():
    assert [ya.kareden_sahneye(k) for k in (1, 2, 3, 4)] == [1, 1, 2, 2]
    assert ya.kareden_sahneye(1, ya.KARE_YUVASI) == 1


def test_agir_kusurlu_kareler_yuvayi_KULLANIYOR():
    review = ya.QualityReview(
        publishable=False,
        visual_alignment_score=0,
        subtitle_readability_score=0,
        agir_kusurlar=["kare 30: yanlis donem", "kare 7: yanlis kisi"],
    )

    assert ya.agir_kusurlu_kareler(review, 1) == [7, 30]
    assert ya.agir_kusurlu_kareler(review, 2) == [4, 15]


# --- Hatta baglanti --------------------------------------------------------


def test_render_ORANI_bicimden_okuyor():
    """⚠️ Sabit "9:16" kalsaydi uzun video Shorts olarak yayinlanir ve
    izlenme saati yazmazdi — hattin butun amaci o saatler."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def run_generator(")
    govde = kaynak[i : kaynak.index("\ndef ", i + 10)]

    assert "en_boy_orani(bicim)" in govde
    assert '"9:16",' not in govde, "sabit oran hala render komutunda"


def test_kare_yerlesimi_bicimi_GECIRILIYOR():
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def run_generator(")
    govde = kaynak[i : kaynak.index("\ndef ", i + 10)]

    assert "bicim=bicim" in govde
