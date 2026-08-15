"""Gorsel palet, isik cesitliligi ve klip suresi (DW-109).

Bu modulun testleri iki olculmus kusuru kilitliyor:

  * palet — 2026-08-09 Mohenjo-Daro kosumunda 7 karenin hepsi 25°-47° ton
    araligindaydi (dairesel yayilim 0,007) ve video tek renkli gorunuyordu;
  * tekrar — 7 sahne × 5 sn = 35,00 sn ama ses 35,88 sn'ydi, MPT acigi bastan
    bir klibi TEKRAR ederek kapatti ve video sahne 1'in tekrariyla bitti.
"""

import math
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KAYNAK = Path(ya.__file__).read_text(encoding="utf-8")

# Prompt govdesini kaynakta bulmak icin kullanilan capa: promptun ACILIS
# cumlesi. ⚠️ Bu cumle degisirse buranin da degismesi gerekir — bkz.
# test_kare_dili.py'deki ayni sabit ve DW-112.
CAPA = "Create a single vertical documentary photograph"


def _prompt_govdesi() -> str:
    """Prompt govdesi, bitisik string parcalari BIRLESTIRILMIS halde.

    ⚠️ Ham kaynakta arama yapmak yaniltici: Python bitisik literalleri
    birlestirdigi icin promptta tek parca duran bir ifade kaynakta
    `"...no invented "` / `"event presented..."` diye ikiye bolunmus olabilir
    ve testi sahte bir sekilde dusurur.
    """
    i = KAYNAK.index(CAPA)
    govde = KAYNAK[i : KAYNAK.index("request = {", i)]
    return re.sub(r'"\s*\n\s*(?:\+\s*)?f?"', "", govde)


# --- Cizgi film gorunumu --------------------------------------------------


def test_gorsel_dil_artik_illustrasyon_istemiyor():
    """⚠️ "sanki cartoon gibi" sikayetinin kaynagi model DEGIL, promptun kendisiydi.

    (b) sikki acikca "richly coloured historical painting or a detailed period
    illustration" diyordu. Gecmisteki sahneler Commons'ta nadiren fotografla
    karsilandigi icin AI dolgusunun cogu bu sikka dusuyor, yani cizim kanalin
    varsayilan gorunumu oluyordu.
    """
    for istenmeyen in ("historical painting", "period illustration"):
        assert istenmeyen not in ya.GORSEL_DIL


def test_gorsel_dil_fotograf_istiyor():
    assert "real photograph" in ya.GORSEL_DIL
    for yasak in ("never a painting", "never an illustration", "never a digital render"):
        assert yasak in ya.GORSEL_DIL.lower()


def test_uydurma_olay_guvencesi_duruyor():
    """⚠️ Fotogerceklik arttikca bu guvence DAHA onemli hale geliyor.

    Canlandirma bugun cekilmis bir fotograf gibi durmali; hayatta kalmis bir
    arsiv belgesi gibi degil. Yoksa uydurulmus bir sahne kanit sanilir.
    """
    assert "no invented event presented as a surviving photograph" in _prompt_govdesi()


# --- Isik cesitliligi -----------------------------------------------------


def test_her_sahne_farkli_isik_aliyor():
    isiklar = [ya.isik_dili(n) for n in range(1, 9)]

    assert len(set(isiklar)) == 8


def test_isik_listesi_kadraj_listesiyle_kilitlenmiyor():
    """⚠️ Iki liste ortak bolen paylassaydi kadraj-isik ciftleri sabitlenirdi.

    Ornegin ikisi de 10 uzunlukta olsaydi 3. sahne HER videoda ayni kadraj +
    ayni isik ikilisini alirdi ve cesitlilik goruntude degil yalnizca listede
    kalirdi. 11 asal; 10 ile de, 6-10 sahne sayilariyla da ortak boleni yok.
    """
    assert len(ya.ISIK_DILI) == 11
    assert math.gcd(len(ya.ISIK_DILI), len(ya.KARE_DILI)) == 1
    for sahne_sayisi in range(6, 11):
        assert math.gcd(len(ya.ISIK_DILI), sahne_sayisi) == 1


def test_kadraj_listesi_isiktan_bahsetmiyor():
    """⚠️ Kadraj ve isik AYRI eksenler; ayni cumlede ikisini tarif etmek,
    bu modulun bir kez dustugu "prompt kendisiyle celisiyor" tuzagi.

    Ilk surumde 6. madde "golden hour ... warm side light", 10. madde
    "overcast ... cool light" diyordu — `ISIK_DILI` eklendiginde bunlar
    sahnenin isigini iki kez, farkli sekilde tarif ederdi.
    """
    isik_sozcukleri = (
        "light",
        "shadow",
        "golden hour",
        "dusk",
        "dawn",
        "overcast",
        "sunlit",
        "rain",
        "weather",
        "night",
    )
    for kadraj in ya.KARE_DILI:
        for sozcuk in isik_sozcukleri:
            assert sozcuk not in kadraj.lower(), f"kadrajda isik tarifi: {kadraj!r}"


