"""Bir konunun KREDISIZ URETILEBILIR olup olmadigini uretimin KENDI olcutleriyle olcer.

Uc kapi birden — ucu de gecmeyen gorsel ise yaramaz:
  1. kadraj  → wm.dikey_karede_yeterli (9:16'da kullanilabilir mi)
  2. lisans  → wm.kullanilabilir_lisans (PD/CC0 ya da CC BY; CC BY-SA RED)
  3. ozne    → dosya adinda oznenin ayirt edici adi geciyor mu

Neden bu betik var: iki koşum iki AYRI sebeple dustu ve ikisini de onceki
olcumlerim kaciriyordu.
  · Augustus  → 45 gorsel kadraja uyuyordu ama cogu ozneyi gostermiyordu (hakem 43)
  · Harald Rose → 8/8 ozneyi gosteriyordu ama lisanslari uygun degildi (skor 0)
Uretimin fonksiyonlari dogrudan cagriliyor ki olcut sapmasin. Kredi harcamaz.
"""

import re
import sys
import unicodedata

sys.path.insert(0, "/Users/mirzasaribiyik/Projects/MoneyPrinterTurbo")
import wikimedia_materials as wm  # noqa: E402

SAHNE = 6


def sadelestir(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower()


ATLA = {"count", "elector", "baron", "first", "archduke", "sultanzade", "batalla", "second"}


def ayirt_edici(baslik: str) -> str:
    parcalar = [p.strip(",.") for p in sadelestir(baslik).split()]
    parcalar = [p for p in parcalar if len(p) > 3 and p not in ATLA]
    return parcalar[-1] if parcalar else sadelestir(baslik)


def olc(konu: str) -> dict:
    kategori = wm.commons_kategorisi(konu)
    if not kategori:
        return {"konu": konu, "kategori": None, "uretilebilir": 0}

    anahtar = ayirt_edici(konu)
    sayfalar = wm.kategori_gorselleri(kategori, limit=100)
    sayac = {"ham": len(sayfalar), "kadraj": 0, "lisans": 0, "uretilebilir": 0}
    ornekler = []

    for s in sayfalar:
        b = (s.get("imageinfo") or [{}])[0]
        if not (b.get("mime") or "").startswith("image/"):
            continue
        g, y = b.get("width") or 0, b.get("height") or 0
        if not (g and y and wm.dikey_karede_yeterli(g, y)):
            continue
        sayac["kadraj"] += 1

        # ⚠️ _metadata_value `extmetadata`yi ARADIGI icin imageinfo[0]'i ister,
        # sayfa sozlugunu degil. Sayfa gecilirse her lisans bos okunur ve
        # her konu "lisans=0" gorunur (once oyle yaptim, Tycho Brahe'nin PD
        # portreleri bile elenmis gibi cikti).
        lisans = wm._metadata_value(b, "LicenseShortName") or ""
        if not wm.kullanilabilir_lisans(lisans):
            continue
        sayac["lisans"] += 1

        if re.search(anahtar, sadelestir(s.get("title") or "")):
            sayac["uretilebilir"] += 1
            if len(ornekler) < 3:
                ornekler.append(f"{(s.get('title') or '')[:52]} [{lisans[:18]}]")

    return {"konu": konu, "kategori": kategori, "anahtar": anahtar, **sayac, "ornek": ornekler}


if __name__ == "__main__":
    for konu in sys.argv[1:]:
        r = olc(konu)
        if not r.get("kategori"):
            print(f"🔴 {konu:34} kategori YOK — kredisiz imkansiz", flush=True)
            continue
        u = r["uretilebilir"]
        isaret = "🟢" if u >= SAHNE else ("🟡" if u >= 3 else "🔴")
        print(
            f"{isaret} {konu[:34]:36} ham={r['ham']:3} kadraj={r['kadraj']:3} "
            f"+lisans={r['lisans']:3} +ozne={u:3}   [{r['anahtar']}]",
            flush=True,
        )
        for o in r["ornek"]:
            print(f"      {o}", flush=True)
