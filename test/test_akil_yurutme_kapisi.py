"""Akil yurutme modeli butun cikti butcesini dusunmeye harciyor.

⚠️ OLCULDU (2026-08-15, DW-51) — uzun format hattini tek basina durduran
kusur buydu ve ALTINCI koşumu oldurdu.

`moonshotai/kimi-k2.6` bir akil yurutme modeli. Uzun format istemi ona
butun cikti butcesini dusunmeye harcatiyor ve `content` BOS donuyor:

    max_tokens  2.000 -> reasoning_tokens 2.115, content None, finish "length"
    max_tokens 16.000 -> reasoning_tokens 16.000, content None
    Hermes'in 65.536'si -> 900 saniyede bile bitmiyor

Ayni istem `reasoning enabled=false` ile 163 saniyede 29.612 karakterlik
gecerli JSON donduruyor.

⚠️ Uc yol denendi ve UCU DE ISE YARAMADI, o yuzden cozum kodda:
  - `reasoning: {"effort": "low"}`  -> yine 15.999 akil token
  - Hermes `reasoning_overrides`    -> ayni istem yine 600 sn'de asildi
  - baska Kimi surumleri (k2.5, k2.7-code) -> ikisi de dusunuyor
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


# --- Akil yurutmeyi kapatan govde eki -------------------------------------


def test_openrouter_icin_KAPALI():
    ek = ya._akil_yurutmeyi_kapat("https://openrouter.ai/api/v1")

    assert ek == {"extra_body": {"reasoning": {"enabled": False}}}


def test_OPENAI_ucuna_gonderilmiyor():
    """⚠️ `reasoning` OpenAI'nin kendi ucunda taninmiyor; yollanirsa istek
    reddedilir ve hat calisan bir saglayicida coker."""
    assert ya._akil_yurutmeyi_kapat("https://api.openai.com/v1") == {}
    assert ya._akil_yurutmeyi_kapat("") == {}


def test_buyuk_harfli_adres_de_taniniyor():
    assert ya._akil_yurutmeyi_kapat("https://OpenRouter.ai/API/v1") != {}


# --- JSON govdesi ----------------------------------------------------------


def test_json_cercevesi_soyuluyor():
    """⚠️ `response_format` her saglayicida uyulan bir soz DEGIL: olculdu,
    OpenRouter uzerinden Kimi cevabi ```json cercevesiyle donduruyor."""
    assert ya._json_govdesi('```json\n{"a": 1}\n```') == {"a": 1}


def test_cerceve_yoksa_da_calisiyor():
    assert ya._json_govdesi('{"a": 1}') == {"a": 1}


def test_dil_etiketsiz_cerceve():
    assert ya._json_govdesi('```\n{"a": 1}\n```') == {"a": 1}


def test_BOS_cevap_SEBEBIYLE_patliyor():
    """⚠️ Bos cevap sessiz gecmemeli: akil yurutme kusuru tam olarak boyle
    gorunuyor ve ciplak `json.loads("")` mesaji sebebi GIZLIYOR."""
    with pytest.raises(RuntimeError, match="akil yurutme"):
        ya._json_govdesi("")

    with pytest.raises(RuntimeError, match="akil yurutme"):
        ya._json_govdesi(None)


# --- Cikti tavani ve zaman asimi ------------------------------------------


def test_cikti_tavani_uzun_formata_yetiyor():
    """Uzun format JSON'u ~7.000 token; tavan bunun en az iki kati olmali."""
    assert ya.AZAMI_CIKTI_TOKEN >= 14000


def test_goru_zaman_asimi_IKI_YOLDA_da_ayni():
    """⚠️ Sayi eskiden `hermes` yolunda GOMULUYDU, openai yolunda ise hic
    zaman asimi yoktu — zaman asimsiz cagri zamanlayici slotunu yer.

    ⚠️ Kaynak metninde SABIT ADI aranmiyor artik: sinir bicime baglandi
    (2026-08-15) ve iki yol da yerel `zaman_asimi` degiskenini kullaniyor.
    Aranan sey davranis — ayni bicimde iki yolun ayni sayiyi almasi.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def _vision_json(") :]
    govde = govde[: govde.index("\ndef ", 10)]

    assert govde.count("zaman_asimi") >= 3, "iki yol da ayni degiskeni kullanmali"
    assert "timeout=float(zaman_asimi)" in govde, "openai yolu zaman asimi almali"


def test_uzun_kipte_goru_siniri_BUYUK():
    """Kontak sayfasi ve `frames` dizisi 45 sahnede kat kat buyuyor."""
    assert ya.goru_zaman_asimi(ya.UZUN_BICIMI) > ya.goru_zaman_asimi(ya.SHORTS_BICIMI)


def test_SHORTS_goru_siniri_DEGISMEDI():
    """⚠️ Kalibre edilmis bir sinir; uzun formatin bedeli Shorts'a odetilmez."""
    assert ya.goru_zaman_asimi(ya.SHORTS_BICIMI) == 360
    assert ya.goru_zaman_asimi(None) == 360


def test_en_kotu_goru_yuku_ZAMANLAYICIYA_sigiyor():
    """⚠️ Kaynak kapisi bir denemede en fazla UC kez cagriliyor (ilk
    inceleme, arsiv iyilestirmesi, AI yedegi). Sinir bedava buyutulemez."""
    assert ya.goru_zaman_asimi(ya.UZUN_BICIMI) * 3 < 3 * 3600


def test_iki_yol_da_akil_yurutmeyi_KAPATIYOR():
    """⚠️ Genelleyen test: bir cagri unutulursa o kapi sessizce duser.

    Metin yolu senaryoyu uretiyor, gorü yolu iki kalite kapisini da
    calistiriyor. Gorü unutulursa kotu video durdurulamaz.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert kaynak.count("**_akil_yurutmeyi_kapat(base_url)") == 2
