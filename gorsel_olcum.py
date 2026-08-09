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
