"""`hermes` cagrisi dustugunde SEBEBI de gorunmeli, yalnizca cikis kodu degil.

⚠️ OLCULDU (2026-08-19, 02:32 koşumu). Koşum plan asamasini HIC red almadan
gecti, videoyu render etti ve son incelemede dustu. Geriye kalan tek bilgi:

    RuntimeError: Hermes CLI vision inference failed with exit code 1

Sebebi sonradan ogrenilemedi — kontak sayfasi gecici dizinde uretiliyor ve
koşumla birlikte siliniyor, yani cagri birebir uretilemiyor. Elle yapilan
bir goru cagrisi ayni anda CALISIYORDU, yani hata ya geciciydi ya da o
goruntuye ozguydu; ikisini ayirt edecek veri yoktu.

Bir video render edildikten SONRA okunamayan bir hatayla olmek, bu oturumda
uc kez kapatilan korluk sinifinin aynisi:
  · `hermes -z` birincil saglayici hatasini yutup sessizce yedege dusuyordu
  · `CikarimZamanAsimi` saglayici arizasini kalite reddinden ayirmak icin eklendi
  · `resmedilemez_kusuru` yalnizca eslesen parcayi logluyordu, cumleyi degil

Depo bu dersi render komutunda ZATEN ogrenmisti (`stdout + STDERR` dosyaya
yaziliyor); iki cikarim yolu payini almamisti.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _sonuc(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(["hermes"], returncode, stdout, stderr)


def test_ozet_stderri_tercih_ediyor():
    assert ya._hermes_hata_ozeti(_sonuc(1, "gurultu", "HTTP 429 usage limit")) == (
        "HTTP 429 usage limit"
    )


def test_stderr_BOSSA_stdouta_dusuyor():
    """⚠️ Bazi hatalar stdout'a yaziliyor; yalnizca stderr'e bakan bir ozet
    tam da teshis edilmesi gereken vakalarda bos doner."""
    assert ya._hermes_hata_ozeti(_sonuc(1, "Error: model not entitled", "")) == (
        "Error: model not entitled"
    )


def test_iki_cikti_da_bossa_ANLASILIR_kaliyor():
    assert ya._hermes_hata_ozeti(_sonuc(1)) == "(cikti bos)"


def test_ozet_SINIRLI():
    """Metin hata mesajina ve log dosyasina giriyor; tam cikti kilobaytlarca olabilir."""
    ozet = ya._hermes_hata_ozeti(_sonuc(1, "", "x" * 5000))

    assert len(ozet) < 1000
    # Sondan kirpiliyor: gercek hata satiri ciktinin SONUNDA olur.
    assert ozet.endswith("x")


@pytest.mark.parametrize(
    "yol,cagri",
    [
        ("metin", lambda: ya._json_completion("sistem", "kullanici")),
        ("goru", lambda: ya._vision_json({"a": 1}, Path("/yok/resim.jpg"))),
    ],
)
def test_HATA_MESAJI_sebebi_tasiyor(monkeypatch, yol, cagri):
    """⚠️ Asil kosul: iki cikarim yolunun IKISI de sebebi yazmali.

    Yol GERCEKTEN yurutuluyor (kaynak metninde dize aranmiyor) — bu deponun
    `ee886ab`'de ogrendigi ders: kaynakta dize aramak kodun calistigini
    kanitlamaz.
    """
    monkeypatch.setattr(ya, "INFERENCE_BACKEND", "hermes-cli")
    monkeypatch.setattr(
        ya, "_run_hermes", lambda *_a, **_k: _sonuc(1, "", "HTTP 429 usage limit reached")
    )

    with pytest.raises(RuntimeError) as hata:
        cagri()

    assert "429" in str(hata.value), f"{yol} yolu sebebi yutuyor"
    assert "exit code 1" in str(hata.value), f"{yol} yolu cikis kodunu kaybetti"
