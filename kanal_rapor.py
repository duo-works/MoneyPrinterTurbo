"""Kanal analitigi — izlenmenin ARKASINDAKI veriyi okur.

⚠️ NEDEN VAR — 2026-08-14. Bu hat aylardir hakem skorunu (gorsel hizalama,
altyazi okunabilirligi) optimize ediyor ama IZLEYICININ ne yaptigina dair
tek bir olcum yok. Kanalda 11 video, ~2.200 izlenme ve **1 abone** var;
biri 709, digeri 5 izlenmis ve FARKIN SEBEBI bilinmiyor.

Ayni kusur bu hatta uc kez olculdu: olculmemis bir vekil degiskeni
iyilestirmek. Hakem skoru "gorsel cumleye uyuyor mu" diyor; "insan izliyor
mu" demiyor.

⚠️ TOKEN AYRI TUTULUYOR. Analitik kapsami `youtube_upload.SCOPES`e
EKLENMEDI, cunku o listeyi genisletmek diskteki token'i yetersiz kilar ve
`get_authenticated_service` yeni bir ONAY EKRANI acar — arka planda calisan
uretim koşumu orada suresiz beklerdi. Yukleme yolu bu dosyadan
etkilenmiyor; analitik kendi token'ini kullaniyor ve yoksa yalnizca bu
komut durur.

Kullanim:
    python kanal_rapor.py            # son 28 gun
    python kanal_rapor.py --gun 90
    python kanal_rapor.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

KOK = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_FILE = os.path.join(KOK, "client_secret.json")
TOKEN_FILE = os.path.join(KOK, "youtube_analytics_token.json")
STATE_YOLU = os.path.join(KOK, "storage", "youtube_automation", "state.json")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Video basina cekilen olcumler. `averageViewPercentage` Shorts'ta en
# belirleyici olan: izlenme sayisi dagitimin sonucu, tutunma ise SEBEBI.
VIDEO_OLCUMLERI = (
    "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
    "subscribersGained,likes,shares"
)


def _token_yaz(creds) -> None:
    """Token'i yalnizca sahibinin okuyabilecegi izinle yazar (yukleme tarafiyla ayni kural)."""
    with open(TOKEN_FILE, "w", encoding="utf-8") as dosya:
        dosya.write(creds.to_json())
    os.chmod(TOKEN_FILE, 0o600)


def yetkilendir(etkilesimli: bool = True):
    """Analitik kimlik bilgisi. Yoksa ve `etkilesimli` degilse ACIK HATA verir.

    ⚠️ Onay ekrani TARAYICI gerektiriyor. Zamanlanmis ya da arka planda
    calisan bir cagri `run_local_server`da suresiz beklerdi; bu yuzden
    etkilesimsiz kipte beklemek yerine ne yapilmasi gerektigini yazip
    duruyoruz.
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # `Credentials.valid` KAPSAM KONTROL ETMIYOR — ayni tuzak yukleme
    # tarafinda da notlu (youtube_upload.get_authenticated_service).
    if creds and creds.valid and creds.has_scopes(SCOPES):
        return creds

    if creds and creds.expired and creds.refresh_token and creds.has_scopes(SCOPES):
        try:
            creds.refresh(Request())
            _token_yaz(creds)
            return creds
        except RefreshError:
            creds = None
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)

    if not etkilesimli:
        raise RuntimeError(
            "Analitik yetkisi yok. Bir kez tarayicidan onay gerekiyor:\n"
            "    python kanal_rapor.py --yetkilendir\n"
            "Bu komut yukleme token'ina DOKUNMAZ."
        )
    if not os.path.exists(CLIENT_SECRET_FILE):
        sys.exit(f"client_secret.json bulunamadi: {CLIENT_SECRET_FILE}")
    akis = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = akis.run_local_server(port=0)
    _token_yaz(creds)
    return creds


AKIS_DURUM_FILE = os.path.join(KOK, ".analitik_akis_durumu.json")
TELEFON_REDIRECT = "http://localhost:8765/"
"""Desktop istemcilerde `http://localhost` her portla kabul ediliyor.

