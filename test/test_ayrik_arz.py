"""Render oncesi AYRIK ARZ kapisi (2026-08-22).

⚠️ OLCULDU — uretim menu boyunda (`sinir=40`), hedef 8 sahne:

    YAYIN  Persepolis 16 · Chichen 13 · Sacsayhuaman 12 · Moai 10 ·
           Palmyra 10 · Great Sphinx 9      -> ALTISI DA GECER
    red    Jenkins Ear 10 · Gajdusek 9      -> gecer (kapi TEK BASINA ayirt
                                               etmiyor ve etmemeli)
    red    May Ayim 6 · PETN 5              -> ELENIR

Iki dogru pozitif, SIFIR yanlis pozitif.

⚠️ Kapinin UCUNCU bir seyi olcmedigi de olculdu: ayni 10 dosya 400px ve
1600px'ten gecirildi -> ayni dosyanin parmak izi benzerligi ort 0,992, AYRIK
sayi 6 = 6, cift benzerliklerinde |fark| max 0,031.

Fikstur: 16x16 rastgele ikili desen 640x480'e NEAREST ile buyutuluyor.
Olculdu — farkli tohumlarin cift benzerligi 0,398-0,629 (esik 0,70), ayni
tohum 1,000. Yani "farkli" ve "ayni" kararlari esikten uzakta duruyor.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gorsel_olcum as go  # noqa: E402
import huni_besle  # noqa: E402
import wikimedia_materials as wm  # noqa: E402
import youtube_automation as ya  # noqa: E402


def _desen(yol: Path, tohum: int) -> Path:
    rng = np.random.default_rng(tohum)
    kucuk = (rng.random((16, 16)) > 0.5).astype("uint8") * 255
    im = Image.fromarray(kucuk).convert("RGB")
    im.resize((640, 480), Image.Resampling.NEAREST).save(yol)
    return yol


@pytest.fixture
def hat(monkeypatch, tmp_path):
    """Aga cikmadan GERCEK donusum + GERCEK parmak izi ile kosturur."""
    monkeypatch.setattr(ya, "KARE_IZI_DOSYASI", tmp_path / "izler.json")
    sayac = {"indirme": 0, "dosya": 0, "donusum": 0}
    tohumlar: dict[str, int] = {}
    menu_sayaci = {"n": 0}

    def _kucuk(dosyalar, hedef_dizin):
        sayac["indirme"] += 1
        hedef_dizin.mkdir(parents=True, exist_ok=True)
        cikti = {}
        for ad in dosyalar:
            sayac["dosya"] += 1
            cikti[ad] = _desen(hedef_dizin / f"{len(cikti)}.jpg", tohumlar[ad])
        return cikti

    monkeypatch.setattr(wm, "menu_kucuk_resimleri", _kucuk)

    gercek_donusum = ya.dikeye_uydur

    def _donustur(kaynak, hedef):
        sayac["donusum"] += 1
        return gercek_donusum(kaynak, hedef)

    monkeypatch.setattr(ya, "dikeye_uydur", _donustur)

    def _menu(*tohum_serisi: int) -> list[dict[str, str]]:
        # ⚠️ Her cagri AYRI dosya adlari uretiyor: onbellek anahtari dosya
        # basligi, yani ayni adlar iki olcumu birbirine baglardi.
        menu_sayaci["n"] += 1
        girdiler = []
        for sira, tohum in enumerate(tohum_serisi):
            ad = f"Menu{menu_sayaci['n']} {sira}.jpg"
            tohumlar[ad] = tohum
            girdiler.append({"dosya": ad, "gosterdigi": "x", "tarih": ""})
        return girdiler

    return SimpleNamespace(menu=_menu, sayac=sayac)


# --- Cekirdek karar ---------------------------------------------------------


def test_AYRIK_hedefin_altinda_kalinca_YETMIYOR(hat):
    """⚠️ ASIL TEST — May Ayim'in birebir sekli: menude 10 dosya, dikeye
    cevrilince 6 ayri kare. Bugunku ham sayi kapisi (10 >= 8) GECIRIYORDU."""
    menu = hat.menu(*range(6), *range(4))

    assert ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI) is False


def test_AYRIK_hedefi_gecince_YETIYOR(hat):
    """Sacsayhuaman'in sekli (12 ayrik / hedef 8) — 00:37'de yayinlandi."""
    menu = hat.menu(*range(12))

    assert ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI) is True


def test_ESIK_gorsel_olcumden_OKUNUYOR(hat, monkeypatch):
    """⚠️ Esik kopyalanmis olsaydi bu mutasyon hicbir seyi degistirmezdi ve
    kapi, indiricinin (`_tekrar_mi`) kullandigi esikten sessizce ayrisirdi."""
    menu = hat.menu(*range(12))
    monkeypatch.setattr(go, "ARSIV_TEKRAR_ESIGI", 0.0)

    assert ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI) is False


# --- Hata halinde ACIK duser ------------------------------------------------


def test_INDIRME_dusunce_ACIK_duser(hat, monkeypatch):
    def _patla(*_a, **_k):
        raise RuntimeError("ag yok")

    monkeypatch.setattr(wm, "menu_kucuk_resimleri", _patla)
    menu = hat.menu(*range(6), *range(4))

    assert ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI) is True


def test_PARMAK_IZI_dusunce_ACIK_duser(hat, monkeypatch):
    def _patla(*_a, **_k):
        raise OSError("bozuk gorsel")

    monkeypatch.setattr(go, "parmak_izi", _patla)
    menu = hat.menu(*range(6), *range(4))

    assert ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI) is True


def test_OLCULEN_kare_hedeften_AZSA_acik_duser(hat):
    """⚠️ Red icin olcumun KENDISI yeterli olmali. Uc kare olcup "ayrik arz
    yok" demek, dusen bir olcumu "arsiv yetersiz" diye raporlamak olurdu —
    tek bir ag hatasi konuyu elerdi."""
    menu = hat.menu(0, 0, 0)

    assert ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI) is True


# --- Donusum ve maliyet -----------------------------------------------------


def test_UZUN_formatta_DONUSUM_UYGULANMIYOR(hat):
    """§B'nin (`880f26c`) enjeksiyon kuralinin aynisi: uzun formatta kare
    zaten ~16:9, dikey kirpma orada BASKA bir goruntuyu olcerdi."""
    ya.ayrik_arz_yeter_mi(hat.menu(*range(12)), 8, bicim=ya.UZUN_BICIMI)
    uzun = hat.sayac["donusum"]

    ya.ayrik_arz_yeter_mi(hat.menu(*range(12)), 8, bicim=ya.SHORTS_BICIMI)

    assert uzun == 0, "uzun formatta dikey donusum uygulandi"
    assert hat.sayac["donusum"] > 0, "Shorts'ta donusum uygulanmadi"


def test_ERKEN_CIKIS_menunun_tamamini_indirmiyor(hat):
    """Sacsayhuaman 37 girdinin 14'unde hedefe ulasti; kalani hic inmedi."""
    menu = hat.menu(*range(40))

    assert ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI) is True
    assert hat.sayac["dosya"] <= 16, hat.sayac


