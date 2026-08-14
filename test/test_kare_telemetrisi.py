"""Hakemin KARE BASINA cevaplari kayda giriyor — olcum korlugu kapaniyor.

⚠️ NEDEN — olculdu (2026-08-14). Hakeme her kare icin uc somut soru
soruluyor ("iceride okunabilir yazi var mi", "anlatilan kisi mi", "donem
uyuyor mu") ve model bunlari cevapliyor. Ama cevap yalnizca
`agir_kusurlari_ayikla`dan geciyordu; gerisi ATILIYORDU.

Sonuc: 183 koşum kaydinin **0'inda** kare verisi yok.

Kanal sahibinin sesli notundaki uc madde tam da bu veriyle olculebilirdi:

  * "cok fazla harita, ustune yazi olan fotograf"
  * "bazi fotograflar sacma, hicbir sey ifade etmiyor"
  * "cok fazla benzer gorsel"

Mevcut 11 kalite kaydinda hakem bunlari ZATEN bildiriyor (yazi %91,
tekrar %73) ama serbest metin olarak; kod yalnizca sayisal skora ve agir
kusur alanlarina bakiyor, o alanlarda ise yazi/harita/benzerlik YOK.

⚠️ TELEMETRI, KAPI DEGIL. Once kaydet, kapiyi veri birikince kur. Ters
sirasi bu oturumda bir kez yapildi ve pahaliya mal oldu: agir kusur
kapisinin gerekcesi "geriye donuk olculdu" diyordu, oysa olculen alan
ayni commit'te eklenmisti ve eski kayitlarda hic yoktu.
"""

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")


def test_kareler_alani_var():
    assert ya.QualityReview(True, 90, 90).kareler == []


def test_hakem_cevabindaki_kareler_TASINIYOR(monkeypatch):
    kareler = [
        {"n": 1, "lettering": "none", "person": "ok", "period": "ok"},
        {"n": 2, "lettering": "DERINKUYU UNDERGROUND CITY", "person": "n/a", "period": "ok"},
    ]
    monkeypatch.setattr(
        ya,
        "_vision_json",
        lambda *_a, **_k: {
            "visual_alignment_score": 88,
            "subtitle_readability_score": 90,
            "issues": [],
            "revised_search_terms": [],
            "frames": kareler,
        },
    )
    plan = ya.ContentPlan("konu", "capa", "baslik", "metin", [], "aciklama", ["a", "b", "c"])

    review = ya.review_video(plan, Path("montaj.jpg"))

    assert review.kareler == kareler
    # ⚠️ Yazi bildirimi kapi DEGIL: skor 88 ve yayin engellenmiyor.
    # Veri birikmeden kapi kurmak, olculmemis bir esikle yayini durdurmak
    # olurdu. Kayit var, karar sonra.
    assert review.agir_kusurlar == []


def test_bozuk_kare_verisi_patlatmiyor(monkeypatch):
    """Eski hakem cevabi, kirik JSON ya da hic gelmeyen alan."""
    for gelen in (None, "metin", [1, 2], []):
        monkeypatch.setattr(
            ya,
            "_vision_json",
            lambda *_a, _g=gelen, **_k: {
                "visual_alignment_score": 90,
                "subtitle_readability_score": 90,
                "frames": _g,
            },
        )
        plan = ya.ContentPlan("konu", "capa", "baslik", "metin", [], "aciklama", ["a"])

        assert ya.review_video(plan, Path("m.jpg")).kareler == []


def test_istem_YAZI_ve_TUR_alanlarini_istiyor():
    """⚠️ Sesli notun iki maddesi bu iki alanla olculebilir hale geliyor.

    "cok fazla harita" ve "ustune yazi olan fotograf" — hakem yazi
    sorusunu ZATEN cevapliyordu ama duzyazi `issues` alaninda; kod onu
    guvenilir okuyamiyor, dolayisiyla olcemiyordu.

    Olculdu (2026-08-14, Tunguska koşumu): 18 karenin 3'u harita, 1'i
    kitap kapagi, 2'si pul, birkaci muze etiketi. Video reddedildi ama
    SKOR uzerinden; hangi karenin neden kotu oldugu sayiyla bilinmiyordu.

    ⚠️ TELEMETRI, KAPI DEGIL. Esik veri birikince konacak.
    """
    # ⚠️ SABIT KARAKTER PENCERESI KULLANILMIYOR. Bu oturumda ayni tuzak
    # uc kez isirdi: metin buyuyunce pencere aranan satiri disarida
    # birakiyor ve test kodun degistigini degil penceresinin kaydigini
    # soyluyor. Sinir bir SONRAKI tanimin kendisi.
    i = KAYNAK.index("def review_video(")
    govde = KAYNAK[i : KAYNAK.index("\ndef ", i + 1)]

    assert '"lettering"' in govde
    assert '"kind"' in govde
    assert '"map"' in govde
    # Esik ANILMIYOR (DW-87): hakem olcer, kod karar verir. Yalnizca
    # ISTEM metni sinaniyor — asagisi kodun kendisi ve orada
    # `publishable=` gecmesi dogru.
    istem = govde[: govde.index("data = _vision_json")]
    assert "publishable" not in istem


def test_yazi_ve_tur_KAPI_DEGIL(monkeypatch):
    """Yazili harita bildiren kare tek basina yayini engellemiyor."""
    monkeypatch.setattr(
        ya,
        "_vision_json",
        lambda *_a, **_k: {
            "visual_alignment_score": 92,
            "subtitle_readability_score": 95,
            "frames": [{"n": 1, "lettering": True, "kind": "map"}],
        },
    )
    plan = ya.ContentPlan("konu", "capa", "baslik", "metin", [], "aciklama", ["a"])

    review = ya.review_video(plan, Path("m.jpg"))

    assert review.agir_kusurlar == [], "veri birikmeden kapi kurulmamali"
    assert review.publishable, "yuksek skorlu video yazi yuzunden dusmemeli"
    assert review.kareler[0]["kind"] == "map"


def test_kareler_KAYDA_yaziliyor():
    """⚠️ `asdict(review)` ile gidiyor; alan eklenmezse kayit yine bos kalirdi."""
    review = ya.QualityReview(True, 90, 90, kareler=[{"n": 1, "lettering": "none"}])

    assert asdict(review)["kareler"] == [{"n": 1, "lettering": "none"}]
    assert '"quality": asdict(review)' in KAYNAK
