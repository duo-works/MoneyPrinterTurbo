"""Kuyrugu KENDI KENDINE besler: `Yeni` -> arsiv arzi olcumu -> `Secildi`.

⚠️ NEDEN VAR — olculdu (2026-08-14). Uretim iki kez durdu ve ikisinde de
sebep hattin kendisi degildi, BESLENMEMESIYDI:

    `Secildi` kuyrugu           2 aday      (uretim buradan besleniyor)
    `Yeni` kuyrugu            100+ aday     (bekliyor, kimse tasimiyor)
    yedek capa havuzu           KALAN 0     -> "could not generate a
                                               sufficiently distinct topic"

Kuyruk bosalinca hat yedek capa havuzuna dusuyor, o da tukenince hic video
uretilmiyor. Yedek havuz bir EMNIYET SUPABI olmali, ana kaynak degil —
ana kaynak insanin ve olculmus talebin sectigi huni.

⚠️ TERFI KOR DEGIL, OLCULU. Adayi arsiv arzina bakmadan `Secildi`ye
tasimak kuyrugu doldurur ama uretimi duzeltmez: konu uretilemezse koşum
yine bos doner, ustelik bu kez bir uretim slotu yakarak. Olcut uretimin
KENDI olcutu (`arsiv_menusu`), tahmin degil.

Kullanim:
    python huni_besle.py            # olcer ve terfi eder
    python huni_besle.py --kuru     # yalnizca olcer, Notion'a dokunmaz
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

import notion_kuyrugu
import wikimedia_materials
from youtube_automation import (
    KARE_YUVASI,
    YTOTO_PATH,
    engellenen_capalar,
    is_duplicate_visual_anchor,
)

HEDEF_DERINLIK = 6
"""`Secildi` kuyrugunda tutulmak istenen aday sayisi.

Gunde ~8 tetikleme ve ~%50 yayin orani var; 6 aday yaklasik 1,5 gunluk
tampon demek. Daha buyuk tutmak insanin sonradan fikrini degistirdigi
adaylari da kilitlerdi (`Secildi` = "bunu uret" demek).
"""

ASGARI_MENU = 6 * KARE_YUVASI
"""Bir konunun uretilebilir sayilmasi icin gereken menu buyuklugu.

