"""Agir kusur tek basina yayindan dusurur — skor ne olursa olsun.

⚠️ Olculdu (2026-08-13): Mehmed II 84 aldi ve AYNI incelemede 10 kusur
listelendi. Skor ortalama bir izlenim ve yuksek ortalama tekil bir yalani
gizleyebiliyor; yanlis kisi gostermek ortalamaya karisacak bir eksiklik
degil.

⚠️ DUZELTME (2026-08-14). Bu dosyada eskiden "geriye donuk olculdu:
yayinlanmis 12 videonun hicbirinde agir kusur yok" yaziyordu. O olcum
BOSTU: `frames` alani hakeme bu kapiyla AYNI commit'te eklendi (3f48840),
yani eski kayitlarda alan hic yoktu ve "kusur yok" sonucu liyakatten degil
alanin yoklugundan geliyordu.

Gercek veriyle ilk sinav (Kon-Tiki koşumu) kapinin YANLISI degil
BELIRSIZLIGI cezalandirdigini gosterdi: gorsel 86 ve 88 alan iki video
(kanalin yayinlanmis en iyisi 90) yalnizca bu kapida dustu; 33 agir kusurun
22'si gercek nesnenin muzedeki fotografiydi. Kapi kaldirilmadi, kusurun
TANIMI duzeltildi.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402
from youtube_automation import (  # noqa: E402
    MIN_SUBTITLE_SCORE,
    MIN_VISUAL_SCORE,
    QualityReview,
    agir_kusurlari_ayikla,
    should_publish,
)


# --- Ayiklama -------------------------------------------------------------


def test_yanlis_kisi_agir_kusur():
    kareler = [{"n": 1, "person": "wrong", "period": "correct", "modern": False}]

    assert agir_kusurlari_ayikla(kareler) == ["kare 1: anlatilan kisi degil"]


def test_donem_uyusmazligi_agir_kusur():
    assert agir_kusurlari_ayikla([{"n": 3, "period": "wrong"}]) == [
        "kare 3: donem uyusmuyor"
    ]


def test_SECILEMEYEN_kisi_agir_kusur_DEGIL():
    """⚠️ Asil duzeltme. Hakemin kendi cumlesi: "the small illustrated figures
    CANNOT BE VERIFIED as Thor Heyerdahl". Bu, yanlis kisi gostermek degil;
    goruntuden secilememek. Ikili sorulan surumde hakem bu kareye `false`
    yaziyordu ve 86 puanlik video yayindan dusuyordu."""
    assert agir_kusurlari_ayikla([{"n": 2, "person": "unclear"}]) == []
    assert agir_kusurlari_ayikla([{"n": 2, "period": "unclear"}]) == []
    assert agir_kusurlari_ayikla([{"n": 2, "person": "none"}]) == []


def test_gercek_nesnenin_BUGUNKU_fotografi_agir_kusur_DEGIL():
    """⚠️ Istem bunu zaten acikca serbest birakiyor: "Modern colour
    photographs of a surviving place or object are welcome."

    Olculdu: 33 agir kusurun 22'si "modern goruntu" cikti ve hepsi Kon-Tiki
    salinin muzedeki halifdi — yani anlatilan nesnenin ta kendisi.
    """
    kare = {"n": 1, "modern": True, "authentic_subject": True}

    assert agir_kusurlari_ayikla([kare]) == []


def test_konuyla_ILGISIZ_modern_goruntu_agir_kusur():
    """Kapinin asil isi: modern tibbi cadir fotografi, ulasim haritasi."""
    kare = {"n": 4, "modern": True, "authentic_subject": False}

    assert agir_kusurlari_ayikla([kare]) == ["kare 4: konuyla ilgisiz modern goruntu"]


def test_temiz_kareler_kusur_uretmiyor():
    kareler = [
        {"n": n, "person": "none", "period": "correct", "modern": False}
        for n in range(1, 7)
    ]

    assert agir_kusurlari_ayikla(kareler) == []


def test_eksik_alan_kusur_sayilmiyor():
    """⚠️ Bu testin konusu: belirsizlik cezalandirilmamali.

    Alan hic gelmezse (eski hakem cevabi, kirik JSON, atlanan kare) kusur
    yazilmiyor. Tersi, cevap bicimi degistigi anda HER videoyu yayindan
    dusururdu — sessiz ve tam bir durus.
    """
    assert agir_kusurlari_ayikla([{"n": 1}, {"n": 2}]) == []


def test_frames_alani_yoksa_bos():
    assert agir_kusurlari_ayikla(None) == []
    assert agir_kusurlari_ayikla("bozuk") == []
    assert agir_kusurlari_ayikla([]) == []


def test_bozuk_kare_atlaniyor_digerleri_okunuyor():
    kareler = ["bozuk", {"n": 2, "person": "wrong"}]

    assert agir_kusurlari_ayikla(kareler) == ["kare 2: anlatilan kisi degil"]


# --- Yayin karari ---------------------------------------------------------


def test_agir_kusur_yuksek_skoru_eziyor():
    """⚠️ Asil kural: 84 alan bir video yanlis kisi gosteriyorsa yayinlanmaz."""
    review = QualityReview(
        publishable=True,
        visual_alignment_score=95,
        subtitle_readability_score=100,
        agir_kusurlar=["kare 4: anlatilan kisi degil"],
    )

    assert should_publish(review) is False


def test_agir_kusur_yoksa_skor_karar_veriyor():
    temiz = QualityReview(
        publishable=True,
        visual_alignment_score=MIN_VISUAL_SCORE,
        subtitle_readability_score=MIN_SUBTITLE_SCORE,
    )

    assert should_publish(temiz) is True


def test_dusuk_skor_hala_dusuruyor():
    """Yeni kapi eskisini GEVSETMEMELI."""
    review = QualityReview(
        publishable=True,
        visual_alignment_score=MIN_VISUAL_SCORE - 1,
        subtitle_readability_score=100,
    )

    assert should_publish(review) is False


# --- Hakem istemi ---------------------------------------------------------


def test_istem_kare_basina_OLGU_soruyor_karar_degil():
    """⚠️ DW-87 korunuyor: modele "yayinlanabilir mi" diye sorulmuyor."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def review_video(")
    yonerge = kaynak[i : kaynak.index("_vision_json(prompt", i)]

    assert '"person"' in yonerge
    assert '"period"' in yonerge
    assert "authentic_subject" in yonerge
    # ⚠️ Ucuncu secenek istemde ACIKCA olmali: yoksa hakem emin olamadigi
    # karede "wrong" yazar ve duzeltme hicbir sey degistirmez.
    assert "unclear" in yonerge
    # Esik ve karar sozcukleri hala yasak.
    assert "publishable" not in yonerge
    assert "at least" not in yonerge


