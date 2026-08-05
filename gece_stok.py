"""Gece boyunca stok video uretir — saatte bir, tavana kadar.

Neden ayri bir surucu: `youtube_automation.py` bilerek TEK dongu kosuyor ve
saat bazli `completed_slots` ayni saatte ikinci yayini engelliyor. Arka arkaya
cagirmak "skipped" doner. Bu betik dogal hizi kabul edip saat basina bir video
uretir; iki sert sinir da ayni sayiya cikiyor:

    slot mekanizmasi : saatte 1 video
    YouTube kotasi   : videos.insert 1600 birim, gunluk 10.000 -> 6 yukleme

⚠️ Para harciyor. Her dongu icerik plani (LLM), en fazla 3 deneme x gorsel
inceleme ve gerekirse gpt-image-1 gorselleri demek. Bu yuzden ucu de zorunlu:

- `--tavan` toplam video sayisini kilitler (varsayilan 6, kotanin tavani)
- ust uste `--pes-pese-hata` kadar basarisizlikta durur — bozuk bir hat butun
  geceyi yakmasin diye
- her sey `private` gider; stok gozden gecirilmeden yayina cikmaz

Kimse basinda degilken kosuyor: her dongu tek satirla gunluge yazilir, ozet
sonda basilir.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KOK = Path(__file__).resolve().parent
GUNLUK = KOK / "storage" / "youtube_automation" / "gece-stok.jsonl"
SAAT_DILIMI = "Europe/Istanbul"


def _simdi() -> datetime:
    return datetime.now(ZoneInfo(SAAT_DILIMI))


def sonraki_saat_basi(an: datetime) -> datetime:
    """Bir sonraki tam saat — slot degismeden yeni dongu anlamsiz."""
    return (an + timedelta(hours=1)).replace(minute=0, second=5, microsecond=0)


def yaz(kayit: dict) -> None:
    GUNLUK.parent.mkdir(parents=True, exist_ok=True)
    with GUNLUK.open("a", encoding="utf-8") as dosya:
        dosya.write(json.dumps(kayit, ensure_ascii=False) + "\n")


def bir_dongu(gizlilik: str) -> dict:
    """Tek bir uretim dongusu kosar ve sonucunu dondurur."""
    surec = subprocess.run(
        [sys.executable, "-u", "youtube_automation.py", "--privacy", gizlilik],
        cwd=KOK,
        capture_output=True,
        text=True,
    )
    # Hat sonucu JSON olarak basiyor; cikti sonundaki nesneyi ayikla.
    sonuc: dict = {}
    metin = surec.stdout.strip()
    if "{" in metin:
        try:
            sonuc = json.loads(metin[metin.rindex("\n{") + 1 :] if "\n{" in metin else metin[metin.index("{") :])
        except (ValueError, json.JSONDecodeError):
            sonuc = {}
    sonuc.setdefault("status", "unknown")
    sonuc["cikis_kodu"] = surec.returncode
    if not sonuc.get("url") and surec.returncode not in (0, 2):
        sonuc["stderr_kuyruk"] = surec.stderr.strip()[-800:]
    return sonuc


def kos(tavan: int, pes_pese_hata: int, gizlilik: str) -> int:
    uretilen = 0
    ard_arda = 0
    dongu = 0
    while uretilen < tavan:
        dongu += 1
        basladi = _simdi()
        print(f"[{basladi:%H:%M:%S}] dongu {dongu} basliyor "
              f"(uretilen {uretilen}/{tavan})", flush=True)

        sonuc = bir_dongu(gizlilik)
        durum = sonuc.get("status")
        kayit = {
            "an": _simdi().isoformat(),
            "dongu": dongu,
            "durum": durum,
            "konu": sonuc.get("topic", ""),
            "url": sonuc.get("url", ""),
            "gorsel_skor": (sonuc.get("quality") or {}).get("visual_alignment_score"),
            "cikis_kodu": sonuc.get("cikis_kodu"),
        }
        yaz(kayit)

        if durum == "published":
            uretilen += 1
            ard_arda = 0
            print(f"  ✅ YAYIN {sonuc.get('url')} · skor="
                  f"{kayit['gorsel_skor']} · {kayit['konu'][:50]}", flush=True)
        elif durum == "skipped":
            # Slot doluysa bu bir hata degil; sadece saat degismesi bekleniyor.
            print("  ⏭️  slot dolu, sonraki saate geciliyor", flush=True)
        else:
            ard_arda += 1
            print(f"  ❌ {durum} · skor={kayit['gorsel_skor']} "
                  f"· ust uste {ard_arda}", flush=True)
            if ard_arda >= pes_pese_hata:
                print(f"\n⛔ ust uste {ard_arda} basarisizlik — duruluyor. "
                      "Bozuk bir hat butun geceyi yakmasin.", flush=True)
                return uretilen

        if uretilen >= tavan:
            break
        uyanma = sonraki_saat_basi(_simdi())
        bekleme = (uyanma - _simdi()).total_seconds()
        print(f"  ⏳ sonraki slot {uyanma:%H:%M} "
              f"({bekleme / 60:.0f} dk)", flush=True)
        time.sleep(max(bekleme, 0))
    return uretilen


def main() -> None:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--tavan", type=int, default=6,
                             help="uretilecek en fazla video (varsayilan 6 = kota tavani)")
    ayristirici.add_argument("--pes-pese-hata", type=int, default=3,
                             help="ust uste bu kadar basarisizlikta dur")
    ayristirici.add_argument("--gizlilik", default="private",
                             choices=["private", "unlisted", "public"])
    secim = ayristirici.parse_args()

    baslangic = _simdi()
    print(f"gece stok basladi {baslangic:%Y-%m-%d %H:%M} · tavan={secim.tavan} "
          f"· gizlilik={secim.gizlilik}", flush=True)
    uretilen = kos(secim.tavan, secim.pes_pese_hata, secim.gizlilik)
    print(f"\n=== ozet ===\nuretilen video: {uretilen}/{secim.tavan}"
          f"\nsure: {_simdi() - baslangic}"
          f"\ngunluk: {GUNLUK}", flush=True)


if __name__ == "__main__":
    main()
