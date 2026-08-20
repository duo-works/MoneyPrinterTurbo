"""
YouTube Data API v3 uzerinden video (Shorts) yukleme betigi.

Ilk calistirmada tarayici acilir, Google hesabinla giris yapip izin
vermen istenir; sonrasinda youtube_token.json'a kaydedilen token
otomatik kullanilir, tekrar giris istemez.

Kullanim:
    python youtube_upload.py <video_dosyasi> --title "Baslik" --description "Aciklama" [--tags tag1,tag2] [--privacy public|unlisted|private]
"""

import argparse
import os
import sys

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    # ⚠️ Yalnizca `upload` kapsami varken `channels.list(mine=True)` 403 doner,
    # yani token'in HANGI kanala bagli oldugu yukleme anina kadar olculemez.
    # Kanal dogrulamasi bu kapsam olmadan yazilamaz.
    "https://www.googleapis.com/auth/youtube.readonly",
]
CLIENT_SECRET_FILE = os.path.join(os.path.dirname(__file__), "client_secret.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "youtube_token.json")

KANAL_AYAR_ANAHTARI = "youtube_channel_id"
KANAL_ORTAM_ANAHTARI = "YOUTUBE_KANAL_ID"


class YanlisKanalHatasi(RuntimeError):
    """Yetkilendirilmis token beklenenden baska bir kanala bagli.

    Yukleme yapilmadan once atilir; hicbir sey yayina gitmez.
    """


def beklenen_kanal() -> str:
    """Yuklemenin gitmesi gereken kanal kimligi (UC...).

    Once ortam degiskeni, sonra `config.toml` icindeki `[app]` bolumu okunur.
    Ikisi de bos ise dogrulama yapilamaz — bkz. `kanali_dogrula`.
    """
    ortamdan = os.environ.get(KANAL_ORTAM_ANAHTARI, "").strip()
    if ortamdan:
        return ortamdan
    try:
        from app.config import config
    except Exception:  # noqa: BLE001 — config yoksa dogrulama zaten yapilamaz
        return ""
    return str(config.app.get(KANAL_AYAR_ANAHTARI, "") or "").strip()


def kanal_bilgisi(youtube):
    """Token'in bagli oldugu kanalin (kimlik, ad) ciftini olcer.

    `channels.list` part=snippet 1 birim kota harciyor — `videos.insert`in
    1600 biriminin yaninda olculemeyecek kadar ucuz.
    """
    yanit = youtube.channels().list(part="snippet", mine=True).execute()
    ogeler = yanit.get("items", [])
    if not ogeler:
        raise YanlisKanalHatasi(
            "Yetkilendirilen Google hesabina bagli bir YouTube kanali yok. "
            "Token dogru hesapla mi alindi?"
        )
    return str(ogeler[0].get("id", "")), str(ogeler[0].get("snippet", {}).get("title", "?"))


def kanali_dogrula(youtube):
    """Yuklemeden ONCE hedef kanali dogrular.

    ⚠️ Kapali-hata (fail closed): beklenen kanal ayarli degilse yukleme
    YAPILMAZ. Olculdu (2026-08-05): token paylasilan dosyaya yazilinca yanlis
    kanala baglandi ve video yanlis kanala gitti. O gun kayip tek videoydu;
    zamanlanmis hatta gunde 6 video var ve hata sessiz.

    Yon asimetrik: yanlis kanala giden videoyu geri almak izlenme ve oneri
    sinyali kaybi; ayar eksikken duran hat tek satirlik bir duzeltme. Bu yuzden
    "ayar yoksa dogrulamayi atla" degil, "ayar yoksa yukleme yok" secildi.

    Ilk kurulumda kimlik `--kanali-goster` ile olculur.
    """
    beklenen = beklenen_kanal()
    gercek, ad = kanal_bilgisi(youtube)
    if not beklenen:
        raise YanlisKanalHatasi(
            f"Hedef kanal ayarli degil, hicbir sey yuklenmedi. Token su an {ad!r} "
            f"({gercek}) kanalina bagli. Dogru kanalsa config.toml icindeki [app] "
            f'bolumune `{KANAL_AYAR_ANAHTARI} = "{gercek}"` satirini ekleyin.'
        )
    if gercek != beklenen:
        raise YanlisKanalHatasi(
            f"Token yanlis kanala bagli: {ad!r} ({gercek}). Beklenen: {beklenen}. "
            "Hicbir sey yuklenmedi. Token'i silip dogru hesapla yeniden yetkilendirin."
        )
    return gercek, ad


def _token_yaz(creds):
    """Token'i yalnizca sahibinin okuyabilecegi izinle yazar.

    Icinde refresh token var: uzun omurlu ve kanala yukleme yetkisi veren bir
    kimlik bilgisi. Duz `open(...).write` dosyayi umask'e birakiyordu ve
    olculdu — pratikte 0644 cikiyor, yani makinedeki her kullanici okuyabilir.
    """
    with open(TOKEN_FILE, "w", encoding="utf-8") as token_file:
        token_file.write(creds.to_json())
    os.chmod(TOKEN_FILE, 0o600)


def get_authenticated_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # `Credentials.valid` KAPSAM KONTROL ETMIYOR — kaynagi yalnizca
    # "token var mi ve dolmus mu" diye bakiyor, `has_scopes` ayri bir metot.
    # SCOPES ileride genisletilirse (or. analytics icin readonly) diskteki eski
    # token gecerli gorunmeye devam eder ve hata calisma aninda
    # `403 insufficient scopes` olarak, cagri yerinde patlar.
    if not creds or not creds.valid or not creds.has_scopes(SCOPES):
        yenilendi = False

        if creds and creds.expired and creds.refresh_token and creds.has_scopes(SCOPES):
            try:
                creds.refresh(Request())
                yenilendi = True
            except RefreshError:
                # Iptal edilmis ya da 7 gunde dolmus refresh token. Onay ekrani
                # "Testing" durumundayken bu yol HER HAFTA geciliyor; yakalanmazsa
                # zamanlanmis gorev kutuphane traceback'i ile oluyor.
                creds = None
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)

        if not yenilendi:
            if not os.path.exists(CLIENT_SECRET_FILE):
                sys.exit(
                    f"client_secret.json bulunamadi: {CLIENT_SECRET_FILE}\n"
                    "Google Cloud Console'dan indirip proje koekune koy."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        _token_yaz(creds)

    return build("youtube", "v3", credentials=creds)


EGITIM_KATEGORISI = "27"
"""Education. Onceden "22" (People & Blogs) gonderiliyordu.

Kategori, YouTube'un videoyu hangi konu kumesine yerlestirdigini ve kime
onerdigini besleyen alanlardan biri. Bu kanal belgesel tarzi tarih anlatiyor;
"People & Blogs" vlog kumesi ve icerigin ne oldugunu YANLIS soyluyor. Dogru
kategori bir kazanc iddiasi degil, bir dogruluk duzeltmesi.
"""

SENTETIK_BEYANI = False
"""`containsSyntheticMedia` — kanal sahibinin karari (2026-08-08, DW-104).

Onceden True idi ve YouTube aciklamaya "Made with AI — sounds or visuals were
altered or fully generated" satirini koyuyordu. Kanal sahibi bunun kalkmasini
istedi; risk anlatildi ve karar tekrarlandi.

⚠️ Bu bir "kapatildi, unutuldu" ayari degil. YouTube beyani GERCEKCI sentetik
icerik icin istiyor ve su hallerde beyan ZORUNLU kaliyor — cagiran taraf
acikca True gecmeli:

  * gercek ve taninabilir bir kisiyi soylemedigi bir seyi soylerken gosteren,
  * gercek bir olayin goruntusunu degistiren,
  * gerceklesmemis bir olayi gerceklesmis gibi sunan sahne.

Bu hattin urettigi tarih anlatimlari bugun bu uc kovanin disinda: sahneler ya
kamu mali arsiv gorseli ya da adi konmus bir yerin illustrasyonu. Kanal
formati bunun disina cikarsa beyan geri acilmali.
"""

VARSAYILAN_DIL = "en"
"""`defaultLanguage` + `defaultAudioLanguage` — ikisi de bos gidiyordu.

⚠️ Gorunurluk acisindan en pahali eksikti: dil belirtilmeyince YouTube
basligi ve aciklamayi hangi dilde arayana eslestirecegini tahmin etmek
zorunda kaliyor, ceviri/altyazi ozellikleri devreye girmiyor. Kanal Ingilizce
icerik uretiyor ve `kanal.py` profilinde `varsayilan_dil="en"` yazili — MPT
yukleyicisi bu bilgiyi hic gondermiyordu.
"""


KAPAK_KOTA_MALIYETI = 50
"""`thumbnails.set` kota maliyeti (`videos.insert` 1600'un yaninda).

⚠️ Neden yazili: gunluk tavan 10.000 birim ve hat gunde en cok 6 yukleme
yapiyor (6 x 1600 = 9.600). Kapak eklendiginde 6 x 50 = 300 daha gidiyor ve
toplam **9.900** oluyor — tavanin 100 birim altinda. Yani kapak bedava
degil, gunluk yukleme tavanini 6'da SABITLIYOR: yedinci yukleme kotayi
zaten asardi. Tavan buyutulurse bu satir hesaba katilmali.
"""


def kapak_bas(youtube, video_id, kapak_yolu):
    """Yuklenmis videoya kapak koyar. Basarisizlik YUKLEMEYI DUSURMEZ.

    ⚠️ Yon asimetrik, o yuzden istisna kasitli yutuluyor: cagri geldiginde
    video ZATEN yayinda. Kapak cagrisi patlarsa (kota, gecici 5xx, dosya
    siniri) dogru davranis yayini geri almak degil kapaksiz birakmak —
    YouTube o zaman kendi otomatik karesini secer, yani sonuc bugunku
    duruma esit. Yukselen bir istisna ise `state.json`a yazilmadan once
    koşumu oldurur ve YAYINLANMIS video kayitsiz kalirdi.

    ⚠️ YouTube siniri 2 MB; `kapak.py` ~200 KB uretiyor, yani sinir pratikte
    uzak. Yine de olculuyor cunku cagirana ham dosya gecirme yolu acik.
    """
    if not kapak_yolu or not os.path.exists(kapak_yolu):
        return False
    boyut = os.path.getsize(kapak_yolu)
    if boyut > 2 * 1024 * 1024:
        print(f"⚠️ kapak 2 MB sinirini asiyor ({boyut // 1024} KB), atlandi")
        return False
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(kapak_yolu, mimetype="image/jpeg"),
        ).execute()
    except Exception as hata:  # noqa: BLE001 — gerekcesi docstring'de
        print(f"⚠️ kapak konulamadi (video yayinda kaldi): {hata}")
        return False
    print(f"✅ kapak kondu: {os.path.basename(kapak_yolu)}")
    return True


