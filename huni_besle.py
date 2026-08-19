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
    ASGARI_SAHNE_ARZI,
    SHORTS_BICIMI,
    YTOTO_PATH,
    aday_kapilabilir_mi,
    arsiv_envanteri,
    arsiv_videoyu_tasir,
    engellenen_capalar,
    is_duplicate_visual_anchor,
    load_state,
)

HEDEF_DERINLIK = 6
"""`Secildi` kuyrugunda tutulmak istenen aday sayisi.

Gunde ~8 tetikleme ve ~%50 yayin orani var; 6 aday yaklasik 1,5 gunluk
tampon demek. Daha buyuk tutmak insanin sonradan fikrini degistirdigi
adaylari da kilitlerdi (`Secildi` = "bunu uret" demek).
"""

PENCERE = 120
"""`Yeni` kuyrugundan kac aday OKUNSUN (ytoto `--limit`).

⚠️ 40'ti; 2026-08-17'de olculup buyutuldu. Gerekcenin tamami
`yeni_adaylar` docstring'inde: kuyrukta esigi gecen 12 aday vardi ve
12'sinin de ham sirasi 40'in OTESINDEYDI, yani huni her koşumda listenin
uretilemeyen basini tarayip 0 terfiyle donuyordu.

120 secildi cunku canli kuyruk 100 aday ve tavan kuyrugun BUYUMESINE de
yer birakmali; okuma tek bir Notion cagrisi, buyutmenin bedeli orada degil
OLCUMDE (bkz. `OLCUM_TAVANI`).
"""

OLCUM_TAVANI = 45
"""Bir besleme koşumunda en fazla kac adayin arsiv arzi olculsun.

⚠️ PENCEREYI GENISLETMENIN BEDELI BURADA — olculdu (2026-08-17):
`uretilebilir_mi` aday basina ~6,0 sn (Commons kategorisi + arama).

Dongu `len(terfi) >= eksik` olunca kiriliyor, yani olcum TEMBEL: canli
kuyrukla simulasyon pencere 120'de 24 olcumde 3 terfi verdi (~198 sn) —
bugunku 40'lik pencereyle neredeyse ayni, cunku bugun de 24 aday olculup
HIC terfi bulunamiyor.

Tavan ORTALAMA hal icin degil EN KOTU hal icin var: hicbir aday gecmezse
120 adayin hepsi olculurdu ve besleme ~12 dakika surerdi. Besleme HER
uretim slotunda koşuyor (`uret.sh:105`) ve zamanlayici 3 saatte bir
tetikliyor; 12 dakikalik bir besleme, uretimin kendisini geciktirir.

45 secildi: simulasyonun gordugu en kotu hali (24 olcum) rahatca asiyor,
ama en kotu hali ~4,5 dakikada tutuyor. Tavana carpilirsa satir basiliyor —
sessiz kesme, "kuyruk kuru" ile "kuyrugu tarayamadim"i birbirine
karistirirdi.
"""

ASGARI_MENU = ASGARI_SAHNE_ARZI
"""Terfi esigi — URETIMIN kendi esigi, burada yeniden tanimlanmiyor.

⚠️ ESKIDEN `6 * KARE_YUVASI` = 12 IDI ve dogru sayi oydu: "her sahneye IKI
ayri dosya". Ama uretim 2026-08-18'de kapma esigini 6'ya indirdi (ikinci
gorsel bir iyilestirme, on kosul degil) ve BURASI 12'de kaldi. Olculdu
(2026-08-19): huni, uretimin kapacagi adayi terfi ettirmiyordu —
`menu 4 < 12`, `menu 0-3 < 12`. Docstring "iki yerde ayri sayi tutmak"
tehlikesini zaten yaziyordu; tehlike gerceklesti.

Sayi artik `youtube_automation.ASGARI_SAHNE_ARZI`; gerekce orada.
"""


