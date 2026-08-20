"""Video kapagi (thumbnail) uretimi — arsiv karesi + uzerine yazi.

⚠️ NEDEN AI DEGIL. Kanal sahibinin kararı (2026-08-20): kapak, videonun
ICINDEN cikan gercek bir arsiv karesi olacak, uretilmis gorsel degil. Sebep
kozmetik degil: `SENTETIK_BEYANI` (`youtube_upload.py`) bu hattin sentetik
medya TASIMADIGINI beyan ediyor. Kapak da videonun yuzu — uretilmis bir kapak
o beyani, videonun kendisi temiz olsa bile, tartismali hale getirirdi.

⚠️ GORSEL DIL ALTYAZIYLA AYNI, ve bu bilincli: beyaz metin, siyah kontur,
KUTU YOK. Kutu kararı DW-103'te ölçülerek verildi (kanal sahibi: kutulu
altyazı görüntüyü örtüyor). Kapak ayrı bir yüzey ama aynı izleyici aynı
kanalda ikisini yan yana görüyor; kutu eklemek kanalı iki dilli yapardı.
Kontur oranı da oradan geliyor: 56 px punto -> 7 px kontur = **%12,5**, ve
burada MUTLAK degil ORAN olarak tasiniyor cunku kapak puntosu otomatik
kuculuyor (`_punto_sec`).

⚠️ YAZI KISA OLMALI, ve bu bir zevk meselesi degil olcum meselesi: YouTube
kapagi oneri akisinda ~210x118 piksele iniyor, yani 1280x720'nin **altida
biri**. Uzun baslik o boyutta okunamaz; bu yuzden `kapak_yazisi` ayri bir
alan (plan modelinin yazdigi 3-5 kelime) ve o alan yoksa `yaziyi_kisalt`
basligi determinist olarak kisaltiyor. Basligi oldugu gibi basmak, kapagi
"var ama ise yaramaz" hale getirirdi.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent

KAPAK_GENISLIGI = 1280
KAPAK_YUKSEKLIGI = 720
"""YouTube'un onerdigi kapak olcusu (16:9). Dosya siniri 2 MB."""

KAPAK_FONTU = ROOT / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"
"""⚠️ Depodaki TEK Latin-bold yuz. Digerleri ya CJK (`MicrosoftYaHei`,
`STHeiti`) ya el yazisi (`Charm`) ya da `Medium` agirlikta — kapak yazisi
kucuk olcekte once agirligini kaybeder, o yuzden Bold pazarlik disi."""

KONTUR_ORANI = 0.125
"""Altyazidan tasinan oran (56 px puntoda 7 px). Bkz. modul basligi."""

KENAR_PAYI = 0.055
"""Metnin dokunamayacagi kenar bandi, genislige oran. YouTube kapagin
sag-alt kosesine SURE ROZETINI basiyor; oran o rozetin ustunde kalmayi
saglamiyor tek basina — `YAZI_YERI` "alt" iken metin ortalanip rozetin
solunda kaliyor, uzun satirlarda `_punto_sec` kuculterek cozuyor."""

EN_BUYUK_PUNTO = 132
EN_KUCUK_PUNTO = 58
"""⚠️ Alt sinir bir TABAN, hedef degil. 58 px 1280 genislikte ~%4,5 eder ve
210 px'lik onizlemede ~9,5 px'e iner — okunabilirligin en altı. Metin bu
puntoda da sigmiyorsa satir sayisi artirilmaz, metin KISALTILIR; yoksa
kapak kucuk olcekte gri bir lekeye doner."""

EN_COK_SATIR = 3

YAZI_YUKSEKLIK_PAYI = 0.30
"""Metin blogunun kaplayabilecegi en fazla yukseklik, kapak yuksekligine oran.

⚠️ BU SATIR OLCUMLE GELDI, tasarim tercihi degil. Ilk uretim "340 WAITED
HERE"i iki satira bolup 296 px kapladi ve tam iskeletlerin — yani kapagi
tiklatan seyin — uzerine oturdu. Once metni "detayi az" banda tasimak
denendi ve **curudu**: kenar enerjisi olculdugunde en duz bant ORTA cikti
(ust 36,3 · orta 26,8 · alt 32,9) cunku odalar golgede; yani olcut, ozneyi
en iyi orten yeri seciyordu.

Gercek kusur yer degil BOYUTTU. Butce konunca `_punto_sec` iki satirlik
buyuk puntoyu reddedip tek satira iniyor ve blok 296 -> ~150 px'e dusuyor;
ozne aciliyor. Yani metin kucultuluyor gibi gorunse de kapak GUCLENIYOR."""

