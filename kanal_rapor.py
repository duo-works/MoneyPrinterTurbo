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

KOK = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_FILE = os.path.join(KOK, "client_secret.json")
TOKEN_FILE = os.path.join(KOK, "youtube_analytics_token.json")

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
    baglanti, durum = akis.authorization_url(
        access_type="offline",  # yenileme jetonu icin
        prompt="consent",
        include_granted_scopes="true",
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


def _yazdir(veri: dict[str, Any]) -> None:
    k = veri["kanal"]
    print(f"=== {veri['baslangic']} → {veri['bitis']} ({veri['gun']} gun) ===")
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
        veri = rapor(secenekler.gun)
    except RuntimeError as hata:
        # Yetki eksikligi bir COKME degil, yapilacak bir is. Traceback
        # basmak kullaniciyi kutuphane yigini okumaya zorluyordu.
        sys.exit(str(hata))
    if secenekler.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        _yazdir(veri)


if __name__ == "__main__":
    main()