def yeni_adaylar(limit: int = PENCERE) -> list[notion_kuyrugu.Aday]:
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

    ⚠️ SIRALAMA PENCEREYI GENISLETMEZ — bu ayrim 2026-08-17'de olculdu ve
    yukaridaki gerekcenin eksik kalan yariydi. Kesme `--limit` ile ytoto
    OKUMASINDA oluyor; siralama yalnizca okunan dilimin ICINDE yer
    degistiriyor. Yani pencere disinda kalan iyi aday siralamayla
    KURTARILAMAZ, cunku listeye hic girmiyor.

    Olculdu — `Yeni` kuyrugunun TAMAMI (100 aday), her biri uretimin kendi
    `arsiv_menusu` olcutuyle:

        esigi gecen aday          12
        bunlarin penceredeki      0        <- hepsi #52 ve sonrasinda
        pencerede gecen           0        <- huni bu yuzden 0 terfi ediyordu

        Ignatius of Loyola  menu 40  (ham #87)
        H. G. Wells         menu 35  (ham #88)
        King Philip's War   menu 16  (ham #57)
        Operation Storm     menu 15  (ham #78)

    `Bosluk skoru` bir TALEP olcusu, arz olcusu degil; skoru yuksek adaylarin
    arsivi yapisal olarak zayif oldugu icin listenin basi sistematik olarak
    uretilemeyenlerle doluyor. Sıralama bunu duzeltemez, yalnizca kotu bir
    kovanin icini karistirir.
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

    ⚠️ URETIMIN OLCUMUYLE AYNI OLMAK ZORUNDA — olculdu (2026-08-19). Burasi
    `wikimedia_materials.arsiv_menusu(baslik, sinir=40)` cagiriyordu; uretim
    ise `arsiv_envanteri(baslik, bicim=...)`. Ikisi ayni sey DEGIL: envanter
    kare oranina gore de eliyor ve onbellekli, yani ayni konu icin iki taraf
    farkli sayi goruyordu (`Ernst Hanfstaengl` terfide 4, uretimde 8).
    Sayilar farkliysa "terfi edilebilir" ile "kapilabilir" ayrisir.
    """
    try:
        envanter = arsiv_envanteri(baslik, bicim=SHORTS_BICIMI)
    except Exception as hata:  # ag hatasi tek adayi atlatmali, koşumu degil
        print(f"  ⚠️ {baslik[:40]}: menu olculemedi ({str(hata)[:60]})", flush=True)
        return False, 0
    return arsiv_videoyu_tasir(envanter, ASGARI_SAHNE_ARZI), len(envanter)


def _kullanilmis_capalar() -> list[str]:
    """⚠️ Uretimle AYNI listeyi dondurmeli — bkz. `engellenen_capalar`.

    Eskiden burada `published` + `rejected` capalari toplaniyordu ve tek bir
    ret konuyu omur boyu yasakliyordu; olcum 2026-08-16'da havuzun 52'de 0'a
    dustugunu gosterdi. Butce mantigi tek yerde tutuluyor.
    """
    return engellenen_capalar()


def takilanlari_kurtar(kuru: bool = False) -> list[str]:
    """`Uretiliyor`da kalmis adaylari `Secildi`ye geri alir.

    ⚠️ NEDEN VAR — olculdu (2026-08-16). Notion'da `Ernst Hanfstaengl` **10
    gundur** `Uretiliyor` durumundaydi, `Video URL` bos: 6 Agustos'ta bir
    koşum kapip sonra olmus ve `adayi_birak` hic cagrilmamis. Kuyruk yalnizca
    `Secildi` okudugu icin o aday bir daha GORUNMUYOR — sessiz kayip.

    ⚠️ ZAMAN DAMGASI GEREKMIYOR, kilit yetiyor: bu fonksiyon `uret.sh`
    icinde uretimden ONCE ve ayni kilit altinda koşuyor (eszamanli koşum
    "atlandi | onceki kosum suruyor" ile engelleniyor). Yani bu noktada
    `Uretiliyor` duran her kayit tanim geregi OKSUZ — kilidi tutan biziz ve
    henuz hicbir aday kapmadik.

    ⚠️ KURTARMA BIR TERFIDIR, DOLAYISIYLA AYNI KAPIDAN GECMELI (olculdu
    2026-08-16, ayni gun). Ilk surum KOSULSUZ kurtariyordu ve bedeli aksam
    goruldu: `Ernst Hanfstaengl` `Secildi`ye geri kondu, uretim onu kuyrugun
    basinda buldu ve 18:00 slotunun UC denemesini de yakti (biri tam render).

        Ernst Hanfstaengl  menu  8   <- asil konu, kapi 12: GECEMEZ
        Franz Hanfstaengl  menu 40   <- DEDESI, 19. yy FOTOGRAFCISI

    Uretim arsivi zengin olan dedeyi capa secti; ama bir fotografcinin
    Commons kategorisi kendi resimleriyle degil CEKTIGI kisilerle doludur.
    Hakem tam bunu yazdi: "Scene 1: Image shows Richard Wagner", "Scene 2:
    Ernst Rietschel", "Scene 6: King Ludwig II". Gorsel 85 aldi ama iki agir
    kusur ("anlatilan kisi degil") ve altyazi 75 ile dustu.

    Aday bir kez `Secildi` olmus olabilir ama bu garanti degil: terfi kapisi
    ondan SONRA duzeldi (H2/H3 menuyu bambaska olcuyor) ve arsiv arzi zaten
    zamanla degisiyor.

    ⚠️ Olcum basarisiz olursa aday kurtarilMIYOR ve bu bilincli: fonksiyon
    HER uretim slotunda kosuyor, yani gecici bir ag hatasi kayip degil bir
    slotluk gecikme demek. `uretilebilir_mi` ag hatasini `(False, 0)` ile
    donduruyor; ikisini ayirmaya gerek yok, iki halde de aday kuyrugun basina
    konmamali.
    """
    try:
        takilanlar = notion_kuyrugu.kuyrugu_oku(
            ytoto_path=YTOTO_PATH, durum="Üretiliyor", limit=HEDEF_DERINLIK
        )
    except Exception as hata:  # kurtarma bir IYILESTIRME, beslemeyi dusuremez
        print(f"  ⚠️ takilan aday taranamadi ({str(hata)[:80]})", flush=True)
        return []
    kurtarilan: list[str] = []
    for aday in takilanlar:
        yeter, olculen = uretilebilir_mi(aday.baslik)
        if not yeter:
            # Sessiz DEGIL: aday `Uretiliyor`da kaliyor ve her slotta bu satir
            # yeniden basiliyor, yani insan Notion'da temizleyebilsin diye
            # gorunur kalıyor. Sessiz kayip bu fonksiyonun kapattigi kusurdu.
            print(
                f"  ⛔ takilmis aday kurtarilMADI: {aday.baslik} "
                f"(menu {olculen} < {ASGARI_MENU}) — uretim slotu yakardi",
                flush=True,
            )
            continue
        print(f"  ♻️ takilmis aday kurtarildi: {aday.baslik} (menu {olculen})", flush=True)
        if not kuru:
            notion_kuyrugu.adayi_birak(
                aday,
                gerekce="onceki koşum bitmeden oldu; besleyici `Secildi`ye geri aldi",
                ytoto_path=YTOTO_PATH,
            )
        kurtarilan.append(aday.baslik)
    return kurtarilan


def besle(kuru: bool = False) -> dict:
    """Kuyrugu hedef derinlige kadar doldurur; ozet doner.

    ⚠️ DERINLIK SATIR SAYMAZ, KAPILABILIR ADAY SAYAR — olculdu
    (2026-08-19, `logs/hata-20260819-023251.log`):

        `Seçildi` kuyruğu: 6/6 — eksik 0
        terfi edilen: 0
        ℹ️ aday atlandı (King Philip's War): ... 15.7 saat daha soğumada
        ℹ️ aday atlandı (Talaat Pasha): durum 'Elendi', beklenen 'Seçildi'
        ⛔ takilmis aday kurtarilMADI: Ernst Hanfstaengl (menu 4 < 12)
        ℹ️ `Seçildi` kuyrugunda kapilabilir aday yok — yedek kip devrede

    Kuyruk BOS DEGILDI, alti KAPILAMAZ adayla doluydu; `eksik <= 0` gorup
    `Yeni` kuyruguna (100+ aday) hic bakmadik. Yani gosterge "durumu
    `Secildi` olan satir" sayiyordu, uretimin KAPABILDIGI aday sayisini
    degil — kuyruk kalici olarak kilitlendi ve hat her slotta yedek kipe
    dustu.

    ⚠️ HEDEF_DERINLIK DEGISMEDI. Sorun hedefte degil sayacta; hedefi
    buyutmek zombileri alti yerine sekiz yapardi.

    ⚠️ Kuyruk gecici olarak HEDEF_DERINLIK'i ASABILIR (kapilamaz adaylar
    duruyorken kapilabilirler ekleniyor). Bilincli: sogumadaki aday saatler
    icinde kendi kendine kapilabilir hale geliyor, `Elendi` gorunenler ise
    Notion indeks gecikmesi (bkz. `run_cycle`) ve kendiliginden duzeliyor.
    Alternatifi — kuyrugu kilitli birakmak — olculdu: 7 gunde 1 huni yayini.
    """
    takilanlari_kurtar(kuru)
    mevcut = notion_kuyrugu.kuyrugu_oku(ytoto_path=YTOTO_PATH, limit=HEDEF_DERINLIK)
    state = load_state()
    kapilabilir = [
        aday
        for aday in mevcut
        if aday_kapilabilir_mi(aday.baslik, state, bicim=SHORTS_BICIMI).kapilabilir
    ]
    eksik = HEDEF_DERINLIK - len(kapilabilir)
    print(
        f"`Seçildi` kuyruğu: {len(mevcut)}/{HEDEF_DERINLIK} — "
        f"kapılabilir {len(kapilabilir)}, eksik {max(eksik, 0)}"
    )
    if eksik <= 0:
        return {"terfi": [], "elenen": [], "eksik": 0}

    kullanilmis = _kullanilmis_capalar()
    terfi: list[str] = []
    elenen: list[tuple[str, int]] = []
    olcum = 0
    tavana_carpti = False
    for aday in yeni_adaylar():
        if len(terfi) >= eksik:
            break
        # ⚠️ Uretilmis konuya benzeyeni terfi etmek, huninin sirasini
        # bozup slot yakar: `generate_content_plan` onu zaten reddediyor.
        # AGA GITMIYOR, yani tavana sayilmiyor.
        if is_duplicate_visual_anchor(aday.baslik, kullanilmis):
            elenen.append((aday.baslik, -1))
            continue
        if olcum >= OLCUM_TAVANI:
            # ⚠️ Sessiz kesme OLMAZ: bu satir olmadan "kuyrukta uretilebilir
            # aday yok" ile "kuyrugun geri kalanina bakmadim" ayni gorunurdu.
            tavana_carpti = True
            break
        olcum += 1
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
    if tavana_carpti:
        print(
            f"  ⏱️ ölçüm tavanı ({OLCUM_TAVANI}) doldu — kuyruğun geri kalanına "
            "BAKILMADI; sonraki slot kaldığı yerden değil baştan tarar",
            flush=True,
        )
    return {
        "terfi": terfi,
        "elenen": elenen,
        "eksik": eksik,
        "olcum": olcum,
        "tavana_carpti": tavana_carpti,
    }


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