_KOYU = (0, 0, 0)
_BEYAZ = (255, 255, 255)


def videodan_kare(video: str | Path, saniye: float, hedef: str | Path) -> Path:
    """Videonun `saniye` anindaki karesini PNG olarak yazar.

    ⚠️ ALTYAZISIZ kurgu (`combined-*.mp4`) verilmeli, `final-*.mp4` DEGIL:
    final altyaziyi kareye yakiyor ve kapakta uzerine bir de kapak yazisi
    binerdi. Hangi dosyanin verilecegi cagiranin isi; burada dogrulanamaz
    cunku iki dosya ayni cozunurlukte.
    """
    hedef = Path(hedef)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            str(float(saniye)),
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(hedef),
        ],
        check=True,
    )
    return hedef


def yaziyi_kisalt(baslik: str, *, en_cok: int = 42) -> str:
    """Basligi kapaga sigacak kadar kisaltir — determinist, cikarimsiz.

    ⚠️ Bu bir YEDEK yol. Iyi kapak yazisini plan modeli yaziyor
    (`kapak_yazisi`); burasi o alan yokken (ornegin bu hattin ESKI
    yayinlarinda) devreye giriyor. Iki adim, ikisi de olculdu:

      1. `"Köktürk: What Happened to Their Writing?"` gibi basliklarda
         iki nokta ONCESI konu adi, sonrasi soru. Kapakta soru daha cok
         merak uyandiriyor, ama konu adi kaybolursa kapak baglamsiz kalir —
         bu yuzden UZUN olan yari degil, `en_cok`a SIGAN yari secilir.
      2. Soru isareti KORUNUR. Merak kancasinin noktalama isareti odur.
    """
    metin = " ".join(str(baslik or "").split())
    if not metin:
        return ""
    if len(metin) <= en_cok:
        return metin
    if ":" in metin:
        on, _, arka = metin.partition(":")
        for aday in (arka.strip(), on.strip()):
            if aday and len(aday) <= en_cok:
                return aday
    # Kelime siniri: `en_cok`i asmadan alinabilen en uzun on ek.
    kelimeler = metin.split()
    parca: list[str] = []
    for kelime in kelimeler:
        deneme = " ".join([*parca, kelime])
        if parca and len(deneme) > en_cok:
            break
        parca.append(kelime)
    return " ".join(parca) if parca else metin[:en_cok]


def _sar(metin: str, font: ImageFont.FreeTypeFont, en_fazla_genislik: int) -> list[str]:
    """Metni satirlara boler; tek kelime sigmiyorsa o kelime kendi satirinda kalir."""
    satirlar: list[str] = []
    gecerli = ""
    for kelime in metin.split():
        deneme = f"{gecerli} {kelime}".strip()
        if gecerli and font.getlength(deneme) > en_fazla_genislik:
            satirlar.append(gecerli)
            gecerli = kelime
        else:
            gecerli = deneme
    if gecerli:
        satirlar.append(gecerli)
    return satirlar


def _satir_yuksekligi(punto: int) -> int:
    return int(punto * 1.12)