Bu adreste HICBIR SEY DINLEMIYOR ve dinlemesi de gerekmiyor: telefon
onaydan sonra buraya yonlendirilince "baglanilamadi" sayfasi gosterir ama
adres cubugunda `?code=...` durur. Ihtiyacimiz olan tek sey o adres.
"""


def telefon_baglantisi() -> str:
    """Onay baglantisini uretir ve akis durumunu diske yazar.

    ⚠️ NEDEN IKI ADIM. Normal akis (`run_local_server`) Mac'te bir sunucu
    acip tarayicinin `localhost`a donmesini bekliyor; TELEFON Mac'in
    `localhost`una ulasamaz. `run_console` ise kutuphaneden kaldirildi
    (google-auth-oauthlib 1.x) cunku Google OOB akisini kapatti.

    Geriye tek saglam yol kaliyor: baglantiyi uret, onay telefonda verilsin,
    donus adresi geri getirilsin. PKCE dogrulayicisi (`code_verifier`) ilk
    adimda uretildigi icin diske yaziliyor — yoksa ikinci adim baska bir
    surecte calisamazdi.
    """
    akis = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    akis.redirect_uri = TELEFON_REDIRECT
    # ⚠️ `include_granted_scopes` BILEREK YOK. Denendi (2026-08-14) ve
    # olculdu: bayrak acikken Google, ayni istemciye DAHA ONCE verilmis
    # izinleri de jetona ekliyor. Donen jeton `youtube.upload` ve
    # `youtube.force-ssl` tasiyordu — yani video silip duzenleyebilen bir
    # yetki, "rapor okuma" komutunun icinde.
    #
    # Daha da sinsisi: kutuphanenin `credentials.scopes` alani yalnizca
    # ISTENEN iki readonly kapsami gosteriyordu. Gercek kapsam ancak
    # Google'in `tokeninfo` ucuna sorulunca goruldu. Yani "kapsam
    # readonly" iddiasi yerel nesneye bakarak DOGRULANAMIYOR.
    baglanti, durum = akis.authorization_url(
        access_type="offline",  # yenileme jetonu icin
        prompt="consent",
    )
    with open(AKIS_DURUM_FILE, "w", encoding="utf-8") as dosya:
        json.dump(
            {"state": durum, "code_verifier": akis.code_verifier, "redirect_uri": TELEFON_REDIRECT},
            dosya,
        )
    os.chmod(AKIS_DURUM_FILE, 0o600)
    return baglanti


def telefon_tamamla(donus_adresi: str):
    """Telefondan gelen donus adresiyle jetonu alir."""
    if not os.path.exists(AKIS_DURUM_FILE):
        raise RuntimeError(
            "Once baglanti uretilmeli:\n    python kanal_rapor.py --yetkilendir-telefon"
        )
    with open(AKIS_DURUM_FILE, encoding="utf-8") as dosya:
        durum = json.load(dosya)
    akis = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET_FILE, SCOPES, state=durum["state"]
    )
    akis.redirect_uri = durum["redirect_uri"]
    akis.code_verifier = durum["code_verifier"]
    akis.fetch_token(authorization_response=donus_adresi.strip())
    _token_yaz(akis.credentials)
    # Tek kullanimlik: durum dosyasi jetondan sonra hicbir ise yaramiyor.
    os.remove(AKIS_DURUM_FILE)
    return akis.credentials


def _basliklar(youtube, video_kimlikleri: list[str]) -> dict[str, str]:
    """Video kimliklerini basliklara cevirir. Analitik ucu baslik dondurmuyor."""
    adlar: dict[str, str] = {}
    for i in range(0, len(video_kimlikleri), 50):
        oebek = video_kimlikleri[i : i + 50]
        yanit = youtube.videos().list(part="snippet", id=",".join(oebek)).execute()
        for oge in yanit.get("items", []):
            adlar[oge["id"]] = oge["snippet"]["title"]
    return adlar


def rapor(gun: int = 28, creds=None) -> dict[str, Any]:
    """Son `gun` gunun kanal ve video kirilimini dondurur."""
    creds = creds or yetkilendir(etkilesimli=False)
    analytics = build("youtubeAnalytics", "v2", credentials=creds)
    youtube = build("youtube", "v3", credentials=creds)

    bitis = date.today()
    baslangic = bitis - timedelta(days=gun)
    ortak = {
        "ids": "channel==MINE",
        "startDate": baslangic.isoformat(),
        "endDate": bitis.isoformat(),
    }

    kanal = analytics.reports().query(**ortak, metrics=VIDEO_OLCUMLERI).execute()
    videolar = (
        analytics.reports()
        .query(**ortak, metrics=VIDEO_OLCUMLERI, dimensions="video", sort="-views", maxResults=50)
        .execute()
    )
    kaynaklar = (
        analytics.reports()
        .query(**ortak, metrics="views", dimensions="insightTrafficSourceType", sort="-views")
        .execute()
    )

    sutunlar = [s["name"] for s in videolar.get("columnHeaders", [])]
    satirlar = videolar.get("rows", []) or []
    kimlikler = [satir[0] for satir in satirlar]
    adlar = _basliklar(youtube, kimlikler) if kimlikler else {}

    video_kayitlari = []
    for satir in satirlar:
        kayit = dict(zip(sutunlar, satir, strict=True))
        kayit["baslik"] = adlar.get(kayit.get("video", ""), "")
        video_kayitlari.append(kayit)

    kanal_sutunlari = [s["name"] for s in kanal.get("columnHeaders", [])]
    kanal_satiri = (kanal.get("rows") or [[0] * len(kanal_sutunlari)])[0]

    return {
        "gun": gun,
        "baslangic": baslangic.isoformat(),
        "bitis": bitis.isoformat(),
        "kanal": dict(zip(kanal_sutunlari, kanal_satiri, strict=True)),
        "videolar": video_kayitlari,
        "trafik": [
            {"kaynak": satir[0], "izlenme": satir[1]}
            for satir in (kaynaklar.get("rows") or [])
        ],
    }


def tutunma_egrisi(video_kimligi: str, gun: int = 90, creds=None) -> list[tuple[float, float]]:
    """Videonun tutunma egrisi: `(oran, izleyen)` ciftleri.

    ⚠️ Bu sorgu bu oturumda ELLE yazildi ve hattin en degerli olcumunu
    verdi (2026-08-14): iki videonun egrisi birebir ayni kalibi gosterdi —
    ilk 5 sn'de tutunma %100'un ustunde (kanca calisiyor, izleyici basa
    sariyor), sonraki ~4 sn'de ucte biri gidiyor. Dususun yeri klip
    suresiyle ortusuyor, yani kayip ILK SAHNE DEGISIMINDE basliyor.

    Elle yazilan bir sorgu bir daha kolay calistirilmaz; kalici hale
    getirilmesinin sebebi bu.
    """
    creds = creds or yetkilendir(etkilesimli=False)
    analytics = build("youtubeAnalytics", "v2", credentials=creds)
    bitis = date.today()
    yanit = (
        analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=(bitis - timedelta(days=gun)).isoformat(),
            endDate=bitis.isoformat(),
            metrics="audienceWatchRatio",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_kimligi}",
        )
        .execute()
    )
    return [(satir[0], satir[1]) for satir in (yanit.get("rows") or [])]


def _egriyi_yazdir(egri: list[tuple[float, float]], sure_sn: int | None) -> None:
    if not egri:
        print("veri yok (video cok yeni olabilir — Analytics 2-3 gun gecikmeli)")
        return
    for oran, izleyen in egri[::10]:
        an = f"{round(oran * sure_sn):>3} sn" if sure_sn else f"%{oran * 100:>5.1f}"
        print(f"  {an}  {izleyen * 100:5.1f}%  {'#' * int(izleyen * 30)}")


def kollari_karsilastir(gun: int = 28, creds=None) -> dict[str, Any]:
    """Sahne sayisi kollarini yan yana koyar — tutunma deneyinin okumasi.

    `state.json`daki `sahne_sayisi` alanina gore gruplar. Alan olmayan eski
    kayitlar "bilinmiyor" kovasina dusuyor; onlari kola saymak deneyi
    kirletirdi.
    """
    creds = creds or yetkilendir(etkilesimli=False)
    veri = rapor(gun=gun, creds=creds)
    olcumler = {kayit.get("video"): kayit for kayit in veri["videolar"]}

    try:
        with open(STATE_YOLU, encoding="utf-8") as dosya:
            yayinlar = json.load(dosya).get("published", [])
    except (OSError, ValueError):
        yayinlar = []

    kollar: dict[str, list[dict[str, Any]]] = {}
    for yayin in yayinlar:
        kimlik = str(yayin.get("url", "")).rsplit("/", 1)[-1]
        olcum = olcumler.get(kimlik)
        if not olcum:
            continue  # Analytics henuz gormemis ya da pencerenin disinda.
        kol = str(yayin.get("sahne_sayisi") or "bilinmiyor")
        kollar.setdefault(kol, []).append({**olcum, "baslik": yayin.get("title", "")})
    return {"gun": gun, "kollar": kollar}


def _karsilastirmayi_yazdir(veri: dict[str, Any]) -> None:
    print(f"=== sahne sayisi kollari · son {veri['gun']} gun ===")
    if not veri["kollar"]:
        print("eslesen video yok (Analytics 2-3 gun gecikmeli)")
        return
    for kol in sorted(veri["kollar"]):
        kayitlar = veri["kollar"][kol]
        n = len(kayitlar)
        tut = sum(k.get("averageViewPercentage", 0) for k in kayitlar) / n
        abone = sum(k.get("subscribersGained", 0) for k in kayitlar)
        izlenme = sum(k.get("views", 0) for k in kayitlar)
        print(
            f"{kol:>10} sahne | {n:>2} video | ort. tutunma {tut:5.1f}% "
            f"| {izlenme:>6} izlenme | +{abone} abone"
        )
    print("\n⚠️ Az sayida videoyla fark gurultu olabilir; kol basina en az 6-8 video birikmeden karar verme.")


def _yazdir(veri: dict[str, Any]) -> None:
    k = veri["kanal"]
    print(f"=== {veri['baslangic']} → {veri['bitis']} ({veri['gun']} gun) ===")
    # ⚠️ Gecikme BASLIKTA yaziyor: olculdu (2026-08-14), 13-14 Agustos'ta
    # yayinlanan videolar (Mehmed II 709 izlenme dahil) raporda HIC yoktu.
    # Bunu bilmeden bakan biri "yeni videolar tutmadi" diye okur.
    print("⚠️ Analytics 2-3 gun gecikmeli — son videolar burada gorunmez.")
    print(f"izlenme        : {k.get('views', 0)}")
    print(f"izlenme suresi : {k.get('estimatedMinutesWatched', 0)} dk")
    print(f"ort. sure      : {k.get('averageViewDuration', 0)} sn")
    print(f"ort. tutunma   : {k.get('averageViewPercentage', 0)}%")
    print(f"abone kazanimi : {k.get('subscribersGained', 0)}")
    print()
    print("--- video basina (izlenmeye gore) ---")
    for v in veri["videolar"]:
        print(
            f"{v.get('views', 0):>6} izlenme | tutunma {v.get('averageViewPercentage', 0):>5.1f}% "
            f"| {v.get('averageViewDuration', 0):>3} sn | +{v.get('subscribersGained', 0)} abone "
            f"| {v.get('baslik', '')[:44]}"
        )
    print()
    print("--- trafik kaynagi ---")
    for t in veri["trafik"]:
        print(f"{t['izlenme']:>6} | {t['kaynak']}")


def main() -> None:
    ayristirici = argparse.ArgumentParser(description="Kanal analitigi raporu")
    ayristirici.add_argument("--gun", type=int, default=28)
    ayristirici.add_argument("--json", action="store_true")
    ayristirici.add_argument(
        "--yetkilendir",
        action="store_true",
        help="Ayni makinedeki tarayicidan onay al (yukleme token'ina dokunmaz)",
    )
    ayristirici.add_argument(
        "--yetkilendir-telefon",
        action="store_true",
        help="Telefondan onaylamak icin baglanti uretir",
    )
    ayristirici.add_argument(
        "--yetkilendir-tamamla",
        metavar="ADRES",
        help="Telefondaki onaydan sonra adres cubugundaki TAM adres",
    )
    ayristirici.add_argument(
        "--tutunma",
        metavar="VIDEO_ID",
        help="Videonun tutunma egrisini bas (izleyici NEREDE birakiyor)",
    )
    ayristirici.add_argument(
        "--sure",
        type=int,
        metavar="SN",
        help="--tutunma ile: video suresi, egriyi saniyeye cevirmek icin",
    )
    ayristirici.add_argument(
        "--karsilastir",
        action="store_true",
        help="Sahne sayisi kollarini yan yana koy (tutunma deneyi)",
    )
    secenekler = ayristirici.parse_args()

    if secenekler.yetkilendir:
        yetkilendir(etkilesimli=True)
        print(f"✅ analitik yetkisi alindi: {TOKEN_FILE}")
        return

    if secenekler.yetkilendir_telefon:
        print("Bu baglantiyi telefonda ac ve onayla:\n")
        print(telefon_baglantisi())
        print(
            "\nOnaydan sonra telefon 'baglanilamadi' sayfasi gosterecek — NORMAL.\n"
            "Adres cubugundaki TAM adresi kopyala ve su komutu calistir:\n"
            '    python kanal_rapor.py --yetkilendir-tamamla "<adres>"'
        )
        return

    if secenekler.yetkilendir_tamamla:
        telefon_tamamla(secenekler.yetkilendir_tamamla)
        print(f"✅ analitik yetkisi alindi: {TOKEN_FILE}")
        return

    try:
        if secenekler.tutunma:
            _egriyi_yazdir(tutunma_egrisi(secenekler.tutunma), secenekler.sure)
            return
        if secenekler.karsilastir:
            karsilastirma = kollari_karsilastir(secenekler.gun)
            if secenekler.json:
                print(json.dumps(karsilastirma, ensure_ascii=False, indent=2))
            else:
                _karsilastirmayi_yazdir(karsilastirma)
            return
        veri = rapor(secenekler.gun)
    except RuntimeError as hata:
        # Yetki eksikligi bir COKME degil, yapilacak bir is. Traceback
        # basmak kullaniciyi kutuphane yigini okumaya zorluyordu.
        sys.exit(str(hata))
    except HttpError as hata:
        # ⚠️ Olculdu (2026-08-14): jeton dogru alindiktan SONRA bile 403
        # geliyordu — Analytics API'si Cloud projesinde acik degildi. Ham
        # traceback bunu 20 satirlik bir yiginin icine gomuyordu; sebep
        # tek satirlik ve yapilacak is tek tiklik.
        if hata.resp.status == 403 and b"accessNotConfigured" in hata.content:
            sys.exit(
                "YouTube Analytics API bu Google Cloud projesinde KAPALI.\n"
                "Bir kez acilmasi gerekiyor:\n"
                "    https://console.developers.google.com/apis/api/"
                "youtubeanalytics.googleapis.com/overview?project=445932056496\n"
                "Actiktan birkac dakika sonra komutu tekrar calistir."
            )
        raise
    if secenekler.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        _yazdir(veri)


if __name__ == "__main__":
    main()
