"""Harita/belge/diyagram kareleri RENDER ONCESI degistiriliyor.

⚠️ NEDEN — kanal sahibinin sesli notu (2026-08-14): "cok fazla harita
kullaniyor, cok fazla ustune yazi olan fotograf kullaniyor... bazilari
cok sacma, hicbir sey ifade etmiyor."

OLCULDU — menu bilesimi (dosya adi + aciklama):

    Tunguska event   18 girdi, %50 fotograf DEGIL (3 harita, 2 pul/kapak,
                     2 diyagram)
    Persepolis       17 girdi, %29 harita
    Great Sphinx     20 girdi, %25 kitap kapagi
    Abu Simbel       14 girdi, %0

Uretilen Tunguska videosunda 18 karenin 3'u harita, 2'si pul, biri kitap
kapagi cikti.

⚠️ NEDEN DOSYA ADI FILTRESI DEGIL: ayni olcum Lycurgus Cup'ta %92 "kirli"
dedi ve YANILDI — "museum" kelimesi gecen kareler gercek nesnenin muze
fotograflariydi. Dosya adi iki yonde de yaniltiyor. Goruntuyu GOREN
hakem dogru alet; regex degil.

⚠️ KARAR KODDA, HAKEMDE DEGIL (DW-87). Hakeme "bu kare ne" diye olgu
soruluyor; "harita kabul edilebilir mi" ona birakilsa konudan konuya
keyfi cevap verirdi.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(konu="Roman aqueducts", capa="Pont du Gard", baslik="baslik #Shorts"):
    return ya.ContentPlan(
        topic=konu,
        visual_anchor=capa,
        title=baslik,
        script="metin",
        scenes=[{"narration": f"sahne {i}", "search_term": f"terim {i}"} for i in range(1, 5)],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def _kareler(*turler: str):
    return [{"n": i, "kind": t} for i, t in enumerate(turler, 1)]


# --- Tur kurali -----------------------------------------------------------


def test_harita_belge_diyagram_sorunlu():
    kareler = _kareler("photo", "map", "document", "diagram")

    assert ya.belge_kareleri(kareler, _plan(), 4) == [2, 3, 4]


def test_fotograf_ve_ARTWORK_sorunsuz():
    """⚠️ Gravur ve tablo bu kanalin gorsel dilinin merkezinde.

    Fotografin var olmadigi donemlerde tek gercek arsiv kaynagi onlar;
    elemek konu havuzunun yarisini kapatirdi.
    """
    assert ya.belge_kareleri(_kareler("photo", "artwork"), _plan(), 2) == []


def test_KONUSU_HARITA_olan_video_korunuyor():
    """⚠️ Bu istisna olmadan kural kanalin KENDI videosunu oldururdu.

    "Piri Reis Map: Did It Show Antarctica?" (2026-08-14, wzXuZKVGuro)
    bastan sona bir haritayi anlatiyor; karelerinin harita olmasi DOGRU.
    """
    plan = _plan(
        konu="The Piri Reis map and its Antarctic claim",
        capa="Piri Reis Map",
        baslik="Piri Reis Map: Did It Show Antarctica? #Shorts",
    )

    assert ya.belge_kareleri(_kareler("map", "map", "map"), plan, 3) == []


def test_belge_konulari_da_korunuyor():
    for konu, capa in (
        ("The Rosetta Stone decipherment", "Rosetta Stone"),
        ("The Voynich manuscript", "Voynich Manuscript"),
    ):
        plan = _plan(konu=konu, capa=capa, baslik=f"{capa}: what is it? #Shorts")
        # "manuscript" ve "stone"... yalnizca belge kelimesi gecen korunur.
        if ya.KONU_TURU_ISTISNASI.search(f"{konu} {capa}"):
            assert ya.belge_kareleri(_kareler("document"), plan, 1) == []


def test_bozuk_kare_verisi_patlatmiyor():
    kareler = [{"n": "x", "kind": "map"}, {"kind": "map"}, {"n": 99, "kind": "map"}, "metin"]

    assert ya.belge_kareleri(kareler, _plan(), 4) == []


def test_bos_kare_listesi():
    assert ya.belge_kareleri([], _plan(), 4) == []


# --- Kapiya baglanti ------------------------------------------------------


def _inceleme(monkeypatch, veri):
    monkeypatch.setattr(ya, "_vision_json", lambda *_a, **_k: veri)
    return ya.review_source_materials(_plan(), Path("montaj.jpg"))


def test_harita_karesi_SORUNLU_SAHNEYE_ekleniyor(monkeypatch):
    """⚠️ Asil kosul: mevcut degistirme makinesi bu listeden besleniyor.

    Eklenmezse hakem haritayi "konuyla ilgili" sayip gecirir ve harita
    videoya girer — olculen davranis buydu.
    """
    review = _inceleme(
        monkeypatch,
        {
            "visual_alignment_score": 85,
            "issues": [],
            "revised_search_terms": [],
            "problem_scene_numbers": [],
            "frames": _kareler("photo", "map", "photo", "document"),
        },
    )

    assert review.problem_scene_numbers == [2, 4]
    assert review.kareler, "kare verisi kayda da gitmeli"


def test_hakemin_isaretledikleri_KORUNUYOR(monkeypatch):
    review = _inceleme(
        monkeypatch,
        {
            "visual_alignment_score": 60,
            "issues": ["sahne 1 alakasiz"],
            "revised_search_terms": ["yeni terim"],
            "problem_scene_numbers": [1],
            "frames": _kareler("photo", "map"),
        },
    )

    assert review.problem_scene_numbers == [1, 2], "hakemin sirasi basta kalmali"


def test_ayni_sahne_iki_kez_eklenmiyor(monkeypatch):
    review = _inceleme(
        monkeypatch,
        {
            "visual_alignment_score": 70,
            "issues": [],
            "revised_search_terms": [],
            "problem_scene_numbers": [2],
            "frames": _kareler("photo", "map"),
        },
    )

    assert review.problem_scene_numbers == [2]


def test_kare_verisi_yoksa_eski_davranis(monkeypatch):
    review = _inceleme(
        monkeypatch,
        {
            "visual_alignment_score": 90,
            "issues": [],
            "revised_search_terms": [],
            "problem_scene_numbers": [],
        },
    )

    assert review.problem_scene_numbers == []
    assert review.kareler == []


def test_istem_TUR_soruyor_KARAR_sormuyor():
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def review_source_materials(")
    govde = kaynak[i : kaynak.index("\ndef ", i + 1)]
    istem = govde[: govde.index("data = _vision_json")]

    assert '"kind"' in istem
    assert '"document"' in istem
    # Esik ve karar ANILMIYOR: hakem olcer, kod karar verir.
    assert "acceptable to use a map" not in istem
    assert "MIN_SOURCE_VISUAL_SCORE" not in istem


# --- SLAYT / INFOGRAFIK (2026-08-18) ----------------------------------------
#
# ⚠️ NEDEN VAR — olculdu (Gobekli Tepe, YAYINLANMIS video, gorsel 78).
# Kapanistaki iki yuva (~7,6 sn, videonun %15'i) `Göbekli Tepe Birthing Woman
# in Leopard Pillar Building.jpg` idi: UC panelli, Ingilizce baslikli, muze
# kunyeli MODERN bir aciklama slaydi; panellerden biri yorum cizimi. Shorts
# boyutunda gomulu yazi okunmuyor ve altyaziyla cakisiyor.
#
# ⚠️ Mekanizma VARDI VE CALISMADI. Kaynak kapisi zaten kare basina `kind`
# soruyor ve Shorts'ta orneklem yok, yani kapi bu kareyi GORDU ve "photo" dedi
# — cunku slayt fotograf ICERIYOR. Eksik olan kapi degil TAKSONOMIYDI: modelin
# "bu bir sayfa duzeni" diyebilecegi bir secenek yoktu.
#
# ⚠️ `ikincil_gorselleri_denetle` ayni kusuru ZATEN yakaliyordu (Gobekli
# koşumunda `scene-06b` bir PowerPoint slaydiydi ve dusuruldu). Iki kapi artik
# ayni dili konusuyor.


def test_SLAYT_sorunlu():
    assert ya.belge_kareleri(_kareler("photo", "composite"), _plan(), 2) == [2]


def test_slayt_FOTOGRAF_OLMAYANLAR_listesinde():
    assert "composite" in ya.FOTOGRAF_OLMAYAN_TURLER


def test_ARTWORK_hala_gecerli():
    """⚠️ Sinir bekcisi: slayt eklenirken gravur/tablo yanlislikla elenmemeli —
    onlar kanalin gorsel dilinin merkezinde."""
    assert ya.belge_kareleri(_kareler("artwork", "photo"), _plan(), 2) == []


def test_IKI_KAPI_ayni_tur_listesini_kullaniyor():
    """⚠️ Tur listesi kaynak kapisi ile render SONRASI hakemde AYNI olmali.
    Ayrisirsa iki kapi ayni goruntuye baska ad verir ve teshis imkansizlasir."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    for baslangic in ("def review_source_materials(", "def review_video("):
        assert baslangic in kaynak, f"{baslangic} YOK"
        i = kaynak.index(baslangic)
        govde = kaynak[i : kaynak.index("data = _vision_json", i)]
        assert '"composite"' in govde, f"{baslangic} slayt turunu sormuyor"


def test_istem_slaytin_NE_OLDUGUNU_tarif_ediyor():
    """Tek kelime yetmez: model `composite`i kendi basina dogru yorumlamaz.
    Tarif, slaytin fotograf ICERDIGINI acikca soylemeli — kafa karisikligi tam
    oradaydi ("photo" denmesinin sebebi buydu)."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def review_source_materials(")
    istem = kaynak[i : kaynak.index("data = _vision_json", i)]

    # ⚠️ Aranan parcalar KAYNAKTA BITISIK olmali: istem metni birden cok
    # dize sabitine bolunmus, yani calisma zamaninda birlesen bir cumle
    # kaynakta bitisik gorunmuyor. Ilk surumum tam bu yuzden kirmizi verdi.
    assert "SEVERAL pictures" in istem
    assert "is a composite even when the pictures" in istem
