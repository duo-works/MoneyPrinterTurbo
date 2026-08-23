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
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LOG_DIZINI = ROOT / "storage" / "youtube_automation" / "logs"
STATE_FILE = ROOT / "storage" / "youtube_automation" / "state.json"
ZAMANLAYICI_LOG = LOG_DIZINI / "zamanlayici.log"

BITIS_OLAYLARI = ("YAYIN", "red", "HATA")
"""Bir kosumun BITTIGINI soyleyen olaylar — koşum paydasi bunlardan cikar.

⚠️ NEDEN `state.json` DEGIL: red kayitlari DENEMEYI sayiyor, koşumu degil.
Olculdu (2026-08-23): bir gunde 7 koşum, 13 kayit — cunku tek koşum bes
denemeye kadar cikiyor ve her denemesi ayri kayit yaziyor. Ustelik plan
asamasinda olen koşum hic kayit YAZMIYOR. Iki hata ters yonde ve
birbirini gizliyor, yani `state.json`dan turetilen "koşum basina yayin"
sayisi iki kere yanlis.

⚠️ NEDEN `kol |` DEGIL: kol satiri 2026-08-22'de eklendi, gecmisin
tamami disarida kalirdi (10 satir / 84 koşum). Bitis olaylari ise ilk
gunden beri yaziliyor ve her koşum bunlardan TAM BIRINI uretiyor.
"""

ATLAMA_OLAYI = "atlandi"
"""Tetik atesledi ama koşum BASLAMADI (kilit dolu, pencere dar, tavan).

Paydaya girmez — koşum degildir; ama ayri sayilir, cunku "slot yandi"
ile "koşum reddedildi" bambaska iki kusur ve ikisi bugun tek satirda
karisiyordu.
"""


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


_SATIR = re.compile(r"^(\d{4}-\d\d-\d\d) \d\d:\d\d:\d\d \s*\|\s*([^|]+?)\s*\|")


def kosum_olcumu(*, gun: int | None = None) -> dict[str, Any]:
    """Zamanlayici logundan GERCEK koşum sayisi ve slot basina yayin orani.

    `gun` verilirse yalnizca son N takvim gunu sayilir.

    ⚠️ Pencere DURUSTCE raporlanir: log ne zaman baslamissa oradan. "Son 3
    gun" istenip log 1 gun tasiyorsa sayi 1 gunluktur ve oyle yazilir —
    yoksa kucuk n buyuk n gibi okunur.
    """
    if not ZAMANLAYICI_LOG.exists():
        return {"kosum": 0, "olaylar": {}, "atlanan": 0, "yayin_orani": None, "pencere": []}

    olay_gunu: list[tuple[str, str]] = []
    for satir in ZAMANLAYICI_LOG.read_text(encoding="utf-8").splitlines():
        m = _SATIR.match(satir)
        if m:
            olay_gunu.append((m.group(1), m.group(2)))

    if gun:
        gunler = sorted({g for g, _ in olay_gunu})[-gun:]
        olay_gunu = [(g, o) for g, o in olay_gunu if g in gunler]

    olaylar = Counter(o for _, o in olay_gunu)
    kosum = sum(olaylar[o] for o in BITIS_OLAYLARI)
    gecen_gunler = sorted({g for g, _ in olay_gunu})
    return {
        "kosum": kosum,
        "yayin": olaylar["YAYIN"],
        "red": olaylar["red"],
        "hata": olaylar["HATA"],
        "atlanan": olaylar[ATLAMA_OLAYI],
        "yayin_orani": round(olaylar["YAYIN"] / kosum, 3) if kosum else None,
        "olaylar": dict(olaylar),
        "pencere": [gecen_gunler[0], gecen_gunler[-1]] if gecen_gunler else [],
    }


def _kusur_ailesi(metin: str) -> str:
    """"kare 3: donem uyusmuyor" -> "donem uyusmuyor"."""
    return str(metin).split(":", 1)[-1].strip().lower()


def red_teshisi(*, gun: int | None = None) -> dict[str, Any]:
    """DUSEN koşumlarin kendi gerekcesi — `<slot>-rejected.json`dan.

    ⚠️ Bu dosyalari bugune kadar OKUYAN HICBIR SEY YOKTU. Icinde asama
    basina hakem incelemesinin tamami duruyor (skor, `issues`,
    `agir_kusurlar`) ve her oturumda elle Python yazilarak cikariliyordu.
    Rapor artik ayni sayiyi kendisi uretiyor.

    ⚠️ Bozuk/yarim dosya raporu DUSURMEZ: atlanir ve `okunamayan` sayilir —
    teshis araci teshis edilecek kusurdan olmemeli.
    """
    dosyalar = sorted(LOG_DIZINI.glob("*-rejected.json")) if LOG_DIZINI.exists() else []
    if gun:
        gunler = sorted({d.name[:10] for d in dosyalar})[-gun:]
        dosyalar = [d for d in dosyalar if d.name[:10] in gunler]

    asama = Counter()
    asama_skorlari: dict[str, list[int]] = {}
    agir = Counter()
    kusur = Counter()
    okunamayan = 0
    for yol in dosyalar:
        try:
            govde = json.loads(yol.read_text(encoding="utf-8"))
            incelemeler = govde.get("reviews") or []
        except (OSError, ValueError, AttributeError):
            okunamayan += 1
            continue
        for kayit in incelemeler:
            # ⚠️ `stage` YOKSA "video" — `rapor()` ayni varsayimi yapiyor
            # (`k.get("stage", "video")`) ve iki taraf ayrisirsa ayni redler
            # iki farkli asamaya yazilir. Olculdu: 104 kayitta alan yok ve
            # `state.json` tarafi onlarin hepsini `video` sayiyor.
            ad = str(kayit.get("stage") or "video")
            asama[ad] += 1
            inceleme = kayit.get("review") or {}
            skor = inceleme.get("visual_alignment_score")
            if isinstance(skor, int):
                asama_skorlari.setdefault(ad, []).append(skor)
            for ham in inceleme.get("agir_kusurlar") or []:
                agir[_kusur_ailesi(ham)] += 1
            for ham in inceleme.get("issues") or []:
                kusur[_kusur_ailesi(ham)] += 1

    return {
        "dosya": len(dosyalar),
        "okunamayan": okunamayan,
        "asama": dict(asama),
        "asama_ortanca_skor": {
            ad: statistics.median(s) for ad, s in sorted(asama_skorlari.items())
        },
        "en_sik_agir_kusur": agir.most_common(5),
        "en_sik_kusur": kusur.most_common(5),
    }


