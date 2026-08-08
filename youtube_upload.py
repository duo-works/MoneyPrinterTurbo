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


def upload_video(
    video_path,
    title,
    description,
    tags,
    privacy_status,
    contains_synthetic_media=True,
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
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
            # ⚠️ Bu beyan zorunlu ve eksikti. Bu hat videoyu LLM senaryosu +
            # TTS ses + stok goruntu ile uretiyor, yani icerik sentetik.
            # YouTube gercekci sentetik/degistirilmis medya icin aciklama
            # istiyor; beyan edilmemesi uyum riski. Varsayilan True cunku bu
            # hattin urettigi HER video sentetik — istisna varsa cagiran taraf
            # acikca False gecmeli.
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
        "--not-synthetic",
        action="store_true",
        help="containsSyntheticMedia=False gonder (bu hat icin normalde gerekmez)",
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
        contains_synthetic_media=not args.not_synthetic,
    )


if __name__ == "__main__":
    main()
