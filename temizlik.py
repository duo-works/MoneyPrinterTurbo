"""Uretim artiklarini siler — disk her kosumda ~120 MB buyuyor.

Olculdu (2026-08-08): `storage/` 1,0 GB ve bunun 822 MB'i ARA DOSYA.

    storage/youtube_automation/commons_materials  383 MB  sahne gorselleri
    storage/local_videos                          284 MB  94 jpg + 94 klip
    storage/tasks/*/combined-1.mp4                155 MB  altyazisiz surum

Ucu de nihai video yazildiktan sonra hicbir ise yaramiyor: `combined-1.mp4`
altyazi eklenmeden onceki surum, `local_videos` her sahnenin kaynak goruntusu
ve ondan uretilmis 5 saniyelik klip, `commons_materials` ise indirilmis arsiv
gorselleri.

⚠️ SILINMEYENLER — bunlar kayit, artik degil:

    state.json         yayin gecmisi; kaybi tekrar ureti ve kanca cesitliligi
                       kontrolunu birden bozar
    credits.json       gorsel atif kaydi; CC BY icin hukuki dayanak
    logs/              metin, toplam 204 KB
    final-1.mp4        TESLIM EDILEN URUN — yalnizca baska bir yerde oldugu
                       KANITLANDIGINDA siliniyor (bkz. `yayinlanmis_videolar`)
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

KOK = Path(__file__).resolve().parent
DEPO = KOK / "storage"
GOREVLER = DEPO / "tasks"
YEREL_VIDEOLAR = DEPO / "local_videos"
OTOMASYON = DEPO / "youtube_automation"
MALZEMELER = OTOMASYON / "commons_materials"
INCELEMELER = OTOMASYON / "reviews"
DURUM = OTOMASYON / "state.json"
KILIT = OTOMASYON / "automation.lock"

KORUNAN_ADLAR = frozenset({"state.json", "credits.json", "final-1.mp4", "script.json"})
"""Adi bunlardan biri olan dosyaya ara dosya muamelesi YAPILMAZ.

