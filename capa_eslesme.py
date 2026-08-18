"""Gorsel capasinin adayla eslesip eslesmedigi — UC KAYNAK ICIN ORTAK.

⚠️ NEDEN AYRI MODUL: `wikimedia_materials`, `met_materials` ve
`europeana_materials`'in ucunde de ayni capa kapisi vardi ve ucu de kendi
`_terms` kopyasini tasiyordu. Kusur duzeltilince uc yerde birden
duzeltilmesi gerekiyordu. Modul notr tutuldu cunku `wikimedia_materials`
digerlerini import ediyor; mantik oraya konsa dairesel import olurdu
(`test_dairesel_import_yok` bunu zaten kilitliyor).

Cozdugu kusur (olculdu 2026-08-13, Murad III kosumu): kapi 4 harften kisa
kelimeleri atiyordu, yani SIRA SAYISI sessizce dusuyordu:

    "Murad III"  -> {"murad"}
    "Mehmed II"  -> {"mehmed"}
    "Louis XIV"  -> {"louis"}

Sonucu somut: `File:Nadia Murad Nobel Peace Prize 2018.jpg` "Murad III"
capasini GECIYORDU. Hakem uc ayri koşumda yakaladi — Nadia Murad, Murad V
ve Fatih'in profili "Murad III" videosuna girdi.

Kanal icin yapisal bir kusur: kuyruk sira sayili hukumdar adlariyla dolu
(Mehmed II/III, Selim I/II, Murad III, Mahmud II).
"""

from __future__ import annotations

import re

