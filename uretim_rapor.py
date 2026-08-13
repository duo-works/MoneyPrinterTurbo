"""Uretim hattinin olculebilir hali — insan icin metin, arayuz icin JSON.

⚠️ NEDEN GEREKLI: "standarda sabitledik" denebilmesi icin once olculebilmesi
gerekiyor. 2026-08-13'te kayitlar bu soruyu cevaplayamiyordu — 120 red
kaydinin hicbiri zaman dilimi tasimiyordu, iki asamanin skorlari
ayrismiyordu ve hangi kipin (huni / yedek) urettigi hic yazilmiyordu.

⚠️ NEDEN `ytoto`DA DEGIL, BURADA: kayit MPT'nin `storage/`sinde yasiyor ve
kopru bilerek TEK YONLU (ADR-0013) — video hatti `ytoto`yu tuketiyor,
tersi degil. Raporu huni deposuna tasimak o ayrimi bozardi ve iki repo
birbirinin dosya yoluna baglanirdi.

Kullanim:
    python uretim_rapor.py            # insan icin ozet
    python uretim_rapor.py --json     # arayuz icin
    python uretim_rapor.py --son 20   # yalnizca son 20 kosum
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "storage" / "youtube_automation" / "state.json"


def _durum() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"published": [], "rejected": []}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def _skor(kayit: dict[str, Any]) -> int | None:
    """Yayin kaydinda skor `quality` altinda, red kaydinda ust duzeyde."""
    kalite = kayit.get("quality") or {}
    for deger in (kalite.get("visual_alignment_score"), kayit.get("visual_alignment_score")):
        if isinstance(deger, int):
            return deger
    return None


def rapor(*, son: int | None = None) -> dict[str, Any]:
    durum = _durum()
    yayinlanan = list(durum.get("published") or [])
    reddedilen = list(durum.get("rejected") or [])
    if son:
        yayinlanan = yayinlanan[-son:]
        reddedilen = reddedilen[-son:]

    toplam = len(yayinlanan) + len(reddedilen)
    skorlar = [s for s in (_skor(k) for k in yayinlanan) if s is not None]
    red_skorlari = [s for s in (_skor(k) for k in reddedilen) if s is not None]

    agir = Counter()
    for kayit in reddedilen:
        for kusur in kayit.get("agir_kusurlar") or []:
            # "kare 3: donem uyusmuyor" -> "donem uyusmuyor"
            agir[str(kusur).split(":", 1)[-1].strip()] += 1

    return {
        "toplam_kosum": toplam,
        "yayinlanan": len(yayinlanan),
        "reddedilen": len(reddedilen),
        "basari_orani": round(len(yayinlanan) / toplam, 3) if toplam else 0.0,
        "asama_kirilimi": dict(Counter(k.get("stage", "video") for k in reddedilen)),
        "kaynak_kirilimi": dict(Counter(k.get("kaynak", "bilinmiyor") for k in yayinlanan)),
        "yayin_skoru": {
            "ortanca": statistics.median(skorlar) if skorlar else None,
            "en_dusuk": min(skorlar) if skorlar else None,
            "en_yuksek": max(skorlar) if skorlar else None,
        },
        "red_skoru_ortanca": statistics.median(red_skorlari) if red_skorlari else None,
        "en_sik_agir_kusur": agir.most_common(5),
        "son_yayinlar": [
            {
                "slot": k.get("slot"),
                "kaynak": k.get("kaynak"),
                "capa": k.get("visual_anchor"),
                "skor": _skor(k),
                "kusur_sayisi": len((k.get("quality") or {}).get("issues") or []),
                "url": k.get("url"),
            }
            for k in yayinlanan[-5:]
        ],
    }


def _yazdir(veri: dict[str, Any]) -> None:
    print(f"kosum      : {veri['toplam_kosum']}  ({veri['yayinlanan']} yayin, {veri['reddedilen']} red)")
    print(f"basari     : %{veri['basari_orani'] * 100:.0f}")
    skor = veri["yayin_skoru"]
    if skor["ortanca"] is not None:
        print(f"yayin skoru: ortanca {skor['ortanca']}  ({skor['en_dusuk']}-{skor['en_yuksek']})")
    if veri["red_skoru_ortanca"] is not None:
        print(f"red skoru  : ortanca {veri['red_skoru_ortanca']}")
    if veri["asama_kirilimi"]:
        print(f"red asamasi: {veri['asama_kirilimi']}")
    if veri["kaynak_kirilimi"]:
        print(f"kaynak     : {veri['kaynak_kirilimi']}")
    if veri["en_sik_agir_kusur"]:
        print("agir kusur :")
        for ad, adet in veri["en_sik_agir_kusur"]:
            print(f"   {adet:>3}  {ad}")
    if veri["son_yayinlar"]:
        print("son yayinlar:")
        for y in veri["son_yayinlar"]:
            print(
                f"   {str(y['slot']):16} {str(y['kaynak'] or '?'):6} "
                f"skor={str(y['skor']):>4} kusur={y['kusur_sayisi']:>2}  {str(y['capa'])[:28]}"
            )


def main() -> None:
    ayristirici = argparse.ArgumentParser(description="Uretim hatti raporu")
    ayristirici.add_argument("--json", action="store_true", help="Arayuz icin JSON bas")
    ayristirici.add_argument("--son", type=int, help="Yalnizca son N kosum")
    args = ayristirici.parse_args()

    veri = rapor(son=args.son)
    if args.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        _yazdir(veri)


if __name__ == "__main__":
    main()