def onarim_ozeti(durum: dict[str, Any] | None = None) -> dict[str, Any]:
    """Kare onarimi denendi mi, TUTTU mu — kapali dongunun okuma ucu.

    ⚠️ Onarim 2026-08-21'e kadar KOR yaziyordu: `ℹ️ kare onarımı` yalnizca
    stdout'a basiliyordu ve `uret.sh` cikti dosyasini cikista siliyor. Alan
    2026-08-23'te eklendi (`onarim`), yani bu ozet o tarihten ONCEKI
    koşumlar icin bos doner — sayi yok demek "onarim calismadi" DEMEZ.
    """
    d = _durum() if durum is None else durum
    denendi = tuttu = 0
    for tip in ("published", "rejected"):
        for kayit in d.get(tip) or []:
            for adim in kayit.get("onarim") or []:
                denendi += 1
                tuttu += 1 if adim.get("tuttu") else 0
    return {
        "denendi": denendi,
        "tuttu": tuttu,
        "tutmadi": denendi - tuttu,
        "tutma_orani": round(tuttu / denendi, 3) if denendi else None,
    }


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
        # ⚠️ KAYIT sayisi, koşum sayisi DEGIL — bir koşum bese kadar kayit
        # yazar ve plan asamasinda olen koşum HIC yazmaz. Koşum paydasi icin
        # `kosum_olcumu` var; ad 2026-08-23'te duzeltildi (eskiden
        # `toplam_kosum` deniyordu ve iki sayi karistiriliyordu).
        "kayit_sayisi": toplam,
        "yayinlanan": len(yayinlanan),
        "reddedilen": len(reddedilen),
        "kayit_basari_orani": round(len(yayinlanan) / toplam, 3) if toplam else 0.0,
        "kosum_olcumu": kosum_olcumu(),
        "red_teshisi": red_teshisi(),
        "onarim": onarim_ozeti(durum),
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
    k = veri["kosum_olcumu"]
    if k["kosum"]:
        pencere = " - ".join(k["pencere"]) if k["pencere"] else "?"
        print(f"KOSUM      : {k['kosum']}  ({k['yayin']} yayin, {k['red']} red, {k['hata']} hata)")
        oran = k["yayin_orani"]
        print(f"slot basina: %{oran * 100:.0f}   [{pencere}]" if oran is not None else "")
        if k["atlanan"]:
            print(f"atlanan tetik: {k['atlanan']}  (koşum baslamadi — kilit/pencere/tavan)")
    print(
        f"kayit      : {veri['kayit_sayisi']}  "
        f"({veri['yayinlanan']} yayin, {veri['reddedilen']} red)  ⚠️ deneme sayar"
    )
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

    t = veri["red_teshisi"]
    if t["asama"]:
        print(f"\nDUSEN KOSUMLAR   ({t['dosya']} slot dosyasi)")
        for ad, adet in sorted(t["asama"].items(), key=lambda x: -x[1]):
            ortanca = t["asama_ortanca_skor"].get(ad)
            ek = f"  ortanca skor {ortanca:g}" if ortanca is not None else ""
            print(f"   {adet:>3}  {ad}{ek}")
        if t["okunamayan"]:
            print(f"   ⚠️ {t['okunamayan']} dosya okunamadi")
    for baslik, anahtar in (("agir kusur", "en_sik_agir_kusur"), ("kusur", "en_sik_kusur")):
        if t[anahtar]:
            print(f"   {baslik}:")
            for ad, adet in t[anahtar]:
                print(f"      {adet:>3}  {ad[:66]}")

    o = veri["onarim"]
    if o["denendi"]:
        print(
            f"\nONARIM     : {o['denendi']} denendi, {o['tuttu']} tuttu, "
            f"{o['tutmadi']} tutmadi  (%{(o['tutma_orani'] or 0) * 100:.0f})"
        )
    else:
        print("\nONARIM     : kayit yok  ⚠️ alan 2026-08-23'te eklendi, oncesi olculemiyor")


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