Ad bazli koruma, dizin bazli mantik yanlis giderse diye ikinci bir kilit.
`final-1.mp4` burada da var: video silme yolu ondan ayri ve acik.
"""


class TemizlikHatasi(RuntimeError):
    """Temizlik guvenli bicimde yapilamiyor."""


@dataclass
class Plan:
    """Ne silinecek — once hesaplanir, sonra uygulanir."""

    dosyalar: list[Path] = field(default_factory=list)
    dizinler: list[Path] = field(default_factory=list)

    @property
    def bayt(self) -> int:
        toplam = sum(d.stat().st_size for d in self.dosyalar if d.exists())
        for dizin in self.dizinler:
            toplam += sum(p.stat().st_size for p in dizin.rglob("*") if p.is_file())
        return toplam

    @property
    def bos_mu(self) -> bool:
        return not self.dosyalar and not self.dizinler


def _iceride(yol: Path) -> bool:
    """Yol `storage/` altinda mi.

    ⚠️ Silme yapan her fonksiyonun son savunmasi. Bir hesaplama hatasi
    sonucu `/` ya da ev dizini listeye girerse burada durur.
    """
    try:
        yol.resolve().relative_to(DEPO.resolve())
    except ValueError:
        return False
    return True


def _yukleme_kaydi() -> dict:
    if not DURUM.exists():
        return {}
    try:
        return json.loads(DURUM.read_text(encoding="utf-8"))
    except json.JSONDecodeError as hata:
        raise TemizlikHatasi(f"state.json okunamadi: {hata}") from hata


def yayinlanmis_videolar(durum: dict | None = None) -> list[Path]:
    """Baska bir yerde oldugu KANITLI nihai videolar.

    Kanit: `state.json` icindeki kayitta dolu bir `url` olmasi — yani video
    YouTube'a yuklenmis. Yalnizca bunlarin yerel kopyasi silinebilir.

    ⚠️ Kapali-hata: kayit yoksa, url bossa ya da yol depo disindaysa video
    KALIR. "Muhtemelen yuklenmistir" diye silmek, geri getirilemeyecek tek
    seyi geri getirilemez bicimde silmek olurdu.
    """
    durum = durum if durum is not None else _yukleme_kaydi()
    cikti: list[Path] = []
    for kayit in durum.get("published", []):
        if not str(kayit.get("url", "")).strip():
            continue
        ham = str(kayit.get("video_path", "")).strip()
        if not ham:
            continue
        yol = Path(ham)
        if yol.exists() and _iceride(yol):
            cikti.append(yol)
    return cikti


def ara_dosyalar(*, koru: set[str] | None = None) -> Plan:
    """Nihai video yazildiktan sonra degeri kalmayan her sey.

    `koru` — dokunulmayacak gorev kimlikleri (or. su an uretilen kosum).
    """
    koru = koru or set()
    plan = Plan()

    # 1) Sahne kaynaklari ve onlardan uretilmis klipler.
    if YEREL_VIDEOLAR.is_dir():
        plan.dosyalar += [p for p in YEREL_VIDEOLAR.iterdir() if p.is_file()]

    # 2) Altyazisiz ara surum — `final-1.mp4` varken olu yuk.
    if GOREVLER.is_dir():
        for gorev in GOREVLER.iterdir():
            if not gorev.is_dir() or gorev.name in koru:
                continue
            for ad in ("combined-1.mp4", "audio.mp3", "subtitle.srt"):
                aday = gorev / ad
                if aday.exists():
                    plan.dosyalar.append(aday)

    # 3) Indirilmis arsiv gorselleri — credits.json KALIYOR.
    if MALZEMELER.is_dir():
        for kosum in MALZEMELER.iterdir():
            if not kosum.is_dir() or kosum.name in koru:
                continue
            plan.dosyalar += [
                p for p in kosum.rglob("*") if p.is_file() and p.name not in KORUNAN_ADLAR
            ]

    # 4) Kalite incelemesi icin uretilmis montajlar.
    if INCELEMELER.is_dir():
        plan.dosyalar += [p for p in INCELEMELER.iterdir() if p.is_file()]

    plan.dosyalar = [
        d for d in plan.dosyalar if _iceride(d) and d.name not in KORUNAN_ADLAR
    ]
    return plan


def bos_dizinleri_topla() -> list[Path]:
    """Icerigi silindikten sonra geriye kalan bos kabuklar."""
    bos: list[Path] = []
    for kok in (MALZEMELER, GOREVLER):
        if not kok.is_dir():
            continue
        for dizin in kok.iterdir():
            if dizin.is_dir() and _iceride(dizin) and not any(dizin.iterdir()):
                bos.append(dizin)
    return bos


def uygula(plan: Plan) -> int:
    """Plani uygular, bosalan bayt sayisini doner."""
    bayt = plan.bayt
    for dosya in plan.dosyalar:
        if not _iceride(dosya):
            raise TemizlikHatasi(f"depo disi yol silinmeye calisildi: {dosya}")
        dosya.unlink(missing_ok=True)
    for dizin in plan.dizinler:
        if not _iceride(dizin):
            raise TemizlikHatasi(f"depo disi dizin silinmeye calisildi: {dizin}")
        shutil.rmtree(dizin, ignore_errors=True)
    return bayt


def kosum_sonrasi_temizle(*korunacaklar: str) -> int:
    """Bir uretim kosumunun ardindan cagrilir.

    Yalnizca ara dosyalar. Nihai video hicbir kosulda burada silinmiyor —
    o karar `--videolar` ile acikca veriliyor.

    ⚠️ SU ANKI kosumun dosyalari korunuyor: montaj ve sahne gorselleri, cikan
    videoya bakarken lazim ve yeniden uretilmesi para/zaman. Bir sonraki
    kosumda temizleniyorlar, yani diskte her zaman en fazla tek kosumluk
    artik kaliyor — hem sinirli hem incelenebilir.
    """
    plan = ara_dosyalar(koru={k for k in korunacaklar if k})
    return uygula(plan)


def _mb(bayt: int) -> str:
    return f"{bayt / 1_048_576:.0f} MB"


def main() -> None:
    ayristirici = argparse.ArgumentParser(description="Uretim artiklarini sil")
    ayristirici.add_argument(
        "--onayla",
        action="store_true",
        help="Gercekten sil. Varsayilan kuru kosum — once ne silinecegi yazilir.",
    )
    ayristirici.add_argument(
        "--videolar",
        action="store_true",
        help=(
            "Yayinlanmis videolarin YEREL kopyasini da sil. Yalnizca state.json'da "
            "dolu bir YouTube baglantisi olan kayitlar silinir."
        ),
    )
    args = ayristirici.parse_args()

    if KILIT.exists():
        raise SystemExit(
            "Uretim suruyor (automation.lock var). Temizlik, yarim kalmis bir "
            "kosumun dosyalarini silebilirdi — hicbir sey yapilmadi."
        )

    plan = ara_dosyalar()
    print(f"Ara dosyalar: {len(plan.dosyalar)} dosya · {_mb(plan.bayt)}")

    video_plani = Plan()
    if args.videolar:
        video_plani.dosyalar = yayinlanmis_videolar()
        print(
            f"Yayinlanmis video kopyasi: {len(video_plani.dosyalar)} dosya · "
            f"{_mb(video_plani.bayt)}"
        )
        for v in video_plani.dosyalar:
            print(f"   · {v.parent.name}/{v.name}")

    toplam = plan.bayt + video_plani.bayt
    if not args.onayla:
        print(f"\nKURU KOSUM — {_mb(toplam)} bosalirdi. Silmek icin: --onayla")
        return

    bosalan = uygula(plan) + uygula(video_plani)
    kabuklar = Plan(dizinler=bos_dizinleri_topla())
    uygula(kabuklar)
    print(f"\n✅ {_mb(bosalan)} bosaldi · {len(kabuklar.dizinler)} bos dizin kaldirildi")


if __name__ == "__main__":
    main()