def test_hakem_cevabi_agir_kusura_baglaniyor(monkeypatch):
    """Baglanti testi — ayiklayici dogru olsa bile cagrilmazsa kusur surer."""
    monkeypatch.setattr(
        ya,
        "_vision_json",
        lambda prompt, gorsel, **_: {
            "visual_alignment_score": 95,
            "subtitle_readability_score": 100,
            "issues": [],
            "revised_search_terms": [],
            "frames": [{"n": 1, "person": "wrong"}],
        },
    )
    plan = ya.ContentPlan(
        topic="t", visual_anchor="a", script="s", description="d", tags=[], title="b",
        scenes=[{"narration": "n", "search_term": "a x"} for _ in range(6)],
    )

    review = ya.review_video(plan, Path("montaj.jpg"))

    assert review.agir_kusurlar == ["kare 1: anlatilan kisi degil"]
    assert review.publishable is False
    assert should_publish(review) is False


def test_KON_TIKI_kaydi_artik_yayinlanabilir():
    """⚠️ Gerileme kilidi — olculmus gercek vaka (2026-08-14).

    Gorsel 86, altyazi 91. Hakemin kareleri: gercek salin muzedeki
    fotograflari (modern ama konunun kendisi) ve uzaktan secilemeyen
    murettebat. Eski kapi bunu dusuruyordu.
    """
    kareler = [
        {"n": 1, "person": "none", "period": "correct", "modern": True, "authentic_subject": True},
        {"n": 2, "person": "unclear", "period": "correct", "modern": False, "authentic_subject": True},
        {"n": 3, "person": "none", "period": "correct", "modern": True, "authentic_subject": True},
    ]

    agir = agir_kusurlari_ayikla(kareler)

    assert agir == []
    assert should_publish(QualityReview(True, 86, 91, agir_kusurlar=agir)) is True


