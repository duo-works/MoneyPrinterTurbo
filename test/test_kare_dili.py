"""Sahne basina kadraj ve benzerlik olcumu (DW-107)."""

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")

# Prompt govdesini kaynakta bulmak icin kullanilan capa: promptun ACILIS
# cumlesi. ⚠️ Bu cumle degisirse buranin da degismesi gerekir — testler capayi
# bulamayinca "substring not found" diye duser, ki DW-112'de tam bu oldu:
# acilis cumlesi "Create a vertical image for a YouTube Short about history"
# idi ve model bunu kucuk-resim turu sanip goruntunun icine baslik yaziyordu.
CAPA = "Create a single vertical documentary photograph"


# --- Kadraj cesitliligi ---------------------------------------------------


def test_her_sahne_farkli_kadraj_aliyor():
    """⚠️ Olculdu (2026-08-08, Nazca): 8 sahnenin ikisi %84 benzer cikti.

    Sebep promptun kendi icindeki celiskiydi: `GORSEL_DIL` "ardisik iki kare
    birbirine benzememeli" diyor, ama hemen ardindan HER sahneye ayni cumle
    gidiyordu — "One clear focal subject, strong vertical composition".
    """
    kadrajlar = [ya.kare_dili(n) for n in range(1, 9)]

    assert len(set(kadrajlar)) == 8, "sekiz sahne sekiz farkli kadraj almali"


def test_kadraj_listesi_sahne_sayisiyla_ortak_bolen_paylasmiyor():
    """Liste 10; sahne sayisi 6-10.

    Ortak bolen olsaydi ayni sahne numarasi her videoda ayni kadraji alirdi
    ve videolar arasi cesitlilik kaybolurdu.
    """
    assert len(ya.KARE_DILI) == 10
    for sahne_sayisi in range(6, 11):
        assert len(ya.KARE_DILI) % sahne_sayisi != 0 or sahne_sayisi == 10


def test_kadraj_donusumlu():
    assert ya.kare_dili(1) == ya.kare_dili(11)
    assert ya.kare_dili(1) != ya.kare_dili(2)


def test_sabit_kompozisyon_cumlesi_kaldirildi():
    """Her sahneye giden "One clear focal subject" cumlesi cesitliligi bozuyordu.

    ⚠️ Kapsam PROMPT GOVDESI, dosyanin tamami degil: ifade kaldirilma
    gerekcesini anlatan yorumda hala geciyor ve orada gecmesi DOGRU.
    """
    i = KAYNAK.index(CAPA)
    govde = KAYNAK[i : i + 1200]

    assert "One clear focal subject" not in govde


def test_kadraj_prompta_bagli():
    """Baglanti testi — liste dogru olsa bile prompt'a girmezse kusur surer."""
    i = KAYNAK.index(CAPA)
    govde = KAYNAK[i : i + 1200]

    # ⚠️ `konu` 2. argumani DW-121'de eklendi: 1. sahne artik listenin ilk
    # elemanini (genis plan, ozne minicik) miras almiyor, kendi acilis
    # kumesinden konuya gore seciyor.
    assert "kare_dili(index, plan.topic)" in govde


# --- Benzerlik olcumu -----------------------------------------------------


def _kare(yol: Path, renk: int, *, cizgi: bool = False) -> Path:
    im = Image.new("L", (64, 96), renk)
    if cizgi:
        for y in range(0, 96, 8):
            for x in range(64):
                im.putpixel((x, y), 255 - renk)
    im.save(yol)
    return yol


def test_ayni_gorsel_yakalaniyor(tmp_path):
    a = _kare(tmp_path / "a.png", 40, cizgi=True)
    b = _kare(tmp_path / "b.png", 40, cizgi=True)

    ((bulgu,),) = [ya.benzer_kareler([a, b])]

    assert bulgu["sahneler"] == [1, 2]
    assert bulgu["benzerlik"] >= 0.8


def test_farkli_gorseller_bildirilmiyor(tmp_path):
    a = _kare(tmp_path / "a.png", 20)
    b = _kare(tmp_path / "b.png", 200, cizgi=True)

    assert ya.benzer_kareler([a, b]) == []


def test_olcum_bir_kapi_degil(tmp_path):
    """⚠️ Benzerlik sahneyi REDDETMIYOR, yalnizca kaydediliyor.

    Esigin dogru degeri henuz bilinmiyor: ayni anitin iki farkli acisi da
    yuksek skor alabilir ve onu reddetmek videoyu konusundan uzaklastirirdi.
    Once birkac kosumda dagilim olculecek.
    """
    assert "SourceMaterialRejected" not in KAYNAK[
        KAYNAK.index("def benzer_kareler") : KAYNAK.index("def _benzerligi_kaydet")
    ]


def test_okunamayan_dosya_olcumu_dusurmuyor(tmp_path):
    bozuk = tmp_path / "bozuk.png"
    bozuk.write_bytes(b"bu bir resim degil")
    saglam = _kare(tmp_path / "a.png", 40)

    assert ya.benzer_kareler([bozuk, saglam]) == []


def test_olcum_hatasi_uretimi_durdurmuyor(tmp_path, monkeypatch):
    """Olcum bir yan is — kaydin yoklugu, videonun yoklugundan iyidir."""
    def patla(*_a, **_k):
        raise RuntimeError("olcum bozuk")

    monkeypatch.setattr(ya, "benzer_kareler", patla)

    ya._benzerligi_kaydet([tmp_path / "yok.png"], tmp_path / "hedef")  # patlamamali


def test_kayit_dosyaya_yaziliyor(tmp_path):
    a = _kare(tmp_path / "a.png", 40, cizgi=True)
    b = _kare(tmp_path / "b.png", 40, cizgi=True)
    hedef = tmp_path / "kosum"

    ya._benzerligi_kaydet([a, b], hedef)

    assert (hedef / "benzerlik.json").exists()


def test_benzerlik_kaydi_temizlikte_korunuyor():
    """Kayit, artik degil — silinirse gecmise donuk karsilastirma kaybolur."""
    import temizlik

    assert "benzerlik.json" in temizlik.KORUNAN_ADLAR


def test_olcum_hatta_bagli():
    """Baglanti testi — fonksiyon dogru olsa bile cagrilmazsa olcum yok."""
    # ⚠️ SABIT UZUNLUKTA DILIM ALMA. Onceki hali `i : i + 3000` idi ve
    # `download_scene_materials` cagrisina alti satir yorum eklenince olcum
    # cagrisi dilimin DISINDA kaldi; test kod bozulmadan patladi. Dilim
    # fonksiyonun kendi sonuna kadar gidiyor.
    i = KAYNAK.index("def run_generator(")
    govde = KAYNAK[i : KAYNAK.index("\ndef ", i + 10)]

    assert "_benzerligi_kaydet(" in govde
