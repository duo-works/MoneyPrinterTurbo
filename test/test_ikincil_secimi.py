"""Ikincil gorsel KOR secilmiyor — sahnenin arama terimi puanlayiciya gidiyor.

⚠️ OLCULDU (2026-08-17). Ikincil gorsel yolu `_kategori_adaylari`yi SORGUSUZ
cagiriyordu. Sorgu bos olunca `_puanli_adaylar` alaka terimi bulamiyor ve
yalnizca en-boy oranina/boyuta bakiyor — yani "kategorinin en iyi
kadrajlanmis dosyasi" donuyor, sahneyle ilgisi hic sorulmuyor. Videoya bu
yoldan girenler:

    scene-04b  deveye binmis modern turist ("Aurelian ... altin zincirlerle
               Roma'da gezdirdi" cumlesinin altinda)
    scene-05b  askeri hava ussunde bayrakli cocuklar, 20. yy
    scene-06b  bir PowerPoint slaydi (Gobekli koşumu)

⚠️ Kodun kendi varsayimi yanlislandi: "Kategori havuzundan esleme guvenli,
uyeligi Commons'in kuratoryasi belirliyor, yani OZNE garantili." Bu yalnizca
YER icin dogru — Commons'in Palmyra kategorisi Palmyra'nin modern turist
fotograflarini da icerir.

⚠️ YENI SUZGEC YAZILMADI. `_puanli_adaylar` sorgu terimlerinin
baslikta/aciklamada gecmesini zaten zorunlu kiliyordu; eksik olan sinyalin
BAGLANMASIYDI.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402


def _sayfa(baslik: str, aciklama: str = "") -> dict:
    # ⚠️ Lisans "Public domain": CC BY-SA bu kanalda REDDEDILIYOR ve fikstur
    # onunla yazilirsa her aday daha suzgece varmadan elenir.
    return {
        "title": f"File:{baslik}",
        "imageinfo": [
            {
                "mime": "image/jpeg",
                "url": f"https://upload.example/{baslik}",
                "descriptionurl": f"https://commons.example/File:{baslik}",
                "width": 2000,
                "height": 1200,
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "ImageDescription": {"value": aciklama},
                    "Artist": {"value": "A"},
                },
            }
        ],
    }


# --- Kalibin kendisi ------------------------------------------------------


def test_SORGUSUZ_cagri_alakasizi_da_donduruyor():
    """Kusurun kendisi — kor siralamanin ne yaptigini sabitler."""
    havuz = [
        _sayfa("Palmyra camel tourist.jpg", "A man rides a camel at Palmyra"),
        _sayfa("Palmyra colonnade.jpg", "The colonnaded street of Palmyra"),
    ]

    adaylar = wm._kategori_adaylari(havuz, set())

    assert len(adaylar) == 2, "sorgu yokken hicbir sey elenmiyor"


def test_SORGU_verilince_alakasiz_ELENIYOR():
    havuz = [
        _sayfa("Palmyra camel tourist.jpg", "A man rides a camel"),
        _sayfa("Palmyra colonnade.jpg", "The colonnaded street of Palmyra"),
    ]

    adaylar = wm._kategori_adaylari(havuz, set(), query="Palmyra colonnade street")
    basliklar = [a["title"] for a in adaylar]

    assert basliklar == ["File:Palmyra colonnade.jpg"]


def test_hedef_oran_KONUMSAL_kalmali():
    """⚠️ `kategori_menusu` bu parametreyi konumsal veriyor; araya konumsal
    bir parametre eklemek onu sessizce bozardi."""
    havuz = [_sayfa("A.jpg", "bir sey")]

    assert wm._kategori_adaylari(havuz, set(), 0.5) == wm._kategori_adaylari(
        havuz, set(), 0.5, query=""
    )


# --- Baglanti: ikincil yolu sorguyu GERCEKTEN veriyor mu ------------------


def test_ikincil_yolu_sahnenin_TERIMINI_geciriyor(monkeypatch, tmp_path):
    """⚠️ Baglanti testi. Fonksiyon dogru olsa bile cagri sorgusuz kalirsa
    kusur aynen surer — kusur zaten tam olarak buydu."""
    gecen: dict = {}

    def sahte_adaylar(havuz, kullanilan, hedef_oran=wm.SHORTS_ORANI, *, query=""):
        gecen["query"] = query
        return []

    monkeypatch.setattr(wm, "_kategori_adaylari", sahte_adaylar)
    monkeypatch.setattr(wm, "_alinti_adayi", lambda *_a, **_k: None)

    wm.ikincil_gorseller(
        [{"search_term": "Palmyra colonnade street", "kaynak_dosya_2": ""}],
        tmp_path,
        [_sayfa("A.jpg", "x")],
        esleme_gerekli=[True],
    )

    assert gecen["query"] == "Palmyra colonnade street"


def test_aday_cikmazsa_sahne_IKINCILSIZ_kaliyor(monkeypatch, tmp_path):
    """⚠️ Dogru sonuc: `kare_yerlesimi` o sahneyi [A, A] yapar, yani bugunku
    davranis. Yanlis gorsel koymaktansa gorsel koymamak."""
    monkeypatch.setattr(wm, "_alinti_adayi", lambda *_a, **_k: None)
    monkeypatch.setattr(wm, "_kategori_adaylari", lambda *_a, **_k: [])

    dosyalar, krediler = wm.ikincil_gorseller(
        [{"search_term": "hicbir seye uymayan terim", "kaynak_dosya_2": ""}],
        tmp_path,
        [_sayfa("A.jpg", "x")],
        esleme_gerekli=[True],
    )

    assert dosyalar == [None]
    assert krediler == [], "indirilmeyen gorsele atif yapilmamali"