# ─────────────────────────────────────────────────────────────────────
# `authentic_subject` uc degerli (2026-08-19). Gerekce
# `agir_kusurlari_ayikla` docstring'inde; ozeti: `person` ve `period`
# 25ede57'de uc degerli yapildi, bu alan IKILI kaldi ve ayni commit onu
# agir kusurun ikinci sarti yapti.
# ─────────────────────────────────────────────────────────────────────
def test_MOAI_kaydi_artik_yayinlanabilir():
    """⚠️ Gerileme kilidi — olculmus gercek vaka (2026-08-19 02:41).

    Gorsel 98 (kanalin olculmus en yuksek skoru), altyazi 95. On iki karenin
    ON BIRI tertemiz. Tek isaretli kare 8 ve hakemin AYNI incelemedeki kendi
    duzyazisi sunu diyor:

        "Frame 8: The montage includes a frame highly blurred to the point
         of losing all visual detail."
        "No other issues detected: all scenes use era-appropriate imagery of
         Moai ... and DO NOT INTRODUCE MODERN/UNRELATED CONTENT."

    Yani hakem "konuyla ilgisiz modern goruntu YOK" diye yaziyor, kod ise
    ayni incelemeden tam olarak onu okuyordu. Kare bulanik oldugu icin
    hakem ne oldugunu SECEMEDI (`period: "unclear"`) ve ikili sorulan
    `authentic_subject`e mecburen `false` yazdi.

    ⚠️ Bu testin savundugu sey "bulanik kare zararsizdir" DEGIL. Bulanikligi
    olcen alan hakemde yok; skora giriyor ve skor 98. Bulanikligin kendi
    kapisi gerekiyorsa ayrica olculup kurulur — baska bir kusurun adiyla
    elenmez.
    """
    kareler = [
        {"n": 1, "person": "none", "period": "correct", "authentic_subject": True, "modern": False},
        {"n": 2, "person": "none", "period": "correct", "authentic_subject": True, "modern": False},
        {"n": 3, "person": "none", "period": "correct", "authentic_subject": True, "modern": True},
        {"n": 4, "person": "none", "period": "correct", "authentic_subject": True, "modern": True},
        {"n": 5, "person": "none", "period": "correct", "authentic_subject": True, "modern": False},
        {"n": 6, "person": "none", "period": "correct", "authentic_subject": True, "modern": False},
        {"n": 7, "person": "none", "period": "correct", "authentic_subject": True, "modern": True},
        # Bulanik kare: hakem donemi de ozgunlugu de SECEMEDI.
        {"n": 8, "person": "none", "period": "unclear", "authentic_subject": "unclear", "modern": True},
        {"n": 9, "person": "none", "period": "correct", "authentic_subject": True, "modern": True},
        {"n": 10, "person": "none", "period": "correct", "authentic_subject": True, "modern": True},
        {"n": 11, "person": "none", "period": "correct", "authentic_subject": True, "modern": True},
        {"n": 12, "person": "none", "period": "correct", "authentic_subject": True, "modern": True},
    ]

    agir = agir_kusurlari_ayikla(kareler)

    assert agir == []
    assert should_publish(QualityReview(True, 98, 95, agir_kusurlar=agir)) is True


def test_secilemeyen_ozgunluk_agir_kusur_DEGIL():
    """'unclear' bir sey SOYLEMIYOR, dolayisiyla bir sey kanitlamiyor."""
    kare = {"n": 8, "modern": True, "authentic_subject": "unclear"}

    assert agir_kusurlari_ayikla([kare]) == []


def test_acik_HAYIR_hala_agir_kusur():
    """⚠️ Kapinin gercek isi kaybolmadi: modern tibbi cadir, ulasim haritasi."""
    kare = {"n": 4, "modern": True, "authentic_subject": "no"}

    assert agir_kusurlari_ayikla([kare]) == ["kare 4: konuyla ilgisiz modern goruntu"]


def test_ESKI_bool_kayitlari_hala_ayni_okunuyor():
    """⚠️ Geriye uyum: `rejected[]` ve eski testler bool tasiyor.

    Bir cevirici yazilsaydi bir bicim sessizce kapinin disinda kalabilirdi;
    iki bicim de ayni normallestirmeden geciyor.
    """
    assert agir_kusurlari_ayikla([{"n": 1, "modern": True, "authentic_subject": False}]) == [
        "kare 1: konuyla ilgisiz modern goruntu"
    ]
    assert agir_kusurlari_ayikla([{"n": 1, "modern": True, "authentic_subject": True}]) == []


def test_istem_OZGUNLUK_icin_de_uc_secenek_sunuyor(monkeypatch):
    """⚠️ Kapi modele GOSTERILENI olcmeli — istem ikili sorarsa kodun uc
    degerli okumasi hicbir sey degistirmez, hakem yine 'no' yazar.

    Istem KAYNAK METINDEN degil, hakeme giden gercek cagridan okunuyor
    (`ee886ab` dersi: kaynakta dize aramak yolu yurutmuyor).
    """
    yakalanan = {}

    def sahte(prompt, gorsel, **_):
        yakalanan["istem"] = prompt["instructions"]
        return {
            "visual_alignment_score": 90,
            "subtitle_readability_score": 90,
            "issues": [],
            "revised_search_terms": [],
            "frames": [],
        }

    monkeypatch.setattr(ya, "_vision_json", sahte)
    plan = ya.ContentPlan(
        topic="t", visual_anchor="a", script="s", description="d", tags=[], title="b",
        scenes=[{"narration": "n", "search_term": "a x"} for _ in range(6)],
    )

    ya.review_video(plan, Path("montaj.jpg"))

    istem = yakalanan["istem"]
    i = istem.index('"authentic_subject"')
    alan = istem[i : istem.index('"modern"', i)]
    assert '"yes"' in alan
    assert '"no"' in alan
    assert '"unclear"' in alan
    # DW-87: alan hala OLGU soruyor, karar sormuyor.
    assert "publishable" not in alan
