"""Slot penceresinde ikinci koşum karari (§C, 2026-08-21).

⚠️ OLCULDU — `zamanlayici.log`un 70 koşumu:

    YAYIN 11 · red 44 · HATA 15   ->  koşum basina yayin p = 0,16
    koşum medyan suresi           :  25 dk
    3 saatlik pencerede kalan bos : 156 dk
    denenen koşum                 :   1

Hat %84 ihtimalle dusuyor ve sonra 2,5 saat hicbir sey yapmiyor. 15:05
koşumu 14 dakikada dustu, 18:05'e kadar bos beklendi.

⚠️ Bu testler kabugu GERCEKTEN CALISTIRIYOR, kaynak metnini sabitlemiyor.
Bu depoda metin sabitleyen testler ayni oturumda UC KEZ kirildi ve hicbiri
gercek bir kusur bildirmedi.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
KARAR = KOK / "scripts" / "slot_karari.sh"
URET = KOK / "scripts" / "uret.sh"


def _karar(kod, kalan, yayin, kilit, uzun=0) -> bool:
    """`ikinci_kosum_gerekli_mi` kabukta calistirilir; cikis kodu dondurulur."""
    sonuc = subprocess.run(
        [
            "bash",
            "-c",
            f'. "{KARAR}"; ikinci_kosum_gerekli_mi {kod} {kalan} {yayin} '
            f"{kilit} {uzun}",
        ],
        capture_output=True,
        text=True,
    )
    return sonuc.returncode == 0


def _kabuk(ifade: str) -> str:
    """`slot_karari.sh` yuklu bir kabukta tek ifade calistirir."""
    sonuc = subprocess.run(
        ["bash", "-c", f'. "{KARAR}"; {ifade}'], capture_output=True, text=True
    )
    return sonuc.stdout.strip()


def _uzun_slot(saat) -> bool:
    sonuc = subprocess.run(
        ["bash", "-c", f'. "{KARAR}"; uzun_slot_mu {saat}'],
        capture_output=True,
        text=True,
    )
    return sonuc.returncode == 0


def _kalan(saat, dakika) -> int:
    sonuc = subprocess.run(
        ["bash", "-c", f'. "{KARAR}"; sonraki_tetige_kalan_dk {saat} {dakika}'],
        capture_output=True,
        text=True,
    )
    return int(sonuc.stdout.strip())


# --- Karar tablosu ----------------------------------------------------------


def test_KALITE_REDDINDE_ikinci_kosum_deneniyor():
    """Asil kazanc: bugun bu durumda hat 2,5 saat bos bekliyordu."""
    assert _karar(kod=2, kalan=150, yayin=1, kilit=0) is True


def test_YAYINLANDIYSA_ikinci_kosum_YOK():
    """Slot dolu; ikinci video ayni saatte zaten `completed_slots`a takilir."""
    assert _karar(kod=0, kalan=150, yayin=1, kilit=0) is False


def test_ADAY_YOKSA_ikinci_kosum_YOK():
    """Hemen yeniden denemek ayni bos kuyruga bakar."""
    assert _karar(kod=3, kalan=150, yayin=1, kilit=0) is False


def test_YAPISAL_HATADA_ikinci_kosum_YOK():
    """⚠️ Olculdu 21 Agu: uc koşum da DISK DOLU ile dustu (cikis 1).
    Yeniden denemek uc kez bosa render ederdi."""
    assert _karar(kod=1, kalan=150, yayin=1, kilit=0) is False


def test_KILIT_DOLUYSA_ikinci_kosum_YOK():
    """Baska bir koşum suruyor; ikincisi zaten kilide takilirdi."""
    assert _karar(kod=2, kalan=150, yayin=1, kilit=1) is False


@pytest.mark.parametrize("kalan", [34, 20, 0])
def test_PENCERE_DARSA_ikinci_kosum_YOK(kalan):
    """⚠️ Koşum medyani 25 dk. Tetik aninda kilit doluysa zamanlayici
    'atlandi | onceki kosum suruyor' yazar, yani bir SONRAKI slot yanar."""
    assert _karar(kod=2, kalan=kalan, yayin=1, kilit=0) is False


@pytest.mark.parametrize("kalan", [35, 60, 150])
def test_PENCERE_YETIYORSA_deneniyor(kalan):
    assert _karar(kod=2, kalan=kalan, yayin=1, kilit=0) is True


@pytest.mark.parametrize("yayin", [10, 11, 20])
def test_GUNLUK_TAVANDA_ikinci_kosum_YOK(yayin):
    """⚠️ Tavan bir EMNIYET SUPABI; eski kota gerekcesi curudu (2026-08-23).

    Burada "videos.insert 1600 birim -> gunde 6 yukleme" yaziyordu. Google'in
    belgesi `videos.insert`in AYRI bir kovasi oldugunu ve gunluk 100 cagri
    verildigini soyluyor. Yanlis tavan, izgara siklasinca (6 -> 9 Shorts
    slotu) GERCEK yayinlari bloklamaya baslardi.
    """
    assert _karar(kod=2, kalan=150, yayin=yayin, kilit=0) is False


@pytest.mark.parametrize("yayin", [0, 1, 3, 4])
def test_TAVANIN_ALTINDA_deneniyor(yayin):
    """Tavanin ALTINDAKI her yayin sayisinda ikinci koşum denenebilmeli.

    ⚠️ 2026-09-12'de parametreler [0, 3, 5, 6, 9] idi ve 6/9 bir REGRESYON
    KILIDIYDI (eski yanlis tavan 6 onlari bloklardi). Izgara tasarruf icin
    10 tetikten 5'e inince tavan da 5'e dustu, yani 5/6/9 artik tanim geregi
    tavanin ALTINDA degil ve o kilit bu haliyle anlamsizlasti.

    ⚠️ Kilidin KENDISI kaybolmadi, turetilmis haliyle duruyor:
    `test_TAVAN_hicbir_SLOTU_bloklamiyor` tavanin gunun hicbir slotunu
    kesemeyecegini TETIK SAYISINDAN turetiyor, yani izgara ne olursa olsun
    ayni ozelligi sinar. Sabit sayi yerine turetilmis kilit daha saglam.
    """
    assert _karar(kod=2, kalan=150, yayin=yayin, kilit=0) is True


def test_TAVAN_TETIK_SAYISINDAN_turuyor():
    """⚠️ Sayi ICAT EDILMIYOR: bir slot yayinladiktan sonra ikinci koşum
    yapmiyor (`ikinci_kosum_gerekli_mi` yalnizca cikis 2'de donuyor), yani
    gun icinde MUMKUN olan en fazla yayin = tetik sayisi. Tavan boylece
    yapisi geregi baglamiyor ama patolojik donguyu kesiyor.

    Mutasyon: tavani sabit bir sayiya (6) donmek bu testi dusurur.
    """
    tavan = int(_kabuk("echo $GUNLUK_YUKLEME_TAVANI"))
    tetik_sayisi = len(_kabuk("echo $TETIK_SAATLERI").split())

    assert tavan == tetik_sayisi, "tavan tetik sayisindan turemeli"


def test_TAVAN_hicbir_SLOTU_bloklamiyor():
    """⚠️ Asil ozellik: tavan gunun HICBIR slotunda bir yayini kesemez.

    Mutasyon: tavani tetik sayisinin ALTINA cekmek bu testi dusurur.
    """
    tetik_sayisi = len(_kabuk("echo $TETIK_SAATLERI").split())

    # Gun icinde ulasilabilecek en yuksek yayin sayisi bir eksigi; o noktada
    # bile son slot denenebilmeli.
    assert _karar(kod=2, kalan=150, yayin=tetik_sayisi - 1, kilit=0) is True


# --- Pencere hesabi ---------------------------------------------------------


@pytest.mark.parametrize(
    "saat,dakika,beklenen",
    [
        # ⚠️ IZGARA 2026-09-12'de 10 tetikten 5'e indi: 0 · 6 · 11 · 16 · 21.
        # Sayilar BILEREK acikca yazili, `TETIK_SAATLERI`den turetilmiyor:
        # turetilseydi test izgara degisiminde sessizce gecerdi ve tripwire
        # islevini kaybederdi. Nitekim bu degisiklikte DUSTU ve guncellendi.
        (0, 30, 335),  # UZUN slot yeni basladi -> 06:05, pencere 6 saat
        (6, 30, 275),  # 11:05 — ⚠️ eski 2 saatlik bantta bu 35 idi
        (8, 30, 155),  # 11:05
        (12, 5, 240),  # 16:05
        (13, 0, 185),  # 16:05
        (15, 19, 46),  # 16:05
        (20, 30, 35),  # 21:05 — gunun SON Shorts slotu (degismedi)
        (21, 10, 175),  # ⚠️ GECE YARISI SARMASI -> uzun slotun kosu pisti
        (23, 59, 6),  # sarmanin sinir vakasi
    ],
)
def test_sonraki_tetige_kalan_dogru(saat, dakika, beklenen):
    """⚠️ IZGARA DUZENSIZ (0 5 7 9 11 13 15 17 19 21) — eski
    `(saat / 3 + 1) * 3` formulu 06:30'da bir sonraki tetigi 09:05 sanip
    155 dk gorurdu, gercekte 07:05 yani 35 dk. Yani ikinci koşumu kalmayan
    pencerede baslatip BIR SONRAKI slotu yakardi.

    Mutasyon: 3 saatlik formule geri donmek bu testi dusurur.
    """
    assert _kalan(saat, dakika) == beklenen


def test_UZUN_SLOTUN_kosu_pisti_3_SAAT():
    """⚠️ 21:05 gunun son Shorts slotu ve ondan sonra 00:05'e kadar tetik YOK.

    Gerekcesi olcum: Shorts koşumu tek koşumda max 60 dk, iki koşumda 144 dk
    surdu. 23:05'e bir tetik konsaydi 1/4 ihtimalle kilidi 00:05'e tasiyip
    UZUN slotu yakardi.

    Mutasyon: 23:05 tetigi eklemek bu testi dusurur.
    """
    assert _kalan(21, 10) == 175, "21:05 sonrasi sonraki tetik 00:05 olmali"
    assert _kalan(22, 0) == 125


def test_kalan_HIC_NEGATIF_olmuyor():
    """⚠️ Sarma olmadan 20:30 NEGATIF donerdi ve `[ "$kalan" -ge 35 ]`
    sessizce yanlis tarafa duserdi — ikinci koşum hic denenmezdi."""
    for saat in range(24):
        for dakika in (0, 30, 59):
            assert _kalan(saat, dakika) > 0, f"{saat}:{dakika}"


def test_SEKIZLIK_tuzagi_yok():
    """⚠️ `date +%H` saat 08/09'da '08'/'09' veriyor ve bash bunu sekizlik
    sanip hata verir. Ayni tuzak `uret.sh`te bir kez yasandi.

    ⚠️ Beklenen deger izgarayla birlikte degisti (2026-09-12): 08:09'dan
    sonraki tetik artik 09:05 degil 11:05. Sinanan sey DEGISMEDI — onemli
    olan cagrinin HATA VERMEMESI ve dogru sayiyi uretmesi.
    """
    assert _kalan("08", "09") == 176  # 11:05


# --- Kol secimi -------------------------------------------------------------


def test_SAAT_SIFIR_uzun_kol():
    """⚠️ Kanal sahibinin karari: 00:05 uzun video, kalani Shorts.

    Mutasyon: kol secimini sabitlemek bu testi dusurur.
    """
    assert _uzun_slot(0) is True


@pytest.mark.parametrize("saat", [5, 8, 11, 14, 17, 20])
def test_KALAN_TETIKLER_shorts(saat):
    assert _uzun_slot(saat) is False


def test_uzun_slot_SEKIZLIK_tuzagina_dusmuyor():
    """`date +%H` saat 08'de "08" veriyor."""
    assert _uzun_slot("08") is False
    assert _uzun_slot("00") is True


# --- Pencere esigi BICIME BAGLI --------------------------------------------


def test_UZUN_pencere_esigi_120():
    """⚠️ Olculdu: en KISA uzun koşum 100 dk (Herculaneum), en uzunu 210
    (Alhambra). 35 dakikalik artikla uzun koşum baslatmak kilidi bir
    sonraki tetige tasirdi.

    Mutasyon: esigi 35'e dusurmek bu testi dusurur.
    """
    assert _kabuk("asgari_pencere_dk 1") == "120"
    assert _kabuk("asgari_pencere_dk 0") == "35"


def test_UZUN_kolda_DAR_pencerede_ikinci_kosum_YOK():
    """Shorts icin yeterli olan 60 dk, uzun icin YETMIYOR."""
    assert _karar(kod=2, kalan=60, yayin=1, kilit=0, uzun=0) is True
    assert _karar(kod=2, kalan=60, yayin=1, kilit=0, uzun=1) is False


def test_UZUN_kolda_GENIS_pencerede_ikinci_kosum_VAR():
    assert _karar(kod=2, kalan=150, yayin=1, kilit=0, uzun=1) is True


def test_KOL_verilmezse_SHORTS_esigi():
    """⚠️ Geriye donuk uyum: bes arguman gecmeyen cagiran bugunku esigi alir."""
    sonuc = subprocess.run(
        ["bash", "-c", f'. "{KARAR}"; ikinci_kosum_gerekli_mi 2 60 1 0'],
        capture_output=True,
        text=True,
    )
    assert sonuc.returncode == 0


# --- Tetik dizisi TEK KAYNAK ------------------------------------------------


def test_PLIST_tetikleri_TETIK_SAATLERI_ile_AYNI():
    """⚠️ Ayrisirlarsa `sonraki_tetige_kalan_dk` gercekte OLMAYAN bir tetigi
    bekler ve ikinci koşum penceresi yanlis hesaplanir.

    Mutasyon: iki taraftan birinde bir saati degistirmek bu testi dusurur.
    """
    import plistlib

    plist = KOK / "scripts" / "com.shemz.uretim.plist"
    with plist.open("rb") as akis:
        tetikler = plistlib.load(akis)["StartCalendarInterval"]

    plist_saatleri = [t["Hour"] for t in tetikler]
    kabuk_saatleri = [int(x) for x in _kabuk("echo $TETIK_SAATLERI").split()]

    assert plist_saatleri == kabuk_saatleri
    assert {t["Minute"] for t in tetikler} == {5}, "hepsi :05'te olmali"


def test_PLIST_yuklenince_KOSMUYOR():
    """⚠️ `launchctl load` bir video uretmeye baslamamali; kurulum bir
    uretim karari degil."""
    import plistlib

    plist = KOK / "scripts" / "com.shemz.uretim.plist"
    with plist.open("rb") as akis:
        assert plistlib.load(akis)["RunAtLoad"] is False


# --- Gunluk yayin sayaci ----------------------------------------------------


def _bugunku(durum_yolu: Path) -> str:
    sonuc = subprocess.run(
        [
            "bash",
            "-c",
            f'. "{KARAR}"; bugunku_yayin_sayisi "{sys.executable}" "{durum_yolu}"',
        ],
        capture_output=True,
        text=True,
    )
    return sonuc.stdout.strip()


def test_gunluk_sayac_BUGUNU_sayiyor(tmp_path):
    from datetime import date, timedelta

    bugun = date.today().isoformat()
    dun = (date.today() - timedelta(days=1)).isoformat()
    d = tmp_path / "state.json"
    d.write_text(
        json.dumps(
            {
                "published": [
                    {"published_at": f"{bugun}T09:00:00"},
                    {"published_at": f"{bugun}T12:00:00"},
                    {"published_at": f"{dun}T23:00:00"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _bugunku(d) == "2", "dunku yayin bugune sayilmis"


def test_gunluk_sayac_BOZUK_dosyada_SIFIR(tmp_path):
    """⚠️ Okunamayan durum dosyasi yuzunden uretimi durdurmak, tavani bir kez
    asmaktan kotu — kota hatasi zaten `uret.sh` tarafinda yakalaniyor."""
    d = tmp_path / "state.json"
    d.write_text("{bozuk json", encoding="utf-8")
    assert _bugunku(d) == "0"


def test_gunluk_sayac_DOSYA_YOKSA_SIFIR(tmp_path):
    assert _bugunku(tmp_path / "olmayan.json") == "0"


def test_gunluk_sayac_PYTHON_CALISMAZSA_SIFIR(tmp_path):
    """⚠️ MUTASYON M8 BURADAN KACTI (2026-08-21).

    Kabuktaki `|| echo 0` yedegini silmek hicbir testi dusurmuyordu, cunku
    BOZUK JSON durumunu python'un kendi `try/except`i zaten karsiliyor. Kabuk
    yedegi BASKA bir seyi koruyor: python'un hic calismamasi.

    ⚠️ Bu gercek bir risk: `uret.sh` launchd altinda DAR bir PATH ile
    calisiyor (kabuk profili okunmuyor) ve ayni dosya bunun bir kez
    yasandigini yaziyor — `hermes` ciplak adla bulunamamisti. Yedek olmazsa
    fonksiyon bos dizge dondururdu ve `[ "" -lt 6 ]` kabukta HATA verip
    ikinci koşumu sessizce oldururdu.
    """
    d = tmp_path / "state.json"
    d.write_text("{}", encoding="utf-8")
    sonuc = subprocess.run(
        [
            "bash",
            "-c",
            f'. "{KARAR}"; bugunku_yayin_sayisi /olmayan/python "{d}"',
        ],
        capture_output=True,
        text=True,
    )
    assert sonuc.stdout.strip() == "0", (
        f"python yokken sayac bos dondu: {sonuc.stdout!r}"
    )


# --- Baglanti: uret.sh gercekten cagiriyor mu ------------------------------
# ⚠️ M9/M8 DERSI (bu oturum): "deger dogru" olcmek yetmiyor, hattin onu
# KULLANDIGI da olculmeli. Iki mutasyon tam bu bosluktan kacti.


def test_uret_sh_karari_YUKLUYOR_ve_CAGIRIYOR():
    govde = URET.read_text(encoding="utf-8")

    assert "slot_karari.sh" in govde, "karar dosyasi yuklenmiyor"
    assert "ikinci_kosum_gerekli_mi" in govde, "karar cagrilmiyor"


def test_IKINCI_kosum_FROM_NOTION_gecmiyor():
    """⚠️ Kanal sahibinin karari: ikinci deneme kanitlanmis capa havuzundan.

    Bayrak davranisi kodda dogrulandi: `--from-notion` yokken `aday` None
    kalir, `--yedek-konu` `no-candidate` donusunu engeller ve akis
    `kaynak = "yedek"` daline duser."""
    govde = URET.read_text(encoding="utf-8")
    bas = govde.index("ikinci_kosum_gerekli_mi")
    kuyruk = govde[bas:]

    assert "uretim_kosumu --yedek-konu" in kuyruk, "ikinci koşum yedek kipte degil"
    ikinci = kuyruk[kuyruk.index("uretim_kosumu --yedek-konu") :][:60]
    assert "--from-notion" not in ikinci, (
        f"ikinci koşum kuyruga bakiyor, havuza degil: {ikinci!r}"
    )


def test_ILK_kosum_DAVRANISI_degismedi():
    """⚠️ Regresyon kilidi: birinci koşum bugunku bayraklarla kalmali."""
    govde = URET.read_text(encoding="utf-8")

    assert "uretim_kosumu --from-notion --yedek-konu" in govde


def test_PLAN_REDLERI_her_kosumdan_sonra_yaziliyor():
    """⚠️ Ikinci koşumun denemeleri de butce yakiyor; #41'in olcmek istedigi
    sinyal tam olarak o. Tek seferlik cikarim ikinci koşumu kacirirdi."""
    govde = URET.read_text(encoding="utf-8")

    assert govde.count("plan_redlerini_yaz") >= 3, (
        "plan reddi cikarimi her koşumdan sonra cagrilmiyor"
    )


def test_UZUN_kolda_SAHNE_SAYISI_gecmiyor():
    """⚠️ CLI `--uzun` ile `--sahne-sayisi`yi YASAKLIYOR (sahne sayisi deneyi
    Shorts koluna ait). Gecirilseydi uzun slot her gun arguman hatasiyla
    olurdu.

    Mutasyon: uzun kola `--sahne-sayisi` eklemek bu testi dusurur.
    """
    govde = URET.read_text(encoding="utf-8")
    bas = govde.index("if uzun_slot_mu")
    uzun_dal = govde[bas : govde.index("else", bas)]

    assert "--uzun" in uzun_dal
    assert "--sahne-sayisi" not in uzun_dal


def test_SHORTS_kolunda_SAHNE_SAYISI_geciyor():
    """⚠️ Regresyon kilidi: sahne sayisi deneyi Shorts'ta SURUYOR."""
    govde = URET.read_text(encoding="utf-8")
    bas = govde.index("if uzun_slot_mu")
    shorts_dal = govde[govde.index("else", bas) : govde.index("fi", bas)]

    assert "--sahne-sayisi" in shorts_dal
    assert "--uzun" not in shorts_dal


def test_IKI_KOSUM_da_AYNI_kolda():
    """⚠️ "Uzun israr et": uzun slotun ikinci denemesi de UZUN, Shorts'a
    dusulmuyor.

    ⚠️ Olculdu (mutasyon M16): `"${KOL_BAYRAKLARI[@]}"` GENISLEMESINI saymak
    YETMIYOR. Ikinci koşumdan once diziyi YENIDEN ATAMAK genisleme sayisini
    hic degistirmiyor — koşum sessizce Shorts'a duserdi ve test gecerdi.
    Olculmesi gereken sey ATAMA: dizi yalnizca kol secim blogunda, iki
    dalda birer kez kuruluyor.
    """
    govde = URET.read_text(encoding="utf-8")

    assert govde.count("KOL_BAYRAKLARI=(") == 2, (
        "kol bayraklari kol secim blogunun DISINDA yeniden atanmis"
    )
    # Iki atamanin ikisi de `if uzun_slot_mu ... fi` blogunun icinde.
    bas = govde.index("if uzun_slot_mu")
    blok = govde[bas : govde.index("\nfi\n", bas)]
    assert blok.count("KOL_BAYRAKLARI=(") == 2

    assert govde.count('"${KOL_BAYRAKLARI[@]}"') == 1
    # Iki koşum da ayni fonksiyondan geciyor.
    assert govde.count("uretim_kosumu --") == 2


def test_IKINCI_kosum_karari_KOLU_aliyor():
    """⚠️ Kol gecirilmezse uzun slot Shorts esigiyle (35 dk) olculur ve
    kilit bir sonraki tetige tasar."""
    govde = URET.read_text(encoding="utf-8")
    bas = govde.index("ikinci_kosum_gerekli_mi")
    cagri = govde[bas : govde.index("; then", bas)]

    assert "$UZUN_KOL" in cagri, f"kol gecmiyor: {cagri!r}"


def test_KABUK_sozdizimi_saglam():
    for betik in (URET, KARAR):
        sonuc = subprocess.run(["bash", "-n", str(betik)], capture_output=True)
        assert sonuc.returncode == 0, f"{betik.name}: {sonuc.stderr.decode()}"


# --- Sahne deneyi kolu ------------------------------------------------------
#
# ⚠️ Bu kolun 2026-08-23'e kadar HIC TESTI YOKTU ve `uret.sh` govdesinde
# `(SAAT / 3) % 2` olarak duruyordu. 3 saatlik izgarada dengeliydi; 2 saatlik
# bantta 2:1 carpitiyordu (8 sahne 6 slot / 6 sahne 3 slot), yani
# `tutunma-ilk-sahne-degisiminde-dusuyor` deneyini SESSIZCE curutuyordu.
# Bozuk oldugu ancak elle hesaplanarak gorulebildi — testin yoklugu kusurun
# kendisiydi.


def _shorts_saatleri() -> list[int]:
    saatler = [int(x) for x in _kabuk("echo $TETIK_SAATLERI").split()]
    uzun = int(_kabuk("echo $UZUN_SAAT"))
    return [s for s in saatler if s != uzun]


def _kollar() -> list[int]:
    return [int(_kabuk(f"sahne_kolu {saat}")) for saat in _shorts_saatleri()]


def test_SAHNE_KOLU_dengeli():
    """⚠️ Asil ozellik: iki kol arasindaki fark EN FAZLA BIR slot.

    Eski `(SAAT / 3) % 2` bu izgarada 6/3 veriyordu — deneyin bir kolu
    digerinin iki kati sans aliyordu.

    Mutasyon: kolu saatten turetmeye (`(SAAT / 3) % 2`) donmek bu testi
    dusurur.
    """
    kollar = _kollar()
    alti = kollar.count(6)
    sekiz = kollar.count(8)

    assert alti + sekiz == len(kollar), f"6/8 disi kol var: {kollar}"
    assert abs(alti - sekiz) <= 1, f"kol dengesizligi 1'den buyuk: {kollar}"


def test_SAHNE_KOLU_ardisik_slotlarda_ALTERNATIF():
    """⚠️ Denge tek basina yetmez: 8·8·8·8·8·6·6·6·6 de "dengeli" olurdu ama
    gunun ilk yarisi tek kola giderdi ve gun ici etkiler (izleyici saati)
    kola karisirdi.

    Mutasyon: kolu sabitlemek ya da sirayi bozmak bu testi dusurur.
    """
    kollar = _kollar()

    for onceki, sonraki in zip(kollar, kollar[1:]):
        assert onceki != sonraki, f"ardisik iki slot ayni kolda: {kollar}"


def test_SAHNE_KOLU_SEKIZLIK_tuzagina_dusmuyor():
    """⚠️ `date +%H` saat 08/09'da '08'/'09' veriyor; bash bunu sekizlik
    sanip hata verir ve kol sessizce yanlis tarafa duserdi."""
    assert _kabuk("sahne_kolu 09") in {"6", "8"}
    assert _kabuk("sahne_kolu 08") in {"6", "8"}


def test_SAHNE_KOLU_izgara_disinda_GECERLI_deger():
    """⚠️ Elle koşum izgara disi bir saatte olabilir. Bos deger donerse
    `--sahne-sayisi ""` gecer ve CLI hatasi uretir."""
    for saat in (2, 6, 10, 22):
        assert _kabuk(f"sahne_kolu {saat}") in {"6", "8"}, f"saat {saat}"


def test_SAHNE_KOLU_uret_sh_TARAFINDAN_kullaniliyor():
    """Baglanti testi — fonksiyon tanimli olup cagrilmazsa islevsiz.

    ⚠️ YORUM SATIRLARI AYIKLANIYOR, ve bu tesadufi degil: ilk yazimda test
    butun dosyada eski formulu ariyordu ve DUSTU — cunku o dize, formulun
    neden kaldirildigini ANLATAN yorumda geciyor. Metne cakili test kendi
    belgelendirmesini kusur sandi. Olculecek sey KOD, dosya degil.

    Mutasyon: kolu `uret.sh` govdesinde yeniden hesaplamak bu testi dusurur.
    """
    kod = "\n".join(
        satir
        for satir in URET.read_text(encoding="utf-8").splitlines()
        if not satir.lstrip().startswith("#")
    )

    assert "sahne_kolu" in kod, "kol fonksiyonu cagrilmiyor"
    assert "% 2" not in kod, "kol hala govdede hesaplaniyor"


def test_SAHNE_KOLU_kaynak_SIRASI_dogru():
    """⚠️ `sahne_kolu` `TETIK_SAATLERI`yi geziyor, yani `slot_karari.sh`
    SAHNE hesabindan ONCE kaynaklanmali. Eskiden sonra geliyordu (hesap bir
    formuldu ve hicbir seye bagli degildi).

    Mutasyon: kaynak satirini SAHNE atamasindan sonraya almak (ya da silmek)
    bu testi dusurur.
    """
    govde = URET.read_text(encoding="utf-8")
    kaynak_satiri = '. "$KOK/scripts/slot_karari.sh"'

    # ⚠️ Capa YORUMDAKI ad DEGIL, gercek kaynak KOMUTU: "slot_karari.sh"
    # dizesi bu dosyada daha once bir yorumda ve bir shellcheck yonergesinde
    # geciyor, yani onu aramak siranin bozuldugunu goremezdi.
    assert kaynak_satiri in govde, "kaynak satiri hic yok"
    assert govde.index(kaynak_satiri) < govde.index("SAHNE=")


# --- Ilk koşum tavan kapisi -------------------------------------------------


def _atlansin(yayin) -> bool:
    sonuc = subprocess.run(
        ["bash", "-c", f'. "{KARAR}"; tetik_atlansin_mi {yayin}'],
        capture_output=True,
        text=True,
    )
    return sonuc.returncode == 0


def test_ILK_KOSUM_tavandayken_ATLANIYOR():
    """⚠️ Bugune kadar tavan yalnizca IKINCI koşumu kapatiyordu; ilk koşum
    ~30 dakikalik render'i yakip yuklemede `quotaExceeded` ile oluyordu.

    Mutasyon: kapiyi kaldirmak bu testi dusurur.
    """
    tavan = int(_kabuk("echo $GUNLUK_YUKLEME_TAVANI"))

    assert _atlansin(tavan) is True
    assert _atlansin(tavan + 5) is True


def test_ILK_KOSUM_tavanin_ALTINDA_calisiyor():
    """⚠️ Regresyon kilidi: kapi her zaman kapaliysa hat hic video uretmez."""
    tavan = int(_kabuk("echo $GUNLUK_YUKLEME_TAVANI"))

    for yayin in (0, 1, tavan - 1):
        assert _atlansin(yayin) is False, f"yayin={yayin} atlanmamaliydi"


def test_ILK_KOSUM_kapisi_uret_sh_de_URETIMDEN_ONCE():
    """⚠️ Kapi uretim koşumundan SONRA cagrilirsa render zaten yanmis olur.

    Mutasyon: kapiyi ilk `uretim_kosumu` satirinin altina almak bu testi
    dusurur.
    """
    govde = URET.read_text(encoding="utf-8")

    assert govde.index("tetik_atlansin_mi") < govde.index("uretim_kosumu --from-notion")


def test_TAVAN_SAYACI_gercek_durum_dosyasini_okuyor(tmp_path):
    """⚠️ Sayac kabukta calisiyor ve bugunun tarihiyle suzuyor; test metne
    degil GERCEK bir `state.json`a bakiyor."""
    from datetime import datetime, timedelta

    bugun = datetime.now().astimezone()
    dun = bugun - timedelta(days=1)
    durum = tmp_path / "state.json"
    durum.write_text(
        json.dumps(
            {
                "published": [
                    {"published_at": bugun.isoformat()},
                    {"published_at": bugun.isoformat()},
                    {"published_at": dun.isoformat()},
                ]
            }
        ),
        encoding="utf-8",
    )

    sayi = _kabuk(f'bugunku_yayin_sayisi "{sys.executable}" "{durum}"')

    assert sayi == "2", "yalnizca BUGUNKU yayinlar sayilmali"


def test_TAVAN_SAYACI_okunamayan_dosyada_ACIK_dusuyor(tmp_path):
    """⚠️ Okunamayan bir durum dosyasi uretimi DURDURMAMALI — tavani bir kez
    asmak, butun gunu bos gecirmekten iyidir."""
    bozuk = tmp_path / "bozuk.json"
    bozuk.write_text("{ bu json degil", encoding="utf-8")

    assert _kabuk(f'bugunku_yayin_sayisi "{sys.executable}" "{bozuk}"') == "0"
    assert _atlansin(0) is False


# --- Gecikmis tetik (uyku) — DW-139 ------------------------------------------


def _gecen(saat, dakika) -> int:
    return int(_kabuk(f"tetikten_gecen_dk {saat} {dakika}"))


@pytest.mark.parametrize(
    "saat,dakika,beklenen",
    [
        (16, 5, 0),  # tam tetik aninda
        (16, 12, 7),  # launchd'nin olagan birkac dakikasi
        (5, 13, 308),  # 12 Eyl: 00:05 tetiginden 05:13'e (05:05 artik tetik degil)
        (11, 12, 7),  # 12 Eyl: 05:13 koşumu 11:12'de uyandi — 11:05 tetigine gore
        (0, 3, 178),  # gunun ilk tetiginden ONCE: son tetik DUNUN 21:05'i
        (23, 59, 174),  # 21:05'ten sonra
    ],
)
def test_tetikten_gecen_dogru(saat, dakika, beklenen):
    """⚠️ Olculdu (2026-09-12): uyuyan makinede launchd tetigi uyaninca
    atesliyor; 05:05 tetigi 05:13'te, 00:05 tetigi 00:13'te basladi. Gecikme
    izgaradaki EN SON tetige gore olculur, en yakina degil.

    Mutasyon: `-le` yerine `-lt` -> tam tetik aninda "dunun sonuncusu"na
    duser ve (16,5,0) satiri kirilir.
    """
    assert _gecen(saat, dakika) == beklenen


def test_gecen_HIC_NEGATIF_olmuyor():
    """Gece yarisi sarmasi: 00:00-00:04 arasinda son tetik dunun 21:05'i."""
    for saat in range(24):
        for dakika in (0, 4, 5, 6, 30, 59):
            assert _gecen(saat, dakika) >= 0, f"{saat}:{dakika}"


def test_gecen_SEKIZLIK_tuzagina_dusmuyor():
    assert _gecen("08", "09") == 124  # 06:05'ten


def test_uret_sh_GECIKMEYI_logluyor_ama_slotu_ATLAMIYOR():
    """`uret.sh` fonksiyonu cagirmali ve sonucu `exit` degil `yaz` ile
    islemeli: gecikmis bir tetik hala bir tetiktir, slot yakilmaz.

    Mutasyon: `yaz "tetik gecikmesi"` satirini `exit 0` yap -> bu test duser.
    """
    metin = URET.read_text(encoding="utf-8")
    assert "tetikten_gecen_dk" in metin
    blok = metin.split('GECIKME_DK="$(tetikten_gecen_dk)"', 1)[1].split("fi", 1)[0]
    assert 'yaz "tetik gecikmesi' in blok
    assert "exit" not in blok


def test_uret_sh_CAFFEINATE_ile_bosta_uykuyu_tutuyor():
    """`caffeinate -i -w $$`: kilit betikle birlikte olmeli; yoksa her tetik
    bir caffeinate sureci birakir. `command -v` korumasi Linux CI icin."""
    metin = URET.read_text(encoding="utf-8")
    assert "caffeinate -i -w $$ &" in metin
    assert "command -v caffeinate" in metin