def test_isik_tohumu_kararli():
    """⚠️ `hash()` KULLANILMAMALI — surec basina rastgele tohumlanir.

    Ayni konu farkli kosumlarda farkli isik alir ve bir kosumu yeniden uretmek
    imkansiz olurdu. Bu deger surecler arasinda sabit olmali.
    """
    assert ya.isik_tohumu("Mohenjo-Daro") == ya.isik_tohumu("Mohenjo-Daro")
    assert ya.isik_tohumu("  MOHENJO-DARO ") == ya.isik_tohumu("mohenjo-daro")

    # ⚠️ Kapsam fonksiyonun KODU, docstring'i degil: `hash()` ifadesi orada
    # neden kullanilmadigini anlatirken geciyor ve gecmesi DOGRU.
    basi = KAYNAK.index("def isik_tohumu")
    kod = KAYNAK[KAYNAK.index('"""', KAYNAK.index('"""', basi) + 3) + 3 : basi + 900]

    assert "hash(" not in kod
    assert "crc32" in kod


def test_isik_tohumu_videolar_arasinda_kayiyor():
    """Kaydirma olmasaydi her video ayni isikla acilirdi."""
    tohumlar = {
        ya.isik_tohumu(konu)
        for konu in (
            "Mohenjo-Daro",
            "Chaco Canyon",
            "The Nazca Lines",
            "Roman Aqueducts",
            "Viking Longships",
        )
    }

    assert len(tohumlar) > 1


def test_isik_prompta_bagli():
    """Baglanti testi — liste dogru olsa bile prompta girmezse olcum degismez."""
    govde = _prompt_govdesi()

    assert "isik_dili(" in govde
    assert "isik_tohumu(" in govde


def test_palet_kurali_prompta_bagli():
    """⚠️ Tek basina isik vermek YETMEDI.

    Model her seyin uzerine tek bir sicak katman koyuyordu; negatif kural
    olmadan "blue hour" bile kehribara donuyordu.
    """
    govde = _prompt_govdesi().lower()

    assert "single global warm colour grade" in govde
    assert "amber, ochre or sepia" in govde


def test_okunabilirlik_tabani_var():
    """⚠️ Olculdu (2026-08-09): isik donusumu eklenince iki kare 0,21-0,22
    parlakliga dustu. Shorts telefonda izleniyor; karanlik kare orada okunmuyor.
    """
    assert "readable at" in _prompt_govdesi()


# --- Klip suresi ----------------------------------------------------------


def test_olculen_kosum_artik_tekrar_uretmiyor():
    """⚠️ Gercek kusur: 7 sahne × 5 sn = 35,00 sn, ses 35,88 sn.

    MPT acigi TAM bir klip ekleyerek kapatiyor, video sahne 1'in tekrariyla
    bitiyordu — kapanis cumlesi geri donusturulmus acilis karesine dusuyordu.
    """
    klip = ya.klip_suresi(35.88, 7)

    assert klip * 7 >= 35.88 + 0.10, "tekrar geri geldi"


@pytest.mark.parametrize("ses", [28.0, 31.4, 35.88, 39.72, 44.0, 52.5])
@pytest.mark.parametrize("sahne", range(6, 11))
def test_ne_tekrar_ne_dusen_sahne(ses: float, sahne: int):
    """Iki yonlu degismez — biri saglanip digeri bozulabilir.

    Cok kisa klip → toplam sesi kapatmaz → MPT bastan bir klibi TEKRAR eder.
    Cok uzun klip → dongu sure dolunca kirilir → SON SAHNE videoya hic girmez.
    """
    klip = ya.klip_suresi(ses, sahne)

    # MPT ses suresine 0,10 sn emniyet payi ekliyor; kapsanmali.
    assert klip * sahne >= ses + 0.10, "tekrar olurdu"
    assert klip * (sahne - 1) < ses, "son sahne dusetdi"


def test_olculemeyen_ses_varsayilana_duser():
    """Ses olculemedi diye video uretmemek yanlis olurdu."""
    assert ya.klip_suresi(0.0, 7) == ya.VARSAYILAN_KLIP_SURESI
    assert ya.klip_suresi(-1.0, 7) == ya.VARSAYILAN_KLIP_SURESI
    assert ya.klip_suresi(35.88, 0) == ya.VARSAYILAN_KLIP_SURESI