6 sahne x 2 kare yuvasi = 12 ayri dosya. Ayni olcut `EDITORIAL_ANCHOR_POOL`
capalarinda da kullanildi; iki yerde ayri sayi tutmak, kuyrugun kabul
ettigi konunun havuzun reddettigi konu olmasi demek olurdu.
"""


def yeni_adaylar(limit: int = 40) -> list[notion_kuyrugu.Aday]:
    """`Yeni` kuyrugunu okur — `kuyrugu_oku`nun `Secildi` ikizi.

    ⚠️ SINIFA GORE SIRALANIYOR (2026-08-16). Notion listeyi `Bosluk skoru`
    AZALAN veriyor ve o skor yapisal olarak AZ BILINEN KISIYI one aliyor:
    talep/arz bosluğu buyukse konu genelde az bilinen bir kisidir, az bilinen
    kisinin de kamu mali gorseli yoktur. Canli kuyrukta 114 `Yeni` adayin
    ezici cogunlugu kisi; huni de tam o dilimin ilk 40'ini okuyordu.

    Olculdu — alti besleme koşumunda 48 atlama, 24'u "menu < 12":
        Rogelio Mortimer 0 · Antigua Confederación Suiza 0
        Franz Count of Meran 3 · Henry Macandrew 3      (hepsi kisi)

    `sinifa_gore_sirala` ELEME DEGIL SIRALAMA: kisi adayi kuyrukta kalir,
    yalnizca sona duser (Mehmed II bir kisi konusuydu ve 84 aldi). Ayni
    fonksiyon `kuyrugu_oku`da (`notion_kuyrugu.py:153`) zaten kullaniliyor;
    burasi ikinci cagri yeri, yeni kod degil.
    """
    sonuc = subprocess.run(
        [
            notion_kuyrugu._ytoto_yolu(YTOTO_PATH),
            "aday", "listele", "--durum", "Yeni", "--json", "--limit", str(limit),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    metin = sonuc.stdout.strip()
    if not metin:
        # ⚠️ Bos cikti BOS KUYRUK DEGIL: `kuyrugu_oku`da olculmus ayni
        # kusur — NOTION_TOKEN yokken ytoto cikis 1 + bos stdout veriyor.
        raise notion_kuyrugu.KopruHatasi(
            f"ytoto aday listele cikti vermedi (cikis {sonuc.returncode}): "
            f"{sonuc.stderr.strip()[-300:] or '(stderr bos)'}"
        )
    return notion_kuyrugu.sinifa_gore_sirala(
        [notion_kuyrugu.Aday.sozlukten(k) for k in json.loads(metin)]
    )


def uretilebilir_mi(baslik: str) -> tuple[bool, int]:
    """Konunun arsiv arzi yetiyor mu — uretimin KENDI menusuyle olculur.

    Kredi harcamaz, yalnizca Commons'a bakar.
    """
    try:
        menu = wikimedia_materials.arsiv_menusu(baslik, sinir=40)
    except Exception as hata:  # ag hatasi tek adayi atlatmali, koşumu degil
        print(f"  ⚠️ {baslik[:40]}: menu olculemedi ({str(hata)[:60]})", flush=True)
        return False, 0
    return len(menu) >= ASGARI_MENU, len(menu)


def _kullanilmis_capalar() -> list[str]:
    """⚠️ Uretimle AYNI listeyi dondurmeli — bkz. `engellenen_capalar`.

    Eskiden burada `published` + `rejected` capalari toplaniyordu ve tek bir
    ret konuyu omur boyu yasakliyordu; olcum 2026-08-16'da havuzun 52'de 0'a
    dustugunu gosterdi. Butce mantigi tek yerde tutuluyor.
    """
    return engellenen_capalar()


def besle(kuru: bool = False) -> dict:
    """Kuyrugu hedef derinlige kadar doldurur; ozet doner."""
    mevcut = notion_kuyrugu.kuyrugu_oku(ytoto_path=YTOTO_PATH, limit=HEDEF_DERINLIK)
    eksik = HEDEF_DERINLIK - len(mevcut)
    print(f"`Seçildi` kuyruğu: {len(mevcut)}/{HEDEF_DERINLIK} — eksik {max(eksik, 0)}")
    if eksik <= 0:
        return {"terfi": [], "elenen": [], "eksik": 0}

    kullanilmis = _kullanilmis_capalar()
    terfi: list[str] = []
    elenen: list[tuple[str, int]] = []
    for aday in yeni_adaylar():
        if len(terfi) >= eksik:
            break
        # ⚠️ Uretilmis konuya benzeyeni terfi etmek, huninin sirasini
        # bozup slot yakar: `generate_content_plan` onu zaten reddediyor.
        if is_duplicate_visual_anchor(aday.baslik, kullanilmis):
            elenen.append((aday.baslik, -1))
            continue
        tamam, adet = uretilebilir_mi(aday.baslik)
        if not tamam:
            elenen.append((aday.baslik, adet))
            continue
        if kuru:
            print(f"  [kuru] terfi edilebilir: {aday.baslik[:50]} (menü {adet})")
        else:
            sonuc = subprocess.run(
                [notion_kuyrugu._ytoto_yolu(YTOTO_PATH), "aday", "sec", aday.kimlik],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if sonuc.returncode != 0:
                # Terfi edemeyen aday koşumu OLDURMEZ: kalanlar denenir.
                print(f"  ⚠️ terfi edilemedi ({aday.baslik[:40]}): "
                      f"{sonuc.stderr.strip()[-160:]}", flush=True)
                continue
            print(f"  ✅ Seçildi: {aday.baslik[:50]} (menü {adet})")
        terfi.append(aday.baslik)
        kullanilmis.append(aday.baslik)

    for baslik, adet in elenen[:8]:
        sebep = "benzeri üretilmiş" if adet < 0 else f"menü {adet} < {ASGARI_MENU}"
        print(f"  – atlandı: {baslik[:46]} ({sebep})")
    return {"terfi": terfi, "elenen": elenen, "eksik": eksik}


def main() -> None:
    ayristirici = argparse.ArgumentParser(description="Huni kuyrugunu besler")
    ayristirici.add_argument("--kuru", action="store_true", help="Notion'a yazmadan ölç")
    secenekler = ayristirici.parse_args()
    try:
        ozet = besle(kuru=secenekler.kuru)
    except (notion_kuyrugu.KopruYok, notion_kuyrugu.KopruHatasi) as hata:
        # ⚠️ Besleme basarisiz olsa bile URETIM DURMAMALI: bu bir
        # iyilestirme adimi, on kosul degil. Cagiran betik cikis kodunu
        # gormezden gelebilsin diye 0 donmuyor ama mesaj net.
        sys.exit(f"❌ huni beslenemedi: {hata}")
    print(f"\nterfi edilen: {len(ozet['terfi'])}")


if __name__ == "__main__":
    main()