def test_ONBELLEK_ikinci_cagrida_AGA_CIKMIYOR(hat):
    menu = hat.menu(*range(12))
    ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI)
    ilk = hat.sayac["dosya"]

    ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI)

    assert ilk > 0
    assert hat.sayac["dosya"] == ilk, "onbellek okunmadi, dosyalar yeniden indi"


def test_ONBELLEK_SURUMU_degisince_eski_kayit_KULLANILMIYOR(hat, monkeypatch):
    """⚠️ Donusum ya da iz bicimi degisirse eski izler yeni olcumle
    karsilastirilamaz — surum kontrolu bunun tek korumasi."""
    menu = hat.menu(*range(12))
    ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI)
    ilk = hat.sayac["dosya"]

    monkeypatch.setattr(ya, "KARE_IZI_SURUMU", ya.KARE_IZI_SURUMU + 1)
    ya.ayrik_arz_yeter_mi(menu, 8, bicim=ya.SHORTS_BICIMI)

    assert hat.sayac["dosya"] > ilk


def test_IZ_tur_donusu_KAYIPSIZ():
    iz = np.random.default_rng(7).random((16, 16)) > 0.5

    assert go.benzerlik(iz, go.izi_oku(go.izi_yaz(iz))) == 1.0


def test_IZ_yanlis_uzunlukta_metni_REDDEDIYOR():
    with pytest.raises(ValueError):
        go.izi_oku("aabb")


# --- Hangi kapi olcuyor, hangisi olcmuyor -----------------------------------


