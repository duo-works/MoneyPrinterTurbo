"""Gorsel benzerligi ve renk dagilimi olcumleri.

Ayri modul olmasinin sebebi ICE BAGIMLILIK: `wikimedia_materials` arsivden
inen adaylarin birbirinin kopyasi olup olmadigina bakmali, ama
`youtube_automation` zaten `wikimedia_materials`'i import ediyor. Olcum orada
kalsaydi dairesel import olurdu. Iki taraf da buradan aliyor, tek uygulama.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

BENZERLIK_ESIGI = 0.80
"""Iki karenin "fazla benzer" sayildigi esik — OLCUM esigi.

Olculdu (2026-08-08, Nazca): 8 sahnenin ikisi %84 benzerdi.
"""

ARSIV_TEKRAR_ESIGI = 0.70
"""Arsivden inen bir aday, secilmis bir sahneye bu kadar benziyorsa REDDEDILIR.

⚠️ Bu bir kapi ama YUMUSAK kapi: reddedilen aday yerine sonraki aday deneniyor,
baska aday yoksa yine de kabul ediliyor (bkz. `wikimedia_materials`). Bu yuzden
esigi biraz agresif tutmak bedava — en kotu ihtimalle bir arama daha yapiliyor.

Veriden secildi (2026-08-09, Library of Alexandria kosumu). Ayni kosumun arsiv
ciftleri:

    0,836  "The Great Library of Alexandria - Colorized" ↔ "Ancientlibraryalex"
           → AYNI gravur, biri renklendirilmis
    0,734  "Alexandria by Boston Public Library" ↔ "The Serapeum of Alexandria"
           → ayni sutun (Pompey Sutunu), biri eski biri yeni fotograf
    0,578  ve altinda: gercekten farkli gorseller

Iki gercek tekrar 0,73 ve ustunde, sonraki cift 0,58 — arada genis bir bosluk
var ve 0,70 tam ortasina dusuyor: ikisini de yakaliyor, mesru gorsellerden
0,12 uzakta duruyor.

⚠️ Ikinci cift (ayni sutunun eski ve yeni fotografi) bilerek kapsama alindi:
izleyici icin "ayni gorsel" ile "ayni oznenin baska fotografi" arasindaki
fark yok, ikisi de tekrar gibi goruluyor. Montajda sahne 2 ve 5 yan yana
konunca ikisi de tek basina duran bir sutundu.

⚠️ Veri TEK kosumdan (n=1): temizlik onceki kosumlarin arsiv gorsellerini
siliyor, gecmise donuk daha genis bir dagilim cikarilamadi. Yumusak kapi
tasarimi bu belirsizligi tasiyor — esik yanlissa bedeli bir arama daha.

⚠️ Baslik karsilastirmasi bu iki durumun HICBIRINI yakalayamaz: dosya adlari
tamamen farkli. `used_titles` zaten vardi ve yetmedi.
"""


PARLAKLIK_TABANI = 45.0
"""Bir karenin "fazla karanlik" sayildigi ortalama luma (0-255) — DUZELTME esigi.

⚠️ Bu esik veriden secildi, goz karariyla degil. Diskteki 22 dikey karenin
parlaklik dagilimi (2026-08-09):

    29,6  41,5  42,0  |  51,1  54,1  56,4  62,5  ...
    37,0  40,8  41,7  |
    ^ sorunlu kume       ^ saglikli kume

Alttaki alti kare 29,6-42,0 arasinda toplaniyor, sonraki kare 51,1 — arada
9 puanlik bos bir aralik var ve 45 tam ortasina dusuyor. Yani esik iki kumeyi
ayiriyor, bir kumenin icinden gecmiyor. Dagilimin ortancasi 70,7.

Olculdu (2026-08-09, Chaco Canyon): acilis karesi 37,0 idi ve telefonda gunduz
isiginda ilk saniye okunmuyordu. Shorts'un ilk karesi izlenme kararinin
verildigi yer — orada karanlik kare dogrudan kayip.