def upload_video(
    video_path,
    title,
    description,
    tags,
    privacy_status,
    contains_synthetic_media=SENTETIK_BEYANI,
    category_id=EGITIM_KATEGORISI,
    language=VARSAYILAN_DIL,
    kapak_yolu=None,
):
    if not os.path.exists(video_path):
        sys.exit(f"Video dosyasi bulunamadi: {video_path}")

    youtube = get_authenticated_service()
    # Dogrulama `videos.insert`ten ONCE: yanlis kanala giden video geri
    # alinabilir ama izlenme ve oneri sinyali geri gelmez.
    kanali_dogrula(youtube)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            # Metnin dili ve konusmanin dili ayri alanlar; ikisi de gerekli.
            "defaultLanguage": language,
            "defaultAudioLanguage": language,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
            # Varsayilani ve hangi hallerde geri acilmasi gerektigi
            # `SENTETIK_BEYANI`'nda yazili.
            "containsSyntheticMedia": contains_synthetic_media,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Yukleniyor: %{int(status.progress() * 100)}")

    video_id = response["id"]
    # Kapak, `videos.insert`ten SONRA: `thumbnails.set` var olan bir videoId
    # istiyor, yani baska sira mumkun degil.
    kapak_bas(youtube, video_id, kapak_yolu)
    url = f"https://youtube.com/shorts/{video_id}"
    print(f"Yukleme tamamlandi: {url}")
    return url


