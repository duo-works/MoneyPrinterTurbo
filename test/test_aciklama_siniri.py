"""Aciklama YouTube'un 5.000 karakter sinirina kirpiliyor.

⚠️ OLCULDU (2026-08-15, DW-51 denetimi). `format_commons_credits` her
benzersiz kaynak icin bir satir yaziyor ve SATIR SAYISINA ust sinir yok:

    Shorts  : 6-10 kaynak   ≈ 1.000 karakter
    uzun    : 24-45 kaynak  ≈ 3.000-5.400 karakter

CC BY satirlari ayrica tam Commons adresini tasiyor (yuzde-kodlu, 100-150
karakter). `format_commons_credits` belgesi zaten "uc gorsel aciklamanin
1200 karakterini yiyordu" diyor.

⚠️ Kusur EN PAHALI anda patliyordu: `videos.insert` 400 doner ve bu, render
ile IKI kalite kapisindan SONRA olur.

⚠️ KIRPMA SIRASI HUKUKI: CC BY atif ZORUNLULUK, kamu mali / CC0 nezaket.
Once nezaket satirlari dusuyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

UST = "Shemz imzasi\n\nvideo aciklamasi"


def _nezaket(n: int) -> list[str]:
    return [f"• Kamu mali eser {i} · Bilinmeyen sanatci" for i in range(n)]


def _zorunlu(n: int) -> list[str]:
    return [
        f"• CC BY eser {i} · Sanatci {i} · CC BY 4.0 · https://commons.wikimedia.org/wiki/File:X{i}.jpg"
        for i in range(n)
    ]


def _kunye(zorunlu: int = 0, nezaket: int = 0) -> str:
    return "\n".join(["Images: Wikimedia Commons", *_zorunlu(zorunlu), *_nezaket(nezaket)])


# --- Sinira sigan durum ----------------------------------------------------


def test_kisa_aciklama_DOKUNULMADAN_geciyor():
    kunye = _kunye(nezaket=8)

    sonuc = ya.aciklamayi_kirp(UST, kunye)

    assert sonuc == f"{UST}\n\n{kunye}"


def test_kunye_yoksa_metin_aynen_kaliyor():
    assert ya.aciklamayi_kirp(UST, "") == UST


# --- Kirpma ----------------------------------------------------------------


def test_uzun_kunye_SINIRA_kirpiliyor():
    """45 kaynak: uzun formatin gercek sayisi."""
    sonuc = ya.aciklamayi_kirp(UST, _kunye(zorunlu=20, nezaket=25))

    assert len(sonuc) <= ya.YOUTUBE_ACIKLAMA_SINIRI


def test_ZORUNLU_atiflar_nezaketten_ONCE_korunuyor():
    """⚠️ CC BY atifi hukuki zorunluluk; kamu mali atifi nezaket."""
    sonuc = ya.aciklamayi_kirp(UST, _kunye(zorunlu=15, nezaket=40), sinir=2500)

    assert "CC BY eser 0" in sonuc
    assert "Kamu mali eser 39" not in sonuc


def test_kirpildigi_GORUNUYOR():
    """Sessizce kesmek, atifin eksik oldugunu gizlerdi."""
    sonuc = ya.aciklamayi_kirp(UST, _kunye(nezaket=60), sinir=1500)

    assert "…" in sonuc


def test_METIN_kunye_ugruna_kesilmiyor():
    """Kanal kimligi ve video aciklamasi her zaman iceride kalmali."""
    sonuc = ya.aciklamayi_kirp(UST, _kunye(zorunlu=30, nezaket=30), sinir=2000)

    assert sonuc.startswith(UST)


def test_kunye_BASLIGI_kaliyor():
    sonuc = ya.aciklamayi_kirp(UST, _kunye(nezaket=60), sinir=1200)

    assert "Images: Wikimedia Commons" in sonuc


def test_kunyesiz_asiri_uzun_metin_de_kirpiliyor():
    uzun = "x" * 6000

    assert len(ya.aciklamayi_kirp(uzun, "")) <= ya.YOUTUBE_ACIKLAMA_SINIRI


# --- Hatta baglanti --------------------------------------------------------


def test_YUKLEMEDEN_once_cagriliyor():
    """⚠️ Fonksiyon dogru olsa da cagrilmazsa kusur surer — ve bu kusur en
    pahali anda, render ile iki kapidan sonra patliyor."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "description = aciklamayi_kirp(" in kaynak


def test_seri_imzasi_UZUN_FORMATTA_da_dogru():
    """⚠️ Imza "short documentaries" diyordu ve 13 dakikalik bir videonun
    aciklamasinin ILK SATIRI oydu."""
    assert "short documentaries" not in ya.SERI_IMZASI
    assert "documentaries" in ya.SERI_IMZASI
