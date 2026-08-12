"""Trend hunisinin uretim kuyrugu — `ytoto` kopruSU uzerinden okunur.

Bu modul Notion'a **dogrudan bagli degil** ve bilerek oyle: sozlesmenin sahibi
trend hatti (ADR-0013). Video hatti dar bir CLI arayuzu tuketiyor, Notion
tokeni gormuyor, olcum alanlarina hic dokunamiyor. Notion sutunu yeniden
adlandirilirsa burasi kirilmiyor; kiriliyorsa da tek yerde kiriliyor.

    ytoto aday listele --durum Secildi --json   -> kuyrugu oku
    ytoto aday basla   <kimlik>                 -> kap (Secildi -> Uretiliyor)
    ytoto aday bitir   <kimlik> --video-url ... -> kapat (-> Uretildi)

⚠️ `ytoto` PATH'te yok; her iki kurulumda da bir sanal ortamin icinde duruyor.
Bu yuzden yol yapilandirmadan geliyor ve bulunamadiginda **sessizce
gecilmiyor** — kuyruga bagli oldugunu saniyorken kendi konusunu ureten bir hat,
bagli olmayan bir hattan daha kotudur.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

VARSAYILAN_ZAMAN_ASIMI = 60


class KopruYok(RuntimeError):
    """`ytoto` calistirilamiyor — yol yanlis ya da kurulum eksik."""


class KopruHatasi(RuntimeError):
    """`ytoto` calisti ama basarisiz dondu."""


@dataclass(frozen=True)
class Aday:
    """Kuyruktan gelen tek aday.

    Alan adlari kopru sozlesmesinden (`Aday.sozluk`) geliyor; Notion sutun
    adlarindan bilincli olarak farklilar.
    """

    kimlik: str
    baslik: str
    sayfa_url: str
    onerilen_format: str | None
    dil: str | None
    bosluk_skoru: float | None
    talep: int | None

    @classmethod
    def sozlukten(cls, ham: dict) -> Aday:
        return cls(
            kimlik=str(ham.get("kimlik", "")),
            baslik=str(ham.get("baslik", "")),
            sayfa_url=str(ham.get("sayfa_url", "")),
            onerilen_format=ham.get("onerilen_format"),
            dil=ham.get("dil"),
            bosluk_skoru=ham.get("bosluk_skoru"),
            talep=ham.get("talep"),
        )


def _ytoto_yolu(yapilandirilmis: str | None) -> str:
    """Calistirilabilir `ytoto` yolunu bulur ya da anlasilir sekilde patlar."""
    if yapilandirilmis:
        yol = Path(yapilandirilmis).expanduser()
        if not yol.exists():
            raise KopruYok(
                f"ytoto bulunamadi: {yol}\n"
                "config.toml icindeki `ytoto_path` degerini duzeltin."
            )
        return str(yol)
    bulunan = shutil.which("ytoto")
    if bulunan:
        return bulunan
    raise KopruYok(
        "ytoto PATH'te yok ve `ytoto_path` yapilandirilmamis.\n"
        "Yt_Automation sanal ortamindaki yolu config.toml'a yazin, orn:\n"
        "  ytoto_path = \"/Users/<kullanici>/.yt-otomasyon/calisan/.venv/bin/ytoto\""
    )


def _kos(
    argumanlar: list[str],
    *,
    ytoto_path: str | None,
    zaman_asimi: int = VARSAYILAN_ZAMAN_ASIMI,
) -> subprocess.CompletedProcess[str]:
    komut = [_ytoto_yolu(ytoto_path), *argumanlar]
    try:
        return subprocess.run(
            komut, capture_output=True, text=True, timeout=zaman_asimi, check=False
        )
    except subprocess.TimeoutExpired as hata:
        raise KopruHatasi(
            f"ytoto {zaman_asimi} saniyede yanit vermedi: {' '.join(argumanlar)}"
        ) from hata


def kuyrugu_oku(
    *,
    ytoto_path: str | None = None,
    format_adi: str | None = "shorts",
    limit: int = 5,
) -> list[Aday]:
    """`Secildi` kuyrugunu okur — insanin "bunu uret" dedigi adaylar.

    Bos kuyruk bir HATA DEGIL: insan henuz secim yapmamis olabilir. `ytoto`
    bu durumda 1 donuyor, o yuzden cikis kodu tek basina basarisizlik sayilmaz;
    ayirt edici olan cikti ayristirilabiliyor mu.

    ⚠️ BOS CIKTI ARTIK BOS KUYRUK SAYILMIYOR (olculdu 2026-08-12). Cevrede
    NOTION_TOKEN yokken `ytoto` cikis 1 + BOS stdout veriyor ve hatayi
    stderr'e yaziyordu; burasi ikisini de "kuyruk bos" diye okuyup hat
    "`Secildi` kuyrugu bos, konu uydurulmadi" diyordu. Yani YAPILANDIRMA
    BOZUKKEN hat, insanin henuz secim yapmadigini soyluyordu — sessiz ve
    yanlis. Gercekten bos kuyruk stdout'a "[]" basiyor, yani ikisi
    ayirt EDILEBILIYOR; ayrimi yapmayan bizdik.
    """
    argumanlar = ["aday", "listele", "--durum", "Seçildi", "--json", "--limit", str(limit)]
    if format_adi:
        argumanlar += ["--format", format_adi]
    sonuc = _kos(argumanlar, ytoto_path=ytoto_path)
    metin = sonuc.stdout.strip()
    if not metin:
        raise KopruHatasi(
            f"ytoto aday listele cikti vermedi (cikis {sonuc.returncode}). "
            "Bos kuyruk '[]' basar; bos cikti kopru ya da yapilandirma "
            f"hatasidir: {sonuc.stderr.strip()[-400:] or '(stderr bos)'}"
        )
    try:
        ham = json.loads(metin)
    except json.JSONDecodeError as hata:
        raise KopruHatasi(
            f"ytoto aday listele JSON vermedi: {metin[:200]}"
        ) from hata
    return [Aday.sozlukten(kayit) for kayit in ham]


def adayi_kap(aday: Aday, *, ytoto_path: str | None = None) -> None:
    """`Secildi` -> `Uretiliyor`.

    Basarisizlik **yutulmaz**: kapamayan bir kosum, baska bir kosumun ayni
    adayi ureteceği anlamina geliyor.
    """
    sonuc = _kos(["aday", "basla", aday.kimlik], ytoto_path=ytoto_path)
    if sonuc.returncode != 0:
        raise KopruHatasi(
            f"aday kapilamadi ({aday.baslik}): {sonuc.stderr.strip()[-400:]}"
        )


def adayi_birak(
    aday: Aday, *, gerekce: str, ytoto_path: str | None = None
) -> None:
    """`Uretiliyor` -> `Secildi`. Kapmanin geri alinmasi.

    Uretim dustugunde cagrilir. Cagrilmazsa aday `Uretiliyor`da mahsur kalir
    ve kuyruk `Secildi` okudugu icin bir daha hic gorunmez — sessiz kayip.

    Bu cagri **hata firlatmaz**: zaten basarisiz olan bir kosumu temizlik
    adimi yuzunden bir kez daha patlatmak, asil hatayi gizler. Sorun ciktisiyla
    bildirilir.
    """
    sonuc = _kos(
        ["aday", "birak", aday.kimlik, "--not", gerekce[:1800]], ytoto_path=ytoto_path
    )
    if sonuc.returncode != 0:
        print(
            f"⚠️ aday kuyruga geri konamadi ({aday.baslik}) — Notion'da "
            f"`Uretiliyor`da kalmis olabilir: {sonuc.stderr.strip()[-300:]}"
        )


def adayi_kapat(
    aday: Aday,
    *,
    video_url: str,
    uretim_notu: str | None = None,
    ytoto_path: str | None = None,
) -> None:
    """`Uretiliyor` -> `Uretildi`, video baglantisiyla."""
    argumanlar = ["aday", "bitir", aday.kimlik, "--video-url", video_url]
    if uretim_notu:
        argumanlar += ["--not", uretim_notu]
    sonuc = _kos(argumanlar, ytoto_path=ytoto_path)
    if sonuc.returncode != 0:
        raise KopruHatasi(
            f"aday kapatilamadi ({aday.baslik}): {sonuc.stderr.strip()[-400:]}"
        )
