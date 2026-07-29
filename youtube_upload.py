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

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = os.path.join(os.path.dirname(__file__), "client_secret.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "youtube_token.json")


def get_authenticated_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET_FILE):
                sys.exit(
                    f"client_secret.json bulunamadi: {CLIENT_SECRET_FILE}\n"
                    "Google Cloud Console'dan indirip proje koekune koy."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_video(video_path, title, description, tags, privacy_status):
    if not os.path.exists(video_path):
        sys.exit(f"Video dosyasi bulunamadi: {video_path}")

    youtube = get_authenticated_service()

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
    parser.add_argument("video_path", help="Yuklenecek video dosyasinin yolu")
    parser.add_argument("--title", required=True, help="Video basligi")
    parser.add_argument("--description", default="", help="Video aciklamasi")
    parser.add_argument("--tags", default="", help="Virgulle ayrilmis etiketler")
    parser.add_argument(
        "--privacy",
        default="public",
        choices=["public", "unlisted", "private"],
        help="Gizlilik durumu (varsayilan: public)",
    )
    args = parser.parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    if "#shorts" not in args.description.lower() and "shorts" not in [t.lower() for t in tags]:
        tags.append("Shorts")

    upload_video(args.video_path, args.title, args.description, tags, args.privacy)


if __name__ == "__main__":
    main()