def test_TERFI_taramasi_HIC_kucuk_resim_INDIRMIYOR(hat, monkeypatch):
    """⚠️ `uretilebilir_mi` koşum basina `OLCUM_TAVANI` (45) adaya kadar
    cagriliyor; ayrik olcumu oraya koymak ~900 indirme/koşum demekti."""
    menu = hat.menu(*range(6), *range(4))
    monkeypatch.setattr(huni_besle, "arsiv_envanteri", lambda *_a, **_k: menu)

    yeter, olculen = huni_besle.uretilebilir_mi("X")

    assert (yeter, olculen) == (True, 10)
    assert hat.sayac["indirme"] == 0, "terfi taramasi kucuk resim indirdi"


def test_BESLE_derinligi_uretimin_KAPMA_kapisini_goruyor(hat, monkeypatch):
    """⚠️ `9824db3`in dersi: derinlik sayaci uretimin KAPABILDIGINDEN baska
    bir sey sayarsa kuyruk zombiyle dolar, `eksik <= 0` gorulur ve terfi
    durur. Cagri `besle()`nin kendi cagri sekli — kapiya yalnizca uretimin
    gectigi bir bayrak eklenirse bu test duser."""
    menu = hat.menu(*range(6), *range(4))
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda *_a, **_k: menu)

    assert huni_besle.aday_kapilabilir_mi is ya.aday_kapilabilir_mi
    karar = huni_besle.aday_kapilabilir_mi(
        "X", {}, bicim=ya.SHORTS_BICIMI, sahne_sayisi=huni_besle.SAHNE_KOLU_TAVANI
    )

    assert karar.kapilabilir is False
    assert karar.engel == "arsiv"


def test_KAPMA_kapisi_ham_sayidan_SONRA_olcuyor(hat, monkeypatch):
    """⚠️ Bedava kapi once: ham sayi zaten reddediyorsa kucuk resim inmemeli.
    Sogumanin agdan once durmasiyla ayni gerekce."""
    menu = hat.menu(0, 1, 2)
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda *_a, **_k: menu)

    karar = ya.aday_kapilabilir_mi("X", {}, bicim=ya.SHORTS_BICIMI, sahne_sayisi=8)

    assert karar.kapilabilir is False
    assert hat.sayac["indirme"] == 0, "ham sayi reddederken kucuk resim indi"


# --- Yedek capa yolu --------------------------------------------------------


def test_YEDEK_CAPA_ayrik_yetmeyeni_ATLIYOR(hat, monkeypatch):
    zayif = hat.menu(*range(6), *range(6), *range(4))  # 16 dosya, 6 ayrik
    guclu = hat.menu(*range(16))
    monkeypatch.setattr(
        ya, "arsiv_envanteri", lambda capa, **_k: zayif if capa == "Z" else guclu
    )

    secilen = ya._yedek_capa_sec(
        ["Z", "G"], bicim=ya.SHORTS_BICIMI, envanter_sinir=40, sahne_sayisi=8
    )

    assert secilen == "G"


def test_YEDEK_CAPA_olcum_TAVANI_dolunca_ham_karara_DUSUYOR(hat, monkeypatch):
    """⚠️ Tavan bir BUTCE, kalite esigi degil: 54 capalik havuzu soguk halde
    bastan sona olcmek slotu yakardi. Tavan dolunca kapi KAPANMIYOR."""
    zayif = hat.menu(*range(6), *range(6), *range(4))  # 16 dosya, 6 ayrik
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda *_a, **_k: zayif)
    capalar = [f"C{i}" for i in range(ya.AYRIK_OLCUM_TAVANI + 2)]

    secilen = ya._yedek_capa_sec(
        capalar, bicim=ya.SHORTS_BICIMI, envanter_sinir=40, sahne_sayisi=8
    )

    assert secilen == capalar[ya.AYRIK_OLCUM_TAVANI]


def test_YEDEK_CAPA_hepsi_yetmezse_BOS_donuyor(hat, monkeypatch):
    zayif = hat.menu(*range(6), *range(6), *range(4))  # 16 dosya, 6 ayrik
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda *_a, **_k: zayif)

    secilen = ya._yedek_capa_sec(
        ["A", "B"], bicim=ya.SHORTS_BICIMI, envanter_sinir=40, sahne_sayisi=8
    )

    assert secilen == ""
