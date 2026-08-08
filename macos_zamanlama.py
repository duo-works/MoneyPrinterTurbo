"""Gunluk uretimi macOS `launchd`'a kurar.

`youtube_schedule.py` ayni isi Windows'ta `schtasks.exe` ile yapiyor. Uretim
Mirza'nin Mac'inde kostugu icin macOS karsiligi gerekiyordu.

    python macos_zamanlama.py kur          # gunde 4 uretim, GIZLI (private)
    python macos_zamanlama.py kur --yayin  # gizlilik public
    python macos_zamanlama.py durum
    python macos_zamanlama.py kaldir

⚠️ VARSAYILAN GIZLILIK `private`. Yayin acik bir karar olmali:

  * Bu kanal, "bot aktivitesi" gerekcesiyle kapatilan bir kanalin yerine
    acildi. Otomatik yayin, tam da o kanali kaybettiren desene benziyor.
  * Yon asimetrik: gec yayinlanan videoyu yayinlamak bir tik, erken
    yayinlanani geri almak izlenme ve oneri sinyali kaybi.
  * Trend hunisi su an KURU (Anthropic kredisi bitti, `konu siniflandir`
    dusuyor). Konu modelin kendi havuzundan geliyor ve 2026-08-06 gecesi bu
    yoldan ayni gecede iki Roma muhendisligi videosu cikmisti.

`--yayin` bayragi bu uc gerekcenin de bilindigi anlamina gelir.
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
ETIKET = "works.duo.mpt-uretim"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{ETIKET}.plist"
GUNLUK_DIZIN = KOK / "storage" / "youtube_automation"

SAATLER = (9, 13, 17, 21)
"""Gunde dort uretim.

YouTube kotasi gunde 6 yuklemeye yetiyor (`videos.insert` 1600 birim, gunluk
tavan 10.000). Dort, tavanin altinda pay birakiyor: elle bir yukleme ya da bir
yeniden deneme kotayi patlatmasin.

Saatler gunduze yayildi — bir kosum dusrse kullanici ayni gun gorup
mudahale edebilsin. Gece kosumlari sabaha kadar sessizce olu kaliyordu.
"""


def _python() -> str:
    venv = KOK / ".venv" / "bin" / "python"
    return str(venv if venv.exists() else Path(sys.executable))


def plist_govdesi(*, gizlilik: str) -> dict:
    """launchd tanimi — `StartCalendarInterval` bir liste alabiliyor."""
    return {
        "Label": ETIKET,
        "ProgramArguments": [
            _python(),
            str(KOK / "youtube_automation.py"),
            "--privacy",
            gizlilik,
        ],
        "WorkingDirectory": str(KOK),
        "StartCalendarInterval": [{"Hour": s, "Minute": 0} for s in SAATLER],
        "StandardOutPath": str(GUNLUK_DIZIN / "zamanlama.log"),
        "StandardErrorPath": str(GUNLUK_DIZIN / "zamanlama.log"),
        "RunAtLoad": False,
        # ⚠️ Uyanma sonrasi kacirilan kosumlar TOPLU calismasin. Mac uykudayken
        # dort saat gecerse launchd normalde hepsini pes pese tetikler; dort
        # video ayni dakikada uretilmeye kalkar, kilit yuzunden ucu duser ve
        # kota bosa gider.
        "AbandonProcessGroup": False,
    }


def kur(*, gizlilik: str) -> int:
    GUNLUK_DIZIN.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    with PLIST.open("wb") as dosya:
        plistlib.dump(plist_govdesi(gizlilik=gizlilik), dosya)

    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True, check=False)
    sonuc = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
    if sonuc.returncode != 0:
        print(f"launchctl load basarisiz: {sonuc.stderr.strip()}", file=sys.stderr)
        return 1

    saatler = ", ".join(f"{s:02d}:00" for s in SAATLER)
    print(f"✅ kuruldu · gunde {len(SAATLER)} uretim ({saatler}) · gizlilik: {gizlilik}")
    if gizlilik != "public":
        print("   Videolar GIZLI kalir. Yayin icin: kur --yayin")
    return 0


def durum() -> int:
    if not PLIST.exists():
        print("kurulu degil")
        return 1
    sonuc = subprocess.run(
        ["launchctl", "list", ETIKET], capture_output=True, text=True, check=False
    )
    print(sonuc.stdout.strip() or f"{ETIKET} yuklu degil")
    return 0 if sonuc.returncode == 0 else 1


def kaldir() -> int:
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True, check=False)
    PLIST.unlink(missing_ok=True)
    print("kaldirildi")
    return 0


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="macOS gunluk uretim zamanlamasi")
    ayristirici.add_argument("komut", choices=["kur", "durum", "kaldir"])
    ayristirici.add_argument(
        "--yayin",
        action="store_true",
        help=(
            "Gizlilik `public` olsun. Varsayilan `private` — gerekcesi modul "
            "docstring'inde: bu kanal kapatilan bir kanalin yerine acildi ve "
            "trend hunisi su an kuru."
        ),
    )
    args = ayristirici.parse_args()

    if args.komut == "kur":
        return kur(gizlilik="public" if args.yayin else "private")
    if args.komut == "durum":
        return durum()
    return kaldir()


if __name__ == "__main__":
    raise SystemExit(main())