def test_anlatim_suresi_hatada_patlamiyor(monkeypatch):
    """Olcum bir yan is; agi yoksa uretim yine de yurumelidir."""

    def patla(*_a, **_k):
        raise RuntimeError("ag yok")

    monkeypatch.setattr("asyncio.run", patla)

    assert ya.anlatim_suresi("herhangi bir metin") == 0.0


def test_ses_ayarlari_tek_yerde():
    """⚠️ Olcum ile CLI ayni sesi kullanmali.

    Ayrisirlarsa olculen sure gercek sesin suresi olmaz ve klip hesabi sessizce
    bozulur — video yine tekrar etmeye baslar ama sebebi gorunmez olur.
    """
    # ⚠️ KARAKTER DILIMI ALINMIYOR artik. Eskiden `--video-clip-duration`
    # sonrasi 400 karaktere bakiliyordu ve araya bir bayrak eklenince
    # (2026-08-15, `--n-threads`) test dustu — oysa olctugu sey hic
    # bozulmamisti. Aranan sey ayni KOMUT LISTESI, sabit bir uzunluk degil.
    i = KAYNAK.index('"--video-clip-duration"')
    govde = KAYNAK[i : KAYNAK.index("subprocess.run(", i)]

    assert "SES_ADI" in govde
    assert "SES_HIZI" in govde
    assert "str(klip)" in govde


# --- Palet olcumu ---------------------------------------------------------


def _renkli_kare(yol: Path, hsv_tonu: int) -> Path:
    from PIL import Image

    Image.new("HSV", (64, 96), (hsv_tonu, 200, 180)).convert("RGB").save(yol)
    return yol


def test_tek_renkli_kosum_dusuk_yayilim_veriyor(tmp_path):
    """Olculdu: Mohenjo-Daro kosumu 0,007 — video tek renkli gorunuyordu."""
    kareler = [_renkli_kare(tmp_path / f"{i}.png", 20 + i) for i in range(5)]

    assert ya.ton_yayilimi(kareler) < 0.05


def test_dagilmis_palet_yuksek_yayilim_veriyor(tmp_path):
    kareler = [_renkli_kare(tmp_path / f"{i}.png", t) for i, t in enumerate((0, 60, 120, 180))]

    assert ya.ton_yayilimi(kareler) > 0.5


def test_ton_dairesel_olarak_olculuyor(tmp_path):
    """⚠️ Duz ortalama yaniltir: 0° ile 359° komsu tonlar, uzak degil.

    Duz hesapla bu iki kare "maksimum farkli" cikar ve tek renkli bir kosum
    cesitli gorunurdu.
    """
    kareler = [
        _renkli_kare(tmp_path / "a.png", 1),
        _renkli_kare(tmp_path / "b.png", 254),
    ]

    assert ya.ton_yayilimi(kareler) < 0.05


def test_olcum_tek_kareyle_patlamiyor(tmp_path):
    assert ya.ton_yayilimi([_renkli_kare(tmp_path / "a.png", 30)]) == 0.0
    assert ya.ton_yayilimi([]) == 0.0


def test_okunamayan_dosya_olcumu_dusurmuyor(tmp_path):
    bozuk = tmp_path / "bozuk.png"
    bozuk.write_bytes(b"bu bir resim degil")

    assert ya.ton_yayilimi([bozuk, _renkli_kare(tmp_path / "a.png", 30)]) == 0.0


def test_iki_eksen_de_kaydediliyor(tmp_path):
    """⚠️ Biri iyilesirken digeri kotulesebilir — Mohenjo-Daro'da tam oyle oldu:
    yapisal tekrar sifir, ton yayilimi 0,007. Tek sayi "duzeldi" yanilgisi verir.
    """
    import json

    kareler = [_renkli_kare(tmp_path / f"{i}.png", 20 + i * 40) for i in range(3)]
    hedef = tmp_path / "kosum"

    ya._benzerligi_kaydet(kareler, hedef)
    kayit = json.loads((hedef / "benzerlik.json").read_text(encoding="utf-8"))

    assert "benzer_kareler" in kayit
    assert "ton_yayilimi" in kayit


def test_klip_suresi_ondalik_gecebiliyor():
    """Tamsayi kisiti ikisinden birini kacinilmaz kiliyordu (35,88 / 7 = 5,13)."""
    from app.models.schema import VideoParams

    params = VideoParams(video_subject="x", video_clip_duration=5.23)

    assert params.video_clip_duration == pytest.approx(5.23)