⚠️ Prompt bunu ZATEN istiyor ("readable at small size on a phone screen — no
crushed shadows") ve TUTMUYOR. Bu yuzden dilek degil, olcum ve duzeltme.
"""

PARLAKLIK_HEDEFI = 65.0
"""Duzeltilen karenin cikarilacagi parlaklik.

Tabanin (45) hemen ustune degil, ortancanin (70,7) hemen altina nisan aliniyor:
tam tabana cikarmak kareyi sinirda birakir, ortancaya cikarmak ise gecesi olan
sahneyi gunduze cevirirdi. 65 ikisinin arasinda ve olculdu — Chaco acilis
karesi bu yolla 37 → 78 cikarildiginda alacakaranlik mavisi ve kumtasinin
sicakligi korundu, harabeler okunur hale geldi.
"""

AZAMI_GAMA = 3.0
"""Duzeltmenin ust siniri.

Neredeyse tamamen siyah bir kare (or. 5/255) hedefe cikarilmaya calisilirsa
gama sinirsiz buyur ve sonuc gurultuden ibaret gri bir yuzey olur. Boyle bir
kare zaten kurtarilamaz; duzeltme durur, kare oldugu gibi gecer ve olcum
kayda yazilir.
"""


def parlaklik(gorsel_ya_da_yol: Any) -> float:
    """Ortalama luma (0-255). Dosya yolu ya da acik bir PIL goruntusu alir."""
    if isinstance(gorsel_ya_da_yol, (str, Path)):
        with Image.open(gorsel_ya_da_yol) as im:
            gri = im.convert("L").resize((64, 96))
            return float(np.asarray(gri, dtype=float).mean())
    gri = gorsel_ya_da_yol.convert("L").resize((64, 96))
    return float(np.asarray(gri, dtype=float).mean())


def _gama_uygula(gorsel: Any, gama: float) -> Any:
    """Gama egrisi — normalize edilmis degerler uzerinde, bu yuzden KIRPMA YOK.

    cikis = giris^(1/gama) ve giris 0-1 araliginda oldugu icin cikis da
    0-1'de kalir; hicbir piksel 255'i asip beyaza yapismaz. Parlatmanin
    "yanik" degil "acilmis" gorunmesinin sebebi bu.
    """
    tablo = [round(255.0 * ((i / 255.0) ** (1.0 / gama))) for i in range(256)]
    return gorsel.point(tablo * len(gorsel.getbands()))


def karanligi_ac(gorsel: Any) -> tuple[Any, float | None]:
    """Kare tabanin altindaysa hedefe kadar acar.

    Doner: (gorsel, uygulanan_gama). Kare zaten yeterince aydinlikse gorsel
    DEGISMEDEN ve gama `None` olarak doner — yani duzeltme sessizce her kareye
    dokunmuyor, yalnizca olcum onu isaret ettiginde devreye giriyor.

    ⚠️ Gama analitik olarak hesaplanmiyor, ARANIYOR: ortalamanin gamasi ile
    gamanin ortalamasi ayni sey degil (Jensen), yani kapali formul hedefi
    isabet ettirmez. Ikili arama olcup dogruluyor, 12 adim 0,001 hassasiyet
    veriyor ve hepsi bellekte — maliyeti yok.
    """
    mevcut = parlaklik(gorsel)
    if mevcut >= PARLAKLIK_TABANI:
        return gorsel, None

    alt, ust = 1.0, AZAMI_GAMA
    en_iyi = None
    for _ in range(12):
        orta = (alt + ust) / 2
        aday = _gama_uygula(gorsel, orta)
        if parlaklik(aday) < PARLAKLIK_HEDEFI:
            alt = orta
        else:
            ust = orta
            en_iyi = aday

    # Hedefe hic ulasilamadiysa (neredeyse siyah kare) elimizden gelenin en
    # iyisi azami gamadir; yine de tabanin altinda kalabilir ve kalmasi dogru —
    # uydurma bir parlaklik, karanlik bir kareden daha yaniltici olurdu.
    if en_iyi is None:
        en_iyi = _gama_uygula(gorsel, AZAMI_GAMA)
        return en_iyi, AZAMI_GAMA
    return en_iyi, round(ust, 3)


def parmak_izi(yol: Path) -> Any:
    """Algisal parmak izi — 16x16 gri kare, ortalamaya gore esiklenmis.

    Renkten bagimsiz oldugu icin ayni gorselin renklendirilmis kopyasini
    yakalar; olculdu (2026-08-09) tam da bu oldu.
    """
    with Image.open(yol) as im:
        gri = im.convert("L").resize((16, 16))
    dizi = np.asarray(gri, dtype=float)
    return dizi > dizi.mean()


def benzerlik(a: Any, b: Any) -> float:
    """Iki parmak izinin ortusme orani (0-1)."""
    return float(np.mean(a == b))


def ton_yayilimi(dosyalar: list[Path]) -> float:
    """Kareler arasi renk dagilimi: 0 = hepsi tek ton, 1 = tam dagilmis.

    ⚠️ Ton DAIRESEL bir buyukluk (0° ile 359° komsu), bu yuzden duz ortalama
    ya da standart sapma yaniltir. Dairesel ortalama vektorunun uzunlugu
    kullaniliyor; pikseller doygunlukla agirliklandiriliyor ki gri alanlar
    rastgele tonlariyla olcumu bulandirmasin.

    Olculdu (2026-08-09): tek renge kilitli Mohenjo-Daro kosumu 0,007;
    isik donusumu eklendikten sonra ayni sahneler 0,433.
    """
    vektorler = []
    for yol in dosyalar:
        if yol is None or not Path(yol).exists():
            continue
        try:
            with Image.open(yol) as im:
                kucuk = im.convert("HSV").resize((64, 96))
        except OSError:
            continue
        dizi = np.asarray(kucuk, dtype=float)
        aci = dizi[..., 0] / 255.0 * 2 * np.pi
        doygunluk = dizi[..., 1] / 255.0
        vektorler.append(
            (
                float(np.sum(np.cos(aci) * doygunluk)),
                float(np.sum(np.sin(aci) * doygunluk)),
            )
        )

    if len(vektorler) < 2:
        return 0.0
    acilar = [np.arctan2(y, x) for x, y in vektorler]
    return round(
        1.0 - float(np.hypot(np.mean(np.cos(acilar)), np.mean(np.sin(acilar)))), 3
    )