def _punto_sec(
    metin: str, en_fazla_genislik: int
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """En buyuk puntodan baslayip UC kosulu birden saglayan ilkini secer.

    Kosullar: satir sayisi `EN_COK_SATIR`i asmasin · hicbir satir banda
    tasmasin · blogun toplam yuksekligi `YAZI_YUKSEKLIK_PAYI`yi asmasin.

    ⚠️ Buyukten kucuge inmek onemli: kucukten buyuye cikan bir arama, bir
    kelime tek basina tasarken durup metni ustteki satira sikistirmis olur.

    ⚠️ Ucuncu kosul (yukseklik butcesi) satir sayisini DOLAYLI olarak
    kisitliyor ve kasitli boyle: dogrudan "tek satir olsun" demek uzun
    basliklari `EN_KUCUK_PUNTO`ya kadar ezerdi. Butce, kisa metinde tek
    satiri secip buyuk basiyor; uzun metinde iki satira izin verip puntoyu
    dusuruyor. Bkz. `YAZI_YUKSEKLIK_PAYI`.
    """
    butce = KAPAK_YUKSEKLIGI * YAZI_YUKSEKLIK_PAYI
    punto = EN_BUYUK_PUNTO
    while True:
        font = ImageFont.truetype(str(KAPAK_FONTU), punto)
        satirlar = _sar(metin, font, en_fazla_genislik)
        uyar = (
            len(satirlar) <= EN_COK_SATIR
            and all(font.getlength(s) <= en_fazla_genislik for s in satirlar)
            and _satir_yuksekligi(punto) * len(satirlar) <= butce
        )
        if uyar or punto <= EN_KUCUK_PUNTO:
            return font, satirlar
        # ⚠️ `max` sart: duz `punto -= 4` tabani ASIYORDU (132'den 4'er inen
        # dizi 58'e ugramiyor, 60'tan 56'ya atliyor) ve kapak tabanin altinda
        # bir puntoyla basiliyordu. Testle yakalandi.
        punto = max(EN_KUCUK_PUNTO, punto - 4)


def _kirp(kare: Image.Image) -> Image.Image:
    """Kareyi 16:9'a ORTADAN kirpar ve kapak olcusune getirir.

    ⚠️ Sikistirma (`resize` ile en-boy bozma) DEGIL kirpma: hattin karesi
    zaten 1920x1080, yani bu yol normalde kimlik. Kirpma, kapak baska bir
    kaynaktan (ornegin ham arsiv gorseli) verilirse diye var.
    """
    hedef_oran = KAPAK_GENISLIGI / KAPAK_YUKSEKLIGI
    g, y = kare.size
    if g / y > hedef_oran:
        yeni_g = int(y * hedef_oran)
        sol = (g - yeni_g) // 2
        kare = kare.crop((sol, 0, sol + yeni_g, y))
    else:
        yeni_y = int(g / hedef_oran)
        ust = (y - yeni_y) // 2
        kare = kare.crop((0, ust, g, ust + yeni_y))
    return kare.resize((KAPAK_GENISLIGI, KAPAK_YUKSEKLIGI), Image.LANCZOS)


def kapak_uret(kare_yolu: str | Path, yazi: str, hedef: str | Path) -> Path:
    """Kareyi kapaga cevirir: 1280x720, alt ortada beyaz yazi + siyah kontur.

    `yazi` bos ise kare oldugu gibi kapak olur — yazisiz kapak, kapaksiz
    videodan iyidir (YouTube aksi halde rastgele bir kare seciyor).
    """
    hedef = Path(hedef)
    hedef.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(kare_yolu) as ham:
        kapak = _kirp(ham.convert("RGB"))

    metin = " ".join(str(yazi or "").split()).upper()
    if metin:
        pay = int(KAPAK_GENISLIGI * KENAR_PAYI)
        font, satirlar = _punto_sec(metin, KAPAK_GENISLIGI - 2 * pay)
        kontur = max(2, round(font.size * KONTUR_ORANI))
        cizici = ImageDraw.Draw(kapak)

        satir_yuksekligi = int(font.size * 1.12)
        toplam = satir_yuksekligi * len(satirlar)
        # Alt kenardan pay birakilir; metin blogu yukari dogru buyur.
        ust = KAPAK_YUKSEKLIGI - pay - toplam

        for sira, satir in enumerate(satirlar):
            cizici.text(
                (KAPAK_GENISLIGI // 2, ust + sira * satir_yuksekligi),
                satir,
                font=font,
                fill=_BEYAZ,
                stroke_width=kontur,
                stroke_fill=_KOYU,
                anchor="ma",
            )

    kapak.save(hedef, "JPEG", quality=90, optimize=True)
    return hedef
