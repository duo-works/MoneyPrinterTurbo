"""Menu SECENEK sunmali: ayni aciklamayi 38 kez gostermek secenek degildir.

⚠️ Olculdu (2026-08-14, Cutty Sark). Menunun 40 girdisinin 38'i
`Cutty Sark 26-06-2012 (...).jpg` idi ve HEPSININ aciklamasi ayni tek
cumleydi ("Cutty Sark, King William Walk, Greenwich... badly damaged by fire
on 21 May 2007"). Bir yukleyicinin ayni gun cektigi 38 kare siralamanin
tepesini kapliyor — buyuk, dikey, yuksek cozunurluklu olduklari icin
`_puanli_adaylar` onlari one aliyor — ve gercekten farkli olan tarihsel SLV
fotograflarini menunun disina itiyor.

Menuye BAGLI bir hatta bu, modelin secebilecegi her seyi ayni tek fotografa
indirger.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402


def _aday(ad: str, aciklama: str) -> dict:
    return {"title": ad, "aciklama": aciklama, "tarih": ""}


def test_ayni_aciklama_tavanla_siniriliyor():
    adaylar = [_aday(f"File:{i}.jpg", "Greenwich, badly damaged by fire") for i in range(38)]
    adaylar.append(_aday("File:SLV.jpg", "The clipper in full sails"))

    seyrek = wm._aciklamayi_seyrelt(adaylar)

    assert len(seyrek) == wm.AYNI_ACIKLAMA_TAVANI + 1
    assert seyrek[-1]["title"] == "File:SLV.jpg", "gercekten farkli dosya menude kalmali"


def test_aciklamasiz_dosyalar_gruplanmiyor():
    """⚠️ Ortak bosluk bir benzerlik kaniti degil.

    Aciklamasi olmayan dosyalar Commons'ta yaygin; hepsini tek gruba
    toplamak menuyu iki girdiye indirirdi.
    """
    adaylar = [_aday(f"File:{i}.jpg", "") for i in range(6)]

    assert len(wm._aciklamayi_seyrelt(adaylar)) == 6


def test_BUYUK_grup_tavana_kadar_menude_kaliyor():
    """⚠️ KARNAK SINIFI — seyreltme gercek arzi yok etmemeli.

    Tavan 2 iken Commons kategori sablonu (Vikipedi giris cumlesi) tasiyan
    her konu terfi kapisinda eksik sayiliyordu: Karnak'in suzgecten gecen 59
    adayi menuye 6 girdi olarak dusuyordu ve kapi 12 istiyor.

    O 45'lik grup ORNEKLENDI (8 dosya, 28 cift): yalnizca 5 cift (%18)
    tekrar esiginin ustunde, ort. benzerlik 0,58. Yani dosyalar farkli ve
    atilmalari YANLIS red uretiyordu.
    """
    adaylar = [_aday(f"File:{i}.jpg", "the karnak temple complex") for i in range(45)]

    seyrek = wm._aciklamayi_seyrelt(adaylar)

    assert len(seyrek) == wm.AYNI_ACIKLAMA_TAVANI
    assert wm.AYNI_ACIKLAMA_TAVANI * 2 >= 12, (
        "iki aciklama grubu tek basina kapiyi (ASGARI_MENU=12) gecirebilmeli"
    )


def test_ilk_bastaki_sira_korunuyor():
    """Seyreltme siralamayi degistirmemeli: puan sirasi hala anlamli."""
    adaylar = [_aday("File:a.jpg", "x"), _aday("File:b.jpg", "y"), _aday("File:c.jpg", "x")]

    assert [a["title"] for a in wm._aciklamayi_seyrelt(adaylar)] == [
        "File:a.jpg",
        "File:b.jpg",
        "File:c.jpg",
    ]
