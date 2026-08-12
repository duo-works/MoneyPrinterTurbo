"""Rijksmuseum OAI-PMH hasatcisi — yerel, aranabilir bir gorsel indeksi kurar.

NEDEN HASAT, NEDEN INDEKS
-------------------------
OAI-PMH bir ARAMA degil HASAT protokolu: "Tycho Brahe" diye sorgulanamaz,
yalnizca set/tarih araligiyla toplu indirilir. Yani kaynaktan yararlanmanin
tek yolu bir kere hepsini cekip YERELDE aranabilir hale getirmek. Bir kez
kurulunca arama yerelde olur — hiz siniri yok, aglayan bir ucu beklemek yok.

OLCUM (2026-08-12, canli uctan):
  * completeListSize = 843.943 kayit, sayfa basi 50 → ~16.900 istek
  * gorsel IIIF ile geliyor (iiif.micr.io) — istenen olcek talep edilebiliyor
  * olculen boyutlar 4096x2843, 4096x3149, 2482x4096
  * anahtar GEREKMIYOR

LISANS KAPISI
-------------
Kaynak hem kamu mali hem TELIFLI kayit donduruyor
(rightsstatements.org/vocab/InC). Bu yuzden filtre BEYAZ LISTE: yalnizca
kamu mali / CC0 / CC BY iceri alinir. CC BY-SA bilerek disarida — pay-benzer
sarti videonun TAMAMINI baglar. Bu, wikimedia_materials.py'deki
SAFE_LICENSE_MARKERS politikasiyla ayni; iki kaynagin kurali sapmasin.

ALAN COZUMLEME TUZAGI
---------------------
dc:creator / dc:subject / dc:type birer METIN DEGIL, rdf:resource URI'si:
    <dc:subject rdf:resource="https://id.rijksmuseum.nl/2212675" />
Etiketin kendisi ayni kaydin icindeki skos:Concept / edm:Agent
dugumlerinde prefLabel olarak duruyor. Yani cozumleme YERELDE yapilabiliyor,
ek istek gerekmiyor — ama yapilmazsa indeks bir URI yigini olur ve hicbir
sey aranamaz. Bulunabilirligi belirleyen alan bu.

Basliklar agirlikli olarak FELEMENKCE; bizim konularimiz Ingilizce. Bu
yuzden hem nl hem en etiketler saklaniyor ve arama ikisine birden bakiyor.

KESINTIYE DAYANIKLILIK
----------------------
Her sayfadan sonra resumptionToken veritabanina yaziliyor. Kosum yarida
kalirsa ayni komut kaldigi yerden devam eder — 17 bin isteklik bir isi
bastan baslatmak kabul edilemez.

Kullanim:
    python3 rijks_hasat.py            # basla / kaldigin yerden devam et
    python3 rijks_hasat.py --durum    # ilerlemeyi goster, hasat etme
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

KOK = Path(__file__).resolve().parent
VERI_DIZINI = KOK / "storage" / "rijks"
VERITABANI = VERI_DIZINI / "rijks.sqlite3"
TABAN_UC = "https://data.rijksmuseum.nl/oai"

# DW-125 dersi: kimliksiz User-Agent kurum uclarinda engellenmeye acik.
KULLANICI_ARACISI = (
    "duo-works-arsiv/1.0 (+https://github.com/duo-works/MoneyPrinterTurbo)"
)

OAI = "{http://www.openarchives.org/OAI/2.0/}"
ORE = "{http://www.openarchives.org/ore/terms/}"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
EDM = "{http://www.europeana.eu/schemas/edm/}"
DC = "{http://purl.org/dc/elements/1.1/}"
DCT = "{http://purl.org/dc/terms/}"
SKOS = "{http://www.w3.org/2004/02/skos/core#}"
XML_DIL = "{http://www.w3.org/XML/1998/namespace}lang"

# Beyaz liste — yalnizca bunlar. "InC degilse alalim" demiyoruz bilerek:
# kara liste yeni bir hak turu eklendiginde sessizce acilir, beyaz liste acilmaz.
IZINLI_HAK_IZLERI = (
    "creativecommons.org/publicdomain/mark",
    "creativecommons.org/publicdomain/zero",
    "creativecommons.org/licenses/by/",
)
YASAKLI_IZLER = ("-sa/", "-nc", "-nd", "rightsstatements.org")

# IIIF adresi "…/full/max/0/default.jpg" olarak geliyor; boyutu KULLANIM
# aninda secebilmek icin taban kismi saklaniyor.
IIIF_SONEKI = "/full/max/0/default.jpg"


def hak_uygun(hak: str) -> bool:
    h = (hak or "").lower()
    if not h or any(k in h for k in YASAKLI_IZLER):
        return False
    return any(k in h for k in IZINLI_HAK_IZLERI)


def veritabani_ac() -> sqlite3.Connection:
    VERI_DIZINI.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(VERITABANI)
    baglanti.executescript(
        """
        CREATE TABLE IF NOT EXISTS kayit (
            oai_id     TEXT PRIMARY KEY,
            baslik_nl  TEXT,
            baslik_en  TEXT,
            yaratici   TEXT,
            konular    TEXT,
            tur        TEXT,
            tarih      TEXT,
            iiif_taban TEXT NOT NULL,
            haklar     TEXT NOT NULL,
            damga      TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS arama USING fts5(
            oai_id UNINDEXED, metin
        );
        CREATE TABLE IF NOT EXISTS durum (
            anahtar TEXT PRIMARY KEY,
            deger   TEXT
        );
        """
    )
    baglanti.commit()
    return baglanti


def durum_oku(baglanti: sqlite3.Connection, anahtar: str) -> str | None:
    satir = baglanti.execute(
        "SELECT deger FROM durum WHERE anahtar = ?", (anahtar,)
    ).fetchone()
    return satir[0] if satir else None


def durum_yaz(baglanti: sqlite3.Connection, anahtar: str, deger: str) -> None:
    baglanti.execute(
        "INSERT INTO durum(anahtar, deger) VALUES(?, ?) "
        "ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger",
        (anahtar, deger),
    )


def _etiket_haritasi(rdf_dugumu: ET.Element) -> dict[str, dict[str, str]]:
    """rdf:about → {dil: etiket}. Kavram ve kisi adlari burada cozuluyor."""
    harita: dict[str, dict[str, str]] = {}
    for dugum in rdf_dugumu:
        uri = dugum.get(f"{RDF}about")
        if not uri:
            continue
        etiketler: dict[str, str] = {}
        for etiket in list(dugum.findall(f"{SKOS}prefLabel")) + list(
            dugum.findall(f"{SKOS}altLabel")
        ):
            dil = etiket.get(XML_DIL) or "?"
            if etiket.text and dil not in etiketler:
                etiketler[dil] = etiket.text.strip()
        if etiketler:
            harita[uri] = etiketler
    return harita


def _coz(
    dugum: ET.Element, etiket_adi: str, harita: dict[str, dict[str, str]]
) -> list[str]:
    """Bir alanin degerlerini metne cevirir: duz metinse kendisi, URI ise etiketi."""
    sonuc: list[str] = []
    for alan in dugum.findall(etiket_adi):
        kaynak = alan.get(f"{RDF}resource")
        if kaynak:
            etiketler = harita.get(kaynak) or {}
            # Ingilizce varsa oncelikli — konularimiz Ingilizce geliyor.
            for dil in ("en", "nl", "?"):
                if dil in etiketler:
                    sonuc.append(etiketler[dil])
                    break
            # Iki dil de varsa ikisini birden koy: arama her ikisini de bulsun.
            if "en" in etiketler and "nl" in etiketler:
                sonuc.append(etiketler["nl"])
        elif alan.text and alan.text.strip():
            sonuc.append(alan.text.strip())
    return sonuc


def _baslik(cho: ET.Element, dil: str) -> str:
    for alan in cho.findall(f"{DC}title"):
        if (alan.get(XML_DIL) or "") == dil and alan.text:
            return alan.text.strip()
    return ""


def kayit_cikar(kayit: ET.Element) -> dict | None:
    """Tek OAI kaydindan indeks satiri uretir; elenmesi gerekiyorsa None."""
    rdf_dugumu = kayit.find(f"{OAI}metadata/{RDF}RDF")
    if rdf_dugumu is None:
        return None

    toplama = rdf_dugumu.find(f"{ORE}Aggregation")
    if toplama is None:
        return None

    hak_dugumu = toplama.find(f"{EDM}rights")
    haklar = (hak_dugumu.get(f"{RDF}resource") if hak_dugumu is not None else "") or ""
    if not hak_uygun(haklar):
        return None

    gorsel_dugumu = toplama.find(f"{EDM}isShownBy")
    gorsel = (
        gorsel_dugumu.get(f"{RDF}resource") if gorsel_dugumu is not None else ""
    ) or ""
    if not gorsel:
        return None
    iiif_taban = gorsel[: -len(IIIF_SONEKI)] if gorsel.endswith(IIIF_SONEKI) else gorsel

    cho = rdf_dugumu.find(f"{EDM}ProvidedCHO")
    if cho is None:
        return None

    harita = _etiket_haritasi(rdf_dugumu)
    yaraticilar = _coz(cho, f"{DC}creator", harita)
    konular = _coz(cho, f"{DC}subject", harita)
    turler = _coz(cho, f"{DC}type", harita)
    tarihler = [a.text.strip() for a in cho.findall(f"{DCT}created") if a.text]

    kimlik = kayit.findtext(f"{OAI}header/{OAI}identifier") or ""
    if not kimlik:
        return None

    return {
        "oai_id": kimlik,
        "baslik_nl": _baslik(cho, "nl"),
        "baslik_en": _baslik(cho, "en"),
        "yaratici": " | ".join(dict.fromkeys(yaraticilar))[:400],
        "konular": " | ".join(dict.fromkeys(konular))[:800],
        "tur": " | ".join(dict.fromkeys(turler))[:300],
        "tarih": (tarihler[0] if tarihler else "")[:60],
        "iiif_taban": iiif_taban,
        "haklar": haklar,
        "damga": kayit.findtext(f"{OAI}header/{OAI}datestamp") or "",
    }


def kaydet(baglanti: sqlite3.Connection, satirlar: list[dict]) -> None:
    for s in satirlar:
        baglanti.execute(
            "INSERT INTO kayit(oai_id, baslik_nl, baslik_en, yaratici, konular, "
            "tur, tarih, iiif_taban, haklar, damga) "
            "VALUES(:oai_id, :baslik_nl, :baslik_en, :yaratici, :konular, :tur, "
            ":tarih, :iiif_taban, :haklar, :damga) "
            "ON CONFLICT(oai_id) DO UPDATE SET "
            "baslik_nl=excluded.baslik_nl, baslik_en=excluded.baslik_en, "
            "yaratici=excluded.yaratici, konular=excluded.konular, "
            "tur=excluded.tur, tarih=excluded.tarih, "
            "iiif_taban=excluded.iiif_taban, haklar=excluded.haklar, "
            "damga=excluded.damga",
            s,
        )
        # Yeniden kosumda FTS satiri ikizlenmesin.
        baglanti.execute("DELETE FROM arama WHERE oai_id = ?", (s["oai_id"],))
        metin = " ".join(
            p
            for p in (
                s["baslik_en"],
                s["baslik_nl"],
                s["yaratici"],
                s["konular"],
                s["tur"],
                s["tarih"],
            )
            if p
        )
        baglanti.execute(
            "INSERT INTO arama(oai_id, metin) VALUES(?, ?)", (s["oai_id"], metin)
        )


def sayfa_getir(parametreler: dict, deneme: int = 4) -> ET.Element | None:
    """Bir OAI sayfasi getirir; gecici hatalarda geri cekilerek yeniden dener."""
    for tur in range(deneme):
        try:
            yanit = requests.get(
                TABAN_UC,
                params=parametreler,
                headers={"User-Agent": KULLANICI_ARACISI},
                timeout=120,
            )
        except requests.RequestException as hata:
            print(f"  ! ag hatasi ({type(hata).__name__}), yeniden deneniyor")
            time.sleep(5 * (tur + 1))
            continue
        if yanit.status_code == 503:
            bekle = int(yanit.headers.get("Retry-After", "20") or 20)
            print(f"  ! 503, {bekle} sn bekleniyor")
            time.sleep(min(bekle, 120))
            continue
        if not yanit.ok:
            print(f"  ! HTTP {yanit.status_code}")
            time.sleep(5 * (tur + 1))
            continue
        try:
            return ET.fromstring(yanit.content)
        except ET.ParseError as hata:
            print(f"  ! XML cozulemedi: {hata}")
            time.sleep(5 * (tur + 1))
    return None


def hasat_et(azami_sayfa: int | None = None) -> int:
    baglanti = veritabani_ac()
    jeton = durum_oku(baglanti, "resumptionToken")
    sayfa = int(durum_oku(baglanti, "sayfa") or 0)
    toplam_gorulen = int(durum_oku(baglanti, "gorulen") or 0)
    basladi = time.time()

    if jeton:
        print(f"↻ kaldigi yerden: sayfa {sayfa}, gorulen {toplam_gorulen}")

    while True:
        if azami_sayfa is not None and sayfa >= azami_sayfa:
            print(f"⏹ ornek siniri ({azami_sayfa} sayfa) doldu")
            break

        parametreler = (
            {"verb": "ListRecords", "resumptionToken": jeton}
            if jeton
            else {"verb": "ListRecords", "metadataPrefix": "edm"}
        )
        kok = sayfa_getir(parametreler)
        if kok is None:
            print("🔴 sayfa alinamadi, duruluyor — komut tekrar calistirilinca devam eder")
            break

        hata = kok.find(f"{OAI}error")
        if hata is not None:
            print(f"⏹ OAI: {hata.get('code')} — {(hata.text or '').strip()[:80]}")
            durum_yaz(baglanti, "bitti", "evet")
            baglanti.commit()
            break

        kayitlar = kok.findall(f".//{OAI}record")
        secilenler = [c for c in (kayit_cikar(k) for k in kayitlar) if c]
        kaydet(baglanti, secilenler)

        sayfa += 1
        toplam_gorulen += len(kayitlar)
        jeton_dugumu = kok.find(f".//{OAI}resumptionToken")
        jeton = (jeton_dugumu.text or "").strip() if jeton_dugumu is not None else ""

        durum_yaz(baglanti, "sayfa", str(sayfa))
        durum_yaz(baglanti, "gorulen", str(toplam_gorulen))
        durum_yaz(baglanti, "resumptionToken", jeton)
        if jeton_dugumu is not None and jeton_dugumu.get("completeListSize"):
            durum_yaz(baglanti, "toplam", jeton_dugumu.get("completeListSize"))
        baglanti.commit()

        if sayfa % 20 == 0 or azami_sayfa is not None:
            tutulan = baglanti.execute("SELECT COUNT(*) FROM kayit").fetchone()[0]
            gecen = time.time() - basladi
            hiz = sayfa / gecen if gecen else 0
            print(
                f"  sayfa {sayfa:>6} · gorulen {toplam_gorulen:>7} · "
                f"indekste {tutulan:>7} · {hiz:.2f} sayfa/sn"
            )

        if not jeton:
            print("✅ hasat tamamlandi — jeton bitti")
            durum_yaz(baglanti, "bitti", "evet")
            baglanti.commit()
            break

        # Kurum ucu, nazik davran.
        time.sleep(0.3)

    tutulan = baglanti.execute("SELECT COUNT(*) FROM kayit").fetchone()[0]
    baglanti.commit()
    baglanti.close()
    return tutulan


def durum_goster() -> None:
    if not VERITABANI.exists():
        print("indeks henuz yok")
        return
    baglanti = veritabani_ac()
    tutulan = baglanti.execute("SELECT COUNT(*) FROM kayit").fetchone()[0]
    print(f"veritabani : {VERITABANI}")
    print(f"boyut      : {VERITABANI.stat().st_size / 1_048_576:.1f} MB")
    for anahtar in ("sayfa", "gorulen", "toplam", "bitti"):
        deger = durum_oku(baglanti, anahtar)
        if deger:
            print(f"{anahtar:11}: {deger}")
    print(f"indekste   : {tutulan} kayit (lisansi gecen)")
    gorulen = int(durum_oku(baglanti, "gorulen") or 0)
    if gorulen:
        print(f"tutma orani: %{100 * tutulan / gorulen:.1f}")
    baglanti.close()


if __name__ == "__main__":
    ayrıstırıcı = argparse.ArgumentParser(description="Rijksmuseum OAI-PMH hasatcisi")
    ayrıstırıcı.add_argument("--durum", action="store_true", help="ilerlemeyi goster")
    ayrıstırıcı.add_argument(
        "--ornek", type=int, default=None, help="yalnizca N sayfa hasat et"
    )
    secenekler = ayrıstırıcı.parse_args()

    if secenekler.durum:
        durum_goster()
        sys.exit(0)

    tutulan = hasat_et(azami_sayfa=secenekler.ornek)
    print(f"\nindekste toplam {tutulan} kayit · {VERITABANI}")
