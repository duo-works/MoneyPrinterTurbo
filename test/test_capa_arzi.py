"""Modelin sectigi CAPA'nin arsivi videoyu tasiyabiliyor mu (DW-51 / #37).

⚠️ OLCULDU (2026-08-17, slot 14, canli). Huni kipinde terfi kapisi KUYRUK
BASLIGINI olcuyor, uretim ise modelin sectigi CAPA'yi kullaniyor:

    kuyruk basligi          menu | modelin capasi    menu
    King Philip's War         16 | Metacom              1
    Köktürk                   18 | Göktürks           10
    Operation Storm           15 | Operation Storm    15   <- uyumlu
    Cemal Bajá                13 | Djemal Pasha       29   <- uyumlu

King Philip's War terfi kapisini 16 ile gecti ve reddedildi: model olayi
birakip KISIYI capa secti, o kisinin arsivi 1 dosya. Sahne 9-12 modern
fotograflarla doldu, hakem 8 agir kusur yazdi.

⚠️ Kapi TERFIYE eklenemez — capayi model seciyor, terfi aninda o menu
heNUZ YOKTUR. Dogru yer plan kurulduktan sonra: capa artik bilinir ve
dongu geri bildirimle yeniden deneyebilir.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(capa: str, sahne: int = 6) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor=capa,
        title="baslik",
        script="metin",
        scenes=[{"narration": "x", "search_term": "y"} for _ in range(sahne)],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def _menu(monkeypatch, adet: int):
    monkeypatch.setattr(
        ya,
        "arsiv_envanteri",
        lambda konu, **_k: [
            {"dosya": f"{konu}-{i}.jpg", "gosterdigi": "x", "tarih": ""}
            for i in range(adet)
        ],
    )


def test_ZAYIF_capa_kusur_bildiriyor(monkeypatch):
    """Canli hal: `Metacom` 1 dosya, 6 sahne icin 12 kare gerek."""
    _menu(monkeypatch, 1)

    kusur = ya._capa_arzi_kusuru(_plan("Metacom"), bicim=ya.SHORTS_BICIMI)

    assert kusur, "1 dosyalik capa gecmemeli"
    assert "Metacom" in kusur
    assert "12" in kusur, "gereken kare sayisi mesajda olmali"


def test_SINIRDAKI_capa_geciyor(monkeypatch):
    """Tam 12 = 6 sahne x 2 yuva — kapi kapali degil, sinirda ACIK."""
    _menu(monkeypatch, 12)

    assert ya._capa_arzi_kusuru(_plan("Tikal"), bicim=ya.SHORTS_BICIMI) == ""


def test_sinirin_ALTI_dusuyor(monkeypatch):
    """11 dosya — slot 14'te `Metacomet` kategorisinin gercek buyuklugu."""
    _menu(monkeypatch, 11)

    assert ya._capa_arzi_kusuru(_plan("Metacomet"), bicim=ya.SHORTS_BICIMI) != ""


def test_MENU_CEKILEMEZSE_kusur_YOK(monkeypatch):
    """⚠️ Menu bir IYILESTIRME, on kosul degil.

    `arsiv_envanteri` ag hatasinda `[]` donduruyor. Bos menuyu kusur saymak,
    tek bir 429'un butun koşumu reddettirmesi demek olurdu.
    """
    _menu(monkeypatch, 0)

    assert ya._capa_arzi_kusuru(_plan("Herhangi"), bicim=ya.SHORTS_BICIMI) == ""


def test_sahne_sayisi_VERILIRSE_ona_bakiyor(monkeypatch):
    """Sahne sayisi kod tarafindan sabitlenebiliyor; olcut ona uymali."""
    _menu(monkeypatch, 8)

    # 4 sahne x 2 = 8 -> yeter
    assert ya._capa_arzi_kusuru(
        _plan("X", sahne=6), bicim=ya.SHORTS_BICIMI, sahne_sayisi=4
    ) == ""
    # 6 sahne x 2 = 12 -> yetmez
    assert ya._capa_arzi_kusuru(
        _plan("X", sahne=6), bicim=ya.SHORTS_BICIMI, sahne_sayisi=6
    ) != ""


def test_olcut_ikinci_gorsel_istenebilir_ILE_AYNI(monkeypatch):
    """⚠️ Iki ayri sayi tutmak, istemin istedigi ile kapinin kabul ettigini
    ayirirdi. Kapi o fonksiyonun KENDISINI cagirmali."""
    cagrildi: list[tuple] = []
    gercek = ya.ikinci_gorsel_istenebilir

    def izle(menu, sahne_sayisi):
        cagrildi.append((len(menu), sahne_sayisi))
        return gercek(menu, sahne_sayisi)

    monkeypatch.setattr(ya, "ikinci_gorsel_istenebilir", izle)
    _menu(monkeypatch, 20)

    ya._capa_arzi_kusuru(_plan("Tikal"), bicim=ya.SHORTS_BICIMI)

    assert cagrildi == [(20, 6)]


def test_kapi_PLAN_dongusunde_calisiyor(monkeypatch):
    """Kusur bildirmek yetmez; `generate_content_plan` onu KULLANMALI.

    Zayif capali ilk plan reddedilip ikinci deneme istenmeli — ve reddin
    gerekcesi isteme yazilmali ki model ayni capayi tekrar secmesin.
    """
    kaynak = Path(ya.__file__).read_text()
    assert "_capa_arzi_kusuru(plan" in kaynak, "kapi donguye baglanmamis"


def test_UZUN_bicimde_tek_yuva(monkeypatch):
    """⚠️ Uzun bicimde `bicim.kare_yuvasi` 1 ama olcut global KARE_YUVASI (2).

    Bu test o farki DONDURUYOR: kapi `ikinci_gorsel_istenebilir`i cagirdigi
    icin uzun bicimde de 2 yuva sayiyor. Davranis bilincli — olcutu tek
    yerde tutmak, bicime gore ikinci bir hesap yazmaktan onemli. Degisirse
    burasi kirilir ve karar yeniden verilir.
    """
    _menu(monkeypatch, 12)

    # 6 sahne: 6*2=12 -> tam yeter (kare_yuvasi=1 olsaydi 6 yeterdi)
    assert ya._capa_arzi_kusuru(
        _plan("X", sahne=6), bicim=ya.UZUN_BICIMI, sahne_sayisi=6
    ) == ""
    assert ya._capa_arzi_kusuru(
        _plan("X", sahne=7), bicim=ya.UZUN_BICIMI, sahne_sayisi=7
    ) != ""
