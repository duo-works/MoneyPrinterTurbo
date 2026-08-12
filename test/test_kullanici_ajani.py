"""Wikimedia User-Agent politikasi: iletisim bilgisi zorunlu (olculdu 2026-08-12).

⚠️ Uretimde iki kosum ust uste dustu: upload.wikimedia.org gorsel
indirmelerine 429 donuyordu. Ilk teshisim "kendi yukum" idi ve YANLISTI.
Kontrol olcumu — ayni URL, saniyeler arayla, tek degisken User-Agent:

    ShemzHistoryShorts/1.0                              → 429
    MoneyPrinterTurbo/1.0 (https://example.org; bot@x)  → 200
    MoneyPrinterTurbo-YouTubeAutomation/1.0             → 429

Sira ters cevrildiginde de 200/429/200 cikti, yani sonuc kova zamanlamasi
degil. Engellenen sey IP de degil, "MoneyPrinterTurbo" adi da degil:
ILETISIM BILGISI TASIMAYAN ciplak "Ad/Surum" bicimi.

Bu test dizeye iletisim bilgisini KILITLIYOR. Kaybolursa arsiv kaynagi
tamamen susar ve sebep hic gorunmez — 429 gorsel indirme katmaninda
patliyor, konu seciminden sonra, yani en pahali yerde.
"""

import importlib
import os

import wikimedia_materials as wm


def test_ajan_iletisim_bilgisi_tasiyor():
    """Politika "size ulasabilelim" diyor; ciplak ad/surum 429 aliyor."""
    assert "http" in wm.USER_AGENT or "@" in wm.USER_AGENT, (
        "User-Agent iletisim bilgisi tasimali; ciplak 'Ad/Surum' 429 aliyor"
    )


def test_ajan_hala_araci_tanitiyor():
    """Iletisim eklenirken aracin adi kaybolmamali — kim istek atiyor belli olsun."""
    assert "MoneyPrinterTurbo" in wm.USER_AGENT


def test_disaridan_ezilebiliyor(monkeypatch):
    """Kanal sahibi kendi adresini koyabilmeli; koda kimsenin kisisel
    adresi gomulmedi."""
    monkeypatch.setenv("WIKIMEDIA_USER_AGENT", "ShemzShorts/2.0 (+https://ornek.tv)")

    yeniden = importlib.reload(wm)
    try:
        assert yeniden.USER_AGENT == "ShemzShorts/2.0 (+https://ornek.tv)"
    finally:
        monkeypatch.delenv("WIKIMEDIA_USER_AGENT", raising=False)
        importlib.reload(wm)


def test_bos_ortam_degiskeni_varsayilani_dusurmuyor(monkeypatch):
    """Bos dize "ezme" degil "tanimsiz" demek; yoksa ciplak UA'ya dusulurdu."""
    monkeypatch.setenv("WIKIMEDIA_USER_AGENT", "   ")

    yeniden = importlib.reload(wm)
    try:
        assert "http" in yeniden.USER_AGENT
    finally:
        monkeypatch.delenv("WIKIMEDIA_USER_AGENT", raising=False)
        importlib.reload(wm)


def test_istekler_bu_ajani_gonderiyor(monkeypatch):
    """Sabit dogru olsa da GONDERILMIYORSA ise yaramaz."""
    gorulen: dict = {}

    class _Yanit:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            return None

    def sahte_get(url, **kwargs):
        gorulen.update(kwargs.get("headers") or {})
        return _Yanit()

    monkeypatch.setattr(wm.requests, "get", sahte_get)

    wm._get_with_retry(
        "https://upload.wikimedia.org/x.jpg", timeout=5, sleep_fn=lambda _s: None
    )

    assert gorulen.get("User-Agent") == wm.USER_AGENT
    assert os.environ.get("WIKIMEDIA_USER_AGENT") is None
