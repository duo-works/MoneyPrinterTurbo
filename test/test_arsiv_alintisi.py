"""Her sahne arsiv menusunden GERCEK bir dosya alintilamali.

⚠️ Bu kapi, `arsiv_destegi_kusuru`nun yerini aldi (2026-08-14). Eski kapi
sahne teriminin kelimeleriyle dosya adlarinin kelimelerini kesistiriyordu ve
pratikte hicbir seyi engellemiyordu: "1974 Terracotta Army discovery farmers
digging well Xi'an" teriminde "xian" kategori dosya adlarinda gectigi icin
sahne geciyordu — oysa arsivde kuyu kazan koylulerin fotografi yok.

Olculdu (2026-08-14): kapi acikken uretilen 12 kosumun HEPSI kaynak
kapisinda dustu, skorlar 0-63 (kapi 70), hakemin gerekcesi hep ayni: "dogru
konu, YANLIS an". Onarim dongusu de coremiyordu — Terracotta kosumunda
hakemin revize terimleriyle 7 gorsel yeniden indirildi, yedisi de yine genel
cukur fotografiydi.

Alinti kontrolu bir KUME ARAMASI: dilbilim tahmini yok. DW-87 dersinin
dogru bicimi bu — kod, dogrulanabilir bir olguyu kontrol ediyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _menu(*adlar: str) -> list[dict[str, str]]:
    return [{"dosya": ad, "gosterdigi": "bir sey", "tarih": "1900"} for ad in adlar]


def _plan(*alintilar: str) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="Cutty Sark",
        title="baslik",
        script="metin",
        scenes=[
            {
                "narration": f"sahne {sira}",
                "search_term": f"Cutty Sark detay {sira}",
                "kaynak_dosya": ad,
            }
            for sira, ad in enumerate(alintilar, 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def test_menudeki_dosyalar_geciyor(monkeypatch):
    monkeypatch.setattr(
        ya, "arsiv_envanteri", lambda _k: _menu("A.jpg", "B.jpg", "C.jpg", "D.jpg")
    )

    assert ya.alinti_kusuru(_plan("A.jpg", "B.jpg", "C.jpg")) == ""


def test_uydurulan_dosya_reddediliyor(monkeypatch):
    """Modelin var SANDIGI dosya — kusurun ta kendisi."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: _menu("A.jpg", "B.jpg", "C.jpg"))

    kusur = ya.alinti_kusuru(_plan("A.jpg", "1974 farmers digging well.jpg", "C.jpg"))

    assert "[2]" in kusur


def test_kusur_mesaji_menuyu_tasiyor(monkeypatch):
    """⚠️ Dogrulama hatasi modele geri besleniyor: mesaj SECENEKLERI tasimazsa
    model ayni uydurmayi tekrarliyor ve dongu bes denemeyi tuketiyor."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: _menu("A.jpg", "B.jpg", "C.jpg"))

    kusur = ya.alinti_kusuru(_plan("yok.jpg", "B.jpg", "C.jpg"))

    assert "A.jpg" in kusur and "C.jpg" in kusur


def test_ayni_dosya_iki_sahnede_reddediliyor(monkeypatch):
    """Kullanicinin birebir sikayeti: 'bir resmi birden fazla kez kullanmissin'."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: _menu("A.jpg", "B.jpg", "C.jpg"))

    kusur = ya.alinti_kusuru(_plan("A.jpg", "B.jpg", "A.jpg"))

    assert "A.jpg" in kusur
    assert "more than one scene" in kusur


def test_menu_sahne_sayisindan_kucukse_capa_reddediliyor(monkeypatch):
    """⚠️ Slotun olculmemis adaya harcanmasini engelleyen kapi.

    Olculdu (2026-08-14): Archimedes Palimpsest ve Pompeii Amon Min menusu
    SIFIR dosya; ikisi de skor 0 aldi ve ikisi de bir uretim slotu yakti.
    """
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: _menu("A.jpg", "B.jpg"))

    kusur = ya.alinti_kusuru(_plan("A.jpg", "B.jpg", "A.jpg"))

    assert "only 2 usable images" in kusur
    assert "different concrete thing" in kusur


def test_menu_yoksa_kapi_kapali(monkeypatch):
    """Menusu kurulamayan konularda hat eskisi gibi aramayla calismali."""
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: [])

    assert ya.alinti_kusuru(_plan("", "", "")) == ""


def test_kapi_ISTEMDEKI_menuye_bakiyor(monkeypatch):
    """⚠️ Kapi, modele GOSTERILEN listeye bakmali; planin capasina degil.

    Olculdu (2026-08-14, canli plan uretimi): huni konusu "Cutty Sark"
    verilmisken model capayi "Jock Willis" (gemiyi siparis eden armator)
    sectI. Istem "Cutty Sark" menusunu gostermisti, kapi "Jock Willis"
    menusune bakti ve modelin DOGRU alintiladigi bes sahneyi birden uydurma
    sayip plani reddetti. Kapinin baska bir listeye bakmasi, onu cozdugu
    kusurun kaynagina cevirir.
    """
    menuler = {"Cutty Sark": _menu("A.jpg", "B.jpg", "C.jpg"), "Jock Willis": _menu("Z.jpg")}
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda k: menuler.get(k, []))

    plan = _plan("A.jpg", "B.jpg", "C.jpg")
    plan.visual_anchor = "Jock Willis"

    assert ya.alinti_kusuru(plan, "Cutty Sark") == ""
    assert ya.alinti_kusuru(plan) != "", "capaya bakan surum kusuru yeniden uretir"


def test_kapi_plan_donguSUNE_bagli():
    """⚠️ Baglanti testi — kapi dogru olsa bile cagrilmazsa kusur surer."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def generate_content_plan(")
    govde = kaynak[i : kaynak.index("def refine_search_terms(", i)]

    assert "alinti_kusuru(plan, konu" in govde


def test_menu_onbellekleniyor(monkeypatch):
    """Ayni capa icin tekrar tekrar Commons'a gidilmemeli."""
    import wikimedia_materials as wm

    sayac = {"n": 0}

    def say(_konu, **_kw):
        sayac["n"] += 1
        return [{"title": "File:A.jpg", "aciklama": "", "tarih": ""}]

    monkeypatch.setattr(wm, "arsiv_menusu", say)

    ya.arsiv_envanteri("Tekrar Eden Konu")
    ya.arsiv_envanteri("Tekrar Eden Konu")

    assert sayac["n"] == 1
