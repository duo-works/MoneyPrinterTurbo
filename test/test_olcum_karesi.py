"""Tekrar kapisi RENDER EDILECEK kareyi mi olcuyor (§B, 2026-08-21).

⚠️ Olculdu, canli koşum (May Ayim, 21 Agu). Ayni sekiz dosya, AYNI 0,70 esigi:

    yatay orijinal (kapinin olctugu) : 0/28 cift esik ustu, en yuksek 0,668
    dikey kare     (hakemin gordugu) : 7/28 cift esik ustu, en yuksek 0,816

Sekiz sahnenin DORDU ayni duvar resmiydi (farkli dosyalar). Hakem
"essentially the same photographs" dedi, koşum 35 aldi. Dosya kimligi
cesitliligi ise 1,0 — yani eski olcut yapisal olarak kordu.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wikimedia_materials as wm  # noqa: E402
import youtube_automation as ya  # noqa: E402


def _ceyrek_paylasan(yol: Path, *, sol_tohum: int, sag_tohum: int) -> Path:
    """Sol %75'i `sol_tohum`, sag %25'i `sag_tohum` ile uretilmis gorsel.

    ⚠️ Desen BLOK BLOK rastgele — `test_arsiv_tekrari._gorsel` ile ayni
    gerekce: parmak izi 16x16'ya indiriyor, duz zemin her tohumda benzer
    cikar.

    ⚠️ PAYLASILAN BOLGE NEDEN CEYREK — olculdu. `parmak_izi` 256 bit ve
    ortalamaya gore esikleniyor, yani rastgele iki gorselin taban ortusmesi
    0,50. Paylasilan oran `f` iken benzerlik ~ `0,5 + 0,5f`, dolayisiyla
    esigin (0,70) ALTINDA kalmak icin `f < 0,40` sart.

    Ilk yazimda paylasilan bolge YARIMDI (f = 0,50 -> ~0,75) ve orijinaller
    zaten tekrar sayiliyordu: test "kirpma karari cevirdi" degil "her sey
    tekrar" olcuyordu ve YESIL gecerdi. Ceyrek (f = 0,25 -> ~0,625) iki
    tarafi da ayirir: orijinal ayrik, kirpilmis ayni.
    """
    import random

    im = Image.new("RGB", (400, 600))
    ciz = ImageDraw.Draw(im)
    for yari, genislik, tohum in ((0, 300, sol_tohum), (300, 100, sag_tohum)):
        rastgele = random.Random(tohum)
        for gy in range(0, 600, 25):
            for gx in range(yari, yari + genislik, 25):
                ton = rastgele.randint(0, 255)
                ciz.rectangle([gx, gy, gx + 25, gy + 25], fill=(ton, ton, ton))
    im.save(yol)
    return yol


def _sag_ceyrege_kirp(kaynak: Path, hedef: Path) -> Path:
    """URETIMDEKI kirpmanin sade benzeri: ayirt edici cevreyi atar.

    Gercek yol `kareye_uydur` ve orada 16:9 gorsel 9:16'ya BULANIK ARKA PLAN
    ile gidiyor; sonuc ayni: iki AYRI dosya donusumden sonra yakinsiyor.
    """
    with Image.open(kaynak) as im:
        im.convert("RGB").crop((300, 0, 400, 600)).save(hedef)
    return hedef


# --- Cekirdek davranis ------------------------------------------------------


def test_DONUSTURUCUSUZ_orijinal_olculuyor(tmp_path):
    """Bugunku davranis korunuyor: parametre verilmezse hicbir sey degismez."""
    a = _ceyrek_paylasan(tmp_path / "a.jpg", sol_tohum=1, sag_tohum=99)
    b = _ceyrek_paylasan(tmp_path / "b.jpg", sol_tohum=2, sag_tohum=99)

    izler = []
    wm._izi_ekle(a, izler)
    assert wm._tekrar_mi(b, izler) is False, (
        "orijinaller ayrik — donusturucusuz kapi bunlari tekrar SAYMAMALI"
    )


def test_DONUSTURUCUYLE_donusmus_kare_olculuyor(tmp_path):
    """⚠️ ASIL TEST — kusurun birebir sekli.

    Iki dosya ORIJINALDE ayrik, DONUSUMDEN SONRA ayni. Eski kapi "temiz"
    diyordu; hakem ekranda ayni goruntuyu goruyordu.
    """
    a = _ceyrek_paylasan(tmp_path / "a.jpg", sol_tohum=1, sag_tohum=99)
    b = _ceyrek_paylasan(tmp_path / "b.jpg", sol_tohum=2, sag_tohum=99)

    izler = []
    wm._izi_ekle(a, izler, _sag_ceyrege_kirp)
    assert wm._tekrar_mi(b, izler, _sag_ceyrege_kirp) is True, (
        "donusumden sonra ayni goruntu — kapi tekrar saymaliydi"
    )


def test_esik_DEGISMEDI(tmp_path):
    """⚠️ Bu bir esik degisikligi DEGIL. Gercekten ayrik kareler, donusum
    uygulansa bile tekrar sayilmamali."""
    a = _ceyrek_paylasan(tmp_path / "a.jpg", sol_tohum=1, sag_tohum=5)
    b = _ceyrek_paylasan(tmp_path / "b.jpg", sol_tohum=2, sag_tohum=7)

    izler = []
    wm._izi_ekle(a, izler, _sag_ceyrege_kirp)
    assert wm._tekrar_mi(b, izler, _sag_ceyrege_kirp) is False


def test_donusum_PATLARSA_orijinale_dusuyor(tmp_path):
    """⚠️ ACIK DUSER. Bir kirpma hatasi yuzunden mesru adayi elemek,
    tekrari kacirmaktan kotu — `_tekrar_mi`nin kendi doktrini."""

    def _patlayan(_kaynak, _hedef):
        raise RuntimeError("kirpma patladi")

    a = _ceyrek_paylasan(tmp_path / "a.jpg", sol_tohum=1, sag_tohum=99)
    b = _ceyrek_paylasan(tmp_path / "b.jpg", sol_tohum=1, sag_tohum=99)

    izler = []
    wm._izi_ekle(a, izler, _patlayan)
    # Ayni tohum -> orijinaller de ayni; olcum orijinale dustugu icin
    # tekrar YINE yakalanmali. Patlama sessizce yutulmamali ama uretimi
    # de durdurmamali.
    assert wm._tekrar_mi(b, izler, _patlayan) is True


def test_GECICI_dosya_birakmiyor(tmp_path):
    """Her aday icin bir gecici kare uretiliyor; sizmamali."""
    import tempfile

    a = _ceyrek_paylasan(tmp_path / "a.jpg", sol_tohum=1, sag_tohum=99)
    gecici_kok = Path(tempfile.gettempdir())
    onces = set(gecici_kok.glob("*.jpg"))

    izler = []
    for _ in range(5):
        wm._izi_ekle(a, izler, _sag_ceyrege_kirp)
        wm._tekrar_mi(a, izler, _sag_ceyrege_kirp)

    yeni = set(gecici_kok.glob("*.jpg")) - onces
    assert not yeni, f"gecici kare sizdi: {sorted(p.name for p in yeni)[:3]}"


# --- Baglanti: hat bunu KULLANIYOR mu --------------------------------------
# ⚠️ M9 DERSI (bu oturum, `f5034ee`): "deger dogru" olcmek yetmiyor, hattin
# onu GECIRDIGI de olculmeli. Asagidaki iki test tam onu yapiyor.


def _donusturucuyu_yakala(monkeypatch):
    """`download_scene_materials`a gecen `kare_donusturucu`yu yakalar.

    ⚠️ Kategori havuzu da susturuluyor: o cagri indirmeden ONCE ve AGA
    cikiyor. Susturulmazsa test aga bagimli olurdu.
    """
    gorulen = {}

    def _sahte(*_a, **k):
        gorulen["kare_donusturucu"] = k.get("kare_donusturucu", "GECILMEDI")
        raise wm.MaterialsUnavailableError("test")

    monkeypatch.setattr(ya, "download_scene_materials", _sahte)
    monkeypatch.setattr(
        wm, "kategori_havuzunu_coz", lambda *_a, **_k: [], raising=False
    )
    return gorulen


def test_SHORTS_uretimi_donusturucu_GECIYOR(monkeypatch, tmp_path):
    gorulen = _donusturucuyu_yakala(monkeypatch)
    plan = ya.ContentPlan(
        topic="k",
        visual_anchor="c",
        title="b",
        script="m",
        scenes=[{"narration": "x", "search_term": "y"} for _ in range(6)],
        description="a",
        tags=["a", "b", "c"],
    )
    try:
        ya.run_generator(plan, 1, bicim=ya.SHORTS_BICIMI)
    except Exception:
        pass
    assert gorulen.get("kare_donusturucu") not in (None, "GECILMEDI"), (
        "Shorts kolunda donusturucu gecmiyor — kapi yine yatayi olcer"
    )


def test_UZUN_uretimi_donusturucu_GECIRMIYOR(monkeypatch, tmp_path):
    """⚠️ Ustteki testin karsi kutbu. Uzun formatta kare zaten ~16:9 ve
    orijinalin olcumu DOGRU olcumdur; buraya da uygulamak yeni bir kusur
    olurdu."""
    gorulen = _donusturucuyu_yakala(monkeypatch)
    plan = ya.ContentPlan(
        topic="k",
        visual_anchor="c",
        title="b",
        script="m",
        scenes=[{"narration": "x", "search_term": "y"} for _ in range(24)],
        description="a",
        tags=["a", "b", "c"],
    )
    try:
        ya.run_generator(plan, 1, bicim=ya.UZUN_BICIMI)
    except Exception:
        pass
    assert gorulen.get("kare_donusturucu") is None, (
        f"uzun kolda donusturucu gecmemeliydi: {gorulen.get('kare_donusturucu')}"
    )


def test_IKINCIL_yola_da_donusturucu_geciyor():
    """⚠️ MUTASYON M8 BURADAN KACTI (2026-08-21).

    `ikincil_gorseller` cagrisindan `kare_donusturucu`yu silmek hicbir testi
    dusurmuyordu. Ikincil gorsel de videoda GORUNUYOR: gecmezse sahnenin
    ikinci karesi tekrar elemesini yatay orijinal uzerinden yapar ve
    duzeltilen kusur yarim kalir.

    ⚠️ Cagri ICINDE araniyor, birebir satirda degil — ayni sekli olcen
    `test_menuden_ikincil.test_cagiran_MENUYU_ve_CAPAYI_geciriyor` ile ayni
    kalip. Davranissal hali `review_source_materials` goru cagrisini taklit
    etmeyi gerektirirdi: kazanci yok, kirilganligi cok.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    bas = kaynak.index("wikimedia_materials.ikincil_gorseller(")
    govde = kaynak[bas : bas + 2600]

    assert "kare_donusturucu=" in govde, (
        "ikincil yola donusturucu gecmiyor — o kareler yatay olculur"
    )
    assert "bicim.dikey" in govde, (
        "donusturucu bicime bagli degil — uzun formatta da uygulanir"
    )
