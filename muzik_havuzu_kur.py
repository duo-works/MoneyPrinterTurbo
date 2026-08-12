"""Arka plan muzigi havuzunu KUNYEDEN yeniden kurar.

NEDEN VAR
---------
Havuz `storage/bgm` altinda duruyor ve `storage/` git tarafindan yok
sayiliyor — yani temiz bir kopyada havuz BOS. `muzik_sec()` bos havuzda
hata vermez, bos dize doner ve video SESSIZCE MUZIKSIZ cikar. Bu betik o
bosluğu kapatiyor: repo'da duran kunyeden havuzu birebir geri kurar.

NEDEN YENIDEN ARAMA DEGIL
-------------------------
Havuz arama ile kurulmuyor bilerek. Arama her kosumda BASKA parcalar
getirir; havuzun dokusu ve lisans denetimi kaybolur. Onun yerine kunyede
yazili kaynaktan AYNI parca indiriliyor ve dosya BAYT BOYUYLA eslenerek
dogru kayit oldugu dogrulaniyor (Internet Archive ogeleri cok dosya
icerebiliyor, ad tek basina yetmez).

Havuzun kendisi 2026-08-12'de kuruldu: besteci adiyla arandi, donen
kayitlarin lisansi tek tek dogrulandi, tarih anlatimina uymayan 10 parca
elendi (video oyunu muzigi, sesli kitap, modern vokal parcalar).

Kullanim:
    python3 muzik_havuzu_kur.py           # eksikleri indir
    python3 muzik_havuzu_kur.py --denetle # indirme yapma, yalnizca rapor
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

KOK = Path(__file__).resolve().parent
KUNYE = KOK / "resource" / "muzik_kunye.json"
HAVUZ = KOK / "storage" / "bgm"
KULLANICI_ARACISI = (
    "duo-works-muzik-havuzu/1.0 (+https://github.com/duo-works/MoneyPrinterTurbo)"
)

# wikimedia_materials.py ile ayni politika: pay-benzer (SA) videonun
# TAMAMINI baglar, bu yuzden disarida.
IZINLI_IZLER = ("publicdomain", "/zero/", "/by/")
YASAKLI_IZLER = ("-sa", "-nc", "-nd")


def lisans_uygun(url: str) -> bool:
    u = (url or "").lower()
    if any(k in u for k in YASAKLI_IZLER):
        return False
    return any(k in u for k in IZINLI_IZLER)


def oge_kimligi(kaynak: str) -> str:
    """https://archive.org/details/<kimlik> → <kimlik>"""
    return kaynak.rstrip("/").rsplit("/", 1)[-1]


def indir(kimlik: str, beklenen_bayt: int) -> tuple[bytes, str] | None:
    """Ogenin dosyalari icinde BAYT BOYU eslesen mp3'u indirir."""
    time.sleep(0.5)
    try:
        veri = requests.get(
            f"https://archive.org/metadata/{kimlik}",
            headers={"User-Agent": KULLANICI_ARACISI},
            timeout=45,
        ).json()
    except (requests.RequestException, ValueError):
        return None

    eslesen = [
        d
        for d in veri.get("files", [])
        if d.get("name", "").lower().endswith(".mp3")
        and int(d.get("size", 0) or 0) == beklenen_bayt
    ]
    if not eslesen:
        return None

    time.sleep(0.3)
    try:
        yanit = requests.get(
            f"https://archive.org/download/{kimlik}/{eslesen[0]['name']}",
            headers={"User-Agent": KULLANICI_ARACISI},
            timeout=240,
        )
        yanit.raise_for_status()
    except requests.RequestException:
        return None
    return yanit.content, eslesen[0]["name"]


def main() -> int:
    ayrıştırıcı = argparse.ArgumentParser(description="Muzik havuzunu kunyeden kur")
    ayrıştırıcı.add_argument(
        "--denetle", action="store_true", help="indirme yapma, durumu bildir"
    )
    secenekler = ayrıştırıcı.parse_args()

    if not KUNYE.exists():
        print(f"🔴 künye yok: {KUNYE}")
        return 1

    kunye: dict[str, dict] = json.loads(KUNYE.read_text(encoding="utf-8"))
    HAVUZ.mkdir(parents=True, exist_ok=True)

    eksik: list[str] = []
    for ad, bilgi in sorted(kunye.items()):
        yol = HAVUZ / ad
        if yol.exists() and yol.stat().st_size == int(bilgi.get("bayt") or 0):
            continue
        eksik.append(ad)

    print(f"künye: {len(kunye)} parça · havuzda tam: {len(kunye) - len(eksik)} · eksik: {len(eksik)}")

    lisanssiz = [a for a, b in kunye.items() if not lisans_uygun(b.get("lisans") or "")]
    if lisanssiz:
        print(f"🔴 LİSANSI GEÇMEYEN {len(lisanssiz)} parça künyede: {lisanssiz}")
        return 1

    if secenekler.denetle:
        for ad in eksik:
            print(f"  eksik: {ad}")
        return 0

    kurulan = 0
    for ad in eksik:
        bilgi = kunye[ad]
        sonuc = indir(oge_kimligi(bilgi["kaynak"]), int(bilgi.get("bayt") or 0))
        if sonuc is None:
            print(f"  🔴 {ad[:46]:48} kaynaktan alınamadı — {bilgi['kaynak']}")
            continue
        ham, kaynak_adi = sonuc
        (HAVUZ / ad).write_bytes(ham)
        kurulan += 1
        print(f"  ✅ {ad[:46]:48} {len(ham) // 1024:6} KB  ({kaynak_adi[:28]})")

    toplam = len([p for p in HAVUZ.iterdir() if p.suffix.lower() == ".mp3"])
    print(f"\n{kurulan} parça indirildi · havuzda toplam {toplam} parça")
    if toplam == 0:
        print("⚠️  HAVUZ BOŞ — üretim videoları sessizce müziksiz çıkar.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