def _roma(sayi: int) -> str:
    basamaklar = ((10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"))
    sonuc = ""
    for deger, harf in basamaklar:
        while sayi >= deger:
            sonuc += harf
            sayi -= deger
    return sonuc


SIRA_SAYILARI = frozenset(_roma(n) for n in range(1, 26))
"""I-XXV. Hukumdar sira sayilari bu araligi asmiyor (en yuksegi XXIII).

⚠️ Genel bir roma-rakami DUZENLI IFADESI kullanilmadi bilerek: "mix"
(M-I-X = 1009) gecerli bir roma rakami ama ayni zamanda gercek bir
Ingilizce kelime, ve capa metni modelden serbest geliyor. Acik liste hem
yanlis eslesmiyor hem okunur. Aralikta tek harfli "i", "v", "x" var;
bunlar zaten capada ancak sira sayisi olarak gecer."""


def kelime_terimleri(deger: str, *, durak_kelimeler: frozenset[str] | set[str] = frozenset()) -> set[str]:
    """Dort harf ve uzunu anlamli kelimeler. Sira sayilari BURADA DEGIL."""
    return {
        kelime
        for kelime in re.findall(r"[a-z0-9]+", (deger or "").lower())
        if len(kelime) >= 4 and kelime not in durak_kelimeler
    }


def sirali_terimler(
    deger: str, *, durak_kelimeler: frozenset[str] | set[str] = frozenset()
) -> list[str]:
    """`kelime_terimleri`nin SIRALI hali — kume degil LISTE.

    Bitisiklik sira ister; kume onu yapisal olarak veremez. Ayni esik ve ayni
    durak listesi kullaniliyor ki iki kapi ayni seyi olcsun.
    """
    return [
        kelime
        for kelime in re.findall(r"[a-z0-9]+", (deger or "").lower())
        if len(kelime) >= 4 and kelime not in durak_kelimeler
    ]


def bitisik_geciyor(
    kanit: str,
    terimler: list[str],
    *,
    durak_kelimeler: frozenset[str] | set[str] = frozenset(),
) -> bool:
    """Capanin anlamli kelimeleri kanitta BITISIK bir obek olarak geciyor mu.

    ⚠️ COZDUGU KUSUR — olculdu (2026-08-18, "Operation Storm" kosumu). Capa
    kapisi kelimeleri SIRASIZ ve BITISIKSIZ ariyordu, yani capanin kelimeleri
    araya baska kelimeler girse de bulunuyordu:

        capa "Operation Storm"  ->  {"operation", "storm"}
        dosya "Operation DESERT Storm"  ->  ikisini de iceriyor, GECIYOR

    Hakem sonucu yakaladi: videonun 3., 4. ve 5. sahnesine Kuveyt'te yanan
    petrol kuyulari, USAF ucaklari ve bir cikartma plaji girdi — 1991 Korfez
    Savasi, oysa konu 1995 Hirvatistan'i. Kaynak skoru 50 / 0 / 53 (kapi 70)
    ve bir uretim slotu yandi.

    Bu, deponun daha once uc kez olctugu sinifin aynisi (`Nadia Murad` /
    `Murad III`, adas kasaba `Herculaneum, Missouri`, `Getty Villa`): kapi
    ADI olcuyor, GORUNTUYU degil. Bitisiklik ADI daha dogru olcer — ayri bir
    ozel ad, capanin kelimelerini tasisa bile onlari bitisik tasimaz.

    ⚠️ ARADAKI KISA KELIMELER MASUM: "Republic of Serbian Krajina" gecerli
    bir capa ve "of" iki harf. Kanit da capa da AYNI suzgecten geciriliyor
    (`sirali_terimler`), yani "of" iki tarafta da dusuyor ve obek bitisik
    kaliyor. Kural, capa metninin kendisini elemek zorunda kalirsa yanlis
    kuraldir.

    ⚠️ BU KURALIN KAPATMADIGI SINIF — bilerek acik birakildi. Capa obegini
    BOZMADAN uzatan adaslar geciyor: "Great Sphinx" capasi Louvre'daki
    "Great Sphinx of Tanis"i geciriyor (00:05 koşumunun menusunde uc dosya).
    Kapatilamaz, cunku ayni bicim MESRU dosyalarin cogunda var: "Operation
    Storm 1995 map", "Cutty Sark in full sails". Son ek uzantisini reddeden
    bir kural arzi kurutur — ve arz olcumu bu turda zaten yapildi. Bu sinifin
    dogru bekcisi GORU kapisi; ad kapisi goruntuyu goremez.

    ⚠️ ON EK ESLESMESI, TAM ESITLIK DEGIL: eski kapi alt dize ariyordu ve bu
    bilincliydi — cogul/tamlama eklerini tasiyordu ("pyramid" -> "pyramids").
    On ek o kazanci korur, ama "storm" ile "brainstorm"u ayirir; alt dize
    ayirmiyordu.
    """
    if not terimler:
        return True
    akis = sirali_terimler(kanit, durak_kelimeler=durak_kelimeler)
    n = len(terimler)
    return any(
        all(akis[i + j].startswith(terimler[j]) for j in range(n))
        for i in range(len(akis) - n + 1)
    )


def sira_sayilari(deger: str) -> set[str]:
    """Capadaki roma rakamlari — "Murad III" -> {"iii"}.

    Ayri donuyor cunku eslesmeleri farkli: kelimeler alt dize olarak
    aranabilir ama rakamlar TAM SOZCUK olmali (bkz. `capa_uyuyor`).
    """
    return {
        kelime
        for kelime in re.findall(r"[a-z]+", (deger or "").lower())
        if kelime in SIRA_SAYILARI
    }


def sira_sayisi_uyuyor(kanit_sozcukleri: set[str], rakamlar: set[str]) -> bool:
    """Sira sayilari TAM SOZCUK olarak kanitta var mi.

    Kanitini kelime kumesi olarak tutan cagiranlar (Met) icin ayri giris;
    duz metinle calisanlar `capa_uyuyor`u kullanir.
    """
    return not rakamlar or rakamlar <= kanit_sozcukleri


def capa_uyuyor(kanit: str, *, kelimeler: set[str], rakamlar: set[str]) -> bool:
    """Kanit metni capanin BUTUN parcalarini tasiyor mu.

    ⚠️ Rakamlar TAM SOZCUK eslesiyor, kelimeler alt dize. Fark onemli:
    alt dize kullanilsaydi "iii" kanittaki "xiii" ve "viii" icinde de
    bulunurdu, yani "Louis III" capasi "Louis XIII" gorselini gecirirdi —
    duzeltmeye calistigimiz kusurun aynisi, bir tik incesi.
    """
    kanit = kanit.lower()
    if not all(kelime in kanit for kelime in kelimeler):
        return False
    if not rakamlar:
        return True
    kanit_sozcukleri = set(re.findall(r"[a-z]+", kanit))
    return rakamlar <= kanit_sozcukleri