def main():
    parser = argparse.ArgumentParser(description="YouTube Shorts yukleme")
    parser.add_argument("video_path", nargs="?", help="Yuklenecek video dosyasinin yolu")
    parser.add_argument("--title", help="Video basligi")
    parser.add_argument(
        "--kanali-goster",
        action="store_true",
        help=(
            "Yukleme yapmadan token'in bagli oldugu kanali olcup yazar. "
            "Ilk kurulumda config.toml'a yazilacak kimlik buradan alinir."
        ),
    )
    parser.add_argument("--description", default="", help="Video aciklamasi")
    parser.add_argument("--tags", default="", help="Virgulle ayrilmis etiketler")
    parser.add_argument(
        "--privacy",
        default="private",
        choices=["public", "unlisted", "private"],
        # ⚠️ Varsayilan "public" idi. PRD'nin "v1'de OLMAYACAKLAR" listesinde
        # "otomatik yayin karari" var; zamanlanmis bir hatta varsayilan public,
        # metadata'da bir satir unutmanin cezasini "yayinda" yapiyor.
        # Yon asimetrik: erken yayinlanan videoyu geri almak izlenme ve oneri
        # sinyali kaybi demek; gec yayinlanani yayinlamak bir tik.
        help="Gizlilik durumu (varsayilan: private — yayin acik bir karar olmali)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help=(
            "containsSyntheticMedia=True gonder. Gercek bir kisiyi ya da olayi "
            "gercekci bicimde canlandiran videolarda gerekli — bkz. SENTETIK_BEYANI."
        ),
    )
    args = parser.parse_args()

    if args.kanali_goster:
        kimlik, ad = kanal_bilgisi(get_authenticated_service())
        print(f"Kanal: {ad}")
        print(f"Kimlik: {kimlik}")
        print(f'config.toml [app] icin: {KANAL_AYAR_ANAHTARI} = "{kimlik}"')
        return

    if not args.video_path or not args.title:
        parser.error("video_path ve --title zorunlu (kanal olcumu icin --kanali-goster)")

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    if "#shorts" not in args.description.lower() and "shorts" not in [t.lower() for t in tags]:
        tags.append("Shorts")

    upload_video(
        args.video_path,
        args.title,
        args.description,
        tags,
        args.privacy,
        contains_synthetic_media=args.synthetic,
    )


if __name__ == "__main__":
    main()
