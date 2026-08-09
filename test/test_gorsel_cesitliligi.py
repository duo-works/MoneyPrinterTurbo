"""Gorsel cesitliligi — arsiv fotograflari korunur, tek estetige sabitlenmez.

Ayri dosya: bu is kendi sozlesmesine sahip. Testler ag'a cikmaz; indirme ve
AI uretimi yamalanir.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402
import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__)


def _plan(sahne_sayisi: int = 8) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Colosseum",
        visual_anchor="Colosseum",
        title="t",
        script="s",
        scenes=[
            {"narration": f"Scene {i}", "search_term": f"Colosseum detail {i}"}
            for i in range(1, sahne_sayisi + 1)
        ],
        description="d",
        tags=[],
    )


# --- Gorsel dil ----------------------------------------------------------


def test_tek_estetige_sabitlenmiyor():
    """Olculdu: "archival-documentary" her sahneyi sepya yapiyordu.

    Ton cesitliligi 0,08'den 0,17'ye cikti (ayni sahne, iki prompt).
    """
    assert "archival-documentary aesthetic" not in KAYNAK.read_text(encoding="utf-8")


def test_gorsel_dil_uc_yolu_da_tarif_ediyor():
    """Uc yol da duruyor; (b)'nin CEVABI degisti (DW-109).

    ⚠️ (b) once "richly coloured historical painting" istiyordu. Kullanicinin
    "sanki cartoon gibi" tarifi tam olarak buydu ve gecmisteki sahneler
    Commons'ta nadiren fotografla karsilandigi icin AI dolgusunun cogu bu
    sikka dusuyordu — cizim, kanalin varsayilan gorunumu olmustu. Ayrim
    (bugun ayakta duran / gecmisteki olay / gercekten arsivlik) korunuyor,
    ama gecmisteki olay artik CANLANDIRMA FOTOGRAFI.
    """
    dil = ya.GORSEL_DIL

    assert "survives today" in dil, "ayakta duran sey gercek fotograf olmali"
    assert "true-to-life colour" in dil
    assert "living-history reconstruction" in dil, "gecmisteki olay canlandirma olmali"
    assert "historical painting" not in dil, "cizim kanalin gorunumu olmustu"
    assert "sepia" in dil, "sepya yalnizca gercekten arsivlik olana"


def test_sahneler_arasi_cesitlilik_isteniyor():
    """Ardisik iki kare birbirine benzememeli — SART DURUYOR, yontem degisti.

    ⚠️ Bu sart once `GORSEL_DIL` icinde tek bir cumleydi ("consecutive images
    do not look like one another") ve HIC ISLEMEDI: sahneler birbirinden
    habersiz, ayri isteklerle uretiliyor, dolayisiyla modelin "onceki kare"
    diye bir bilgisi yok. Olculdu (2026-08-09): cumle promptta dururken 7
    karenin hepsi 25°-47° ton araligina dustu (yayilim 0,007).

    Cesitlilik artik dilekle degil, her sahneye acikca BASKA bir kadraj ve
    BASKA bir isik vererek saglaniyor. Test o yuzden cumleyi degil, iki
    donusumun da prompta bagli oldugunu kilitliyor.
    """
    kaynak = KAYNAK.read_text(encoding="utf-8")
    i = kaynak.index("Create a vertical image for a YouTube Short")
    govde = kaynak[i : kaynak.index("request = {", i)]

    assert "kare_dili(index)" in govde, "kadraj sahne basina degismeli"
    assert "isik_dili(" in govde, "isik sahne basina degismeli"


def test_gorsel_kalitesi_yuksek():
    """Shorts tam ekran izleniyor; `medium` doku ve kenar netligini kaybettiriyor."""
    kaynak = KAYNAK.read_text(encoding="utf-8")
    i = kaynak.index('"size": "1024x1536"')

    assert '"quality": "high"' in kaynak[i : i + 400]


# --- Kismi arsiv ---------------------------------------------------------


def test_tek_eksik_sahne_butun_arsivi_atmiyor(tmp_path, monkeypatch):
    """DW-97'nin kapattigi asil kusur.

    8 sahnenin 7'sinde gercek arsiv fotografi bulunmus olsa bile, 8'inci
    bulunamayinca hepsi cope gidiyor ve butun video AI ile uretiliyordu.
    Olculdu: 96 AI gorselin 76'si tam da bu yoldan geldi.
    """
    dosyalar = [tmp_path / f"s{i}.jpg" for i in range(1, 8)] + [None]
    for d in dosyalar[:-1]:
        d.write_bytes(b"x")

    uretilen_sahneler = []

    def sahte_ai(_plan, hedef, scene_numbers=None, **_k):
        uretilen_sahneler.extend(scene_numbers or [])
        yollar = []
        for n in scene_numbers or []:
            p = tmp_path / f"ai-{n}.png"
            p.write_bytes(b"y")
            yollar.append(p)
        return yollar

    monkeypatch.setattr(ya, "_generate_ai_or_reject", sahte_ai)

    sonuc = ya._delikleri_doldur(_plan(8), dosyalar, tmp_path)

    assert uretilen_sahneler == [8], "yalnizca eksik sahne AI ile uretilmeli"
    assert len(sonuc) == 8
    assert sonuc[0].name == "s1.jpg", "bulunan arsiv gorselleri korunmali"
    assert sonuc[7].name == "ai-8.png"


def test_hicbir_delik_yoksa_ai_hic_cagrilmiyor(tmp_path, monkeypatch):
    dosyalar = [tmp_path / f"s{i}.jpg" for i in range(1, 4)]
    for d in dosyalar:
        d.write_bytes(b"x")

    def patla(*_a, **_k):
        raise AssertionError("delik yokken AI cagrilmamali")

    monkeypatch.setattr(ya, "_generate_ai_or_reject", patla)

    assert ya._delikleri_doldur(_plan(3), dosyalar, tmp_path) == dosyalar


def test_kismi_kip_kapaliysa_eski_davranis_suruyor(tmp_path, monkeypatch):
    """AI yedegi yokken delikli video yapilamaz — sert hata dogru davranis."""
    monkeypatch.setattr(wm, "search_commons", lambda *_a, **_k: [])
    monkeypatch.setattr(wm, "download_met_scene_material", lambda *_a, **_k: None)

    with pytest.raises(wm.MaterialsUnavailableError, match="scene 1"):
        wm.download_scene_materials(
            "Colosseum",
            [{"search_term": "Colosseum arch"}],
            tmp_path,
            kismi=False,
        )


def test_kismi_kipte_hicbiri_bulunamazsa_yine_hata(tmp_path, monkeypatch):
    """Bos bir arsiv sonucu, "kismi" degil tam basarisizliktir."""
    monkeypatch.setattr(wm, "search_commons", lambda *_a, **_k: [])
    monkeypatch.setattr(wm, "download_met_scene_material", lambda *_a, **_k: None)

    with pytest.raises(wm.MaterialsUnavailableError, match="any of the"):
        wm.download_scene_materials(
            "Colosseum",
            [{"search_term": f"Colosseum {i}"} for i in range(3)],
            tmp_path,
            kismi=True,
        )


def test_kismi_kip_hatta_baglanmis():
    """Baglanti testi — `_delikleri_doldur` tek basina dogru olsa bile
    `run_generator` onu cagirmazsa kusur geri gelir.

    Mutasyonla bulundu: `kismi=AI_VISUAL_FALLBACK_ENABLED` yerine
    `kismi=False` yazildiginda izole testlerin hicbiri dusmuyordu.
    """
    kaynak = KAYNAK.read_text(encoding="utf-8")
    i = kaynak.index("def run_generator(")
    govde = kaynak[i : i + 2500]

    assert "kismi=AI_VISUAL_FALLBACK_ENABLED" in govde, "kismi kip hatta bagli olmali"
    assert "_delikleri_doldur(" in govde, "delikler doldurulmali"


# --- Arsiv kalite barasi (DW-98) -----------------------------------------


@pytest.mark.parametrize(
    "baslik",
    [
        "File:Letter of 1869 January 17 - DPLA - ba98c73e.jpg",
        "File:Manuscript folio 23 recto.jpg",
        "File:Title page of Historia Naturalis.jpg",
        "File:Diary of a traveller 1890.jpg",
        "File:Map of ancient Alexandria.jpg",
    ],
)
def test_belge_taramalari_eleniyor(baslik):
    """Olculdu: arsiv 5 sahne besledi, ikisi belge cikti.

    1869 tarihli el yazisi bir mektup sahne 4'u doldurdu — ekrani tam
    kapliyor ama izleyici okunamayan bir el yazisi goruyor. Kalite kapisi da
    yakalayamadi (85 verdi) cunku "gorsel anlatimla uyumlu mu" diye soruyor,
    "bu bir belge mi" diye degil.
    """
    assert wm.belge_taramasi(baslik)


@pytest.mark.parametrize(
    "baslik",
    [
        "File:Pottery found at the Pueblo Hungo Pavie, Pl. 32.jpg",
        "File:Plate 14 - Skull specimens.jpg",
        "File:Fig. 7 cross-section of the aqueduct.jpg",
        "File:Diagram of Inca terracing.png",
        "File:Table of Roman emperors.jpg",
        "File:Inscription from the temple wall.jpg",
    ],
)
def test_bilimsel_yayin_plakalari_da_eleniyor(baslik):
    """Olculdu (2026-08-07): "Pottery found at the Pueblo Hungo Pavie" bir
    KITAP SAYFASIYDI — ustunde "Senate Ex. doc." ve "Pl. 32" yazili, beyaz
    zeminde cizim panelleri.

    Baslikta belge kelimesi gecmedigi icin ilk filtre kacirdi. Bunlar
    arkeolojik olarak degerli ama dikey videoda izleyiciye hicbir sey
    anlatmiyor.
    """
    assert wm.belge_taramasi(baslik)


@pytest.mark.parametrize(
    "baslik",
    [
        # Chaco videosunun 1., 5. ve 7. sahneleri — ucu de kitap sayfasiydi.
        (
            "File:Hieroglyphics on north wall of the Canon of Chaco - Near ruins of the "
            "Pueblo Chetho Kette. R. H. Kern delt. P.S. Duval's (IA dr hieroglyphics-on-"
            "north-wall-0380039).jpg"
        ),
        (
            "File:Pottery found at the Publo Hungo Pavie. R. H. delt. P.S. Duval's Lith. "
            "Steam Press. Philada. (to accompany) Reports of the secretary (IA dr "
            "pottery-0380036).jpg"
        ),
        (
            "File:Masonry of the Chaco and other ruins. R. H. Kern delt. P.S. Duval's "
            "Lith. Steam Press. Philada. (to accompany) Reports of the (IA dr "
            "masonry-0380044).jpg"
        ),
    ],
)
def test_kitap_taramasi_kisaltmalari_da_eleniyor(baslik):
    """⚠️ Olculdu (2026-08-08): bu uc gorsel YAYINLANACAK bir videoya girdi.

    DW-98 "lithograph" kelimesini eliyordu ama bu basliklarda kelime degil
    KISALTMA var: "delt.", "Lith. Steam Press.". Kalite kapisi da yakalamadi
    (video 70/80 aldi) cunku "gorsel anlatimla uyumlu mu" diye soruyor.

    "(IA " Commons'ta Internet Archive kitap tarama kimligi. Gecmise karsi
    olculdu: 45 arsiv gorselinin 3'unde geciyor, ucu de bu sayfalar.
    """
    assert wm.belge_taramasi(baslik)


@pytest.mark.parametrize(
    "baslik",
    [
        "File:Colosseum in Rome, Italy - April 2007.jpg",
        "File:Karnak Temple hypostyle hall columns.jpg",
        "File:Philip Galle - Lighthouse of Alexandria.jpg",
        # ⚠️ Filtre fazla agresif olmamali: bunlar gercek gorsel.
        "File:Machu Picchu, Peru (2018).jpg",
        "File:Chaco Canyon Pueblo Bonito aerial.jpg",
        "File:The Lighthouse of Alexandria by Magdalena van de Passe.jpg",
        "File:Terracotta Army pit 1 soldiers.jpg",
        "File:Lascar Llamas at Machu Picchu.jpg",
    ],
)
def test_gercek_gorseller_elenmiyor(baslik):
    assert not wm.belge_taramasi(baslik)


def test_cok_genis_gorsel_eleniyor():
    """1,20-1,30 oranindaki gravurler ekranin yalnizca %43-47'sini dolduruyor."""
    assert not wm.dikey_karede_yeterli(1280, 984)  # oran 1,30 → %43
    assert not wm.dikey_karede_yeterli(1280, 1062)  # oran 1,21 → %47


def test_dikey_ve_kare_gorseller_geciyor():
    assert wm.dikey_karede_yeterli(1280, 1606)  # dikey
    assert wm.dikey_karede_yeterli(1024, 1536)  # 2:3
    assert wm.dikey_karede_yeterli(1000, 1000)  # kare


def test_hafif_yatay_gorsel_geciyor():
    """Kirp-doldur esigi icindeki gorsel tam ekran veriyor, elenmemeli."""
    assert wm.dikey_karede_yeterli(1200, 1300)


def test_gecersiz_olcu_eleniyor():
    assert not wm.dikey_karede_yeterli(0, 100)
    assert not wm.dikey_karede_yeterli(100, 0)


def test_filtreler_secime_bagli():
    """Fonksiyonlar dogru olsa bile aday secimi onlari cagirmazsa kusur surer.

    Mutasyon dersi (DW-97): izole dogruluk yetmiyor, baglanti da kilitlenmeli.
    """
    kaynak = Path(wm.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def select_candidate(")
    govde = kaynak[i : i + 3000]

    assert "belge_taramasi(title)" in govde
    assert "dikey_karede_yeterli(width, height)" in govde
