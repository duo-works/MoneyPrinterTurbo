from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, cast
from zoneinfo import ZoneInfo

from imageio_ffmpeg import get_ffmpeg_exe
from moviepy.video.io.VideoFileClip import VideoFileClip
from openai import (
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    OpenAI,
)
from PIL import Image, ImageDraw, ImageOps
import requests

from app.config import config
import gorsel_olcum
import notion_kuyrugu
import tekrar_olcusu
import temizlik
import wikimedia_materials
from wikimedia_materials import MaterialsUnavailableError, download_scene_materials
from youtube_upload import upload_video

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "storage" / "youtube_automation" / "state.json"
LOCK_FILE = ROOT / "storage" / "youtube_automation" / "automation.lock"
LOG_DIR = ROOT / "storage" / "youtube_automation" / "logs"
REVIEW_DIR = ROOT / "storage" / "youtube_automation" / "reviews"
ANALYSIS_FILE = ROOT / "storage" / "channel_analysis" / "latest.json"
TIMEZONE_NAME = "Europe/Istanbul"
# ⚠️ 50'den 80'e cikarildi (2026-08-12). Yayinlanmis 10 videonun kayitli
# `quality` skorlariyla olculdu: 68-78 arasi skor alan 6 videonun HER
# BIRINDE 9-11 kayitli `issues` vardi (yanlis kisi/sahne uyumsuzlugu, orn.
# Berlichingen 72 puanla "cannot be confidently identified as Götz von
# Berlichingen"); 85-90 alan 4 videoda issues SIFIRDI. Iki kume arasinda
# net bir bosluk var (78 → 85), 50 esigi ise "issues dolu" kumeyi bastan
# sona geciriyordu — kullanicinin "anlatimla resimler uyusmuyor" sikayeti
# tam bu araligin yayinlanmis urunuydu. 80 bu bosluga oturuyor.
#
# Bu esik yalnizca VIDEO incelemesine (`review_video`, render'dan SONRA)
# uygulanir. `MIN_SOURCE_VISUAL_SCORE` asagida kaynak-goruntu on-kapisi
# icin AYRI bir sabit — ikisi eskiden ayni sabiti (80) paylasiyordu ve bu
# yanlisti: kaynak kapisi hic kendi verisiyle kalibre edilmemisti, video
# kapisinin verisiyle 80'e cikarilmisti. Olculdu (2026-08-13): kisi
# biyografisi konulari (Ludendorff, Talaat Pasha) kaynak kapisinda 12+15
# deneme boyunca 80'i hic gecemedi ama en iyi denemeleri (75, 78) hicbir
# yanlis-kisi kusuru TASIMIYORDU — yalnizca tekrarlayan portre ve olay-
# spesifik gorsel eksikligi. Kaynak arzi tarihi kisiler icin yapisal
# olarak portre agirlikli; 80 bu konu sinifini sistemik olarak eliyordu.
#
# ⚠️ 80'den 75'e INDIRILDI (2026-08-17, kanal sahibinin karari). Yukaridaki
# 2026-08-12 kalibrasyonu 10 YAYINLANMIS videonun skoruyla yapilmisti; o
# gunden beri hat degisti (menu disiplini, ikincil gorsel denetimi, capa
# arzi kapisi) ve esik bir daha olculmedi. 16-17 Agu'da uretilen 31 RENDER
# olculdu — kaynak asamasi retleri HARIC, cunku `review_source_materials`
# altyaziya sabit 100 yaziyor ve onlari render saymak bu oturumda iki kez
# yapilmis bir hata:
#
#     gorsel  >= 80     3/31
#     altyazi >= 80    16/31
#     IKISI BIRDEN      0/31      <- iki gunde SIFIR yayin
#
# Gorsel skorunun dagilimi darbogazi acikca gosteriyor:
#
#     85 ▏1  ·  82 ▏▏2  ·  78 ▏▏▏▏▏▏▏▏▏▏▏11  ·  72 ▏▏▏▏▏▏▏▏▏▏▏▏12  ·  <72 ▏▏▏▏▏5
#
# 23 render tam 72-78 bandinda. Hakem bu hatta pratikte 80 ustu vermiyor,
# yani esik ulasilabilir bandin USTUNDE duruyordu ve kaliteyi degil
# URETIMI engelliyordu. Agir kusuru SIFIR olan 13 render da ayni bantta
# takildi — orn. Hadrian's Wall 72/85, agir kusur 0.
#
# ⚠️ AGIR KUSUR KAPISI DEGISMEDI ve asil koruma odur: `agir_kusurlar` dolu
# olan video skoru ne olursa olsun reddediliyor. 2026-08-12'de elenen 50
# esiginden farki tam bu — o zaman boyle bir kapi YOKTU, yani "issues dolu"
# kume yayina gidiyordu. Bugun gitmiyor.
#
# ⚠️ 75, MIN_SOURCE_VISUAL_SCORE'un (70) USTUNDE kalmali; testi koruyor.
MIN_VISUAL_SCORE = 75
MIN_SOURCE_VISUAL_SCORE = 70
MIN_SUBTITLE_SCORE = 80
AI_VISUAL_FALLBACK_ENABLED = str(
    config.app.get("enable_ai_visual_fallback", "false")
).strip().lower() in {"1", "true", "yes", "on"}
INFERENCE_BACKEND = str(
    config.app.get("youtube_automation_inference_backend", "hermes-cli")
).strip().lower()
# Trend hunisinin CLI koprusu. PATH'te olmadigi icin (her iki kurulumda da bir
# sanal ortamin icinde) yol yapilandirmadan geliyor; bos birakilirsa
# `shutil.which` denenir ve bulunamazsa anlasilir bir hata verilir.
YTOTO_PATH = str(config.app.get("ytoto_path", "")).strip() or None
# ⚠️ Hermes sağlayici/modeli HAT TARAFINDAN belirleniyor, kullanicinin kuresel
# `~/.hermes/config.yaml` ayarina birakilmiyor. Gerekce `hermes_temel_komut`
# docstring'inde: `chat` alt komutu o ayari dikkate almiyor ve kotasi dolu
# kimligi secebiliyor. Ortam degiskeni yapilandirmayi ezer (zamanlayici ve
# elle koşum ayni degeri kullansin diye ikisi de destekleniyor).
HERMES_SAGLAYICI = (
    os.getenv("YT_HERMES_PROVIDER")
    or str(config.app.get("youtube_automation_hermes_provider", ""))
).strip()
HERMES_MODEL = (
    os.getenv("YT_HERMES_MODEL")
    or str(config.app.get("youtube_automation_hermes_model", ""))
).strip()
EDITORIAL_ANCHOR_POOL = [
    "Great Sphinx",
    "Moai",
    "Persepolis",
    "Palmyra",
    "Tikal",
    "Chichen Itza",
    "Sacsayhuaman",
    "Chartres Cathedral",
    "Hadrian's Wall",
    "Ellora Caves",
    "Ajanta Caves",
    "Sigiriya",
    # ⚠️ Asagidakiler 2026-08-13'te EKLENDI cunku havuz TUKENMISTI: 15 capanin
    # 15'i de kullanilmisti ve `eligible_anchors` bos donuyordu. Model bos
    # liste alinca ince arsivli gizemlere kayiyordu (Baychimo, Vasa, Phaistos
    # Diski, Piltdown) ve kaynak kapisinda 25-43 aliyordu.
    #
    # Hicbiri tahminle secilmedi; her biri uretimin KENDI kapilariyla olculdu
    # (kategori var mi, kac dosya kadraj+lisanstan geciyor) ve yalnizca 12+
    # kullanilabilir gorseli olanlar alindi. Olcum ayni tabloda elenenleri de
    # gosterdi: Pompeii 0, Leptis Magna 0, Teotihuacan 2, Krak des Chevaliers
    # 2, Skara Brae 3, Terracotta Army 4, Alhambra 5, Sutton Hoo 7.
    # Sutton Hoo'nun 7'si onemli — bu hat onu secmis ve 25 almisti.
    "Petra",                    # 24
    "Borobudur",                # 28
    "Stonehenge",               # 12
    "Mesa Verde National Park",  # 47
    "Gobekli Tepe",             # 18
    "Ephesus",                  # 29
    "Hagia Sophia",             # 29
    "Baalbek",                  # 17
    "Pont du Gard",             # 15
    "Brooklyn Bridge",          # 28
    "Panama Canal",             # 20
    "Suez Canal",               # 18
    "Cutty Sark",               # 25
    "Mary Rose",                # 23
    "Antikythera mechanism",    # 17
    "Book of Kells",            # 33
    "Staffordshire Hoard",      # 33
    "Tutankhamun",              # 29
    # ⚠️ 2026-08-14 ikinci tur — havuz SIFIRLANMISTI. Olculdu: 34 capanin
    # 34'u de kullanilmis, `eligible_anchors` bos donuyor ve yedek kipteki
    # koşumlar "could not generate a sufficiently distinct topic" ile
    # oluyordu. 20:05 koşumu tam bu yuzden video uretmedi.
    #
    # Ayni olcut (Commons menusunde 12+ kullanilabilir gorsel) 32 adaya
    # uygulandi, 10'u gecti. Yeni kare duzeninde esik zaten 6 sahne x 2
    # yuva = 12, yani olcut kendiliginden dogru sayida.
    #
    # Elenenler kayda geciyor ki tekrar denenmesin: Meteora 11, Nazca
    # Lines 11, Machu Picchu 11, Sutton Hoo helmet 11, Carnac stones 7,
    # Karnak Temple 7, Chand Baori 6, Teotihuacan 5, Leptis Magna 4,
    # Skara Brae 3, Vasa ship 2, Ggantija 1.
    "Angkor Thom",              # 14
    "Mont Saint-Michel",        # 14
    "Alhambra",                 # 32
    "Bagan",                    # 40
    "Pompeii",                  # 12
    "Herculaneum",              # 38
    "Terracotta Army",          # 12
    "Bayeux Tapestry",          # 15
    "Eiffel Tower",             # 12
    "Trevi Fountain",           # 27
    # ⚠️ 2026-08-16 UCUNCU tur — havuz YINE sifirlandi ve bu kez bedeli
    # olculdu: kanal 27 SAAT sessiz kaldi. 04:18 koşumunun logu birebir
    # "⚠️ Editoryal capa havuzu TUKENDI" yazdi, model konusunu serbest
    # secti ("Library of Alexandria"), o arsiv Ohio ve Minnesota'daki
    # Alexandria halk kutuphaneleriyle doluydu ve bes denemenin besi de
    # yandi. Zamanlayici bunu yalnizca "red | skor 0" diye raporluyor.
    #
    # ⚠️ HAVUZ TEK BASINA SUCLU DEGIL: Notion hunisi de terfi edemiyordu
    # (`huni_besle` ciktisi, ayni saat): sekiz adayin ucu "menu 0-3 < 12",
    # dordu "benzeri uretilmis". Adaylarin HEPSI kisiydi ve kisi arsivleri
    # yapisal olarak ince (bkz. `MIN_SOURCE_VISUAL_SCORE` gerekcesi).
    # Havuz bu yuzden ANIT/YER agirlikli dolduruluyor — olculen kusur
    # orani o sinifta en dusuk.
    #
    # Ayni olcut (Commons kategorisinde 12+ kadraj VE lisans VE ozne
    # gecen gorsel) 36 adaya uygulandi, 9'u gecti.
    #
    # Elenenler kayda geciyor ki tekrar denenmesin: Taj Mahal 9, Volubilis
    # 9, Paestum 8, Parthenon 7, Aqueduct of Segovia 7, Neuschwanstein
    # Castle 7, Great Wall of China 6, Chan Chan 6, Machu Picchu 5,
    # Sanchi 5, Westminster Abbey 5, Pergamon 4, Palenque 4, Monte Alban 4,
    # Tower of London 4, Carcassonne 4, Cologne Cathedral 3, Delphi 2,
    # Potala Palace 2, Registan 2, Saint Basil's Cathedral 1, Mosque-
    # Cathedral of Cordoba 1, Ostia Antica 1, Valley of the Kings 0,
    # Himeji Castle 0.
    #
    # ⚠️ "Forbidden City" 27 OLCTU ama ALINMADI: `arsiv_arzi_olc.ayirt_edici`
    # basligin SON kelimesini anahtar aliyor ve burada o kelime "city" —
    # icinde "city" gecen her dosya sayiliyor, yani sayi guvenilir degil.
    # Ayni tuzak "Great Wall of China" → "china", "Valley of the Kings" →
    # "kings", "Himeji Castle" → "castle" icin de var.
    "Mycenae",                  # 20
    "Abu Simbel",               # 19
    "Colosseum",                # 15
    "Knossos",                  # 14
    "Jerash",                   # 14
    "Copan",                    # 14
    "Aphrodisias",              # 12
    "Todai-ji",                 # 27
    # ⚠️ "Karnak" ONCE EKLENDI, SONRA CIKARILDI — olcum araci ile KAPININ
    # kendisi ayrisiyor. `arsiv_arzi_olc.py` 13 dedi, ama uretimin gercekten
    # kullandigi `arsiv_envanteri` yalnizca 6 dosya veriyor. Ikisi ayni seyi
    # saymiyor: betik `kategori_gorselleri` + dosya adinda anahtar ararken,
    # kapi menuyu kendi suzgecinden geciriyor.
    #
    # Ders: havuza capa eklerken olcumu KAPININ fonksiyonuyla dogrula —
    # `arsiv_envanteri(konu, sinir=40, bicim=...)`. Eklenen diger sekiz capa
    # bu ikinci olcumden gecti: Colosseum 40, Knossos 24, Jerash 17,
    # Aphrodisias 17, Abu Simbel 14, Mycenae 14, Copan 15, Todai-ji 13.
    #
    # ⚠️ 2026-08-16 DORDUNCU tur — ilk kez capalar ELLE SECILMEDI. Adaylar
    # Yt_Automation'daki arsiv-once kaynagin (`trend/arsiv.py`, PR #59)
    # buldugu Commons kategorilerinden geldi: kaynak arsivi zengin
    # kategorileri tarayip Wikidata koprusuyle makaleye baglıyor. Havuzu
    # besleyen sey artik bir tahmin degil bir OLCUM.
    #
    # ⚠️ KOPRU ILE ARAMA AYRISIYOR — olculdu (29 kategori adayi):
    #     Wikidata koprusu cozdu      12  -> hepsi gercek konu
    #     metin aramasina dustu        5  -> 5'i de COP (Plumbing,
    #        List_of_shipwrecks_in_1952, Art_in_Ruins, Taban_ruins,
    #        Ruins_(comics))
    #     hic cozulmedi               12  -> kategori adi, makale degil
    # Yani yedek arama kolu bu kaynak icin deger uretmiyor.
    #
    # ⚠️ HAM DOSYA SAYISI KULLANILABILIR ARZI ONGORMUYOR. Kaynagin kendi
    # esigi ham sayiya bakiyor (`arsiv.ASGARI_DOSYA = 25`) ama iki olcum
    # ILISKISIZ cikti: Scythian Neapolis 200 ham -> 6 kullanilabilir,
    # Tabula Traiana 56 -> 4, Roman roads 66 -> 10. Olcegi buyutmek
    # duzeltmez; kapi zaten kendi fonksiyonuyla yeniden olcuyor.
    #
    # Elenenler kayda geciyor ki tekrar denenmesin: Roman roads 10,
    # Groma (surveying) 8, Scythian Neapolis 6, SS Choctaw 6,
    # Tabula Traiana 4.
    #
    # ⚠️ "Antikythera wreck" MENUYU GECTI (21) ama capa kapisinda elendi:
    # `is_duplicate_visual_anchor` onu yanan "Antikythera mechanism"
    # capasiyla ayni sayiyor. Dogru davranis — ayni videoyu iki kez
    # cekmemek icin var — ve kararı fonksiyonun kendisi verdi.
    # ⚠️ 2026-08-17: `ICERIKSIZ_ACIKLAMA` suzgeci menuyu daralttı ve havuz
    # yeniden olculdu (kapinin kendi fonksiyonuyla, 58 capa): **54 geciyor**.
    # Esigin altina dusen DORT capa kayda geciyor — esik DUSURULMEDI, cunku
    # aciklamasi kunye olan bir arsiv modele kor secim yaptiriyor:
    #
    #     Notre Dame Cathedral  5    Newgrange     10
    #     Rani ki Vav          10    Masada        11
    #
    # ⚠️ DORDU DE HAVUZDAN CIKARILDI — ilk hali "cikarilmadi" diyordu ve o
    # karar AYNI GECE yanlislandi. 01 slotu yedek kipte kostu, model Masada'yi
    # secti (menu 11) ve ucuncu deneme KAYNAK KAPISINDA 45 ile dustu
    # (`state.json` -> `stage: source_materials`), yani render'a bile
    # varmadan. Bedel yine de tam bir deneme: indirmeler + bir gorü cagrisi.
    # Yedek kipte capa secimi menu boyutuna BAKMIYOR
    # (`eligible_anchors` yalnizca tekrar kapisini uyguluyor), yani havuzda
    # duran ince capa er gec secilir.
    #
    # Geri donulebilir: olcut yine 12+, `arsiv_envanteri` ile yeniden olcup
    # ekleyin. Emsal ayni dosyada — Pompeii ilk turda 0 olcup elenmisti,
    # sonra 12 olcup geri alindi (bkz. yukarisi).
    #
    # ⚠️ ELENEN TASARIM, tekrar onerilmesin: havuza CANLI menu kapisi koymak
    # (`eligible_anchors` icinde `arsiv_envanteri`). Yedek kipte istem
    # asamasinda hicbir menu cekilmiyor, yani kapi 58 capayi da soguk
    # olcerdi: olculdu, capa basina ~12 sn -> ~12 dk, koşumun kendisi ~20 dk.
    # Maliyet kabul edilemez.
    #
    # Kalici secenek (SIMDI YAPILMADI): modelin SECTIGI capayi plan sonrasi
    # tek seferde olcmek — 1 cagri (~12 sn) + yanan bir cikarim, tam render
    # bedelinden ucuz. Cikarilmadan sonra bilinen ince capa KALMADI, yani
    # neredeyse hic atesleneceği icin simdi yazilmadi; gorü on kontrolu
    # (ayri DW) bu isi zaten ustlenebilir.
    "Roman aqueduct",           # 20
    "Cryptoporticus",           # 16
    "Mastaba",                  # 15
    #
    # ⚠️ Ikinci hasat (ayni gun): tohum kumesi ANIT/SIT agirlikli genisletildi
    # (Ziggurats, Hittite sites, Mesoamerican pyramids, Ancient Roman baths...),
    # 83 alt kategori tarandi, 9'u Wikidata koprusuyle makaleye baglandi.
    # Tamami Commons+Wikidata, yani ANAHTARSIZ ve KREDISIZ.
    "Ziggurat of Ur",           # 24
    "Tepe Sialk",               # 40
    "Tipasa",                   # 40
    # Menu kapisinda kalanlar: Dur-Kurigalzu 2, San Andres 0, Amasra Fortress 6.
    # "Karnak" yine cikti ve capa kapisi onu dogru sekilde eledi.
    #
    # ⚠️ MENU KAPISI ARZI OLCER, EDITORYAL UYGUNLUGU DEGIL — iki aday kapiyi
    # GECTI ama ELLE elendi ve sebebi buraya yaziliyor ki tekrar denenmesin:
    #
    #   Getty Villa   menu 31 — 1974 yapimi Kaliforniya REPLIKASI, antik yapi
    #                 degil. Arsivi zengin diye almak, `RESMEDILEMEZ_KALIPLAR`
    #                 ile ayni gun kapatilan "konuyla ilgisiz modern goruntu"
    #                 kusurunu elle geri koymak olurdu. Zaten kayitli bir vaka.
    #   Monopteros    menu 33 — mimari TUR, ve Cryptoporticus'tan farkli:
    #                 kriptoportik yalnizca antik Roma'da var, monopteros'un
    #                 unlu ornekleri 19. yuzyil (Munih Englischer Garten).
    #                 Arsivi donem olarak karisik, "donem uyusmuyor" riski.
]


@dataclass
class ContentPlan:
    topic: str
    visual_anchor: str
    title: str
    script: str
    scenes: list[dict[str, str]]
    description: str
    tags: list[str]
    ruh_hali: str = ""
    """Anlatimin tonu — arka plan muzigi secimi icin (`RUH_HALLERI`).

    ⚠️ VARSAYILANI VAR ve bu bilincli: alan istemde ISTEGE BAGLI. Bu depoda
    plan semasina ZORUNLU alan eklemek bes denemenin dordunu yakmis bir kusur
    sinifi. Model alani yazmazsa ya da tanimayan bir deger verirse bos kalir
    ve muzik havuz genelinden secilir — bugunku davranis.
    """


@dataclass
class QualityReview:
    publishable: bool
    visual_alignment_score: int
    subtitle_readability_score: int
    issues: list[str] = field(default_factory=list)
    revised_search_terms: list[str] = field(default_factory=list)
    problem_scene_numbers: list[int] = field(default_factory=list)
    kareler: list[dict[str, Any]] = field(default_factory=list)
    """Hakemin KARE BASINA verdigi ham cevaplar — TELEMETRI, kapi degil.

    ⚠️ OLCULDU (2026-08-14) ve bir olcum korlugunu kapatiyor. Hakeme
    kare basina "iceride okunabilir yazi var mi", "anlatilan kisi mi",
    "donem uyuyor mu" soruluyor ve model bunlari cevapliyor; ama cevap
    yalnizca `agir_kusurlari_ayikla`dan geciyor ve gerisi ATILIYORDU.

    Sonuc: 183 koşum kaydinin **0'inda** kare verisi yok. Kanal sahibinin
    sesli notundaki uc madde (cok fazla harita, ustu yazili gorsel,
    birbirine benzeyen kareler) tam da bu veriyle olculebilirdi ve
    olculemiyor. `script` alaninda ayni kusur ayni gun bulundu: once
    kaydet, kapiyi veri birikince kur.
    """

    agir_kusurlar: list[str] = field(default_factory=list)
    """Yayini TEK BASINA engelleyen kusurlar — skordan bagimsiz.

    Skor ortalama bir izlenim: 84 alan bir video 10 kusur tasiyabiliyor
    (Mehmed II, olculdu 2026-08-13). Yanlis kisi gostermek ise ortalamaya
    karisacak bir eksiklik degil, tek basina yayindan dusuren bir olgu.
    """


class SourceMaterialRejected(RuntimeError):
    def __init__(self, review: QualityReview, credits: list[dict[str, Any]] | None = None):
        super().__init__("source materials failed the pre-render visual quality gate")
        self.review = review
        # ⚠️ Kunye de tasiniyor: reddin SEBEBINI okumak icin sahnenin NE
        # ISTEDIGI kadar NE ALDIGI da gerekiyor. Kayitlarda bu ikisi hic yan
        # yana durmadigi icin, bu oturumdaki teshis 12 kosumu tek tek elle
        # okumayi gerektirdi.
        self.credits = credits or []


class AIVisualUnavailableError(RuntimeError):
    pass


class DistinctTopicUnavailableError(RuntimeError):
    pass


class UzunFormatUygunDegilError(RuntimeError):
    """Arsiv bu konuda uzun formati besleyemiyor — Shorts'a dusulmeli.

    ⚠️ NEDEN TIPLI HATA, NEDEN KAPIYA BIRAKILMADI: `alinti_kusuru`'nun
    "menu sahne sayisindan kucuk" kolu bu durumu huni kipinde COZEMEZ.
    Konu disaridan sabitlenmis oluyor ("Keep this subject") ve kapinin
    modele verdigi geri bildirim "baska bir seye capa at" diyor — model
    bunu yapamaz, bes deneme yanar, koşum `DistinctTopicUnavailableError`
    ile HIC VIDEO URETMEDEN duser. Bu hatta olculmus bir kusur (18:05).

    Onun yerine cikarim koşumu BASLAMADAN once menu olculuyor ve cagiran
    tarafa "bu konuda uzun format olmaz" deniyor. Maliyeti sifir.
    """


# NFKD'nin AYRISTIRMADIGI harfler. Ayrismayan bir harf `[a-z0-9]+` suzgecinde
# kelimeyi ikiye boluyor, o yuzden tek tek karsiliklari yaziliyor.
_AYRISMAYAN_HARFLER = str.maketrans(
    {"ß": "ss", "ø": "o", "ł": "l", "æ": "ae", "œ": "oe", "đ": "d", "ı": "i", "ħ": "h"}
)


def _sade_harfler(value: str) -> str:
    """Aksanlari dusurur: "Weizsäcker" → "weizsacker"."""
    kucuk = value.lower().translate(_AYRISMAYAN_HARFLER)
    return "".join(
        k for k in unicodedata.normalize("NFKD", kucuk) if not unicodedata.combining(k)
    )


def _normalize_topic(value: str) -> set[str]:
    """Konuyu karsilastirilabilir belirteclere ayirir.

    ⚠️ ASKI DEGIL, KILITTI (olculdu 2026-08-12). `[a-z0-9]+` suzgeci aksanli
    harfi kelime siniri sayiyordu:

        "Carl Friedrich von Weizsäcker" → {carl, friedrich, von, weizs, cker}

    Dort kelimelik ad BES belirtec veriyordu ve `validate_content_plan`'in
    "gorsel capa 1-4 kelime" kurali hicbir zaman gecilemiyordu. Model uc kez
    "capayi kisalt" uyarisi alip ayni adi yeniden yaziyor, dorduncu denemede
    hermes zaman asimina ugrayip kosum COKUYORDU. Yani aksanli ve uc
    kelimeden uzun her ozel ad — huninin Alman, Turk, Ispanyol adaylarinin
    buyuk kismi — deterministik olarak uretilemezdi.

    Ikinci ve daha sinsi zarar: adin AYIRT EDICI belirteci ("weizsacker") hic
    olusmuyordu. `is_duplicate_topic` ve `_ensure_visual_anchor` o belirtec
    uzerinden eslesiyor; ikisi de sessizce zayifliyordu. "Götz von
    Berlichingen" kilidi tam sinirda (4) tesadufen geciyordu ve belirtecleri
    {g, tz, von, berlichingen} idi.
    """
    stopwords = {"a", "an", "and", "of", "the", "that", "to", "short", "shorts"}
    words = re.findall(r"[a-z0-9]+", _sade_harfler(value))
    return {word for word in words if word not in stopwords}


def _ensure_visual_anchor(term: str, visual_anchor: str) -> str:
    if _normalize_topic(term) & _normalize_topic(visual_anchor):
        return term
    return " ".join((visual_anchor.split() + term.split())[:7])


def is_duplicate_topic(candidate: str, previous: list[str]) -> bool:
    candidate_words = _normalize_topic(candidate)
    if not candidate_words:
        return True
    for item in previous:
        existing_words = _normalize_topic(item)
        if not existing_words:
            continue
        overlap = len(candidate_words & existing_words)
        union = len(candidate_words | existing_words)
        if candidate_words <= existing_words or existing_words <= candidate_words:
            if overlap >= 4:
                return True
        if union and overlap / union >= 0.6:
            return True
    return False


KANCA_KALIP_KELIMESI = 2
"""Ozneden sonraki kac kelime "kalip" sayilir.

Iki kelime olculdu: tekrarlayan acilislarin ortak iskeleti ozneden hemen
sonra basliyor ("... did not ...", "... was never ..."). Uc kelime
istemek kalibi kaciriyordu, cunku ucuncu kelime fiilin kendisi ve konudan
konuya degisiyor: "Mehmed II did not RULE" / "Murad III did not TAKE".
"""


def _kalip_iskeleti(cumle: str) -> list[str]:
    """Ozne atildiktan sonra kalan ilk kelimeler — acilisin "kalibi".

    ⚠️ Ozne SABIT UZUNLUKTA DEGIL: "Mehmed II" iki, "Sutton Hoo" iki,
    "Cleopatra" tek kelime. Ilk N kelimeyi atmak bu yuzden calismiyordu
    (ilk surum oyleydi ve "Murad III did not" ile "Mehmed II did not"
    kalibini kaciriyordu). Bunun yerine bastaki BUYUK HARFLI dizi
    atiliyor — ozel adlar ve sira sayilari orada bitiyor.
    """
    parcalar = re.findall(r"[A-Za-z']+", cumle)
    sira = 0
    while sira < len(parcalar) and parcalar[sira][:1].isupper():
        sira += 1
    return [kelime.lower() for kelime in parcalar[sira:]]


def _kanca_tekrari(senaryo: str, onceki_kancalar: list[str]) -> bool:
    """Acilis, daha once kullanilmis bir kalibi tekrarliyor mu.

    ⚠️ Karsilastirilan sey acilisin KELIME KELIME aynisi degil KALIBI:
    "Mehmed II did not rule once" ile "Murad III did not take the throne
    quietly" farkli cumleler ama ayni kalip, ve kanal ust uste bunlari
    yayinlarsa izleyici ayni videoyu izliyormus gibi hissediyor (DW-94).
    """
    kanca_metni = kanca(senaryo)
    if not kanca_metni or not onceki_kancalar:
        return False
    iskelet = _kalip_iskeleti(kanca_metni)[:KANCA_KALIP_KELIMESI]
    if len(iskelet) < KANCA_KALIP_KELIMESI:
        return False
    for onceki in onceki_kancalar:
        if iskelet == _kalip_iskeleti(onceki or "")[:KANCA_KALIP_KELIMESI]:
            return True
    return False


def is_duplicate_visual_anchor(candidate: str, previous: list[str]) -> bool:
    generic = {
        "ancient", "roman", "greek", "great", "city", "temple", "lighthouse",
        "mechanism", "shipwreck", "pyramid", "pyramids", "construction",
        "engineering", "road", "ruins", "site", "statue",
        # ⚠️ YAPISAL ISIMLER (2026-08-16). Bunlar bir yapinin TURU; iki farkli
        # yapinin ayni turden olmasi ayni konu olduklarini gostermez.
        # Olculdu — havuzda YALNIZCA bu yuzden engellenen iki capa vardi:
        #     Notre Dame Cathedral  <- Chartres Cathedral  (ortak: cathedral)
        #     Brooklyn Bridge       <- Boyacá Bridge       (ortak: bridge)
        # ⚠️ Liste KORLEMESINE genisletilmedi: kumeyi buyutmek tekrar
        # savunmasini zayiflatir. Once "hangi capa yalnizca yapisal bir isim
        # yuzunden engelli" olculdu, sonra yalnizca kanitlananlar eklendi.
        "cathedral", "bridge",
    }
    candidate_words = _normalize_topic(candidate)
    if not candidate_words:
        return True
    for item in previous:
        existing_words = _normalize_topic(item)
        if not existing_words:
            continue
        if candidate_words == existing_words:
            return True
        if (candidate_words & existing_words) - generic:
            return True
    return False


RET_DENEME_BUTCESI = 3
"""Bir konunun KALICI olarak kapanmasi icin gereken ret sayisi.

⚠️ NEDEN VAR — olculdu (2026-08-16). Dislama listesi `published` + `rejected`
capalarindan kuruluyordu, yani **tek bir ret konuyu omur boyu yasakliyordu.**
Kanalin 18 yayini ve 192 reddi var; liste %85 basarisizliktan olusuyordu:

    kullanilmis capa kaydi              211  (tekil 117)
    yalniz REDDEDILMIS capa              99
    havuzda kalan uygun capa           0 / 52
    yalniz yayinlananlar engelleseydi  46 / 52

Yanan 99 konunun 17'si esige 1-10 puan yaklasmisti: Buyuk Piramit, Knossos,
Akrotiri, Aphrodisias, Jerash TEK denemede 78 alip (kapi 80) yasaklandi.

⚠️ Ama sinirsiz tekrar da yanlis: Murad III 15, Talaat Pasha 13 deneme yakti
ve ikisi de gecemedi. 3 butcesi ikisini de disarida tutar (zaten asmislar),
tek denemelik yakin isabetleri geri acar. Kendi kendini sinirlar: 2 retli bir
capa yeniden denenir, duserse 3 olur ve kapanir.

⚠️ YAYIN farkli: yayinlanmis capa KALICI engel. Ayni videoyu iki kez cekmek
tekrar politikasi ihlali; ret ise yalnizca "bu deneme tutmadi" demek.
"""


def _ret_denemeleri(state: dict[str, Any]) -> dict[str, int]:
    """Her capa/konu icin kac ret kaydi var.

    Anahtar `visual_anchor`; bos ise `topic`'e dusulur — eski kayitlarin bir
    kisminda capa alani yok.
    """
    sayac: dict[str, int] = {}
    for kayit in state.get("rejected", []):
        anahtar = str(kayit.get("visual_anchor") or kayit.get("topic") or "").strip()
        if anahtar:
            anahtar = anahtar.casefold()
            sayac[anahtar] = sayac.get(anahtar, 0) + 1
    return sayac


def _butce_doldu(ad: str, sayac: dict[str, int]) -> bool:
    return sayac.get(str(ad).strip().casefold(), 0) >= RET_DENEME_BUTCESI


def engellenen_capalar(state: dict[str, Any] | None = None) -> list[str]:
    """Yeniden kullanilamayacak capalar — yayinlananlar + butcesi dolmus retler.

    ⚠️ TEK KAYNAK. Huni (`huni_besle`) ve uretim (`generate_content_plan`)
    ayni listeyi gormeli; iki tarafin farkli engel listesi tasimasi bu repoda
    daha once yasanmis bir kusur sinifi (kuyrugun kabul ettigi konuyu besleyici
    reddediyordu).
    """
    durum = load_state() if state is None else state
    sayac = _ret_denemeleri(durum)
    engelli = [
        str(kayit.get("visual_anchor", ""))
        for kayit in durum.get("published", [])
        if str(kayit.get("visual_anchor", "")).strip()
    ]
    engelli.extend(
        str(kayit.get("visual_anchor", ""))
        for kayit in durum.get("rejected", [])
        if str(kayit.get("visual_anchor", "")).strip()
        and _butce_doldu(str(kayit.get("visual_anchor", "")), sayac)
    )
    return engelli


ADAY_SOGUMA_SAATI = 24
"""Reddedilen bir Notion adayinin kuyrukta yeniden gorunmesi icin gecmesi
gereken sure.

⚠️ NEDEN VAR — olculdu (2026-08-17), `state.json`. Kuyruk kipli 12 reddin
SEKIZI tek bir adayda:

    8  King Philip's War    <- uc ayri slot; 14:00 slotu tek basina alti deneme
    4  Ernst Hanfstaengl    <- menu kapisiyla 16 Agu'da ayrica kapandi

Sebep kapali bir dongu: uretim dustugunde `adayi_birak` adayi `Seçildi`ye
geri cekiyor, `adaylari_getir` ise `Boşluk skoru` DESCENDING siraliyor. Skor
degismedigi icin aday tam da geldigi yere — kuyrugun basina — donuyor ve
sonraki koşum onu yeniden ilk sirada buluyor. Yani red bir SONUC DOGURMUYOR.

⚠️ SURE BAZLI, DENEME BUTCESI DEGIL. Ayrimi bilerek koruyoruz:
`RET_DENEME_BUTCESI` CAPA duzeyinde calisir ve kalici kapatir; burasi ADAY
duzeyinde calisir ve yalnizca ERTELER. Insanin `Seçildi`ye aldigi bir aday
sessizce cope atilamaz — arsiv zamanla degisiyor ve bugun 8 dosyasi olan
konunun yarin 40 dosyasi olabilir.

24 saat bir gunun butun slotlarini kapsiyor: aday ertesi gun kendiliginde
geri geliyor, o gun ise slot yakmiyor.
"""


def _aday_anahtari(ad: str) -> str:
    return str(ad or "").strip().casefold()


def adayin_son_reddi(baslik: str, state: dict[str, Any]) -> datetime | None:
    """Bu Notion adayinin en son ne zaman reddedildigi — yoksa `None`.

    ⚠️ IKI ESLESME YOLU var ve ikincisi bir GECIS KOPRUSU. `aday_basligi`
    alani 2026-08-17'de eklendi; ondan onceki 235 kayitta yok. Eski kayitlar
    icin `kaynak == "huni"` olanlarda `topic`e dusuluyor, cunku kuyruk kipinde
    model konuyu bazen aynen biraktiginda ikisi esitleniyor (King Philip's
    War'un sekiz kaydinda oyle).

    ⚠️ Kopru EKSIK ESLESIR ve bu bilincli: Hanfstaengl'in dort kaydinda model
    konuyu yeniden yazmis, dordu de birbirinden farkli. Yani eski kayitlarin
    bir kismi soguma uretmeyecek. Alternatifi — bulanik eslesme — YANLIS
    adaylari sogutur, ki bu insanin secimini sessizce yok saymak demek.
    Kopru bir kac gun icinde kendiliginden gereksizlesiyor.
    """
    anahtar = _aday_anahtari(baslik)
    if not anahtar:
        return None

    en_son: datetime | None = None
    for kayit in state.get("rejected", []):
        kayitli = kayit.get("aday_basligi")
        if kayitli is None and kayit.get("kaynak") == "huni":
            kayitli = kayit.get("topic")
        if _aday_anahtari(kayitli) != anahtar:
            continue
        ham = str(kayit.get("rejected_at", "")).strip()
        if not ham:
            continue
        try:
            ne_zaman = datetime.fromisoformat(ham)
        except ValueError:
            # Bozuk zaman damgasi sogumayi dusurmemeli; o kayit yok sayilir.
            continue
        if en_son is None or ne_zaman > en_son:
            en_son = ne_zaman
    return en_son


def aday_sogumada_mi(
    baslik: str, state: dict[str, Any], *, simdi: datetime | None = None
) -> float:
    """Adayin soguma bitimine kalan SAAT; sogumada degilse 0.

    Sayi donuyor cunku cagiran taraf bunu loga basiyor — "atlandi" demek tek
    basina yetmez, insan ne kadar bekleyecegini gormeli.
    """
    son_red = adayin_son_reddi(baslik, state)
    if son_red is None:
        return 0.0
    an = simdi or datetime.now(ZoneInfo(TIMEZONE_NAME))
    if son_red.tzinfo is None:
        son_red = son_red.replace(tzinfo=an.tzinfo)
    kalan = ADAY_SOGUMA_SAATI - (an - son_red).total_seconds() / 3600
    return max(0.0, kalan)


KANAL_SESI = """You are the editorial producer of an English global-history YouTube Shorts channel.

THE CHANNEL HAS ONE FIXED EDITORIAL ANGLE, AND EVERY SCRIPT MUST HAVE IT: the gap between what people assume happened and what the surviving evidence actually shows. Not "here are facts about a place", but "here is what the record says, and it is not what you were told."
Build each script on one of these moves: a widely believed story the evidence contradicts, a mystery where you name what is actually known and where the knowledge stops, a detail so specific it could only come from someone who read the source, or a consequence that outlived the event.
Say what is NOT known, out loud, at least once. "No one has found..." / "The record stops here." Certainty about everything is the signature of a shallow script; naming the edge of the evidence is what a real researcher does and what makes a viewer trust the channel.
Take a position in the final line. Not a summary of what was just said, but a judgement, an implication, or a question the evidence leaves open. A script that ends by restating its own middle has no author.
Vary the structure between videos. If the last scripts opened on an object, open on a person or a moment of discovery instead. A recognisable channel is one where the VOICE is constant and the SHAPE is not."""
"""Kanalin sabit editoryal kimligi — ses ve arastirma acisi (DW-105).

Kanal sahibinin istegi: videolar sablon gibi degil, bir insanin arastirip
yazdigi gibi dursun. Kimlik iddiayla degil ICERIKLE kuruluyor; bunun icin
prompt'a "insan yazdi de" gibi bir cumle KONMADI — konsaydi yalan olurdu ve
zaten izleyicinin gordugu sey metnin kendisi.

Uc unsur seciliyor cunku ucu de olculebilir bicimde jenerik uretimden ayrisiyor:

  * Sabit aci (yayginn inanis ↔ kanit) — her videoya ayni bakis acisini
    veriyor, kanal bir sey SAVUNUYOR hale geliyor.
  * Bilginin sinirini soylemek — "kimse bulamadi", "kayit burada bitiyor".
    Her seye kesin cevap veren metin sig oldugunun isaretidir.
  * Degisken yapi — ses sabit, kalip degil. Ayni iskeletle uretilen 20 video
    tam olarak "toplu uretim" gibi gorunen seydir.
"""

EDITORYAL_YONERGE = """
Return valid JSON only. Create a factual, emotionally compelling, evergreen true story.
The script must be 80-120 spoken English words and end with a memorable line. The first 2-3 seconds must deliver a short, immediately understandable hook that creates a curiosity gap through a surprising factual claim, an unresolved question, or a strong contrast; do not begin with greetings, channel introductions, dates, or slow setup. Scene 1 narration and its visual must directly support that hook.
NEVER open with "Did you know", "Have you ever wondered", "Imagine a world", or any other stock quiz-show phrasing; an opening that could be pasted onto a different topic is a failed hook. Open instead with the single most surprising concrete detail of THIS subject (a number, an object, a contradiction, or an unfinished action) so the first six words could belong to no other video.
Create 6-10 chronological scenes. Define visual_anchor as a specific named civilization, landmark, artifact, archaeological site, vessel, invention, or PERSON in 1-4 words. WHEN THE STORY IS ABOUT ONE NAMED PERSON, THE VISUAL_ANCHOR MUST BE THAT PERSON'S NAME, never an award, institution, or object associated with them, because an anchor like "Victoria Cross" or "Vassar College" retrieves pictures of other people who share it, and the video then shows the wrong human being.
Every scene needs narration and a concrete 3-7 word English Wikimedia Commons search term that repeats at least one distinctive visual_anchor word. Never use abstract terms alone. When the user request carries an ARCHIVE MENU, each scene also needs source_file: one entry's 'dosya' value copied exactly, never invented, never reused by two scenes, and the narration must describe what that file shows.
The anchor holds the video together; it does not have to fill every frame. Vary what the camera is actually on: the person, their hands or possessions, the room, the wider place, the landscape, a document, the crowd, the aftermath. Six scenes of the same building from six angles is a failed scene list even when every search term is correct.
EVERY SCENE NEEDS ITS OWN SEARCH TERM AND THE BARE ANCHOR IS NOT A SEARCH TERM. Repeating one query ("Murad III", "Murad III", ...) returns the same ranked archive results every time, and the video becomes a row of near-identical portraits, which is the single most common reason a video is rejected. Write instead: "Murad III tughra", "Murad III imperial berat", "Murad III Topkapi palace", "Murad III Ottoman map", which is the anchor plus the concrete thing THIS scene is about.
Prefer subjects with visual evidence on Wikimedia Commons or Met Open Access (photographs of any era, engravings, archaeological plates, museum scans), but do not reject a strong story because its imagery is thin; scenes without an archive match are illustrated instead. Use the eligible visual-anchor shortlist in the user request rather than defaulting to famous examples from prior plans. Modern colour photographs of a surviving place or object are welcome; generic modern people, factories, vehicles, schools, water systems, maps, or buildings that merely share one broad word with the narration are forbidden.
NEVER WRITE A SENTENCE WHOSE SUBJECT IS THE RECORD ITSELF. "No one can reconstruct every transition from this summary alone" and "the record here does not name each turning point" are not narration; they are padding you reach for when you do not know enough about the subject, and no archive image can illustrate them, so that scene is guaranteed to show something unrelated. If you cannot fill a scene with a concrete thing that happened, a named person, a place, an object, or a date, write fewer scenes. This ALSO bans naming the source material as the subject: "photographs show the walls", "portraits from the same era show him", "the images do not show" are the same mistake wearing a specific noun; write what the walls WERE and what he DID. Honest uncertainty ABOUT THE WORLD stays welcome ("locals still claim...", "his body was never found", "no one has found the tomb", "the record stops here" as a closing line about the world, not as a scene subject).
Every planned scene must be illustratable either by a real view of the visual_anchor or by an honest historical illustration of the moment being described. Scenes may show a specific event, a named person, a discovery, a disappearance, or a legend as long as the narration stays truthful about what is known and what is only told.
NEVER BUILD A SCENE ON THE MODERN RECOVERY EPISODE OR ON LABORATORY ANALYSIS. Sentences like "a sponge diver found a bronze arm in 1900", "salvagers dragged the marble up with hooks", "a CT scan revealed the hidden join" or "radiocarbon dating placed it at 1600 BC" cannot be illustrated here, because every search term must carry the visual_anchor and the archive holds the ancient object itself, not the dive, the winch, or the scanner. The archive will return a present day museum photograph instead and the scene will be marked as an unrelated modern image. Say what the object IS and what happened to it in its own time; if the date came from a laboratory, state the date as a fact and leave the instrument out.
TELL A STORY, DO NOT DESCRIBE AN OBJECT. A list of a monument's features is not a video; a specific thing that happened there is. Build every script around one of: a documented event with a beginning and an end, a discovery or a disappearance, a legend or myth the culture itself told about the place, a mystery that is still unsolved, or a person whose fate is tied to the anchor. Name people, dates, and outcomes when they are known.
When a legend or myth is used, say plainly that it is a legend ("the Inca told of...", "locals still claim...") and separate it from the archaeological record. An honest legend is compelling; a legend presented as fact is not.
The subject may be a monument, civilization, artifact, invention, vessel, or site, but the SCRIPT must be about something that happened, not about how the thing was built or how large it is. Dimensions, construction techniques, and material lists belong in a single supporting sentence at most.
Avoid graphic violence, medical misinformation, politics, religion advocacy, copyrighted characters, and uncertain claims.
WRITE THE TITLE AS A SEARCH QUERY, NOT AS A HEADLINE. It must read like the phrase an English-speaking viewer would actually type into YouTube: usually a direct question ("What Happened to...", "Why Did...", "Who Built...") or the named subject followed by the hook. Put the searchable proper noun in the first three words. When a subject has a widely used popular name and a scholarly name, the TITLE takes the popular one because that is what people type; the description carries the scholarly one. Under 65 characters when practical, and contain #Shorts.
What you write in `description` is placed UNDER a fixed one line channel signature that already exists, so do not write a channel description, a signature or a sign off yourself. Your own first sentence still carries the search: restate the title's search phrase as a full sentence naming the place, the people, and the century. Then two or three sentences that deliver the answer the title promised; never leave the question unanswered in the description. Then 3 to 5 hashtags.
END ON A REASON TO COME BACK, NOT ON A SUMMARY. The last sentence is the only moment a viewer decides whether this channel is worth following, and a closing that merely restates the video ("the mystery remains unsolved") gives them nothing. Close instead on what this channel keeps doing: the next thing in the archive, the pattern this story belongs to, the question the next one answers. Say it in the video's own voice and in a different shape every time; never write "subscribe", "follow", "like and comment" or any other stock call to action, and never repeat a closing line you have used before.
NEVER USE A DASH CHARACTER ANYWHERE IN THE SCRIPT OR THE SCENE NARRATION: no em dash, no en dash, no hyphen. Rephrase instead: write "single handedly", not "single-handedly"; use a comma or a full stop where you would reach for an em dash; write year ranges as "1652 to 1674". Titles and tags may keep an ordinary hyphen inside a proper name.
Tags must be an array of 6-10 concise strings mixing three kinds: exact named entities including the subject's alternative and popular spellings, broad category terms an interested viewer browses ("ancient history", "archaeology", "lost civilization"), and one format term. Tags are search terms, not a summary; never write a phrase nobody would type into a search box.
Optionally add "mood": one of "agirbasli" (grave: war, death, collapse, loss), "merak" (curious: a puzzle, an unexplained find, an open question), "gorkemli" (grand: monuments, empires, engineering, ceremony). It only picks the background music, so choose the one that fits the script's dominant tone and omit the key entirely if none clearly fits. Never distort the script to match a mood.
JSON keys: topic, visual_anchor, title, script, scenes, description, tags, and optionally mood."""
"""Sozlesmenin geri kalani — kanal kimliginden AYRI tutuluyor.

⚠️ Ikisi de modul duzeyinde sabit. Testler eskiden prompt'u KAYNAK
METNINDEN dilimliyordu (`index("You are the editorial producer")` ile bir
sonraki uc-tirnak arasi). Kimlik ayri bir sabite tasininca o dilim koptu ve
11 test dustu — kusur promptta degil, testin onu okuma bicimindeydi.
"""


UZUN_YONERGE = """
THIS IS A LONG FORM DOCUMENTARY, NOT A SHORT, and the difference is not length alone. The viewer has chosen to sit down for eight to fifteen minutes; a Short's script stretched to that length is the one failure to avoid. No filler, no restating what was already said, no list of a monument's features.
Build the script in parts: an opening that poses the question, then three to five thematic sections that each answer a different part of it, then a closing that takes a position. Each section must move the story somewhere the previous one did not; a section that could swap places with another is a section that should be cut.
NEVER ANNOUNCE THE STRUCTURE. Do not write "in this section", "first we will look at", "as we saw earlier", or any other signposting. The viewer feels a new section through the change of subject, not through being told about it.
AIM FOR ABOUT 1600 SPOKEN WORDS, not the minimum. A script that lands just under the floor is rejected outright and the entire plan is thrown away, so write comfortably inside the range rather than close to its edge.
DO THE ARITHMETIC BEFORE YOU WRITE, because the scene count decides the script length and getting this wrong is the most common way this plan is thrown away. Multiply the number of scenes you intend to write by the words you intend to put in each narration; if that product is under the floor the plan is rejected. Roughly 45 words per narration at 35 scenes, 65 at 24 scenes, 36 at 45 scenes. A narration of 25-30 words is a Short's scene and lands well under the target.
THE SCENE NARRATIONS ARE THE SCRIPT, SPLIT INTO PARTS. Read in order they must tell the same story, in the same words, as `script`. This means the narrations together ARE the full script, not a summary of it: their combined word count must equal the script's, so a 1600 word script split into 35 scenes puts about 45 words in each. Each one must be about the same length as the others, because every image is on screen for exactly the same number of seconds; a scene carrying twice the words of its neighbours leaves the wrong picture on screen for half of what it says.
Length makes one failure far more expensive: inventing facts to fill time. When the source text runs out, write fewer scenes about what it does contain, never more scenes about what it does not."""
"""Uzun formata OZEL yonerge — Shorts sozlesmesinin ustune eklenir.

⚠️ Sahne anlatimlarinin esit uzunlukta olmasi maddesi kozmetik degil:
`run_generator` her materyale ESIT `clip_duration` veriyor (`klip_suresi`),
yani sahne i'nin karesi sesin i'nci esit diliminde ekranda. Shorts'ta 8
sahne × ~12 kelimede kayma gorunmuyordu; 45 sahnede birikiyor ve gorsel
soylenenden kopuyor.
"""


KELIME_CUMLESI = "The script must be 80-120 spoken English words"
"""`EDITORYAL_YONERGE` icindeki kelime araligi cumlesi — HER KIPTE degistiriliyor.

⚠️ Buradaki 80-120 bir DEGER DEGIL, bir CAPADIR: metinde ne yaziyorsa o,
`editoryal_sistem_yonergesi` onu bicimin `kelime_araligi`'yla degistiriyor.
Yani bu sayilari gormek "modele 120 deniyor" anlamina gelmez.

Sabit ayri duruyor ki `EDITORYAL_YONERGE` metni degistiginde `_yonerge_degistir`
TEK yerde patlasin ve iki kip birden duzeltilsin. Eskiden capa dize iki ayri
yerde ciplak yaziliydi ve yalnizca uzun kipte kullaniliyordu.
"""


def _yonerge_degistir(metin: str, eski: str, yeni: str) -> str:
    """Istem cumlesini degistirir; hedef cumle YOKSA PATLAR.

    ⚠️ Sessiz `str.replace` burada tehlikeli olurdu: Shorts sozlesmesi
    zamanla degisirse uzun kipin istemi eski sayilari (80-120 kelime, 6-10
    sahne) tasimaya devam eder ve model her denemede dogrulamadan doner.
    Bes deneme tukendiginde koşum hic video uretmeden duser — bu hatta
    olculmus bir kusur (18:05 koşumu).
    """
    if eski not in metin:
        raise RuntimeError(
            f"uzun format yonergesi kurulamadi: {eski!r} artik istemde yok. "
            "Shorts sozlesmesi degistiyse uzun kipin karsiligi da guncellenmeli."
        )
    return metin.replace(eski, yeni)


def editoryal_sistem_yonergesi(bicim: "VideoBicimi | None" = None) -> str:
    """Modele giden tam sistem yonergesi. Testler bunu okur, kaynagi degil.

    ⚠️ Uzun kipte sozlesme DEGISTIRILIYOR, uzerine yazilmiyor. Ilk tasarim
    "80-120 kelime" cumlesini yerinde birakip sonuna bir gecersiz kilma
    blogu eklemekti; birakilsaydi istem kendi kendisiyle celisirdi ve her
    celiskili deneme ~2.000 kelimelik bir cikarim koşumu demek. Bes deneme
    o sekilde tukenirse o saat icin video uretilmez.

    ⚠️ `bicim` varsayilani `None`, `SHORTS_BICIMI` degil: bu fonksiyon
    dosyada `SHORTS_BICIMI`den ONCE tanimli ve varsayilan degerler `def`
    aninda hesaplaniyor. Ayni sinif kusur bu oturumda uc koşum oldurdu.

    ⚠️ KELIME ARALIGI ARTIK BICIMDEN TURETILIYOR, iki yerde ayri ayri
    yazilmiyor — olculdu (2026-08-18) ve iki gun boyunca uretimi yiyen kusur
    tam olarak buydu:

        istem  (`EDITORYAL_YONERGE`)  "80-120 spoken English words"
        kapi   (`kelime_araligi`)      (80, 150)

    16 Agustos'ta tavan 120'den 150'ye cikarildi (`6d409ed`) ama istemdeki
    SABIT METIN guncellenmedi. Yani modele 120 soyleniyor, dogrulama 150
    istiyor ve red mesaji "must contain 80-150 words" diyordu: model uc ayri
    sayi goruyordu. Shorts dali bu satira kadar sozlesmeyi HIC
    degistirmiyordu, o yuzden tutarsizlik yalnizca Shorts'ta vardi — ve hat
    yalnizca Shorts uretiyor.
    """
    bicim = bicim or SHORTS_BICIMI
    kelime_en_az, kelime_en_cok = bicim.kelime_araligi
    sahne_en_az, sahne_en_cok = bicim.sahne_araligi

    if bicim.ad == SHORTS_BICIMI.ad:
        return KANAL_SESI + _yonerge_degistir(
            EDITORYAL_YONERGE,
            KELIME_CUMLESI,
            f"The script must be {kelime_en_az}-{kelime_en_cok} spoken English words",
        )

    kimlik = _yonerge_degistir(
        KANAL_SESI,
        "English global-history YouTube Shorts channel",
        "English global-history YouTube documentary channel",
    )
    sozlesme = _yonerge_degistir(
        EDITORYAL_YONERGE,
        KELIME_CUMLESI,
        f"The script must be {kelime_en_az}-{kelime_en_cok} spoken English words",
    )
    sozlesme = _yonerge_degistir(
        sozlesme,
        "Create 6-10 chronological scenes.",
        f"Create {sahne_en_az}-{sahne_en_cok} chronological scenes.",
    )
    # ⚠️ Basliktaki `#Shorts` istemden DUSUYOR; kalirsa YouTube videoyu
    # Shorts sayar ve IZLENME SAATI YAZMAZ — uzun formatin butun amaci o
    # saatler. Yasak acikca yaziliyor cunku isteme ayrica son basliklar
    # veriliyor ve hepsi `#Shorts` ile bitiyor: model onlari taklit eder.
    sozlesme = _yonerge_degistir(
        sozlesme,
        "Under 65 characters when practical, and contain #Shorts.",
        "Under 65 characters when practical. NEVER put #Shorts, or any other Shorts "
        "tag, anywhere in the title: this is a long form video and that tag makes "
        "YouTube file it as a Short, which destroys the watch time this video exists "
        "to earn. Earlier titles quoted to you below end in #Shorts because they were "
        "Shorts; do not copy that from them.",
    )
    return kimlik + sozlesme + UZUN_YONERGE


KALIP_ACILISLAR = (
    "did you know",
    "have you ever",
    "imagine a",
    "imagine you",
    "picture this",
    "what if i told you",
    "welcome back",
    "in this video",
    "let me tell you",
    "here's something",
)

# "In the 12th century", "By 1130", "Around the 1500s", "1130 was the year..."
TARIHLE_ACILIS = re.compile(
    r"^\s*(?:(?:in|by|around|during|about|circa|before|after)\s+(?:the\s+)?\d"
    r"|\d{3,4}\b"
    r"|(?:in|by|around|during)\s+the\s+\w+\s+century)",
    re.IGNORECASE,
)


UZUN_TIRELER = "—–―‒"
TUM_TIRELER = "-" + UZUN_TIRELER


# Oznesi DUNYA degil KAYDIN KENDISI olan cumleler. Model konuyu yeterince
# bilmeyince olgu yerine bunlari yaziyor ve ortaya RESMEDILEMEZ bir sahne
# cikiyor: hicbir arsiv gorseli "kayit her donum noktasini anmiyor"u
# gosteremez, dolayisiyla o sahneye zorunlu olarak alakasiz bir gorsel
# geliyor ve hakem haklı olarak uyusmazlik yaziyor.
#
# Olculdu (2026-08-13): Ibn Saud koşumunda 8 sahnenin 2'si buydu — "No one
# can reconstruct every transition from this summary alone" ve "The record
# here does not name each turning point". Talaat Pasha koşumlarinda da ayni
# kalip vardi ("archival uncertainty", "incomplete surviving record").
#
# ⚠️ Kapsam BILEREK dar tutuldu. Istem baska yerde tarihsel belirsizligi
# acikca SERBEST birakiyor ("locals still claim...", "the Inca told of...")
# ve iyi tarih anlatimi bunu gerektiriyor. Burada yalnizca **kendine gonderme
# yapan** cumleler yasakli: oznesi bu ozet/kayit/video olanlar. Genis bir
# belirsizlik yasagi dogrulama-yeniden deneme dongusunu kilitler; her
# yeniden deneme bir cikarim koşumu demek.
RESMEDILEMEZ_KALIPLAR = (
    re.compile(r"\bno one can (?:reconstruct|recover|name|list)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:this|the) (?:summary|record|account|video|list|text) (?:here )?"
        r"(?:does not|cannot|says nothing|is silent)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bfrom (?:this|the) (?:summary|account|record) alone\b", re.IGNORECASE),
    re.compile(r"\bcannot be reconstructed (?:here|from this)\b", re.IGNORECASE),
    # ⚠️ Model ayni ailenin YENI bir ifadesini buldu (2026-08-13, Mehmed II
    # 2. deneme): "Why it ended is not known from the evidence given."
    #
    # Ayrim onemli: "Why it ended is not known" TEK BASINA mesru — Fatih'in
    # 1446'da tahttan inisinin sebebi gercekten tartismali ve bu dunya
    # hakkinda durust bir belirsizlik. Kusurlu olan "from the evidence
    # given" eki: ozneyi dunyadan MODELE VERILEN METNE kaydiriyor. Bu yuzden
    # kalip yalnizca o eki ariyor, belirsizligin kendisini degil.
    re.compile(
        r"\bfrom the (?:evidence|information|details|material|summary|text) "
        r"(?:given|provided|here|above|supplied)\b",
        re.IGNORECASE,
    ),
    # ⚠️ Ailenin UCUNCU bicimi (2026-08-14, arsiv menusu ilk canli plani):
    # "An 1871 image shows the fast vessel", "Another image shows her
    # carrying full sail", "One later port photograph may show Sydney".
    #
    # Bu kez ozne kayitta degil GORSELIN KENDISINDE. Sahne hala yanlis: alt
    # yazi bir kaptiyon oluyor ve izleyici seyrettigi seyin hikayesini degil
    # dosyanin tarifini dinliyor. Kusur menuyle birlikte GELDI, cunku model
    # artik elindeki dosyayi biliyor ve onu anlatmaya egilimli — yani bu
    # kalip, alinti kapisinin yan etkisini kapatiyor.
    #
    # Kasten DAR: yalnizca gorsel turunden bir ozne + "show/depict" fiili.
    # "The photograph was taken in 1871" gibi bir cumle mesru kalmali, bu
    # dunya hakkinda bir olgu.
    re.compile(
        r"\b(?:image|photo|photograph|picture|portrait|engraving|drawing|painting|"
        r"illustration|plate|film|footage)s?\b[^.]{0,40}?\b"
        r"(?:shows?|showing|depicts?|depicting|captures?)\b",
        re.IGNORECASE,
    ),
    # ⚠️ Ailenin DORDUNCU bicimi: KURTARMA/CIKARMA ANI (2026-08-16).
    #
    # Olculdu — ayni gun iki koşum 78 aldi (kapi 80) ve ikisinin de agir
    # kusurlari ayni yerden geldi. Antikythera koşumunda 5 karede "konuyla
    # ilgisiz modern goruntu", Great Sphinx koşumunda kaynak skoru 35:
    #
    #     "a sponge diver finding a bronze arm in 1900"       Antikythera 45
    #     "salvagers dragging the marble with hooks"          Antikythera 45
    #
    # Nedensellik zinciri bu dosyada zaten belgeli: sahnenin arama terimi
    # capayi TASIMAK ZORUNDA (`validate_content_plan`), yani sorgu
    # "Antikythera mechanism sponge diver" oluyor ve arsiv 1900'deki dalis
    # anini degil nesnenin bugunku muze fotografini donduruyor. Sahne
    # zorunlu olarak alakasiz bir goruntu aliyor ve hakem `modern` +
    # `authentic_subject: false` yaziyor — kusur senaryoda dogup gorselde
    # goruluyor.
    #
    # ⚠️ Kasten DAR — genel "found/discovered" BILEREK disarida. "Archaeologists
    # found no human remains in the ash" (Akrotiri) dunya hakkinda mesru bir
    # olgu ve o koşumda agir kusur YOKTU. Yasakli olan, sahnenin gorsel
    # eylemi olarak KURTARMA episodunu anlatmak: ya suraltI kurtarma oznesi,
    # ya da fiziksel cikarma fiili tasiyan bir ozne.
    re.compile(
        r"\b(?:sponge divers?|salvagers?|salvage (?:crew|team|ship|diver|operation)s?|"
        r"treasure hunters?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:divers?|workmen|labou?rers?|crews?|excavators?)\b[^.]{0,40}?\b"
        r"(?:hauled|dragged|raised|hoisted|winched|dredged|lifted|prised|prized)\b",
        re.IGNORECASE,
    ),
    # ⚠️ Ailenin BESINCI bicimi: MODERN ANALIZ TEKNOLOJISI (2026-08-16).
    #
    # Ayni kok: hicbir antik-anit arsivi bir tomografi cekimini ya da
    # radyokarbon olcumunu gosteremez, ve sahnenin sorgusu capaya bagli
    # oldugu icin donen sey yine nesnenin modern fotografi oluyor.
    #
    # ⚠️ Olgunun kendisi yasak DEGIL — yalnizca SAHNE anlatimi olamaz.
    # Radyokarbon tarihi aciklamada ya da bir olguyu destekleyen cumlede
    # yasayabilir; burada elenen, o olcumu resmedilecek AN gibi yazmak.
    re.compile(
        # ⚠️ "x ray" BOSLUKLU da yakalanmali: istem anlatimda her turden tireyi
        # yasakliyor (`tiresiz_anlatim`), yani model "X-ray" yazamiyor ve
        # yalnizca tireli bicimi arayan bir kalip tam da uretilen metni kacirir.
        r"\b(?:x[ -]?rays?|ct scans?|cat scans?|3d scans?|laser scans?|tomograph(?:y|ic)|"
        r"radiocarbon|carbon dating|spectromet(?:ry|er)|dna (?:analysis|test(?:ing|s)?|"
        r"sequenc\w+)|computer models?|digital reconstructions?)\b",
        re.IGNORECASE,
    ),
)


def resmedilemez_kusuru(anlatim: str) -> str:
    """Sahne anlatiminin resmedilemez kusuru — yoksa bos dize.

    Mesaj NE YAPILACAGINI soyluyor, cunku dogrulama hatasi modele geri
    besleniyor ve yalnizca kurali tekrarlayan bir mesaj donguyu kirmiyor
    (ayni ders `validate_content_plan` icindeki gorsel-capa notunda).
    """
    for kalip in RESMEDILEMEZ_KALIPLAR:
        if eslesme := kalip.search(anlatim):
            return (
                f"narration says {eslesme.group(0)!r}, which talks about the record "
                "instead of the world and no archive image can show it; replace the "
                "sentence with a concrete thing that happened, a named person, a "
                "place, an object, or a date"
            )
    return ""


def _noktalama_topla(metin: str) -> str:
    """Tire cikarildiktan sonra geriye kalan bosluk/noktalama artigini toplar."""
    metin = re.sub(rf"[ \t]*[{TUM_TIRELER}][ \t]*", " ", metin)
    metin = re.sub(r"[ \t]+([,.;:!?])", r"\1", metin)
    metin = re.sub(r",[ \t]*([,.;:!?])", r"\1", metin)
    metin = re.sub(r"[ \t]{2,}", " ", metin)
    return metin.strip()


def tiresiz_anlatim(metin: str) -> str:
    """Anlatim metnindeki HER tureden tireyi kaldirir (kanal sahibi, 2026-08-12).

    Istek acikti: "alt yazi metinlerde '-' isareti bulunmasin". Alt yazi
    seslendirme metninden uretiliyor, yani tireyi alt yazidan degil KAYNAKTAN
    silmek gerekiyor — SRT'yi sonradan temizlemek zamanlamayi bozardi.

    Olculdu (son 6 senaryo): 2'sinde uzun tire ("alone—and", "paper—not"),
    4'unde kelime ici tire ("post-conspiracy", "single-handedly",
    "pre-telescopic", "Anglo-Dutch"). Yani tek bir kural yetmiyor, uc ayri
    kullanim var ve her biri farkli karsilik istiyor:

      * Sayi araligi (1652–1674) → " to ". Bosluga cevirmek alt yazida iki
        ayri sayi gibi okunur, seslendirme de oyle soyler.
      * Uzun tire cumle kesmesi → virgul. Ayni duraklamayi veriyor; noktaya
        cevirmek cumleyi ikiye bolup ritmi degistirirdi.
      * Kelime ici tire → bosluk. "single handedly" seslendirmede AYNI,
        alt yazida temiz.

    ⚠️ Yonergeye "tire kullanma" yazmak tek basina YETMEZ: sistem yonergesinin
    kendisi uzun tire kullaniyor (satir 165, 168, 190...), yani model kurali
    okurken ornegini de goruyor. Kanca kusurunda olcusu alinan ders bu
    (DW-87): modele kurali soylemek yetmiyor, KOD kontrol etmeli. Yonerge yine
    de eklendi — duzeltilecek metin sayisini azaltiyor.
    """
    if not metin:
        return metin
    metin = re.sub(rf"(?<=\d)[ \t]*[{TUM_TIRELER}][ \t]*(?=\d)", " to ", metin)
    for tire in UZUN_TIRELER:
        metin = metin.replace(tire, ", ")
    metin = re.sub(r"(?<=\w)-(?=\w)", " ", metin)
    return _noktalama_topla(metin)


def tiresiz_baslik(metin: str) -> str:
    """Baslik/aciklama: uzun tire dusuyor, kelime ici tire KALIYOR.

    Ayrimin sebebi: baslik ve aciklama alt yazi degil, ARAMA metni.
    "Anglo-Dutch War" yazimini "Anglo Dutch" yapmak YouTube aramasinda tam
    eslesmeyi kaybettirir — istegi karsilamayan bir gorunurluk bedeli. Uzun
    tire ise aramaya hicbir sey katmiyor, yalnizca model tiki.
    """
    if not metin:
        return metin
    for tire in UZUN_TIRELER:
        metin = metin.replace(tire, ", ")
    metin = re.sub(r"[ \t]+([,.;:!?])", r"\1", metin)
    metin = re.sub(r",[ \t]*([,.;:!?])", r"\1", metin)
    return re.sub(r"[ \t]{2,}", " ", metin).strip()


def kanca_kusuru(metin: str) -> str:
    """Acilis cumlesinin kusuru — yoksa bos dize.

    ⚠️ Prompt bunlari ZATEN yasakliyordu ve model yine de yapti. Olculdu
    (2026-08-07): yonerge acikca "do not begin with ... dates" diyor,
    uretilen senaryo "In the 12th century, Chaco Canyon was a thriving hub..."
    diye basladi ve yayina cikti.

    Bu, esik hikayesinin (DW-87) aynisi: modele kurali soylemek yetmiyor,
    KOD kontrol etmeli. Ucuz da — dogrulama hatasi zaten modele geri
    besleniyor, tek denemede duzeliyor.

    Acilis neden bu kadar onemli: Shorts'ta dagitimi belirleyen sey ilk 2-3
    saniyedeki tutunma. Tarihle baslayan bir cumle merak degil ders havasi
    kuruyor ve izleyici o cumleyi bitirmeden kaydiriyor.
    """
    ilk = kanca(metin).lower()
    if not ilk:
        return "script must open with a sentence"
    for kalip in KALIP_ACILISLAR:
        if ilk.startswith(kalip):
            return (
                f"opening line starts with the stock phrase {kalip!r}; open with the single "
                "most surprising concrete detail of this subject instead"
            )
    if TARIHLE_ACILIS.match(ilk):
        return (
            "opening line starts with a date or century, which reads like a lecture; "
            "lead with the surprising fact and let the date arrive in a later sentence"
        )
    return ""


KARE_YUVASI = 2
"""Sahne basina kac kare yuvasi (Shorts).

⚠️ SABIT olmasi zorunlu, "elden geldiginde iki" degil. MPT her materyale
ESIT `clip_duration` veriyor; bir sahne iki yuva, digeri tek yuva alsaydi
iki yuvali sahne ayni ses icin iki kat ekran suresi yer ve gorsel
anlatimdan kayardi. Ikinci gorsel yoksa BIRINCISI iki yuvaya konuyor —
o sahne bugunku haliyle birebir ayni gorunur, zamanlama bozulmaz.

⚠️ Tanim BURADA, dosyanin ortasinda degil: `SHORTS_BICIMI` bunu varsayilan
deger olarak okuyor ve varsayilan degerler `def` anında hesaplaniyor.
Asagida biraktigimda ice aktarma `NameError` ile oluyordu — bu oturumda
uc uretim koşumunu olduren kusurun aynisi.
"""


@dataclass(frozen=True)
class VideoBicimi:
    """Bir video biciminin sayisal sozlesmesi — TEK YERDE.

    ⚠️ Dagitilmis `if uzun_format:` dallari yerine tek bir nesne, cunku bu
    sayilar birbirine bagli: kelime sayisi konusma suresini, konusma suresi
    gereken gorsel sayisini, gorsel sayisi da arsiv arzini belirliyor.
    Ayri ayri degistirilirlerse sessizce tutarsiz bir video cikar.
    """

    ad: str
    kelime_araligi: tuple[int, int]
    sahne_araligi: tuple[int, int]
    kare_yuvasi: int
    dikey: bool


SHORTS_BICIMI = VideoBicimi(
    ad="shorts",
    # ⚠️ TAVAN 120'den 150'ye CIKARILDI (2026-08-16, kanal sahibinin karari).
    #
    # Gerekce olculdu: cikarim arka ucu Kimi'ye gectikten sonra model dogal
    # olarak 122-151 kelime yaziyor ve 120 tavani bunu her seferinde
    # reddediyordu. Tek koşumda olculen redler: 122, 127, 146, 151, 249 —
    # yani bes denemenin dordu SIRF kelime sayisi yuzunden yaniyordu ve her
    # deneme bir model cagrisi.
    #
    # 150 GUVENLI: 170 kelime/dk olculdu (bkz. `UZUN_BICIMI`), yani
    #     120 kelime = 42,4 sn   (eski tavan)
    #     150 kelime = 52,9 sn   (yeni tavan)
    #     170 kelime = 60,0 sn   (YouTube Shorts SINIRI)
    # Yeni tavan sinirin 7 saniye altinda kaliyor.
    #
    # ⚠️ Eski 120'nin yazili bir gerekcesi YOKTU — olculmus bir tutunma
    # degeri degil, editoryal bir secimdi. Video uzunlugu ~42 sn'den ~50
    # sn'ye cikiyor; tutunma bundan etkilenirse ilk bakilacak yer burasi
    # (kanalin olculen kusuru izleyicinin ILK KESMEDE gitmesi).
    kelime_araligi=(80, 150),
    sahne_araligi=(6, 10),
    # Sahne basina iki kare: gorsel altyazi ritmine yaklassin (2026-08-14,
    # kanal sahibinin sesli notu).
    kare_yuvasi=KARE_YUVASI,
    dikey=True,
)

UZUN_BICIMI = VideoBicimi(
    ad="uzun",
    # ⚠️ Olculdu (2026-08-15), gercek edge-tts yolunda uc uzunlukta:
    # 120 kelime 42,10 sn · 1.200 kelime 423,07 sn · 2.200 kelime 774,79 sn
    # -> ucunde de 170 kelime/dakika. Yani bu aralik 7,1-12,9 dakika.
    #
    # Onceki not "~150 kelime/dk" diyordu; o sayi TEK bir Shorts orneginden
    # (Anita 41 sn / ~100 kelime) cikarilmisti ve olcum onu duzeltti. Ayni
    # koşum TTS'in 2.200 kelimeyi TEK PARCADA uretebildigini de gosterdi.
    #
    # ⚠️ TABAN 1.200'DEN 900'E INDIRILDI (2026-08-15, kanal sahibinin karari).
    # Sebep olculdu: dokuz koşumda model su uzunluklari uretti —
    #
    #     876 · 926 · 1.055 · 1.208 · 1.210 · 1.353
    #
    # yani ortalama ~1.100 ve 1.200 taban dagilimin TAM ORTASINI kesiyordu.
    # Bes deneme bu yuzden yaniyordu: model kotu yazmiyordu, sozlesme
    # modelin dogal ciktisinin ustune konmustu.
    #
    # ⚠️ 1.200 bir YouTube GEREGI DEGILDI, editoryal bir tercihti. Uzun
    # format esigi 60 saniye; 900 kelime 170 kelime/dk ile 5,3 dakika eder
    # ve fazlasiyla uzun formattir. Kanalin tutunma verisi de kisa lehine:
    # izleyicinin ucte biri ILK SAHNE DEGISIMINDE gidiyor, yani 13 dakikalik
    # bir ilk deneme kanitlanmamis bir bahis olurdu.
    #
    # Istemdeki "1600 hedefle" yonergesi KALIYOR: hedef yuksek, taban
    # gercekci. Aralik artik 5,3-12,9 dakika.
    kelime_araligi=(900, 2200),
    # ⚠️ Sahne sayisinin tavani ARSIV ARZINDAN geliyor, tercihten degil.
    # Olculdu (2026-08-15, menu siniri 60): Bagan 49, Herculaneum 37,
    # Alhambra 32, Egyptian pyramids 23 kullanilabilir gorsel. 45'in
    # ustunu istemek, arzin veremedigi videoyu istemek olurdu.
    #
    # ⚠️ TAVAN 45'TEN 39'A INDI (2026-08-15), sebep RITIM. Kelime tabani
    # 900'e inince en kotu durum su oluyordu:
    #
    #     900 kelime / 170 = 317 sn ses ; 317 / 45 sahne = 7,0 sn/kare
    #
    # ve belgesel ritmi icin taban 8 saniye (bkz. asagidaki hesap ve
    # `test_sahne_basina_sure_belgesel_ritmi`). Kanalin olculen kusuru da
    # tam burada: izleyicinin ucte biri ILK SAHNE DEGISIMINDE gidiyor, yani
    # kesmeyi hizlandirmak en yanlis yon.
    #
    #     317 sn / 8 sn = 39 sahne
    #
    # Ust uc degismedi: 2.200 kelime / 24 sahne = 32 sn/kare.
    sahne_araligi=(24, 39),
    # ⚠️ Uzun formatta sahne basina TEK kare. Shorts'ta iki yuva vardi
    # cunku 5 saniyelik bir kare altyazidan yavas kaliyordu; 15 saniyelik
    # bir belgesel karesinde ayni sorun yok ve ikiye bolmek gereken gorsel
    # sayisini iki katina cikarip arzi asardi.
    kare_yuvasi=1,
    dikey=False,
)


def validate_content_plan(
    plan: ContentPlan,
    sahne_sayisi: int | None = None,
    *,
    bicim: VideoBicimi = SHORTS_BICIMI,
    konu: str = "",
    sahne_tavani: int | None = None,
) -> None:
    word_count = len(re.findall(r"\b[\w'-]+\b", plan.script))
    if kusur := kanca_kusuru(plan.script):
        raise ValueError(kusur)
    en_az, en_cok = bicim.kelime_araligi
    if not en_az <= word_count <= en_cok:
        raise ValueError(f"script must contain {en_az}-{en_cok} words, got {word_count}")
    # ⚠️ `sahne_sayisi` verilirse aralik degil TAM SAYI zorunlu. Sebep bir
    # deney: klip suresi `ses ÷ sahne` oldugu icin sahne sayisi, ilk kesmenin
    # NE ZAMAN geldigini belirliyor. Olculdu (2026-08-14, `audienceWatchRatio`):
    # izleyicinin ucte biri tam ilk sahne degisiminde gidiyor (Anita 41sn/8 =
    # 5,1sn, Chaco 33sn/8 = 4,1sn — dusus iki videoda da orada basliyor).
    # Modelin 6 ile 10 arasinda serbestce secmesi, deneyin iki kolunu
    # birbirine karistirirdi.
    if sahne_sayisi is not None:
        if len(plan.scenes) != sahne_sayisi:
            raise ValueError(
                f"content plan must contain exactly {sahne_sayisi} scenes, "
                f"got {len(plan.scenes)}"
            )
    else:
        sahne_en_az, sahne_en_cok = bicim.sahne_araligi
        # ⚠️ TAVAN ARZA GORE DARALTILIYOR, ama TAM SAYI ISTENMIYOR.
        #
        # Olculdu (2026-08-15, ONUNCU koşum): tam sayi istemek bes denemenin
        # ikisini tek basina yakti — model 35 istenirken 38 ve 34 yazdi, ve
        # o iki plan baska her acidan GECERLIYDI (1.176 ve 1.444 kelime,
        # dogru capa). Tam sayi, araliktan olculebilir sekilde daha zor.
        #
        # Tavan yine de gerekli: arsiv 38 dosya veriyorsa 41 sahnelik plan
        # alinti kapisinda dusuyordu (dokuzuncu koşum).
        if sahne_tavani is not None:
            sahne_en_cok = min(sahne_en_cok, sahne_tavani)
        if not sahne_en_az <= len(plan.scenes) <= sahne_en_cok:
            raise ValueError(
                f"content plan must contain {sahne_en_az}-{sahne_en_cok} scenes, "
                f"got {len(plan.scenes)}"
            )
    if not plan.topic.strip() or not plan.title.strip():
        raise ValueError("topic and title are required")
    anchor_words = _normalize_topic(plan.visual_anchor)
    if not 1 <= len(anchor_words) <= 4:
        # ⚠️ Mesaj eskiden yalnizca kurali soyluyordu ve model uc denemede de
        # AYNI adi geri yaziyordu; dorduncude cikarim zaman asimina ugrayip
        # kosum cokuyordu. Dogrulama hatasi modele geri besleniyor, yani
        # mesaj NE YAPILACAGINI soylemezse dongu kirilmiyor.
        raise ValueError(
            f"visual anchor {plan.visual_anchor!r} resolves to {len(anchor_words)} "
            "words; use at most 4. Drop honorifics and middle names and keep the "
            "shortest form a viewer would recognise"
        )
    # ⚠️ KOD KAPISI. Uzun kipte capa, ARZI OLCULEN konunun kendisi olmali.
    # Olculdu (2026-08-15, dorduncu Herculaneum koşumu): model capayi
    # "Herculaneum" yerine "House of the Stags" (tek bir ev) sectI. Asagidaki
    # `:844` kapisi her sahnenin teriminin capayi TASIMASINI zorunlu kildigi
    # icin 35 sahnenin 35'i de "Stags" aradi; arsiv modern geyik heykelleri
    # dondurdu ve kaynak kapisi 63 puan verdi.
    #
    # Kusur uzun formata OZGU: 8 sahnede dar capa calisiyor, 35 sahnede o
    # capanin arsivi tukeniyor. Arz olcumunu (`arsiv_arzi_olc.py`) biz KONU
    # uzerinde yapiyoruz, model ise kimsenin olcmedigi bir alt kumeye
    # geciyor — yani olculen sayi ile uretilen video baska seyden bahsediyor.
    #
    # Yalnizca `konu` disaridan verildiginde uygulanir: yedek kipte capayi
    # model sectigi icin karsilastirilacak bir konu YOK. Shorts'ta dar capa
    # kasitli ve dokunulmuyor (bkz. "Vassar College" gerekcesi, `:403`).
    if konu and not bicim.dikey and not (anchor_words & _normalize_topic(konu)):
        raise ValueError(
            f"visual anchor {plan.visual_anchor!r} shares no word with the topic "
            f"{konu!r}. In a long form video every scene search term must carry the "
            "anchor, so a narrower anchor points all of them at a subset of the "
            "archive and it runs out. Use the topic itself as the visual anchor and "
            "put the narrower subject in the individual scene search terms instead"
        )
    if len(plan.title) > 100:
        raise ValueError("YouTube title must be at most 100 characters")
    # ⚠️ KOD KAPISI, yalnizca istem degil. Uzun formatin butun amaci izlenme
    # saati ve YouTube `#Shorts` etiketli videoyu Shorts sayip saat YAZMIYOR.
    # Isteme ayrica son 40 baslik veriliyor ve hepsi `#Shorts` ile bitiyor,
    # yani modelin onunde yasagi delen 40 ornek var; DW-87 dersi geregi
    # dogrulanabilir olguyu kod denetliyor.
    if not bicim.dikey and "#shorts" in plan.title.casefold():
        raise ValueError(
            f"title {plan.title!r} contains #Shorts, but this is a long form video. "
            "YouTube would file it as a Short and it would earn no watch time. "
            "Write the same search phrase without any Shorts tag"
        )
    if len(plan.tags) < 3:
        raise ValueError("at least three tags are required")
    for index, scene in enumerate(plan.scenes, 1):
        term = scene.get("search_term", "").strip()
        narration = scene.get("narration", "").strip()
        if not narration or len(term.split()) < 2:
            raise ValueError(f"scene {index} must contain narration and a concrete search term")
        if not (_normalize_topic(term) & anchor_words):
            raise ValueError(f"scene {index} search term must include the visual anchor")
        if kusur := resmedilemez_kusuru(narration):
            raise ValueError(f"scene {index} {kusur}")
        # ⚠️ Capayi TEKRARLAMAK yetmiyor, capaya bir sey EKLEMEK gerekiyor.
        # "Murad III" tek basina 2 kelime ve capayi iceriyor, yani eski
        # dogrulamayi geciyordu.
        if not (_normalize_topic(term) - anchor_words):
            raise ValueError(
                f"scene {index} search term {term!r} is only the visual anchor; add "
                "the concrete thing this scene is about (an object, a document, a "
                "building, a place, an event) so the archive returns something other "
                "than another portrait"
            )
    # ⚠️ Sahne terimleri BIRBIRINDEN farkli olmali. Olculdu (2026-08-13):
    # uretilen planlarda 8 sahnenin 8'i de birebir ayni terimi tasiyordu
    # ("Mehmed II", "Murad III"). Ayni sorgu her sahnede ayni sirali aday
    # listesini getiriyor; `used_titles` yalnizca birebir tekrari
    # engelledigi icin sahne N listenin N'inci gorselini aliyor — hepsi ayni
    # havuzun en tepesindeki portreler. Hakem bunu her koşumda "duruk portre
    # yigini, tekrarlayan format" diye cezalandirdi ve gorsel skor 78'i
    # gecemedi (kapi 80).
    #
    # Istem cesitliligi ZATEN istiyordu ("Vary what the camera is actually
    # on..."). DW-87 dersi: modele soylemek yetmiyor, KOD kontrol etmeli.
    terimler = [
        " ".join(sorted(_normalize_topic(scene.get("search_term", "")))) for scene in plan.scenes
    ]
    tekrarlayan = {terim for terim in terimler if terimler.count(terim) > 1}
    if tekrarlayan:
        raise ValueError(
            f"{len(tekrarlayan)} search term(s) repeat across scenes "
            f"({', '.join(sorted(tekrarlayan))}); every scene needs its OWN concrete "
            "search term, because an identical query returns the same ranked archive "
            "results and the video becomes a row of near-identical portraits. Vary "
            "what the camera is on: the person, a document they signed, their seal, "
            "the room, the city, the battle, the tomb"
        )


def parse_cli_result(stdout: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    best: dict[str, Any] | None = None
    best_end = -1
    best_start = len(stdout)
    for start, character in enumerate(stdout):
        if character != "{":
            continue
        try:
            payload, relative_end = decoder.raw_decode(stdout[start:])
        except json.JSONDecodeError:
            continue
        absolute_end = start + relative_end
        if not isinstance(payload, dict):
            continue
        if absolute_end > best_end or (
            absolute_end == best_end and start < best_start
        ):
            best = payload
            best_end = absolute_end
            best_start = start
    if best is not None:
        return best
    # ⚠️ CIKTIYI MESAJA KOY. Eski hali yalnizca "complete JSON object" diyordu
    # ve bu, JSON'u KESILMIS bir cevapla JSON HIC OLMAYAN bir cevabi ayirt
    # edilemez kiliyordu. Olculdu (2026-08-15, ilk uzun format koşumu): CLI
    # duz metin `API call failed after 3 retries: HTTP 429: The usage limit
    # has been reached` dondurdu, hat bunu "eksik JSON" diye bildirdi ve
    # teshis istemin cok uzun oldugu yonune saptI — oysa istem hic
    # gonderilmemisti. Kota, ag ve kimlik hatalarinin hepsi bu yoldan gecer.
    ozet = " ".join(stdout.split())[:300] or "(cikti bos)"
    raise ValueError(f"CLI output did not contain a complete JSON object: {ozet}")


AZAMI_KAYNAK_BASLIGI = 70
AZAMI_SANATCI = 45


def _kaynak_basligi(baslik: str) -> str:
    """Commons dosya adini okunabilir bir baslik haline getirir.

    Ham ad aciklamaya oldugu gibi girmemeli:

        File:Masonry of the Chaco and other ruins. R. H. Kern delt. P.S.
        Duval's Lith. Steam Press. Philada. (to accompany) Reports of the
        (IA dr masonry-of-the-chaco-and-other-ruins-...-0380044).jpg

    Icindeki `(IA ...)` arsiv kimligi ve baski atolyesi kunyesi izleyiciye
    hicbir sey anlatmiyor; yalnizca yer kapliyor.
    """
    ad = re.sub(r"^File:", "", (baslik or "").strip())
    ad = re.sub(r"\.(jpe?g|png|tiff?|gif|svg|webp)$", "", ad, flags=re.IGNORECASE)
    ad = ad.replace("_", " ")

    # ⚠️ Kunye KESILIYOR, desenle silinmiyor. Ilk deneme
    # `[A-Z][\w.\s]*\bdelt\b\..*$` idi ve acgozlu oldugu icin basligin tamamini
    # yedi — "Pottery found at the Publo Hungo Pavie. R. H. delt." ifadesinde
    # `[\w.\s]*` bastan itibaren esletti ve geriye bos dize kaldi.
    kesim = len(ad)
    for kunye in (r"\bdelt\b", r"\blith\b", r"\bduval", r"\bsteam press\b",
                  r"\bphilada\b", r"to accompany", r"reports of the", r"\(IA\b"):
        if bulunan := re.search(kunye, ad, flags=re.IGNORECASE):
            kesim = min(kesim, bulunan.start())
    kesilmis = ad[:kesim]
    # Kunyeden geriye kalan sanatci basharfleri: "... Pavie. R. H. " / "... Kern "
    kesilmis = re.sub(r"(?:\b[A-Z]\.\s*)+(?:[A-Z][a-z]+\s*)?$", "", kesilmis)
    ad = (kesilmis or ad).strip(" .-,")

    ad = re.sub(r"\s+", " ", ad).strip(" .-,")
    if len(ad) > AZAMI_KAYNAK_BASLIGI:
        ad = ad[:AZAMI_KAYNAK_BASLIGI].rsplit(" ", 1)[0].rstrip(" .-,") + "…"
    return ad


def _kaynak_sanatcisi(sanatci: str, *, zorunlu: bool = False) -> str:
    """Sanatci alanini kisaltir.

    Commons bu alani kitap kunyesinden aldigi icin bazen bir isim degil bir
    isim listesi geliyor: "Johnston, Joseph E. Marcy, R. B. Simpson. James H.
    Whiting, W.H.C. Kern, Richard H., 1821-1853". Okunmayan bir satir atif
    islevi gormuyor.

    ⚠️ `zorunlu` ayrimi hukuki. Kamu mali/CC0'da sanatci nezaket, uzunsa
    dusuruluyor. CC BY'de eser sahibinin adi lisansin ISTEDIGI unsur — orada
    dusurmek atif ihlali olurdu, bu yuzden kisaltiliyor ama yaziliyor.
    """
    ad = re.sub(r"<[^>]+>", "", (sanatci or "")).strip()
    ad = re.sub(r",?\s*\d{4}-\d{0,4}\.?$", "", ad).strip(" .,")
    ad = re.sub(r"\s+", " ", ad)
    if len(ad) <= AZAMI_SANATCI:
        return ad
    if not zorunlu:
        return ""
    return ad[:AZAMI_SANATCI].rsplit(" ", 1)[0].rstrip(" .,") + "…"


def format_commons_credits(credits: list[dict[str, Any]]) -> str:
    """Gorsel kaynaklarini video aciklamasi icin bicimlendirir.

    ⚠️ CC BY gorselleri icin atif **hukuki zorunluluk**, nezaket degil: lisans
    eser sahibinin adini, lisansi ve kaynagi istiyor. Kamu mali / CC0 icin ise
    zorunluluk yok — kaynak gostermek nezaket.

    Bicimi bu ayrim belirliyor. Once ham baglanti listesi yaziliyordu ve uc
    gorsel aciklamanin 1200 karakterini yiyordu; yuzde-kodlu Commons adresleri
    okunmuyor bile. Artik:

      * Hepsi kamu mali/CC0 ise: tek basliK altinda temiz baslik + sanatci.
        Baglanti yok, cunku gerekmiyor.
      * Aralarinda CC BY varsa: YALNIZCA o satirlar baglanti ve lisans adi
        tasiyor — zorunlulugun oldugu yerde tam, olmadigi yerde sade.

    Ayni kaynak birden cok sahnede kullanildiysa bir kez yaziliyor.
    """
    from wikimedia_materials import is_safe_license

    satirlar: list[str] = []
    gorulen: set[str] = set()
    hepsi_serbest = True
    for credit in credits:
        link = str(credit.get("source_url", "")).strip()
        if not link or link in gorulen:
            continue
        gorulen.add(link)
        lisans = str(credit.get("license", "")).strip()
        # ⚠️ Kosul "CC BY mi" degil "kamu mali/CC0 DEGIL mi". Bilinmeyen bir
        # lisansi serbest saymak, atifi tam da emin olmadigimiz yerde atlamak
        # olurdu; yon asimetrik — gereksiz atif zarar vermiyor, eksik atif
        # lisans ihlali.
        serbest = is_safe_license(lisans)
        parcalar = [_kaynak_basligi(str(credit.get("title", "")))]
        if sanatci := _kaynak_sanatcisi(str(credit.get("artist", "")), zorunlu=not serbest):
            parcalar.append(sanatci)
        if not serbest:
            hepsi_serbest = False
            parcalar.append(lisans)
            parcalar.append(link)
        # Ayirac uzun tireydi; aciklama da izleyicinin okudugu bir metin ve
        # kanal sahibi metinlerde tire istemiyor (2026-08-12). Icerik ayni,
        # yalnizca ayirac degisti — atifin hicbir parcasi dusmuyor.
        satirlar.append("• " + " · ".join(p for p in parcalar if p))
    if not satirlar:
        return ""
    # ⚠️ Baslik SABIT "Wikimedia Commons" idi. Hat artik Met ve Europeana'dan
    # da gorsel aliyor (DW-130); sabit baslik, Europeana'dan gelen bir
    # gravuru Commons'a mal ediyordu — aciklama kaynagi YANLIS gosteriyordu.
    # Saglayici artik kunyelerden okunuyor.
    saglayicilar: list[str] = []
    for credit in credits:
        ad = str(credit.get("provider") or "Wikimedia Commons").strip()
        if ad and ad not in saglayicilar:
            saglayicilar.append(ad)
    baslik = "Images: " + ", ".join(saglayicilar or ["Wikimedia Commons"])
    if hepsi_serbest:
        baslik += " (public domain / CC0)"
    return baslik + "\n" + "\n".join(satirlar)


YOUTUBE_ACIKLAMA_SINIRI = 5000
"""YouTube `videos.insert` aciklama sinirI, karakter."""


def aciklamayi_kirp(
    ust: str, kunyeler: str, sinir: int = YOUTUBE_ACIKLAMA_SINIRI
) -> str:
    """Aciklamayi YouTube sinirina sigdirir — atifi SONDAN keserek.

    ⚠️ OLCULDU (2026-08-15, DW-51 denetimi): `format_commons_credits` her
    benzersiz kaynak icin bir satir yaziyor ve UST SINIR YOK. Satir ici
    kisitlar var (`AZAMI_KAYNAK_BASLIGI = 70`, `AZAMI_SANATCI = 45`) ama
    satir SAYISINA yok.

        Shorts  : 6-10 kaynak   ≈ 1.000 karakter
        uzun    : 24-45 kaynak  ≈ 3.000-5.400 karakter

    CC BY varsa o satirlar ayrica tam Commons adresini tasiyor (yuzde-kodlu,
    100-150 karakter) — fonksiyonun kendi belgesi "uc gorsel aciklamanin
    1200 karakterini yiyordu" diyor.

    ⚠️ Kusur EN PAHALI anda patliyordu: `videos.insert` 400
    `invalidDescription` doner ve bu, render ile IKI kalite kapisindan SONRA
    olur. Kirpma render'dan once, bu fonksiyonda.

    ⚠️ SIRA HUKUKI: CC BY satirlari atif ZORUNLULUGU tasiyor, kamu mali /
    CC0 satirlari nezaket (bkz. `format_commons_credits`). O yuzden once
    serbest lisansli satirlar dusuyor; zorunlu atiflar sona kadar kaliyor.
    Bu asimetri fonksiyonun kendi gerekcesiyle ayni: gereksiz atif zarar
    vermiyor, eksik atif lisans ihlali.
    """
    tam = f"{ust}\n\n{kunyeler}" if kunyeler else ust
    if len(tam) <= sinir:
        return tam
    if not kunyeler:
        # Kunye yoksa kisaltilacak tek sey metnin kendisi.
        return ust[:sinir]

    satirlar = kunyeler.split("\n")
    baslik, kunye_satirlari = satirlar[0], satirlar[1:]
    # Zorunlu atif = adres tasiyan satir (`format_commons_credits` yalnizca
    # serbest OLMAYAN satirlara baglanti koyuyor).
    zorunlu = [s for s in kunye_satirlari if "http" in s]
    nezaket = [s for s in kunye_satirlari if "http" not in s]

    not_satiri = "• …"
    while nezaket or zorunlu:
        tutulan = zorunlu + nezaket
        govde = "\n".join([baslik, *tutulan, not_satiri])
        aday = f"{ust}\n\n{govde}"
        if len(aday) <= sinir:
            return aday
        if nezaket:
            nezaket.pop()
        else:
            # ⚠️ Buraya duşulmesi lisans ihlali riski demek; yine de sessiz
            # birakilmiyor, cunku alternatif yuklemenin tamamen dusmesi.
            zorunlu.pop()
    return f"{ust}\n\n{baslik}"[:sinir]


def yayina_uygun(gorsel_skor: int, altyazi_skor: int) -> bool:
    """Esik kararini KOD verir; inceleyici modele sorulmaz.

    Olculdu (2026-08-05, DW-87): prompt "visual_alignment_score en az 50
    olmali" dedigi surece model, kusur gordugu her kagida esigin bir tik
    altini yaziyordu. Ayni kagit, ayni model, ayni sicaklik, ucer tekrar:

        esik promptta anilinca : 45, 45, 45
        esik anilmayinca       : 75, 75, 70

    Yani skor bir olcum degildi — "hayir" oyunun sayiya cevrilmis haliydi ve
    yapisi geregi esigi hicbir zaman gecemezdi. Kapiyi acacak sayiyi kapinin
    kendisi yaziyordu. Uc kosum, dokuz deneme, dokuzunda da tam 45; tek bir
    video cikmadi. Sorunlu sahne teshisi ise iki kolda da ayniydi ([3, 7]) —
    model gordugunu dogru raporluyor, bozuk olan yalnizca sayiydi.

    Bundan sonra model yalnizca OLCER (hangi sahne tutmuyor, kagit ne kadar
    hizali); gecti/kaldi karari burada verilir.
    """
    return gorsel_skor >= MIN_VISUAL_SCORE and altyazi_skor >= MIN_SUBTITLE_SCORE


def agir_kusurlari_ayikla(kareler: Any) -> list[str]:
    """Hakemin kare basina bildirdigi OLGULARI agir kusura cevirir.

    ⚠️ Kararin sahibi burasi, hakem degil (DW-87). Modele "bu yayinlanabilir
    mi" diye sorulmuyor; "bu karede gordugun kisi anlatilan kisi mi"
    soruluyor ve cevabin ne anlama geldigine KOD karar veriyor.

    ⚠️ EKSIK ALAN KUSUR SAYILMAZ. Alan hic gelmezse (eski hakem cevabi, kirik
    JSON, modelin atladigi kare) kusur yazilmiyor. Tersi, cevap bicimi
    degistigi anda her videoyu yayindan dusururdu — sessiz ve tam bir
    duruş. Kapinin isi yanlisi yakalamak, belirsizligi cezalandirmak degil.

    ⚠️ "YANLIS" ILE "SECILEMIYOR" AYRI (2026-08-14). Ilk surum ikili sordu
    (`person_ok` true/false) ve hakem emin olamadigi her karede `false`
    yazdi; kod bunu "yanlis kisi" sayiyordu. Olculdu: Kon-Tiki koşumunda
    gorsel 86 ve 88 alan (kanalin en iyi yayinlanmis videosu 90) iki video
    yalnizca bu yuzden dustu, hakemin kendi cumlesi ise "the small
    illustrated figures CANNOT BE VERIFIED as Thor Heyerdahl" idi. Kapi
    yanlisi degil belirsizligi ceza landiriyordu.

    ⚠️ MODERN GORUNTU TEK BASINA AGIR KUSUR DEGIL. Ayni olcumde 33 agir
    kusurun 22'si "modern goruntu" cikti ve hepsi GERCEK nesnenin bugunku
    fotografiydi (Kon-Tiki salinin muzedeki hali). Istem bunu zaten acikca
    serbest birakiyor: "Modern colour photographs of a surviving place or
    object are welcome." Kusur, modern bir goruntunun konuyla ilgisiz
    olmasi: `modern` VE `authentic_subject` degilse agir.
    """
    if not isinstance(kareler, list):
        return []
    kusurlar: list[str] = []
    for sira, kare in enumerate(kareler, 1):
        if not isinstance(kare, dict):
            continue
        numara = kare.get("n", sira)
        if str(kare.get("person", "")).strip().lower() == "wrong":
            kusurlar.append(f"kare {numara}: anlatilan kisi degil")
        if str(kare.get("period", "")).strip().lower() == "wrong":
            kusurlar.append(f"kare {numara}: donem uyusmuyor")
        if kare.get("modern") is True and kare.get("authentic_subject") is False:
            kusurlar.append(f"kare {numara}: konuyla ilgisiz modern goruntu")
    return kusurlar


def should_publish(review: QualityReview) -> bool:
    # `review.publishable` bilerek OKUNMUYOR: karar skorlardan yeniden
    # turetiliyor ki modelden gelen bir bayrak ileride sessizce geri sizmasin.
    #
    # ⚠️ AGIR KUSUR TEK BASINA YETER. Skor ortalama bir izlenim ve yuksek bir
    # ortalama tekil bir yalani gizleyebiliyor: Mehmed II 84 aldi ve ayni
    # incelemede 10 kusur listelendi (olculdu 2026-08-13). Yanlis kisi
    # gostermek ortalamaya karisacak bir eksiklik degil.
    #
    # ⚠️ DUZELTME (2026-08-14). Burada eskiden su yaziyordu: "Geriye donuk
    # olculdu: yayinlanmis 12 videonun HICBIRINDE agir kusur yok, yani bu
    # kapi gecmisteki tek bir basariyi bile engellemezdi." O olcum BOSTU:
    # `frames` alanini hakeme ayni oturumda bu kapiyla BIRLIKTE ekledim
    # (3f48840), yani eski kayitlarda alan hic yoktu ve "kusur yok" sonucu
    # liyakatten degil alanin yoklugundan geliyordu.
    #
    # Gercek veriyle ilk sinav (2026-08-14, Kon-Tiki): gorsel 86 ve 88,
    # altyazi 91 ve 84 alan iki video — kanalin yayinlanmis en iyi videosu
    # 90 — YALNIZCA bu kapida dustu. 33 agir kusurun 22'si gercek nesnenin
    # muzedeki fotografiydi. Kapi kaldirilmadi, kusur TANIMI duzeltildi;
    # gerekce `agir_kusurlari_ayikla` icinde.
    if review.agir_kusurlar:
        return False
    return yayina_uygun(
        review.visual_alignment_score, review.subtitle_readability_score
    )


def sorunlu_sahneler(review: QualityReview, toplam_sahne: int) -> list[int]:
    """Hangi sahneler yeniden uretilecek — inceleme ciktisi kendi icinde celisebilir.

    `problem_scene_numbers` tek basina guvenilmiyor. Olculdu (2026-08-05,
    "The Marvel of Sigiriya"): `issues` metni **6 ve 7. sahneleri** isaret
    ederken `problem_scene_numbers` **[3, 4]** dondu. Hat bildirilen listeye
    guvendigi icin YANLIS sahneleri yeniden uretti; gercekten bozuk olanlara
    hic dokunulmadi, skor 45'te kaldi (esik 50) ve konu reddedildi.

    Ayni kosumda "The Marvels of Persepolis" tutarliydi ([1-5] / [1-5]), yani
    celiski her zaman olmuyor — sessizce oluyor. Kimse fark etmeden pahali bir
    yeniden uretim bosa gidiyor.

    Cozum ikisinin BIRLESIMI. Fazladan bir sahne uretmek birkac kurus; bozuk
    sahneyi kacirmak butun konuyu ve o ana kadar harcanan LLM/gorsel parasini
    kaybettiriyor. Yon asimetrik, o yuzden genis taraf dogru taraf.

    Hicbir sahne isaret edilmemisse hepsi doner — onceki davranis korunuyor.
    """
    bildirilen = {
        n for n in (review.problem_scene_numbers or []) if 1 <= n <= toplam_sahne
    }
    metinde = {
        int(m)
        for konu in (review.issues or [])
        for m in re.findall(r"[Ss]cene (\d+)", str(konu))
        if 1 <= int(m) <= toplam_sahne
    }
    birlesim = bildirilen | metinde
    return sorted(birlesim) if birlesim else list(range(1, toplam_sahne + 1))


def kareden_sahneye(kare: int, yuva: int = KARE_YUVASI) -> int:
    """Hakemin kare numarasini sahne numarasina cevirir.

    ⚠️ SHORTS'TA SAHNE BASINA IKI KARE var (`KARE_YUVASI`), yani kare 1-2
    sahne 1, kare 3-4 sahne 2... Bu esleme TEK YERDE tanimli olmali: kare
    duzeni degisip cevrim degismezse hakemin isaretledigi kusur YANLIS
    sahneyi onartir ve bozuk kare videoda kalir. Sessiz kirilmanin ders
    kitabi ornegi — bu oturumda ayni sinif kusur uc uretim koşumunu oldurdu.

    ⚠️ `yuva` PARAMETRE, cunku uzun formatta sahne basina TEK kare var ve
    orada kare i = sahne i. Sabit 2'ye bolunseydi hakemin 30. karede
    gordugu kusur 15. sahneyi onartirdi — yani her onarim yanlis sahneye
    giderdi ve kimse fark etmezdi.
    """
    yuva = max(int(yuva), 1)
    return (max(int(kare), 1) + yuva - 1) // yuva


def hakem_karesinden_sahne(
    sira: int, yuva: int = KARE_YUVASI, ornekler: list[int] | None = None
) -> int:
    """Hakemin MONTAJDA gordugu sira numarasini gercek sahne numarasina cevirir.

    ⚠️ IKI AYRI CEVRIM UST USTE ve ikisini karistirmak sessiz bir kusur:

      montaj sirasi  --(ornekler)-->  gercek kare  --(yuva)-->  sahne

    Shorts'ta ilk cevrim kimlik (butun kareler montajda), o yuzden bugune
    kadar yalnizca ikincisi vardi. Uzun formatta montaj yalnizca 12 kare
    tasiyor (`HAKEM_ORNEK_TAVANI`): hakemin "kare 7" dedigi sey videonun
    7. karesi DEGIL, orneklemin 7. elemani. Cevrim atlanirsa `kareyi_onar`
    her seferinde YANLIS sahnenin gorselini degistirir ve kimse fark etmez —
    hakem hakli, onarim yanlis yere gider.
    """
    p = max(int(sira), 1)
    gercek_kare = ornekler[p - 1] if ornekler and p <= len(ornekler) else p
    return kareden_sahneye(gercek_kare, yuva)


def agir_kusurlu_kareler(
    review: QualityReview,
    yuva: int = KARE_YUVASI,
    ornekler: list[int] | None = None,
) -> list[int]:
    """Agir kusurlu karelerin ait oldugu SAHNE numaralari ("kare 6: ...").

    ⚠️ Doner deger SAHNE, kare degil: cagiran taraf (`kareyi_onar`)
    `plan.scenes` uzerinde islem yapiyor. Iki kare ayni sahneyi
    isaretlerse sahne bir kez doner.
    """
    numaralar = {
        hakem_karesinden_sahne(int(eslesme.group(1)), yuva, ornekler)
        for kusur in review.agir_kusurlar
        if (eslesme := re.match(r"kare (\d+):", kusur))
    }
    return sorted(numaralar)


def kareyi_onar(
    plan: ContentPlan,
    review: QualityReview,
    menu_konusu: str = "",
    *,
    bicim: VideoBicimi = SHORTS_BICIMI,
    ornekler: list[int] | None = None,
) -> list[int]:
    """Hakemin isaretledigi karelerin GORSELINI degistirir; degisen sahneler doner.

    ⚠️ NEDEN VAR — olculdu (2026-08-14, Roman Dodecahedron). Video gorsel 89,
    altyazi 88 aldi (kanalin yayinlanmis en iyi videosu 90) ve SEKIZ karenin
    YEDISI temizdi. Tek kusur 6. karedeydi: dodekahedron yerine faseti
    taslar. Montaj gozle de dogrulandi, hakem hakliydi.

    Hat o videoyu cope atip konuyu bastan planliyordu. Yeniden deneme daha
    kotusunu uretti (88, uc kusur). Oysa hakem hangi karenin bozuk oldugunu
    ZATEN soyluyor; yapilacak sey videoyu atmak degil o kareyi degistirmek.

    ⚠️ ANLATIM DEGISMIYOR, GORSEL DEGISIYOR. Ses `plan.script`ten uretiliyor
    ve zaten kayitli; sahnenin `narration` alani yalnizca o anda NE
    SOYLENDIGINI tarif ediyor. Yani problem "bu cumleye hangi resim uyar"
    sorusu ve secim menudeki gercek dosyalar arasindan yapiliyor. Rastgele
    bir dosya koymak, kapatilan kusuru (anlatim-gorsel uyusmazligi) geri
    acardi.

    Menu yoksa ya da kullanilmamis dosya kalmadiysa BOS DONER — cagiran
    taraf eski davranisa (arama terimlerini revize etme) duser.

    ⚠️ IKINCIL KARE DE ONARILIYOR (2026-08-17). Eskiden yalnizca
    `kaynak_dosya` degistiriliyordu, yani sahnenin BIRINCI karesi; sahnenin
    ikinci karesi (`kaynak_dosya_2`) onarimdan muaftI. Shorts'ta sahne
    basina iki kare var ve cift numarali kare ikincil yuvadir:

        kare  9 -> sahne 5 birincil     kare 10 -> sahne 5 IKINCIL
        kare 11 -> sahne 6 birincil     kare 12 -> sahne 6 IKINCIL

    Sonucu olculdu — 84 agir kusurun dagilimi kare 9-12'ye yigiliyordu ve
    skor kapilarini GECEN uc render tek bir kusurla dustu:

        16:48  85/75  "kare 11: konuyla ilgisiz modern goruntu"
        16:48  75/85  "kare 11: konuyla ilgisiz modern goruntu"
        18:28  78/85  "kare 10: anlatilan kisi degil"      <- IKINCIL
    """
    bozuk = agir_kusurlu_kareler(review, bicim.kare_yuvasi, ornekler)
    bozuk = [n for n in bozuk if 1 <= n <= len(plan.scenes)]
    if not bozuk:
        return []
    menu = arsiv_envanteri(
        menu_konusu.strip() or plan.visual_anchor,
        sinir=envanter_siniri(bicim),
        bicim=bicim,
    )
    if not menu:
        return []
    # ⚠️ IKINCIL DOSYALAR DA "kullanilmis" sayiliyor. Yalnizca `kaynak_dosya`
    # toplansaydi onarim, sahnenin ikinci yuvasinda ZATEN duran bir dosyayi
    # "bos" sanip secebilirdi; sonuc ayni videoda ayni goruntunun iki kez
    # cikmasi olurdu ve tekrar kapisi (`ikincil_alintilari_temizle`) onu
    # zaten kusur sayiyor.
    kullanilan = {
        str(sahne.get(alan, "")).strip()
        for sahne in plan.scenes
        for alan in ("kaynak_dosya", "kaynak_dosya_2")
    } - {""}
    aday_menu = [girdi for girdi in menu if girdi["dosya"] not in kullanilan]
    if not aday_menu:
        return []
    gecerli = {girdi["dosya"] for girdi in aday_menu}
    # ⚠️ Anahtar SAHNE numarasi, kare degil — `bozuk` da oyle. Hakem kare
    # numarasi bildiriyor (sahne basina iki kare) ve cevrim burada da
    # yapilmali; yapilmazsa kusur metni hicbir sahneye eslesmez ve model
    # neyin bozuk oldugunu ogrenmeden secim yapar.
    kusur_metni = {n: [] for n in bozuk}
    # ⚠️ HANGI YUVA bozuk, o da takip ediliyor. Sahne basina iki kare var ve
    # bunlar AYRI dosyalar: tek numarali kare `kaynak_dosya`, cift numarali
    # `kaynak_dosya_2`. Yalnizca birincili degistirmek, hakemin isaretledigi
    # kare ikincilse hicbir sey duzeltmez — video ayni kusurla yeniden
    # render edilir. Olculdu: 18:28 koşumu 78/85 aldi ve tek kusuru
    # "kare 10: anlatilan kisi degil"di, yani sahne 5'in IKINCIL karesi.
    ikincil_bozuk: set[int] = set()
    for kusur in review.agir_kusurlar:
        if eslesme := re.match(r"kare (\d+): (.+)", kusur):
            ham_kare = int(eslesme.group(1))
            sahne_no = hakem_karesinden_sahne(ham_kare, bicim.kare_yuvasi, ornekler)
            if sahne_no in kusur_metni:
                kusur_metni[sahne_no].append(eslesme.group(2))
                gercek_kare = (
                    ornekler[ham_kare - 1]
                    if ornekler and ham_kare <= len(ornekler)
                    else ham_kare
                )
                # Cift numarali kare = ikincil yuva. `kare_yuvasi == 1` olan
                # uzun formatta ikincil yuva YOK, o yuzden kosul sart.
                if bicim.kare_yuvasi > 1 and gercek_kare % 2 == 0:
                    ikincil_bozuk.add(sahne_no)
    try:
        data = _json_completion(
            "Return JSON only: {\"picks\": [{\"n\": <scene number>, \"source_file\": "
            "\"<exact dosya value from the menu>\"}]}. For each scene choose the archive "
            "file that best illustrates the sentence spoken during it. Copy the file name "
            "exactly. Never choose the same file for two scenes, and never invent a name.",
            json.dumps(
                {
                    "subject": plan.visual_anchor,
                    "scenes": [
                        {
                            "n": numara,
                            "spoken_line": plan.scenes[numara - 1].get("narration", ""),
                            "what_was_wrong": kusur_metni.get(numara, []),
                        }
                        for numara in bozuk
                    ],
                    "menu": aday_menu,
                },
                ensure_ascii=False,
            ),
        )
    except Exception:
        # ⚠️ Onarim bir IYILESTIRME; cikarim dusserse kosum devam etmeli.
        return []
    secilen: set[str] = set()
    degisen: list[int] = []
    for secim in data.get("picks", []):
        if not isinstance(secim, dict):
            continue
        try:
            numara = int(secim.get("n", 0))
        except (TypeError, ValueError):
            continue
        dosya = str(secim.get("source_file", "")).strip()
        if numara not in bozuk or dosya not in gecerli or dosya in secilen:
            continue
        secilen.add(dosya)
        # ⚠️ BOZUK OLAN YUVAYA yaziliyor. Kusur sahnenin ikinci karesindeyse
        # birincili degistirmek temiz bir kareyi bozup bozugu birakirdi.
        # Sahnenin HER IKI karesi de isaretlenmisse ikisi de yenilenmeli:
        # o durumda birincil bu dosyayi alir, ikincil bir sonraki turda
        # (hakem yine isaretlerse) degisir — tek cikarimda iki dosya
        # istemek, modelin ayni dosyayi iki yuvaya koyma riskini getirirdi
        # ve tekrar kapisi zaten onu reddediyor.
        alan = "kaynak_dosya_2" if numara in ikincil_bozuk else "kaynak_dosya"
        plan.scenes[numara - 1][alan] = dosya
        degisen.append(numara)
    return sorted(degisen)


def should_abandon_topic(review: QualityReview) -> bool:
    # Eskiden ucuncu bir kosul daha vardi: "publishable false ama iki skor da
    # esigi geciyor" — modelin gerekcesiz reddi. `publishable` artik skorlardan
    # turetildigi icin o durum olusamiyor; kosul kaldirildi (DW-87).
    # Esik de artik elle yazilmiyor, MIN_VISUAL_SCORE'dan geliyor.
    issue_text = " ".join(review.issues).lower()
    return (
        review.visual_alignment_score < MIN_VISUAL_SCORE
        or "modern footage" in issue_text
    )


def publication_slot_key(moment: datetime | None = None) -> str:
    moment = moment or datetime.now(ZoneInfo(TIMEZONE_NAME))
    return moment.astimezone(ZoneInfo(TIMEZONE_NAME)).strftime("%Y-%m-%d-%H")


def konu_slug(konu: str) -> str:
    """Konuyu klasor adinda kullanilabilir kisa bir parcaya cevirir (DW-119).

    ⚠️ Aksanli harfler ASCII'ye DUSURULMEZ, atilir: "Jacopo de' Pazzi" →
    "jacopo-de-pazzi". Amac okunabilir bir ayirt edici, kayipsiz bir kimlik
    degil. Iki konu ayni slug'a duserse saat anahtari yine ayiriyor.

    Bos slug mumkun (ornegin konu tamamen Latin disi bir alfabedeyse); o
    durumda "konu" donuyor ki yol parcasi hicbir zaman bos kalmasin.
    """
    harfler = [
        karakter.lower() if (karakter.isascii() and karakter.isalnum()) else "-"
        for karakter in konu.strip()
    ]
    slug = "".join(harfler).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:40] or "konu"


# ⚠️ Ozel adin gorsel modeline GITMEMESI icin (DW-116). Ayrintili gerekce
# `adsiz_gorsel_ifadesi` docstring'inde.
_TUR_SOZLUGU = {
    "academy": "military academy building",
    "college": "college campus building",
    "university": "university campus building",
    "school": "school building",
    "palazzo": "renaissance palace",
    "palace": "palace",
    "castle": "castle",
    "cathedral": "cathedral",
    "church": "church",
    "abbey": "abbey",
    "temple": "temple",
    "monastery": "monastery",
    "fortress": "fortress",
    "fort": "fort",
    "tower": "tower",
    "bridge": "bridge",
    "canyon": "canyon landscape",
    "valley": "valley landscape",
    "island": "island landscape",
    "mountain": "mountain landscape",
    "river": "river landscape",
    "cross": "military gallantry medal",
    "medal": "military medal",
    "ship": "sailing ship",
    "vessel": "sailing ship",
    "wreck": "shipwreck",
    "tomb": "tomb",
    "pyramid": "pyramid",
    "ruins": "stone ruins",
    "museum": "museum interior",
    "library": "library interior",
    "hospital": "hospital building",
    "prison": "prison building",
    "theatre": "theatre building",
    "theater": "theatre building",
    "observatory": "observatory building",
    "manuscript": "illuminated manuscript",
    "codex": "illuminated manuscript",
}


def adsiz_gorsel_ifadesi(capa: str) -> str:
    """Gorsel capasini OZEL AD ICERMEYEN bir tarife cevirir (DW-116).

    ⚠️ Olculdu (2026-08-10, Franziska Scanagatta): gorsel istemine
    `Visual anchor: Theresian Military Academy` yaziyordu ve model 2. sahneye
    kadraji kaplayan kazili bir tas koydu: "THERESIANISCHES MILITÄRAKADEMIE
    WIENER NEUSTADT".

    DW-112 bu nesneleri ("inscribed slabs, plaques") ZATEN yasakliyordu ve
    yasak tutmadi. Sebep yasagin zayifligi degil: model gordugu adi yaziyor.
    Gercek dunyada askeri akademilerin adi kapisinda kazilidir, yani model
    HATA yapmiyor — istenen seyi yapiyor. Ustelik iki kez soyleniyordu,
    cunku her sahnenin arama terimi de capayi icermek zorunda.

    Bu yuzden cozum daha sert bir yasak degil: adi HIC GONDERMEMEK. Model
    goremedigi bir adi yazamaz.

    Ad yalnizca GORSEL URETIMDEN cikariliyor. Arsiv aramasi (Commons, Met)
    adi olduğu gibi kullanmaya devam ediyor — orada ad tam olarak dogru
    fotografi bulmanin yolu.

    Donen ifade kasitli olarak GENEL: "Theresian Military Academy" →
    "military academy building". Sahnenin kim/ne oldugunu anlatim ve arama
    terimi zaten tasiyor; capanin isi turu ve donemi sabitlemek.
    """
    kelimeler = re.findall(r"[A-Za-z]+", capa.lower())
    for kelime in reversed(kelimeler):
        if kelime in _TUR_SOZLUGU:
            return _TUR_SOZLUGU[kelime]
    # ⚠️ Tur sozlugunde yoksa capa muhtemelen bir KISI ya da uygarlik adi.
    # Bos donmek dogru: cumle tamamen dusuyor ve sahne tarifi anlatimla
    # arama teriminden geliyor. Uydurma bir tur vermek yanlis donemde bir
    # bina cizdirmekten daha kotu.
    return ""


def adsiz_sahne_tarifi(terim: str, capa: str) -> str:
    """Arama teriminden capanin ozel adini ayiklar (DW-116).

    ⚠️ Adi yalnizca `Visual anchor:` cumlesinden cikarmak YETMEZ. Ad gorsel
    istemine IKI yerden giriyor: o cumleden ve `Required visible detail`
    olarak gelen arama teriminden. Arama terimi de capayi icermek ZORUNDA
    (`_ensure_visual_anchor`), yani ad orada garantili duruyor.

    Tek kanali kapatip digerini acik birakmak kusuru duzeltmez, yalnizca
    hangi cumlenin suclu oldugunu belirsizlestirir.

    Geriye anlamli bir sey kalmazsa terim OLDUGU GIBI donuyor: bos bir
    "gorunmesi gereken detay" modele hicbir sey soylemez ve sahne tamamen
    modelin insafina kalir.
    """
    capa_kelimeleri = _normalize_topic(capa)
    if not capa_kelimeleri:
        return terim
    kalan = [
        kelime
        for kelime in terim.split()
        if not (_normalize_topic(kelime) & capa_kelimeleri)
    ]
    return " ".join(kalan) if kalan else terim


MUZIK_UZANTILARI = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma")
MUZIK_GECMISI = ROOT / "storage" / "youtube_automation" / "muzik_gecmisi.json"
MUZIK_KUNYESI = ROOT / "resource" / "muzik_kunye.json"

RUH_HALLERI = ("agirbasli", "merak", "gorkemli")
"""Parcaya ve konuya verilebilecek ruh hali etiketleri.

⚠️ UC TANE ve bilerek az. Her etiket havuzu boluyor; 15 parcalik bir havuzda
alti etiket, etiket basina iki-uc parca demek olurdu ve tekrar korumasi
(`muzik_sec` penceresi) ile birlikte secimi tek secenege dusururdu.
"""

MUZIK_SES_TABANI = 0.2
"""Anlatimin ustunde muzigin taban seviyesi.

CLI varsayilani; konusma uzerinde muzigi duyulur ama bastirmaz tutuyor.
Parca basina `ses_kazanci` ile CARPILIYOR — gerekce `muzik_kazanci`'nda.
"""


@lru_cache(maxsize=1)
def muzik_kunyesi() -> dict[str, dict]:
    """Parca kunyesi — lisans, baslik, ses kazanci, ruh hali.

    ⚠️ Kunye bir IYILESTIRME, on kosul degil: okunamazsa bos sozluk doner ve
    hat kazancsiz/etiketsiz calismaya devam eder. Muzik ugruna video uretimi
    dusmemeli — ayni ilke `muzik_sec`te de yazili.
    """
    try:
        ham = json.loads(MUZIK_KUNYESI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return ham if isinstance(ham, dict) else {}


def muzik_kazanci(ad: str) -> float:
    """Parcanin ses carpani — havuzu tek seviyeye getiren duzeltme.

    ⚠️ NEDEN VAR — olculdu (2026-08-17). Havuzdaki 22 parcanin ilk 40
    saniyesi (videonun gercekten duydugu kisim) 44,1 dB'ye yayilmisti;
    kullanilamayacak kadar sessiz olani ayikladiktan sonra bile 15,0 dB
    kaliyordu:

        en sessiz   Tchaikovsky, Dance of the Flutes   -27,8 dB
        en gurultulu Tchaikovsky, Serenade melancolique -12,8 dB

    Karistirma yolu (`app/services/video.py`) `MultiplyVolume(bgm_volume)`,
    yani DUZ BIR CARPAN. Sabit 0,2 ayari bu yuzden her parcada BASKA bir sey
    demekti: biri anlatimla yarisiyor, oburu hic duyulmuyordu. Kanal
    sahibinin "muzikler BAZEN siritiyor" demesi teshisin kendisi — sabit
    degil, parcadan parcaya degisen bir kusur.

    Kazanc havuz MEDYANINA (-20,3 dB) gore hesaplandi ve kunyeye yazildi.
    Medyan secildi cunku 0,2 tabani bugunku orta seviyeye gore ayarlanmisti;
    keyfi bir yayin hedefi (LUFS) o ayari gecersiz kilardi.

    ⚠️ DOSYALAR DEGISTIRILMEDI. Normalize edilmis dosya yazmak, kunyedeki
    `bayt` alanini gecersiz kilardi — o alan hem indirme dogrulamasi hem de
    havuz butunluk kontrolu (`muzik_havuzu_kur.py`), yani her kurulumda
    parcalar "eksik" sanilip yeniden indirilirdi. Kazanc bir SAYI olarak
    kunyede duruyor: makineden bagimsiz, git'te gorunur, ffmpeg surumune
    duyarsiz.

    Kunyede yoksa 1.0 doner — yani bugunku davranis.
    """
    try:
        deger = float(muzik_kunyesi().get(ad, {}).get("ses_kazanci", 1.0))
    except (TypeError, ValueError):
        return 1.0
    # Cilgin bir kunye degeri sesi patlatmasin; olculen aralik 0,42-2,37.
    return min(max(deger, 0.1), 4.0)


def _ruh_halini_coz(ham: object) -> str:
    """Serbest metni bilinen bir etikete indirger; tanimazsa bos doner.

    ⚠️ TANIMAYAN DEGER HATA DEGIL. Alan istemde ISTEGE BAGLI: bu depoda plan
    semasina ZORUNLU alan eklemek bes denemenin dordunu yakmis bir kusur
    sinifi. Model alani hic yazmazsa ya da uydurursa muzik havuz genelinden
    secilir — yani bugunku davranis.
    """
    etiket = str(ham or "").strip().casefold()
    return etiket if etiket in RUH_HALLERI else ""


def muzik_secenekleri() -> list[str]:
    """Kullanilabilir parca ADLARI — yol degil.

    CLI `--bgm-file`'i `storage/bgm` ve `resource/songs` beyaz listesinde
    cozuyor, dolayisiyla ciplak dosya adi yeterli ve daha guvenli: yol
    kacisi diye bir sey kalmiyor.
    """
    adlar: set[str] = set()
    for dizin in (ROOT / "storage" / "bgm", ROOT / "resource" / "songs"):
        if not dizin.is_dir():
            continue
        for parca in dizin.iterdir():
            if parca.is_file() and parca.suffix.lower() in MUZIK_UZANTILARI:
                adlar.add(parca.name)
    return sorted(adlar)


def muzik_sec(
    secenekler: list[str] | None = None,
    gecmis_yolu: Path | None = None,
    *,
    ruh_hali: str = "",
) -> str:
    """Bu video icin bir parca sec ve secimi KAYDA GECIR (DW-120).

    ⚠️ Eskiden secim `--bgm-type random` ile MPT'nin icinde yapiliyordu:
    `random.choice(29 parca)`, iadeli ve hicbir yere yazilmadan. Iki sonucu
    vardi.

    Birincisi: hangi videoda hangi parcanin caldigi HIC BILINMIYORDU.
    Kullanici "hepsinde ayni muzik var" dediginde iddiayi sinamak icin
    nihai sesten anlatimi cikarip 29 parcayla korelasyon olcmek gerekti
    (2026-08-10). Olcum iddiayi cürüttü — 4 video 4 farkli parca kullanmisti,
    benzerlik 0,99'a karsi ikinci sira 0,04 — ama bunu ogrenmenin baska yolu
    yoktu. Kayit tutulsaydi tek satirlik bir bakis yetecekti.

    Ikincisi: iadeli secim oldugu icin bir sonraki kosumda ayni parcanin
    ust uste cikmasi mumkundu. 29 parcadan 5 video icin cakisma olasiligi
    ~%35; yani "sansa" birakilmis bir sey degil, beklenen bir olay.

    Cozum: son yarinin disindan sec ve secimi diske yaz. Boylece tekrar
    yalnizca parca havuzu tukendiginde mumkun olur.

    Parca yoksa BOS DONER; cagiran taraf muziksiz devam eder — muzik
    ugruna video uretimi dusmemeli.

    ⚠️ RUH HALI (2026-08-17) bir TERCIH, filtre degil. Uc kademe var:

        1. etiketi konuya UYAN parcalar
        2. etiketi OLMAYAN parcalar        <- "bilmiyorum" ne odul ne ceza
        3. havuzun tamami

    Bir ust kademe tekrar penceresinden sonra bos kalirsa bir alt kademeye
    inilir. Filtre olsaydi ii ruh hali etiketi az olan bir havuzda secim tek
    parcaya duser, tekrar korumasi anlamsizlasirdi — ayni gerekce
    `sinifa_gore_sirala`da da yazili: eleme degil siralama.
    """
    havuz = secenekler if secenekler is not None else muzik_secenekleri()
    if not havuz:
        return ""

    yol = gecmis_yolu if gecmis_yolu is not None else MUZIK_GECMISI
    try:
        gecmis = [str(ad) for ad in json.loads(yol.read_text(encoding="utf-8"))]
    except (OSError, ValueError):
        # Bozuk veya olmayan gecmis muzigi engellememeli — en kotu ihtimalle
        # bir tekrar olur, ki zaten duzeltmeye calistigimiz sey o kadar.
        gecmis = []

    # Havuzun yarisi kadar geriye bakiliyor: tamamina bakmak son parca
    # kalana kadar secimi tek secenege dusurur ve "rastgele" anlamsizlasir.
    pencere = max(1, len(havuz) // 2)
    yakinda_kullanilan = set(gecmis[-pencere:])

    istenen = _ruh_halini_coz(ruh_hali)
    kunye = muzik_kunyesi()
    kademeler: list[list[str]] = []
    if istenen:
        kademeler.append(
            [a for a in havuz if _ruh_halini_coz(kunye.get(a, {}).get("ruh_hali")) == istenen]
        )
        kademeler.append(
            [a for a in havuz if not _ruh_halini_coz(kunye.get(a, {}).get("ruh_hali"))]
        )
    kademeler.append(list(havuz))

    uygun: list[str] = []
    for kademe in kademeler:
        uygun = [ad for ad in kademe if ad not in yakinda_kullanilan]
        if uygun:
            break
    # Butun kademeler pencereye takildiysa tekrar korumasindan vazgeciliyor:
    # muziksiz video, tekrar eden muzikten kotu.
    uygun = uygun or list(havuz)
    secilen = random.choice(uygun)

    gecmis.append(secilen)
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(
            json.dumps(gecmis[-len(havuz):], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as hata:
        # Yazamadiysak secim yine gecerli; yalnizca bir sonraki kosum bu
        # parcayi tekrar secebilir. Sessiz kalmiyoruz ki fark edilsin.
        print(f"⚠️ muzik gecmisi yazilamadi ({hata}); tekrar korumasi bu kosumda yok")
    return secilen


def _openai_client() -> tuple[OpenAI, str]:
    api_key = str(config.app.get("openai_api_key", "")).strip()
    if not api_key:
        raise RuntimeError("openai_api_key is not configured in config.toml")
    model = str(config.app.get("openai_model_name", "gpt-4o-mini")).strip() or "gpt-4o-mini"
    base_url = str(config.app.get("openai_base_url", "")).strip()
    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs), model


# ⚠️ Uzun format JSON'u ~7.000 token. Tavan konmazsa saglayicinin varsayilani
# geciyor ve cevap ORTASINDAN kesiliyor — hat bunu "eksik JSON" diye gorup
# denemeyi yakiyor. Fatura URETILEN tokene gore, yani genis tavan bedava.
AZAMI_CIKTI_TOKEN = 16000


def _akil_yurutmeyi_kapat(base_url: str) -> dict[str, Any]:
    """OpenRouter'da akil yurutmeyi kapatan govde eki.

    ⚠️ OLCULDU (2026-08-15, DW-51) ve bu hattin uzun formatini tek basina
    durduran kusur buydu. `moonshotai/kimi-k2.6` bir AKIL YURUTME modeli:
    uzun format istemi ona butun cikti butcesini dusunmeye harcatiyor ve
    `content` BOS donuyor.

        max_tokens  2.000 -> reasoning_tokens 2.115, content None
        max_tokens 16.000 -> reasoning_tokens 16.000, content None
        Hermes'in 65.536'si -> 900 sn'de bile bitmiyor

    Ayni istem `reasoning enabled=false` ile 163 sn'de 29.612 karakterlik
    gecerli JSON donduruyor. `effort: "low"` YETMIYOR (15.999 akil token).
    Kimi'nin gorulu diger surumleri de (k2.5, k2.7-code) ayni sekilde
    dusunuyor, yani model degistirmek cozum degil.

    ⚠️ Yalnizca OpenRouter'a gonderiliyor: `reasoning` OpenAI'nin kendi
    ucunda taninmayan bir alan ve oraya yollanirsa istek reddedilir.
    """
    if "openrouter" not in base_url.lower():
        return {}
    return {"extra_body": {"reasoning": {"enabled": False}}}


def _json_govdesi(icerik: str | None) -> dict[str, Any]:
    """Modelin dondurdugu metni JSON'a cevirir; ```json cercevesini soyar.

    ⚠️ `response_format={"type": "json_object"}` her saglayicida uyulan bir
    soz DEGIL: olculdu (2026-08-15), OpenRouter uzerinden Kimi cevabi
    ```json cercevesiyle donduruyor ve ciplak `json.loads` patliyor.
    """
    metin = (icerik or "").strip()
    if metin.startswith("```"):
        metin = re.sub(r"^```[a-zA-Z]*\s*", "", metin)
        metin = re.sub(r"\s*```$", "", metin)
    if not metin:
        # ⚠️ Bos cevap SESSIZ gecmemeli: akil yurutme kusuru tam olarak
        # boyle gorunuyordu ve `json.loads("")` mesaji sebebi gizliyordu.
        raise RuntimeError(
            "model bos cevap dondurdu — cikti butcesi akil yurutmeye gitmis "
            "olabilir (bkz. _akil_yurutmeyi_kapat)"
        )
    return json.loads(metin)


def _windows() -> bool:
    """Windows'ta miyiz — platform kontrolu bilerek TEK bir fonksiyonda.

    ⚠️ Testler bunu yamalamali, `os.name`'i DEGIL. Olculdu (2026-08-06, DW-90):
    `monkeypatch.setattr("youtube_automation.os.name", "nt")` global `os`
    modulunu degistiriyor (kopyasini degil), cunku `youtube_automation.os` ile
    `os` ayni nesne. `os.name == "nt"` oldugu surece `pathlib.Path()` her
    cagrida `WindowsPath` uretmeye calisiyor ve POSIX'te
    `NotImplementedError` firlatiyor.

    Sonucu tek bir testin dusmesi degildi: pytest'in kendi onbellegi ve
    terminal yazicisi da `Path()` cagirdigi icin butun oturum `INTERNALERROR`
    ile coktu. Linux CI 3 Agustos'tan beri kirmiziydi ve dort PR'i birden
    bloke ediyordu. Windows isi ise yalnizca 6 servis dosyasi kosuyor, bu
    testi hic almiyor — yani test hicbir yerde calismiyordu.
    """
    return os.name == "nt"


def _run_hermes(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    popen_kwargs: dict[str, Any] = {
        "cwd": ROOT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if _windows():
        # `CREATE_NEW_PROCESS_GROUP` yalnizca Windows'ta tanimli. `getattr`
        # olmadan Windows dalini POSIX'te sinamak `AttributeError` veriyor,
        # yani dal test edilemez hale geliyordu.
        popen_kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    process = subprocess.Popen(command, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if _windows():
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                text=True,
                capture_output=True,
                timeout=30,
            )
        else:
            process.kill()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        raise RuntimeError(f"Hermes CLI inference timed out after {timeout} seconds") from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def hermes_temel_komut() -> list[str]:
    """`hermes` cagrisinin ONEKI — sağlayici ve model ACIKCA geciriliyor.

    ⚠️ NEDEN BAYRAK, NEDEN KURESEL YAPILANDIRMA DEGIL — olculdu
    (2026-08-15). `~/.hermes/config.yaml` sağlayiciyi `github-copilot`
    gosterirken:

        hermes -z ...                    -> CALISTI  (12,2 sn)
        hermes chat -Q --image ... -q ... -> HTTP 429 usage limit

    Yani `chat` alt komutu yapilandirmadaki sağlayiciyi DIKKATE ALMIYOR ve
    kimlik havuzundan kotasi DOLU olani (openai-codex) seciyor. Metin yolu
    calisip görü yolu dusunce hat sessizce kalite kapisiz kalirdi: senaryo
    uretilir, kaynak ve video incelemeleri patlar.

    Ayni bayraklar iki yolda da geciliyor ki hat hangi modelle urettigini
    KENDI soylesin; kullanicinin kuresel hermes ayari degisince uretim
    modeli sessizce degismesin.

    Bos birakilirsa hicbir bayrak eklenmiyor — onceki davranis birebir.
    """
    komut = ["hermes"]
    if HERMES_SAGLAYICI:
        komut += ["--provider", HERMES_SAGLAYICI]
    if HERMES_MODEL:
        komut += ["-m", HERMES_MODEL]
    return komut


CIKARIM_ZAMAN_ASIMI = 180
"""Kisa (Shorts) bir JSON cevabi icin ust sinir, saniye."""

GORU_ZAMAN_ASIMI = 360
"""Gorü (montaj okuma) cagrilari icin ust sinir, saniye — SHORTS olcusu.

⚠️ `hermes` yolunda bu sayi 360 olarak GOMULUYDU; openai yolunda ise hic
zaman asimi yoktu. Sabit hale getirildi ki iki yol ayni siniri paylassin —
zaman asimsiz bir gorü cagrisi zamanlayici slotunu sessizce yer.
"""

UZUN_GORU_ZAMAN_ASIMI = 900
"""Uzun formatta gorü siniri.

⚠️ 360, metin yolundaki 180'in DUZELTILMEMIS ikiziydi: ikisi de Shorts'a
gore konmustu, biri (ucuncu koşumda) duzeltildi, digeri gozden kacti.

Uzun formatta gorü cagrisinin iki ucu birden buyuyor:
  girdi  — kontak sayfasi 4 sutunda 12 kare (Shorts'ta 16 kare ama daha
           kucuk), `detail: "high"` ile gonderiliyor
  cikti  — `frames` dizisi sayfadaki her sahne icin bir nesne, arti
           `issues` ve `revised_search_terms`

Kaynak kapisi bir denemede en fazla uc kez cagriliyor (ilk inceleme, arsiv
iyilestirmesi sonrasi, AI yedegi sonrasi), yani en kotu durum 3 x 900 sn.
Bu, render icin ayrilan butceyle BIRLIKTE dusunulmeli (bkz. `RENDER_ZAMAN_ASIMI`).
"""


def goru_zaman_asimi(bicim: "VideoBicimi | None" = None) -> int:
    """Bicime gore gorü siniri.

    ⚠️ Varsayilan `None`: bu fonksiyon dosyada `SHORTS_BICIMI`den ONCE
    tanimli ve varsayilan degerler `def` aninda hesaplaniyor. Ayni sinif
    kusur bu oturumda uc koşum oldurdu.
    """
    if bicim is None or bicim.dikey:
        return GORU_ZAMAN_ASIMI
    return UZUN_GORU_ZAMAN_ASIMI

UZUN_CIKARIM_ZAMAN_ASIMI = 600
"""Uzun format icin ust sinir.

⚠️ OLCULDU (2026-08-15, ucuncu Herculaneum koşumu): sabit 180 sn ile cagri
`TimeoutExpired` verdi ve koşum 188,4 saniyede oldu. Sinir Shorts'a gore
konmustu: 80-120 kelimelik senaryo + 8 sahne ~800 token. Uzun format
1.200-2.200 kelime + 30-45 sahne, yani ~7.000 token uretiyor — ayni surede
bitmesi beklenemezdi.

Sinir tamamen kaldirilmadi: asili kalan bir cagri zamanlayici slotunu
sessizce yer. 600 sn, olculen uretim hizina gore genis bir pay birakiyor
ve 3 saatlik koşum araligina hala uc denemeyle sigiyor.
"""


def _json_completion(
    system: str, user: str, *, zaman_asimi: int = CIKARIM_ZAMAN_ASIMI
) -> dict[str, Any]:
    if INFERENCE_BACKEND == "hermes-cli":
        prompt = (
            f"SYSTEM INSTRUCTIONS:\n{system}\n\n"
            f"USER REQUEST:\n{user}\n\n"
            "Return the requested JSON object only, with no markdown fences or commentary."
        )
        result = _run_hermes(
            hermes_temel_komut() + ["--ignore-rules", "--safe-mode", "-z", prompt],
            zaman_asimi,
        )
        if result.returncode:
            raise RuntimeError(
                f"Hermes CLI text inference failed with exit code {result.returncode}"
            )
        return parse_cli_result(result.stdout)
    if INFERENCE_BACKEND != "openai":
        raise RuntimeError(f"unsupported inference backend: {INFERENCE_BACKEND}")
    client, model = _openai_client()
    base_url = str(config.app.get("openai_base_url", "")).strip()
    # ⚠️ METIN YOLU DA TEKRAR DENIYOR (2026-08-17). Gerekce `GORU_JSON_DENEMESI`
    # docstring'inde ve o ders 2026-08-16'da YALNIZCA gorü yoluna
    # uygulanmisti; metin yolu tek bir bos cevapta hala coküyordu. Ayni
    # istisna 17 Agu 12:35 koşumunu oldurdu:
    #
    #     RuntimeError: model bos cevap dondurdu
    #
    # Ret degil ÇÖKME: `run_cycle` yigin iziyle oluyor, slot kayboluyor ve
    # zamanlayici "HATA | cikis 1" yaziyor. O koşum plani uc kez kurmus,
    # Tikal icin arsivi indirmis ve iki kez render'a kadar gitmisti.
    #
    # ⚠️ Metin denemesi gorü denemesinden UCUZ (goruntu yok), yani 3 burada
    # daha da rahat savunulur. `temperature=0.65` denemeler arasinda gorü
    # yolundakinden (0.1) daha fazla degisiklik birakiyor.
    son_hata: Exception | None = None
    for deneme in range(1, METIN_JSON_DENEMESI + 1):
        response = client.chat.completions.create(
            model=model,
            temperature=0.65,
            response_format={"type": "json_object"},
            max_tokens=AZAMI_CIKTI_TOKEN,
            # ⚠️ Zaman asimi ISTEMCIYE de veriliyor. Verilmezse `hermes` yolunda
            # yakalanan asilma burada SESSIZCE sonsuza kadar bekler ve
            # zamanlayici slotunu yer.
            timeout=float(zaman_asimi),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **_akil_yurutmeyi_kapat(base_url),
        )
        try:
            return _json_govdesi(response.choices[0].message.content)
        except (RuntimeError, ValueError) as hata:
            # ⚠️ `ValueError` `json.JSONDecodeError`i de kapsiyor — 06:13
            # koşumunu olduren buydu.
            son_hata = hata
            print(
                f"⚠️ metin cikarimi okunamadi ({deneme}/{METIN_JSON_DENEMESI}): {hata}",
                flush=True,
            )
    raise son_hata if son_hata else RuntimeError("metin cikarimi basarisiz")


METIN_JSON_DENEMESI = 3
"""Metin modeli okunamayan cevap verirse kac kez tekrar denenecek.

⚠️ AYNI DERS, IKINCI YOL. `GORU_JSON_DENEMESI` 2026-08-16'da eklendi ama
yalnizca gorü yoluna; metin yolu tek bir bos cevapta cökmeye devam etti ve
17 Agu 12:35 koşumunu ayni istisna oldurdu (`model bos cevap dondurdu`).
Cozum depoda hazir duruyordu, buraya uygulanmamisti — `kaynak_ornegi`
docstring'indeki ayni sinif korluk.
"""

GORU_JSON_DENEMESI = 3
"""Görü modeli okunamayan cevap verirse kac kez tekrar denenecek.

⚠️ NEDEN VAR — olculdu (2026-08-16), AYNI GUN IKI KOŞUM bu yuzden oldu:

    06:13  json.decoder.JSONDecodeError: Expecting value: line 1 column 1
    14:15  RuntimeError: model bos cevap dondurdu

Ikisi de RET degil ÇÖKME: `run_cycle` yigin iziyle olyor, slot kayboluyor ve
zamanlayici "HATA | cikis 1" yaziyor. 14:15 koşumu Terracotta Army'yi ta
hakem asamasina getirmisti — render tamamlanmis, ~25 dakikalik is cope gitti.

Tekrar denemek dogru cozum cunku kusur MODELIN CIKTISINDA, girdide degil:
ayni istem ikinci denemede okunabilir JSON dondurebiliyor. `temperature=0.1`
denemeler arasi kucuk bir degisiklik birakiyor.

3 secildi: her deneme yuksek cozunurluklu bir gorü cagrisi, yani pahali;
ama kaybedilen alternatif TUM koşum (plan + indirme + render).
"""


def _vision_json(
    prompt: dict[str, Any],
    image_path: Path,
    *,
    bicim: "VideoBicimi | None" = None,
) -> dict[str, Any]:
    zaman_asimi = goru_zaman_asimi(bicim)
    if INFERENCE_BACKEND == "hermes-cli":
        query = (
            json.dumps(prompt, ensure_ascii=False)
            + "\nReturn the requested JSON object only, with no markdown fences or commentary."
        )
        result = _run_hermes(
            hermes_temel_komut()
            + [
                "--ignore-rules",
                "--safe-mode",
                "chat",
                "-Q",
                "--max-turns",
                "1",
                "--image",
                str(image_path),
                "-q",
                query,
            ],
            zaman_asimi,
        )
        if result.returncode:
            raise RuntimeError(
                f"Hermes CLI vision inference failed with exit code {result.returncode}"
            )
        return parse_cli_result(result.stdout)
    if INFERENCE_BACKEND != "openai":
        raise RuntimeError(f"unsupported inference backend: {INFERENCE_BACKEND}")
    client, model = _openai_client()
    base_url = str(config.app.get("openai_base_url", "")).strip()
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    son_hata: Exception | None = None
    for deneme in range(1, GORU_JSON_DENEMESI + 1):
        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=AZAMI_CIKTI_TOKEN,
            timeout=float(zaman_asimi),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": json.dumps(prompt, ensure_ascii=False)},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            # ⚠️ Gorü yolunda da kapali: iki kalite kapisi da buradan geciyor ve
            # akil yurutme butceyi yerse kapi BOS cevap alip sessizce duser.
            **_akil_yurutmeyi_kapat(base_url),
        )
        try:
            return _json_govdesi(response.choices[0].message.content)
        except (RuntimeError, ValueError) as hata:
            # ⚠️ ValueError `json.JSONDecodeError`i de kapsiyor.
            son_hata = hata
            print(
                f"⚠️ görü yanıtı okunamadı (deneme {deneme}/{GORU_JSON_DENEMESI}): "
                f"{str(hata)[:120]}",
                flush=True,
            )
    raise RuntimeError(
        f"görü modeli {GORU_JSON_DENEMESI} denemede de okunabilir JSON vermedi"
    ) from son_hata


def _recent_titles() -> list[str]:
    titles: list[str] = []
    state = load_state()
    titles.extend(item.get("topic", "") for item in state.get("published", []))
    titles.extend(item.get("title", "") for item in state.get("published", []))
    titles.extend(item.get("visual_anchor", "") for item in state.get("published", []))
    # ⚠️ RET KOLU BUTCEYE BAGLI — bu liste `is_duplicate_topic`e (Jaccard >=
    # 0,6) giriyor ve yedek kipte capa AYNI ZAMANDA konu. Butce uygulanmazsa
    # `engellenen_capalar` capayi serbest biraksa bile "Knossos" ile daha once
    # reddedilmis "Knossos" Jaccard 1,0 verip plan asamasinda yine reddedilir;
    # yani H1 listeyi acar ama kapi yine kapali kalirdi.
    sayac = _ret_denemeleri(state)
    for item in state.get("rejected", []):
        capa = str(item.get("visual_anchor") or item.get("topic") or "")
        if not _butce_doldu(capa, sayac):
            continue
        titles.append(item.get("topic", ""))
        titles.append(item.get("visual_anchor", ""))
    if ANALYSIS_FILE.exists():
        analysis = json.loads(ANALYSIS_FILE.read_text(encoding="utf-8"))
        titles.extend(item.get("title", "") for item in analysis.get("all_shorts", []))
    return [title for title in titles if title]


SERI_IMZASI = (
    "Shemz — documentaries built from public domain archives, "
    "one forgotten story at a time."
)
"""Aciklamanin ilk satiri: kanalin NE OLDUGUNU soyleyen sabit cumle.

⚠️ "short" kelimesi CIKARILDI (2026-08-15): hat artik 5-13 dakikalik uzun
format da uretiyor ve o videolarin aciklamasinin ILK SATIRI "short
documentaries" diyordu. Sabit iki bicimde de dogru olmali — kimlik cumlesi
bicime gore degisirse kimlik olmaz (asagidaki gerekce).

⚠️ Olculdu (2026-08-14): 1.115 izlenme, **1 abone** (%0,09) ve trafigin
%96'si Shorts akisi. Yani dagitim calisiyor, DONUSUM calismiyor —
izleyicinin karsisina cikan hicbir yerde kanalin ne yaptigi yazmiyordu.
Abone olmak icin bir sebep verilmemis, yalnizca tek bir video gosterilmis.

Sabit olmasi bilincli: seri kimligi videodan videoya degisirse kimlik
olmaz. Degisen kisim (`plan.description`) altinda kaliyor.
"""


def kanca(metin: str) -> str:
    """Anlatimin ilk cumlesi — videonun izlenip izlenmeyecegini belirleyen yer."""
    ilk = re.split(r"(?<=[.!?])\s", metin.strip(), maxsplit=1)[0]
    return ilk.strip()


def kapanis(metin: str) -> str:
    """Anlatimin SON cumlesi — izleyicinin geri gelip gelmeyecegini belirleyen yer.

    ⚠️ Kancanin ikizi ve ayni sebeple var. Olculdu (2026-08-14): tutunma
    egrisi videonun sonunda %31-36'ya iniyor ve o noktaya kadar gelen
    izleyici, kanalin var oldugunu bile ogrenmeden kayiyor. 1.115 izlenme
    yalnizca 1 abone getirdi.
    """
    cumleler = [p.strip() for p in re.split(r"(?<=[.!?])\s", metin.strip()) if p.strip()]
    return cumleler[-1] if cumleler else ""


KAPANIS_ORTUSME_ORANI = tekrar_olcusu.ORTUSME_ESIGI
"""Kapanis, onceki bir kapanisla bu orandan fazla kelime paylasirsa tekrar.

⚠️ Bu esik SECILDI, olculmedi — kapanislar yeni kaydedilmeye basladi ve
karsilastirilacak gecmis henuz yok. Veri birikince `kanal_rapor.py --tekrar`
ciktisiyla gozden gecirilmeli.

⚠️ TEK KAYNAKTAN geliyor ve gelmeli. Ilk surumde burada `0.6` yaziyordu ve
`--tekrar` raporu kendi esigiyle olcuyordu: iki sabit, iki ayri kelime
ayiklayici. Rapor "tekrar yok" derken kapi baska bir cetvelle calisiyordu —
yani tetik, engellenen seyden baskasini olcuyordu. Ayni sebeple ORAN da
`tekrar_olcusu.kelime_ortusmesi` ile hesaplaniyor.
"""


def _kapanis_tekrari(senaryo: str, onceki_kapanislar: list[str]) -> bool:
    """Kapanis, daha once kullanilmis bir kapanisi tekrarliyor mu.

    ⚠️ Kanca tarafinda ogrenilen ders burada da gecerli (DW-94): modele
    "tekrarlama" demek yetmiyor, KOD kontrol etmeli. Ve kapanista risk daha
    buyuk — "geri gelmek icin sebep ver" talimati, dogal olarak modeli her
    videoda AYNI cumleye itiyor. Ayni kapanisi ust uste duyan izleyici icin
    bu bir seri kimligi degil, bir reklam kusagi.

    ⚠️ KANCANIN KALIP OLCUSU BURADA CALISMIYOR ve sebebi ogretici:
    `_kalip_iskeleti` bastaki BUYUK HARFLI diziyi atiyor. Kancada ozne bir
    ozel ad oldugu icin bu dogru sonucu veriyor ("Mehmed II did not" →
    `did not`). Kapanislar ise "The archive still holds..." bicimindeki
    cumleler: yalnizca "The" atiliyor ve AYIRT EDICI isim kalibin icinde
    kaliyor, yani yapisi ayni iki cumle farkli gorunuyor.

    Bu yuzden olcu KELIME ORTUSMESI: "The archive still holds the rest of
    that fleet" ile "The vault still holds the rest of that hoard" ortak
    kelimelerin cogunu paylasiyor ve ozne degisse de ayni cumle.
    """
    kapanis_metni = kapanis(senaryo)
    if not kapanis_metni or not onceki_kapanislar:
        return False
    if len(tekrar_olcusu.kelimeler(kapanis_metni)) < 3:
        # Cok kisa kapanista ortusme orani gurultu; olcmeye degmez.
        return False
    return any(
        tekrar_olcusu.kelime_ortusmesi(kapanis_metni, onceki or "") >= KAPANIS_ORTUSME_ORANI
        for onceki in onceki_kapanislar
    )


TEKRAR_PENCERESI = 40
"""Kanca ve kapanis tekrari kac gecmis videoya karsi olculuyor.

⚠️ OLCULDU (2026-08-14) ve DEGISTI: 12'ydi. 12 kayitlik pencere, ayda ~10
video uretilirken bir aydan uzun hafiza demekti. Zamanlayici kurulunca hiz
gunde 4-5 videoya cikti ve ayni 12 kayit **2,4-3 GUNE** dustu — uc gun
sonra donen bir kalip artik hic yakalanmiyordu. Yani pencere sabit
kalirken hafiza sessizce kisaldi.

⚠️ Genisletmenin uretimi kilitleme riski YOK: yumusak kapilar yalnizca ilk
uc denemede acik (`YUMUSAK_KAPI_DENEMESI`), sonra kapaniyor. En kotu
ihtimalle uc deneme yanar, koşum olmez.
"""


def _son_kapanislar(adet: int = TEKRAR_PENCERESI) -> list[str]:
    """Daha once kullanilmis kapanislar — `_son_kancalar`in ikizi."""
    return [
        k for k in (item.get("kapanis", "") for item in load_state().get("published", [])) if k
    ][-adet:]


def _son_kancalar(adet: int = TEKRAR_PENCERESI) -> list[str]:
    """Daha once kullanilmis acilislar — modele "bunlari tekrarlama" demek icin.

    ⚠️ Yasaklamak tek basina yetmiyor; model gecmisini gormeli. Olculdu
    (2026-08-06, DW-94): prompt zaten "merak boslugu yarat" diyordu ama
    uretilen **6 videonun 4'u** birebir "Did you know..." ile basladi. Kalan
    ikisi ("Imagine a world without running water") belirgin sekilde daha
    guclu — yani cesitlilik mumkun, sadece zorlanmiyordu.

    Sadece yayinlanan kayitlar okunuyor: reddedilen bir videonun kancasi
    tekrar denenebilir, sorun onda degildi.
    """
    return [k for k in (item.get("hook", "") for item in load_state().get("published", [])) if k][
        -adet:
    ]


BASLIK_BICIMI_PENCERESI = 3
"""Baslik bicimi kac gecmis videoya karsi olculuyor.

⚠️ Kanca/kapanis penceresinden (`TEKRAR_PENCERESI`) KASITLI olarak dar.
Soru kelimesi havuzu kucuk (why/who/how/what/did/when/where); "son 40
videoda why kullanildi" demek bicimi tuketir ve uretimi kilitlerdi. Amac
kaliplari yasaklamak degil, aralarinda DONDURMEK.
"""

_baslik_bicimi = tekrar_olcusu.baslik_bicimi


def _son_basliklar(adet: int = BASLIK_BICIMI_PENCERESI) -> list[str]:
    """Son yayinlanan basliklar — bicim tekrarini olcmek icin."""
    return [t for t in (item.get("title", "") for item in load_state().get("published", [])) if t][
        -adet:
    ]


def _baslik_bicimi_tekrari(baslik: str, onceki_basliklar: list[str]) -> bool:
    """Baslik, son videolarin bicimini tekrarliyor mu.

    ⚠️ OLCULDU (2026-08-14, yayindaki 15 video): ilk bes video "The ... of
    ..." tamlamasi, son dokuzu duz soru, SON ALTISININ ALTISI da soru ve
    ucu "Why ...". En uzun ardisik ayni-bicim serisi **5**. Konu tekrari
    icin kapi vardi (`_recent_titles` tum gecmisi okuyor, 15/15 konu
    benzersiz), kanca ve kapanis icin kapi vardi — bicim icin YOKTU. Kanal
    sayfasina bakan biri bu yuzden iki blok halinde tekrar goruyor.

    ⚠️ BU KAPI SORU BICIMINI YASAKLAMIYOR, CESITLENDIRIYOR. Soru bicimi
    KASITLI (DW-104): baslik arama kutusuna yazilan ifadeye benzedigi
    olcude bulunuyor, ve bulunurluk su an kanalin calisan tek yani (%96
    trafik Shorts akisindan). Yasaklanan sey ust uste AYNI soru kelimesi.
    """
    bicim = _baslik_bicimi(baslik)
    # ⚠️ Siniflanmayan kovalar bir kalip degil. Onlari tekrar saymak
    # birbirinden tamamen farkli iki basligi reddederdi.
    if bicim in tekrar_olcusu.SINIFLANMAYAN or not onceki_basliklar:
        return False
    return any(_baslik_bicimi(onceki) == bicim for onceki in onceki_basliklar)


ARSIV_ENVANTER_SINIRI = 40
"""Menude en fazla kac dosya gosterilecek.

Havuzun tamami degil, `_kategori_adaylari` siralamasinin tepesi: model
secim yapabilsin diye genis, isteme sigsin diye sinirli. Olculdu
(2026-08-14): suzgecten gecen dosya sayisi konu basina 13-40 arasinda,
yani sinir cogu konuda zaten baglayici degil.
"""

UZUN_ENVANTER_SINIRI = 60
"""Uzun formatta menude en fazla kac dosya gosterilecek.

⚠️ 40 yetmez: uzun format 24-45 sahne istiyor ve her sahne menuden AYRI bir
dosya alintilamak zorunda (`alinti_kusuru`). 40'lik menuyle 45 sahne
istemek, modelden imkansizi istemek olurdu.

Olculdu (2026-08-15) — bu sinirla kullanilabilir gorsel: Bagan 49,
Herculaneum 37, Alhambra 32, Egyptian pyramids 23. Yani sinir cogu konuda
baglayici bile degil; asil sinir arsivin kendisi.
"""

ARZ_PAYI = 3
"""Sahne sayisi belirlenirken menuden birakilan yedek dosya sayisi.

⚠️ Sahne sayisi menunun TAMAMI yapilmiyor. Her sahne menuden AYRI bir dosya
secmek zorunda (`alinti_kusuru`), yani 38 dosyaya 38 sahne demek modelin her
dosyayi kullanmak zorunda kalmasi ve anlatiya uymayan bir gorseli bile
atlayamamasi demek. Birkac yedek, secim ozgurlugu birakiyor.

Kucuk secildi: pay buyudukce video kisalir ve arsivin verebilecegi sahneleri
bosa harcamis oluruz.
"""


def envanter_siniri(bicim: "VideoBicimi | None" = None) -> int:
    """Bicimin menu siniri. Tek yerden okunur ki kapi ile istem ayrisamasin."""
    return UZUN_ENVANTER_SINIRI if bicim and not bicim.dikey else ARSIV_ENVANTER_SINIRI


_ENVANTER_ONBELLEGI: dict[tuple[str, int], list[dict[str, str]]] = {}
ACIKLAMA_SINIRI = 140

ASGARI_ACIKLAMA = 12
"""Bir menu aciklamasinin bilgi tasidigi sayilmasi icin gereken uzunluk."""

ICERIKSIZ_ACIKLAMA = re.compile(
    r"(https?://|www\.|\.com\b|\.org\b|\.net\b"
    r"|complete indexed photo|photo collection at"
    r"|own work|self[- ]photographed|uploaded by"
    r"|all rights reserved)",
    re.IGNORECASE,
)
"""Gorselin ICERIGINI anlatmayan aciklama kaliplari.

⚠️ NEDEN VAR — olculdu (2026-08-16/17, 11 ret). Hakemin en sik yazdigi agir
kusur `konuyla ilgisiz modern goruntu` (20 kez; `donem uyusmuyor` 7, `anlatilan
kisi degil` 2). Sebep modernlik DEGIL: hakem `modern` VE
`authentic_subject: false` istiyor, yani secilen dosya anlatilan seyi
gostermiyor.

Model dosyayi bu menudeki ACIKLAMAYA bakarak seciyor. Ama aciklamalarin buyuk
kismi gorselin icerigini hic anlatmiyor — Terracotta Army menusunde ilk on
girdinin ALTISI ayni satirdi:

    "2007. Complete indexed photo collection at WorldHistoryPics.com."

Yani secim pratikte KOR yapiliyor: model bir kunyeye bakip etrafina anlati
yaziyor, render'da cikan kare uymuyor ve slot yaniyor.

⚠️ KISMI COZUM oldugu BILINEREK eklendi. Olculdu:

    Terracotta Army  40 -> 15   (kunye yigini temizlendi)
    Petra            40 -> 35
    Tipasa           40 -> 34
    Moai             31 -> 31   <- HIC ETKILENMIYOR
    Cryptoporticus   16 -> 16
    Mastaba          15 -> 14

Moai'nin aciklamalari kunye degil seyahat anlatisi ("After visiting the North
of Chile, we flew down to Santiago...") ve bu kaliplarla ayirt edilemiyor.
O sinifi kapatan tek yol render ONCESI goru kontrolu — ayri is.

⚠️ Kaliplar KASTEN DAR tutuldu: aciklama metnini "kalitesine" gore yargilayan
genis bir kural, mesru ama kisa aciklamalari da elerdi ve menuyu kurutmak
kapiyi kapatmak demek (`arsiv_envanteri` ayni zamanda kapma kapisi).
"""


def aciklama_iceriksiz_mi(aciklama: str) -> bool:
    """Aciklama gorselin icerigi hakkinda bir sey soyluyor mu."""
    sade = (aciklama or "").strip()
    return len(sade) < ASGARI_ACIKLAMA or bool(ICERIKSIZ_ACIKLAMA.search(sade))


def arsiv_envanteri(
    konu: str,
    *,
    sinir: int = ARSIV_ENVANTER_SINIRI,
    bicim: "VideoBicimi | None" = None,
) -> list[dict[str, str]]:
    """Konu icin kullanilabilir arsiv gorsellerinin MENUSU. Yoksa BOS DONER.

    Her girdi `{dosya, gosterdigi, tarih}`. Sahneler bu menuden secim yapmak
    zorunda (bkz. `alinti_kusuru`), yani bu liste "fikir verir" degil
    "secenekleri belirler".

    ⚠️ NEDEN DOSYA ADI YETMIYOR — olculdu (2026-08-14). Bu fonksiyon
    onceki halinde kategorinin ilk 45 dosya ADINI donduruyordu ve model
    onlardan senaryo yazamiyordu: `20190415 151806b.jpg`, `500px photo
    (50204564).jpeg`, `Ujung.jpg`, `Bingmayong Gisela-Brantl 03.JPG`. Bir
    dosya adi neyin resmedilebilir oldugunu SOYLEMIYOR, o yuzden model
    tahmine devam etti ve arsivde bulunmayan anlari istedi ("1974'te kuyu
    kazan koyluler", "denizde dumenini kaybeden gemi"). Son 12 kosumun
    kaynak skoru 0-63'tu (kapi 70) ve hakemin gerekcesi hep ayniydi: dogru
    konu, YANLIS an.

    Ayni dosyalarin Commons aciklamasi ise kullanilabilir: "The clipper
    CUTTY SARK re-conditioned at anchor at Falmouth" (1922 sonrasi),
    "Boroboedoer bij Magelang, KITLV 99831". Tarih de veriliyor cunku
    donem, sahnenin anlatiyla uyusup uyusmadigini belirleyen sey.

    Bos donmek bilincli: menu kurulamayan konularda uretim durmamali.
    """
    # ⚠️ Onbellek anahtari SINIRI DA iceriyor. Yalnizca konuyla anahtarlansaydi
    # ayni surecte once calisan Shorts koşumu 40'lik menuyu onbellege koyar,
    # sonraki uzun koşum 60 isteyip 40 alirdi — ve tersi de mumkun. Kapinin
    # modele gosterilenden BASKA bir listeye bakmasi, bu dosyada zaten
    # olculmus bir kusur sinifi (bkz. `alinti_kusuru`, "Jock Willis").
    oran = kare_orani(bicim)
    anahtar = (konu.strip().casefold(), sinir, round(oran, 4))
    if anahtar in _ENVANTER_ONBELLEGI:
        return _ENVANTER_ONBELLEGI[anahtar]
    try:
        adaylar = wikimedia_materials.arsiv_menusu(
            konu, sinir=sinir, hedef_oran=oran
        )
    except Exception:
        # ⚠️ Menu bir IYILESTIRME; cekilemezse uretim durmamali. Kategori ve
        # arama uclari 429/5xx donebiliyor ve o an plan asamasindayiz, yani
        # elde henuz hicbir sey yok.
        return []
    menu: list[dict[str, str]] = []
    for aday in adaylar:
        dosya = str(aday.get("title") or "").removeprefix("File:").strip()
        if not dosya:
            continue
        gosterdigi = str(aday.get("aciklama") or "")[:ACIKLAMA_SINIRI]
        # ⚠️ Aciklamasi iceriksiz olan dosya menuye GIRMIYOR — gerekce
        # `ICERIKSIZ_ACIKLAMA`da. Model dosyayi aciklamadan seciyor; ne
        # gosterdigini soylemeyen bir girdi kor secim demek.
        #
        # ⚠️ Bu, kapinin saydigi sayiyi da dusurur ve DOGRUSU bu:
        # `arsiv_envanteri` ayni zamanda kapma kapisi (`run_cycle`) ve terfi
        # olcumunun karsiligi. Menuyu suzup kapiyi suzmemek, konuyu terfi
        # ettirip `alinti_kusuru` asamasinda oldurmek olurdu — menu
        # seyreltmesinde ayni ders olculmustu.
        if aciklama_iceriksiz_mi(gosterdigi):
            continue
        menu.append(
            {
                "dosya": dosya,
                "gosterdigi": gosterdigi,
                "tarih": str(aday.get("tarih") or "")[:40],
            }
        )
    _ENVANTER_ONBELLEGI[anahtar] = menu
    return menu


def sahne_kaydi(
    plan: ContentPlan, credits: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Sahne basina NE ISTENDI / NE GELDI — koşum kaydinin en teshis edici alani.

    ⚠️ NEDEN VAR — bu oturumda darbogazi bulmak, 12 koşumun hakem
    ciktilarini tek tek elle okumayi gerektirdi, cunku `state.json` sahne
    duzeyinde HICBIR sey tutmuyordu: hangi terim arandi, hangi dosya
    alintilandi, karsiliginda ne indirildi. Kayit olmadan bir sonraki
    "olcup degistir" turu da ayni korlukle baslar.

    Arayuzun okuyacagi bicim: `{sahne, terim, kaynak_dosya, gelen, anlatim}`.
    """
    gelen_by_scene = {
        int(kredi.get("scene", 0)): str(kredi.get("title") or "")
        for kredi in (credits or [])
    }
    return [
        {
            "sahne": sira,
            "terim": str(sahne.get("search_term", "")),
            "kaynak_dosya": str(sahne.get("kaynak_dosya", "")),
            "gelen": gelen_by_scene.get(sira, ""),
            "anlatim": str(sahne.get("narration", "")),
        }
        for sira, sahne in enumerate(plan.scenes, 1)
    ]


def ikinci_gorsel_istenebilir(menu: list[dict[str, str]], sahne_sayisi: int) -> bool:
    """Menu her sahneye IKI AYRI dosya verebilir mi.

    ⚠️ OLCULDU (2026-08-14) ve bir GERILEME kapatiyor. Ikinci alinti
    eklenince istem her sahne icin iki dosya istiyordu; menusu kucuk
    konularda bu imkansiz bir talep oldu. Yedek capa havuzunun 14
    girdisinden 5'i 6 sahne icin gereken 12 ayri dosyayi veremiyor:

        Newgrange 7 · Notre Dame 5 · Sigiriya 8 · Sacsayhuaman 11 ·
        Hadrian's Wall 11

    Model imkansiz talebi karsilamak icin dosya tekrar ediyordu, tekrar
    kapisi PLANIN TAMAMINI reddediyordu ve bes deneme boşa gidiyordu —
    18:05 zamanlanmis koşumu tam bu yuzden hic video uretmeden dustu
    (materyal dizini bile olusmadi).
    """
    return len(menu) >= sahne_sayisi * KARE_YUVASI


def _capa_arzi_kusuru(
    plan: ContentPlan,
    *,
    bicim: VideoBicimi,
    sahne_sayisi: int | None = None,
) -> str:
    """Modelin sectigi CAPA'nin arsivi videoyu tasiyabilir mi. Tasiyorsa "".

    ⚠️ NEDEN BURADA — olculdu (2026-08-17, slot 14, canli). Huni kipinde
    terfi kapisi KUYRUK BASLIGINI olcuyor, uretim ise modelin sectigi
    CAPA'yi kullaniyor ve bu ikisi ayni sey degil:

        kuyruk basligi          menu | modelin capasi    menu
        King Philip's War         16 | Metacom              1
        Köktürk                   18 | Göktürks           10
        Operation Storm           15 | Operation Storm    15   <- uyumlu
        Cemal Bajá                13 | Djemal Pasha       29   <- uyumlu

    King Philip's War kuyruktan cekildi, terfi kapisini 16 ile gecti ve
    REDDEDILDI: model olayi birakip KISIYI (`Metacom`) capa secti, o kisinin
    arsivi 1 dosya. Sahne 9-12 modern fotograflarla doldu ve hakem sekiz
    agir kusur yazdi ("donem uyusmuyor", "konuyla ilgisiz modern goruntu").

    ⚠️ TERFI KAPISINA EKLENEMEZ, ve bu #37'nin acilis tasariminin cürüdügü
    yer: capayi MODEL seciyor, yani terfi aninda o menu heNUZ YOKTUR.
    Kapinin dogru yeri plan kurulduktan SONRA — capa artik bilinir ve
    dongu geri bildirimle yeniden deneyebilir.

    ⚠️ OLCUT `ikinci_gorsel_istenebilir`in KENDISI, kopyasi degil. O
    fonksiyon global `KARE_YUVASI`ye (2) bakiyor; uzun bicimde
    `bicim.kare_yuvasi` 1. Burada `bicim.kare_yuvasi` ile ayri bir hesap
    yazmak, kapinin reddettigi sayi ile mesajin soyledigi sayiyi
    ayirirdi — `ASGARI_MENU` docstring'inin uyardigi kusurun aynisi, tek
    fark bu kez ayni fonksiyonun icinde olurdu.

    ⚠️ UZUN BICIMDE ZATEN BIR ON KONTROL VAR (`UzunFormatUygunDegilError`)
    ve o `konu`yu olcuyor; burasi CAPAYI olcuyor, yani ikisi ayni sey degil
    ve ust uste binmiyorlar.

    Bos donmek (menu cekilemedi) kusur SAYILMIYOR: menu bir iyilestirme, on
    kosul degil. Ag hatasi butun koşumu reddettirmemeli — `arsiv_envanteri`
    zaten istisnayi yutup `[]` donduruyor ve o durumda uretim eski yoluna
    (arama terimleri) dusuyor.
    """
    hedef = sahne_sayisi or len(plan.scenes) or bicim.sahne_araligi[1]
    menu = arsiv_envanteri(
        plan.visual_anchor, sinir=envanter_siniri(bicim), bicim=bicim
    )
    if not menu:
        return ""
    if ikinci_gorsel_istenebilir(menu, hedef):
        return ""
    return (
        f"capa arzi yetersiz: {plan.visual_anchor!r} icin {len(menu)} gorsel, "
        f"{hedef} sahne icin gereken {hedef * KARE_YUVASI} kareyi vermiyor"
    )


def _kaynak_ve_menu_blogu(
    konu: str,
    *,
    bicim: VideoBicimi,
    envanter_sinir: int,
    sahne_sayisi: int | None = None,
    sahne_tavani: int | None = None,
) -> str:
    """AUTHORITATIVE SOURCE + ARCHIVE MENU bloklari — iki kip de ayni metni alir.

    ⚠️ ORTAK YARDIMCI OLDU (2026-08-17). Eskiden bu iki blok yalnizca
    `generate_content_plan`in `if konu:` dalinda kuruluyordu, yani menu
    disiplini SADECE kuyruk kipinde vardi. Yedek kipte model menuyu hic
    gormuyordu ve `source_file` / `source_file_2` alanlari bos kaliyordu —
    yani ikinci gorsel "bulunamiyor" degil HIC ISTENMIYORDU.

    Bloklari iki dala kopyalamak yerine buraya alindi: kopyalansaydi iki kip
    zamanla birbirinden sapardi ve kusur yalnizca birinde duzelirdi.
    """
    kaynak_cek = (
        wikimedia_materials.vikipedi_ozeti
        if bicim.dikey
        else wikimedia_materials.vikipedi_tam_metin
    )
    if kaynak := kaynak_cek(konu):
        blok = (
            "\n\nAUTHORITATIVE SOURCE — this is the Wikipedia "
            + ("summary" if bicim.dikey else "article")
            + " of the subject. "
            "Every factual claim in your script, title, description and tags must be "
            "consistent with it. Inventing a fact is the one failure this channel "
            "cannot survive. Where the summary is silent, do NOT write a sentence "
            "about the silence: narrow the video to an aspect the summary DOES cover "
            "and build the scenes from that. A script about three well documented "
            "events beats a script about eight events where five are unexplained.\n"
            f"{json.dumps(kaynak, ensure_ascii=False)}"
        )
    else:
        # Kaynak yoksa uretim durmuyor ama model UYARILIYOR: bos kaynak,
        # "serbestsin" degil "temkinli ol" demek.
        blok = (
            "\n\nNo encyclopedia summary could be retrieved for this subject. Write only "
            "what you are confident is true of THIS specific subject and keep the claims "
            "few and general. Do not invent names, dates, professions or events to fill "
            "the script, and do not fill it with sentences about the record being thin "
            "either: write fewer scenes about what you do know."
        )
    # ⚠️ ARSIV MENUSU — gerekcesi `arsiv_envanteri`nde. Kaynak metni
    # modele NE ANLATACAGINI soyluyor; bu liste NEYI GOSTEREBILECEGINI.
    # Ikisi ayri bilgi ve ikisi de eksikse model tahmin ediyor.
    if envanter := arsiv_envanteri(konu, sinir=envanter_sinir, bicim=bicim):
        # Sahne sayisi verilmemisse (model bicimin araliginda secer) en
        # KOTU ihtimale gore karar veriliyor: aralikin USTU icin yeterli
        # degilse ikinci gorsel istenmiyor. Iyimser davranip sonra
        # temizlemek, modelin bosuna dosya uydurmasini davet ederdi.
        blok += _menu_talimati(
            envanter,
            sahne_sayisi or sahne_tavani or bicim.sahne_araligi[1],
            bicim=bicim,
        )
    return blok


def _yedek_capa_sec(
    eligible_anchors: list[str],
    *,
    bicim: VideoBicimi,
    envanter_sinir: int,
    sahne_sayisi: int | None = None,
) -> str:
    """Yedek kip icin ARSIVI OLCULMUS bir capa secer; yoksa "" doner.

    ⚠️ NEDEN KOD SECIYOR (kanal sahibinin karari, 2026-08-17). Menu bir
    OZNE gerektiriyor, ozne ise bugune kadar modelden geliyordu — yani
    menuyu istem kuruldugu anda cekmek imkansizdi ve yedek kip menusuz
    kaliyordu. Ozneyi kod secince tavuk-yumurta kiriliyor ve yedek kip
    kuyruk kipinin (iyi calisan) yoluna giriyor. Model yine aciyi, basligi
    ve sahneleri yaziyor; yalnizca ozne sabitleniyor.

    ⚠️ Alternatif ELENDI: once modele capayi sectirip SONRA menuyle sahneleri
    yeniden yazdirmak. Iki cikarim cagrisi demekti ve ilk cagrinin sahneleri
    copе gidiyordu.

    ⚠️ Menusu yetmeyen capa ATLANIYOR. Havuzdaki capalarin hepsi 12+ olcmustu
    (`8ad4b4c`) ama olcum onbellege ve Commons'a bagli; burada yeniden
    dogrulaniyor. Hicbiri yetmezse "" doner ve cagiran taraf BUGUNKU serbest
    secim davranisina duser — menu bir iyilestirme, on kosul degil.
    """
    for capa in eligible_anchors:
        try:
            menu = arsiv_envanteri(capa, sinir=envanter_sinir, bicim=bicim)
        except Exception as hata:  # noqa: BLE001 - menu on kosul degil
            print(f"⚠️ yedek capa menusu okunamadi ({capa}): {hata}", flush=True)
            continue
        if ikinci_gorsel_istenebilir(menu, sahne_sayisi or bicim.sahne_araligi[1]):
            return capa
    return ""


def capayi_konuya_genislet(plan: ContentPlan, konu: str) -> str:
    """Dar secilmis capayi KONUNUN kendisi yapar; eski capa doner, yoksa "".

    ⚠️ NEDEN REDDETMEK DEGIL ONARMAK. Bu kapi once REDDEDIYORDU (2026-08-15)
    ve olculdu ki dogru cevap ZATEN BELLI: konu disaridan sabit, capa da o
    olmali. Modelden bunu yeniden uretmesini istemek, uzun formatta ~400
    saniyelik bir cikarim koşumu demek.

    ⚠️ Daha kotusu, iki kapi birbirine KARSI calisiyordu. `alinti_kusuru`
    "capayi arsivi olan baska bir seye bagla" diyor, bu kapi "capa konunun
    kendisi olmali" diyordu. Model birincisine uyup 'Villa of the Papyri'
    yazdi, ikincisi reddetti (dokuzuncu koşum, 2->3 gecisi).

    ⚠️ Terimler YENIDEN turetiliyor: eski capaya gore kurulmus terimler yeni
    capayi tasimazsa `validate_content_plan`in sahne kapisi bu kez ONLARI
    reddederdi. `_ensure_visual_anchor` capayi ekliyor ve sahnenin kendi
    somut kelimesi duruyor — "Villa of the Papyri scrolls" bilgisini
    kaybetmeden "Herculaneum ..." haline geliyor.

    Yalnizca uzun kipte ve `konu` verildiginde cagriliyor. Shorts'ta dar capa
    KASITLI (bkz. "Vassar College" gerekcesi).
    """
    konu_kelimeleri = _normalize_topic(konu)
    if not konu_kelimeleri or (_normalize_topic(plan.visual_anchor) & konu_kelimeleri):
        return ""
    eski = plan.visual_anchor
    plan.visual_anchor = konu.strip()
    for sahne in plan.scenes:
        sahne["search_term"] = _ensure_visual_anchor(
            str(sahne.get("search_term", "")), plan.visual_anchor
        )
    return eski


def arama_terimlerini_tekillestir(plan: ContentPlan) -> int:
    """Tekrarlayan arama terimlerini AYIRIR; onarilan sahne sayisi doner.

    ⚠️ NEDEN REDDETMEK DEGIL ONARMAK — olculdu (2026-08-15, ilk Herculaneum
    koşumu). Uzun formatta bes denemenin ucuncusu tam gecerli bir plandi:
    1.353 kelime, 31 sahne, 31/31 gecerli arsiv alintisi. 31 terimin 3'u
    benzestigi icin PLANIN TAMAMI reddedildi ve ~2 dakikalik bir uretim
    cope gitti. Bes deneme boyunca ayni sinif kayip iki kez yasandi.

    Kapinin ölçülmüş gerekcesi uzun formatta GECERLI DEGIL: o kapi (2026-08-13)
    ayni terimin ayni sirali arama sonucunu getirmesine karsi kondu. Burada
    sahne gorselini ARAMADAN degil ALINTIDAN aliyor — `ikincil_gorseller`
    once `kaynak_dosya`yi indiriyor ve terim yalnizca alinti dustugunde
    devreye giren bir yedek. Yani alintisi olan sahnede terim tekrari
    gorsel tekrarina yol acmiyor.

    Bu yuzden onarim SADECE alintisi olan sahnelerde yapiliyor; alintisiz
    sahnede terim tek gorsel kaynagi oldugu icin sert kapi duruyor.

    Ayirma yontemi: dosya adindaki, terimde HENUZ GECMEYEN kelimeler
    ekleniyor — yani ayirt edici bilgi uydurulmuyor, alintilanan dosyadan
    aliniyor. Ayni yaklasim `_ensure_visual_anchor`de de var (terim
    yeniden yaziliyor, plan reddedilmiyor).
    """
    gorulen: set[str] = set()
    onarilan = 0
    for sahne in plan.scenes:
        terim = str(sahne.get("search_term", "")).strip()
        anahtar = " ".join(sorted(_normalize_topic(terim)))
        if anahtar and anahtar not in gorulen:
            gorulen.add(anahtar)
            continue
        dosya = str(sahne.get("kaynak_dosya", "")).strip()
        if not dosya:
            # Alintisiz sahnede terim tek gorsel kaynagi — sert kapi dursun.
            continue
        mevcut = _normalize_topic(terim)
        ekler = [k for k in _normalize_topic(Path(dosya).stem) if k not in mevcut]
        if not ekler:
            continue
        yeni = f"{terim} {' '.join(ekler[:3])}".strip()
        yeni_anahtar = " ".join(sorted(_normalize_topic(yeni)))
        if yeni_anahtar in gorulen:
            continue
        sahne["search_term"] = yeni
        gorulen.add(yeni_anahtar)
        onarilan += 1
    return onarilan


def ikincil_alintilari_temizle(
    plan: ContentPlan,
    menu_konusu: str = "",
    *,
    sinir: int = ARSIV_ENVANTER_SINIRI,
    bicim: "VideoBicimi | None" = None,
) -> int:
    """Gecersiz ya da tekrarlayan IKINCI alintilari siler; silinen sayisi doner.

    ⚠️ NEDEN REDDETMEK DEGIL TEMIZLEMEK: ikinci gorsel bir IYILESTIRME.
    Birincil alinti sahnenin anlatimini tasiyor ve yanlissa video yanlis
    olur — orada reddetmek dogru. Ikinci gorsel ise yoksa sahne birincil
    kareyi iki yuvada gosterir ve bugunku haliyle birebir ayni durur.
    Iyilestirme ugruna calisan bir plani cope atmak, kazanci maliyetten
    kucuk bir takas.
    """
    menu = arsiv_envanteri(
        menu_konusu.strip() or plan.visual_anchor, sinir=sinir, bicim=bicim
    )
    gecerli = {girdi["dosya"] for girdi in menu} if menu else set()
    gorulen = {str(s.get("kaynak_dosya", "")).strip() for s in plan.scenes}
    silinen = 0
    for sahne in plan.scenes:
        ad = str(sahne.get("kaynak_dosya_2", "")).strip()
        if not ad:
            continue
        if (menu and ad not in gecerli) or ad in gorulen:
            sahne["kaynak_dosya_2"] = ""
            silinen += 1
            continue
        gorulen.add(ad)
    return silinen


def _menu_talimati(
    menu: list[dict[str, str]],
    sahne_sayisi: int = 0,
    *,
    bicim: VideoBicimi = SHORTS_BICIMI,
) -> str:
    """Menuyu isteme koyan metin. Kapinin (`alinti_kusuru`) sozlu karsiligi.

    Metin tek bir sey soyluyor: ONCE goruntuyu sec, SONRA onun uzerine cumle
    yaz. Ters sira bu oturumun en pahali kusuruydu — senaryo fotografi
    cekilmemis anlari anlatiyor, arsiv onlari veremiyor ve kaynak kapisi
    kosumu render'dan once olduruyordu.
    """
    return (
        "\n\nARCHIVE MENU — this is every usable public-domain image that exists for "
        "this subject, with what it shows and when it was made. These are the ONLY "
        "pictures the video can display.\n"
        f"{json.dumps(menu, ensure_ascii=False)}\n"
        "Write the video FROM this menu, not the other way round. For each scene: pick "
        "one entry, copy its 'dosya' value EXACTLY into the scene's source_file field, "
        "and write narration that tells the story of the THING in that picture. A "
        "different entry for every scene. "
        # ⚠️ SAHNE TAVANINI MENU BELIRLIYOR ve model bunu BILMELI. Uzun kipte
        # sozlesme 24-45 sahne diyor; 32 dosyalik bir arsivde 40 sahne
        # istenirse her sahne ayri dosya alintilayamaz, `alinti_kusuru`
        # plani reddeder ve bes deneme yanar. Tek cumle, cogu yeniden
        # denemeyi bastan siliyor.
        + (
            f"This archive holds {len(menu)} usable images, so this video can have at "
            f"most {len(menu)} scenes: write between {bicim.sahne_araligi[0]} and "
            f"{min(bicim.sahne_araligi[1], len(menu))} scenes and no more. "
            if not bicim.dikey
            else ""
        )
        # ⚠️ IKINCI GORSEL YALNIZCA MENU YETIYORSA isteniyor — kanal
        # sahibinin karari (2026-08-14): her sahne iki kare gosteriyor,
        # cunku tek gorsel altyazinin 2,5 kati yavas kaliyordu.
        #
        # ⚠️ Kosul OLCULEREK kondu: ilk surum menu boyutuna bakmadan her
        # sahne icin iki dosya istiyordu ve kucuk menulu konularda bu
        # imkansiz bir talepti (`ikinci_gorsel_istenebilir`). Model
        # imkansizi karsilamak icin dosya tekrar ediyor, plan reddediliyor
        # ve koşum hic video uretmeden dusuyordu.
        + (
            "ALSO pick a SECOND entry for each scene and copy its 'dosya' value into "
            "source_file_2. It must show the same subject from another angle, another "
            "moment or another detail, and it must fit the SAME narration — the viewer "
            "sees both pictures while that sentence is spoken. Never reuse an entry that "
            "any scene already cites, in either field. If you cannot find a distinct "
            "second entry for a scene, leave its source_file_2 empty rather than "
            "repeating one. "
            if bicim.kare_yuvasi >= 2
            and ikinci_gorsel_istenebilir(menu, sahne_sayisi or len(menu))
            # ⚠️ Uzun kipte sahne basina TEK kare var (`kare_yuvasi = 1`), yani
            # ikinci gorsel istemenin yeri yok: istenirse model gereksiz yere
            # menunun iki katini tuketir ve ekranda hicbir sey degismez.
            else "Leave source_file_2 empty for every scene: each scene shows exactly "
            "one picture in this format. "
            if bicim.kare_yuvasi < 2
            else "Leave source_file_2 empty for every scene: this archive is too small "
            "to give each scene a second distinct picture. "
        )
        + "Do not narrate a moment no entry depicts: if "
        "nothing here shows the discovery, the battle, the storm or the person at work, "
        "that moment cannot be a scene, however important it is. Choose entries whose "
        "date suits the story, and do not describe a modern photograph as a historical "
        "scene.\n"
        "NEVER MAKE THE PICTURE ITSELF THE SUBJECT OF A SENTENCE. \"An 1871 image shows "
        "the vessel\", \"another photograph depicts her under sail\" and \"one later port "
        "photograph may show Sydney\" are not narration; they are captions, and a video "
        "of captions is a failed video. Say what happened to the ship, the building or "
        "the person that the viewer is looking at."
    )


def alinti_kusuru(
    plan: ContentPlan,
    menu_konusu: str = "",
    *,
    sinir: int = ARSIV_ENVANTER_SINIRI,
    bicim: "VideoBicimi | None" = None,
) -> str:
    """Her sahne menuden GERCEK bir dosya secmis mi — secmemisse kusur metni.

    ⚠️ NEDEN ALINTI, NEDEN KELIME ORTUSMESI DEGIL: bu kapinin onceki hali
    (`arsiv_destegi_kusuru`) sahne teriminin kelimeleriyle dosya adlarinin
    kelimelerini kesistiriyordu ve pratikte hicbir seyi engellemiyordu.
    Olculdu (2026-08-14): "1974 Terracotta Army discovery farmers digging
    well Xi'an" teriminde "xian" kelimesi kategori dosya adlarinda gectigi
    icin sahne kapiyi geciyordu — oysa arsivde kuyu kazan koylulerin
    fotografi yok. Kapi acikken uretilen 12 kosumun kaynak skoru 0-63'tu.

    Alinti kontrolu bir KUME ARAMASI: dilbilim tahmini yok, "bu dosya adi
    menude var mi" var. DW-87 dersinin dogru bicimi bu — kod, dogrulanabilir
    bir olguyu kontrol ediyor.

    Ikinci is: menu sahne sayisindan kucukse capa REDDEDILIYOR. Slotun
    olculmemis adaya harcanmasi bu oturumun en pahali kusuruydu — Archimedes
    Palimpsest ve Pompeii Amon Min menusu 0 dosya, ikisi de skor 0 aldi ve
    ikisi de bir uretim slotu yakti.

    Menu kurulamazsa BOS DONER — kapi degil iyilestirme; hat eskisi gibi
    aramayla calisir.

    ⚠️ `menu_konusu` ISTEMDEKI menunun anahtari olmali, planin capasi degil.
    Olculdu (2026-08-14, canli plan uretimi): huni konusu "Cutty Sark"
    verilmisken model capayi "Jock Willis" (gemiyi siparis eden armator)
    olarak sectI. Istem "Cutty Sark" menusunu gostermisti, kapi ise
    "Jock Willis" menusune bakti — model DOGRU alinti yapmisti ve kapi
    bes sahneyi birden uydurma sayip plani reddetti. Kapinin modele
    gosterilenden BASKA bir listeye bakmasi, kapiyi cozdugu kusurun
    kaynagina cevirir.
    """
    menu = arsiv_envanteri(
        menu_konusu.strip() or plan.visual_anchor, sinir=sinir, bicim=bicim
    )
    if not menu:
        return ""
    if len(menu) < len(plan.scenes):
        # ⚠️ GERI BILDIRIM BICIME GORE (2026-08-15). Eski metin her iki kipte
        # de "capayi baska bir seye bagla" diyordu ve uzun formatta bu, capa
        # kapisinin (`validate_content_plan`, "use the topic itself as the
        # visual anchor") TAM YASAKLADIGI hamle.
        #
        # Olculdu (dokuzuncu koşum, 2->3 gecisi): model bu mesaja UYDU,
        # capayi 'Villa of the Papyri'ye daraltti, oteki kapi reddetti. Iki
        # kapi birbirine karsi deneme yakiyordu ve celiski buraya capa kapisi
        # eklenirken girdi.
        #
        # Uzun formatta dogru cozum zaten belli: sahne sayisini indir. Konu
        # DISARIDAN sabit, yani capa degistirilemez.
        if not bicim or bicim.dikey:
            return (
                f"the archive holds only {len(menu)} usable images for "
                f"{plan.visual_anchor!r}, fewer than the {len(plan.scenes)} scenes "
                "this plan needs. Anchor the video on a different concrete thing that "
                "archives actually photographed, and build the script around that."
            )
        return (
            f"the archive holds only {len(menu)} usable images for "
            f"{plan.visual_anchor!r}, fewer than the {len(plan.scenes)} scenes this "
            f"plan needs. Keep the same visual anchor and write at most {len(menu)} "
            "scenes instead, each citing a different file from the menu."
        )
    gecerli = {girdi["dosya"] for girdi in menu}
    alintilar = [str(sahne.get("kaynak_dosya", "")).strip() for sahne in plan.scenes]
    eksik = [sira for sira, ad in enumerate(alintilar, 1) if ad not in gecerli]
    if eksik:
        return (
            f"scenes {eksik} cite a source_file that does not exist in this subject's "
            "archive. Every scene's source_file must be copied EXACTLY from this menu, "
            "and its narration must describe what that file actually shows:\n"
            f"{json.dumps(menu, ensure_ascii=False)}"
        )
    tekrar = sorted({ad for ad in alintilar if alintilar.count(ad) > 1})
    if tekrar:
        return (
            f"the same archive file is cited by more than one scene ({tekrar}). Each "
            "scene must cite a different file so the video does not repeat an image."
        )
    # ⚠️ IKINCI ALINTI BURADA DENETLENMIYOR ve bu bilincli bir karar.
    #
    # Ilk surum ikinci alintiyi da ayni sertlikte denetliyordu: uydurma ya
    # da tekrarlayan bir `source_file_2` PLANIN TAMAMINI reddediyordu.
    # Olculdu (2026-08-14): yedek capa havuzunun 14 girdisinin 5'i 6 sahne
    # icin gereken 12 ayri dosyayi veremiyor (Newgrange 7, Notre Dame 5,
    # Sigiriya 8, Sacsayhuaman 11, Hadrian's Wall 11). Model imkansiz
    # talebi karsilamak icin dosya tekrar ediyor, plan reddediliyor, bes
    # deneme yaniyordu — 18:05 zamanlanmis koşumu hic video uretmeden
    # dustu.
    #
    # Dogru davranis `ikincil_alintilari_temizle`de: bozuk ikinci alinti
    # SILINIYOR, plan yasiyor. Ikinci gorsel bir iyilestirme; yoksa sahne
    # birincil kareyi iki yuvada gosterir ve bugunku haliyle ayni durur.
    return ""


def generate_content_plan(
    extra_exclusions: list[str] | None = None,
    konu: str | None = None,
    sahne_sayisi: int | None = None,
    *,
    bicim: VideoBicimi = SHORTS_BICIMI,
    capa_tekrari_serbest: bool = False,
) -> ContentPlan:
    """Video planini uretir; `konu` verilirse KONUYU SECMEZ, verileni isler.

    `konu` disaridan geldiginde (trend hunisinden, DW-89) benzerlik kontrolu
    uygulanmaz. Sebep: bu konuyu model degil, olculmus talep verisi ve onu
    onaylayan insan sectI. "Cok benziyor" diye reddetmek, insanin kararini
    modelin cagrisimina feda etmek olurdu.

    Bu ayrimin bedeli olculdu: 6 Agustos gecesi uretilen 6 videonun konusunu
    model kendi havuzundan sectI ve ayni gecede iki Roma muhendisligi videosu
    cikti. Huni beslemesinin varlik sebebi bu.

    ⚠️ UZUN BICIM `konu` ZORUNLU KILIYOR — ve bu yasak 2026-08-17'den sonra da
    duruyor. Kaynak metin + arsiv menusu artik yedek kipte de kuruluyor
    (`_yedek_capa_sec` bir capa bulursa), ama YALNIZCA bulursa: havuz
    tukendiginde ya da menu cekilemediginde dal menusuz eski davranisa dusuyor.
    Yani yedek kipte menu bir GARANTI degil. `konu=None` ile uzun bir plan
    istemek, o dususte modelden 2.000 kelimeyi HAFIZADAN yazmasini istemek ve
    alinti kapisini sessizce kapatmak olurdu. Uydurma bu hatta olculmus bir
    kusur (DW-114, "Franziska Scanagatta") ve uzun formatta kelime basina
    degil kelime SAYISIYLA olcekleniyor.
    """
    if not bicim.dikey and not konu:
        raise ValueError(
            "uzun bicim icin `konu` zorunlu: kaynak metin ve arsiv menusu yalnizca "
            "konu verildiginde isteme giriyor, konusuz uzun plan hafizadan yazilir"
        )
    envanter_sinir = envanter_siniri(bicim)
    # ⚠️ ON KONTROL — cikarim koşumu BASLAMADAN. Gerekcesi
    # `UzunFormatUygunDegilError` docstring'inde: bu durumu `alinti_kusuru`
    # huni kipinde cozemez, cunku konu sabit ve kapinin geri bildirimi
    # "baska bir seye capa at" diyor. Bes deneme yanar, koşum hic video
    # uretmeden duser. Burada maliyet sifir.
    sahne_tavani: int | None = None
    if not bicim.dikey:
        on_menu = arsiv_envanteri(konu or "", sinir=envanter_sinir, bicim=bicim)
        if len(on_menu) < bicim.sahne_araligi[0]:
            raise UzunFormatUygunDegilError(
                f"{konu!r} icin arsivde {len(on_menu)} kullanilabilir gorsel var, "
                f"uzun formatin gerektirdigi {bicim.sahne_araligi[0]} sahneden az; "
                "bu konu Shorts olarak uretilmeli"
            )
        # ⚠️ SAHNE SAYISINI KOD BELIRLIYOR, model degil (2026-08-15).
        #
        # Istem zaten arzi soyluyordu ("this archive holds 38 usable images,
        # so write at most 38 scenes") ve model 41 yazdi. Yani sayiyi
        # SOYLEMEK yetmiyor — DW-87 dersinin aynisi, dogrulanabilir olguyu
        # kod denetlemeli.
        #
        # Olculdu (dokuzuncu koşum): bes redden UCU bu tek karara bagliydi —
        # 39 sahne (kelime tabanini tutturamadi), 41 sahne (arz 38), 35
        # sahne (yine kelime). Sayi sabitlenince model bir tek seyi
        # ayarliyor: sahne basina kelime.
        #
        # ⚠️ CLI'daki `--uzun ile --sahne-sayisi birlikte kullanilamaz`
        # yasagi DURUYOR ve dokunulmadi: o yasak INSANIN elle sayi vermesini
        # engelliyor (sahne sayisi deneyi Shorts koluna ait). Degisen sey
        # kodun kendi turettigi sayi.
        #
        # ⚠️ TAVAN, TAM SAYI DEGIL. Ilk hali tam sayi istiyordu ve olculdu
        # (onuncu koşum): bes denemenin ikisini tek basina yakti — 35
        # istenirken model 38 ve 34 yazdi, ikisi de baska her acidan
        # GECERLIYDI. Aralik modele nefes birakiyor, tavan arzi koruyor.
        #
        # ⚠️ Hedef sayi isteme AYRICA yaziliyor (`ARZ_PAYI` kadar tavanin
        # altinda): her sahne menuden AYRI bir dosya secmek zorunda, yani
        # tavana dayanan bir plan modelin her dosyayi kullanmasi demek ve
        # anlatiya uymayan bir gorseli bile atlayamaz. Tavan KAPI, hedef
        # TAVSIYE.
        sahne_tavani = min(bicim.sahne_araligi[1], len(on_menu))
    previous = _recent_titles() + list(extra_exclusions or [])
    state = load_state()
    previous_anchors = engellenen_capalar(state)
    eligible_anchors = [
        anchor
        for anchor in EDITORIAL_ANCHOR_POOL
        if not is_duplicate_visual_anchor(anchor, previous_anchors)
    ]
    if not eligible_anchors and not konu:
        # ⚠️ SESSIZ TUKENME. Olculdu (2026-08-13): havuzdaki 15 capanin 15'i
        # de kullanilmisti, liste bos gidiyordu ve model bos listeyle ince
        # arsivli gizemlere kayiyordu (Baychimo, Vasa, Phaistos Diski) —
        # kaynak kapisinda 25-43. Disaridan bakan biri "model kotu konu
        # seciyor" sanirdi; oysa hat ona secenek vermiyordu.
        print(
            "⚠️ Editoryal capa havuzu TUKENDI — model kendi konusunu serbestce "
            "seciyor. `EDITORIAL_ANCHOR_POOL`a olculmus yeni capa ekleyin "
            "(olcut: Commons kategorisinde 12+ kadraj ve lisans gecen gorsel).",
            flush=True,
        )
    system = editoryal_sistem_yonergesi(bicim)
    if konu:
        # Konu sabit: model yalnizca acilari, sahneleri ve gorsel capayi kurar.
        # Kisitlar (sahne sayisi, capa tekrari, kamu malI gorsel) aynen gecerli.
        user = (
            "Build one video plan about this exact subject, which was chosen from measured "
            "search-demand data by a human editor:\n"
            f"{json.dumps(konu, ensure_ascii=False)}\n"
            "Keep this subject. Do not substitute a different topic, era, or place. "
            "You choose the visual_anchor, the angle, and the scenes so that every scene is "
            "honestly illustratable from Public Domain or CC0 imagery of that same subject. "
            "If the subject is broad, narrow it to one concrete named site, artifact, or invention "
            "that belongs to it."
        )
        # ⚠️ KAYNAK METIN — olculdu (2026-08-09, DW-114). Bu blok olmadan model
        # yalnizca konunun ADINI goruyordu ve az bilinen konularda ictigi suyu
        # uyduruyordu: "Franziska Scanagatta" icin senaryo ve etiketler
        # "Italian opera / 19th century music / opera history" cikti; gercekte
        # 1794'te erkek kiligina girip Habsburg ordusunda subaylik yapmis bir
        # kadin. Huninin varlik sebebi arzi az konular bulmak, arzin az olmasinin
        # en yaygin sebebi ise konunun az bilinmesi — yani huni ne kadar iyi
        # calisirsa modelin bilmedigi konu o kadar cok geliyor.
        # ⚠️ Uzun kipte OZET DEGIL TAM MAKALE. Olculdu (2026-08-15): ozet
        # 32-102 kelime, tam makale 1.492-7.539 (27-193 kat). 56 kelimelik
        # ozetten 2.000 kelime yazmasi istenen model aradaki farki uydurur.
        user += _kaynak_ve_menu_blogu(
            konu,
            bicim=bicim,
            envanter_sinir=envanter_sinir,
            sahne_sayisi=sahne_sayisi,
            sahne_tavani=sahne_tavani,
        )
    else:
        user = (
            "Create one new video plan. Do not repeat or closely paraphrase these existing topics/titles:\n"
            + json.dumps(previous[-50:], ensure_ascii=False)
            + "\nNever reuse any of these concrete visual anchors:\n"
            + json.dumps(previous_anchors, ensure_ascii=False)
        )
        # ⚠️ YEDEK KIP ARTIK ARSIV-ONCE (2026-08-17). Eskiden bu dal modele
        # yalnizca kisa listeyi verip capayi ONA sectiriyordu; menu bir OZNE
        # gerektirdigi icin istem kuruldugu anda cekilemiyordu ve yedek kip
        # menusuz kaliyordu. Sonucu olculdu: `source_file` ve `source_file_2`
        # HIC istenmiyordu, yani ikinci gorsel "bulunamiyor" degil hic
        # SORULMUYORDU; gorsel tam metin aramasina, o da tutmayinca kor
        # kategori yedegine dusuyordu (bkz. `ikincil_gorseller`).
        #
        # ⚠️ Menulu yolun ise yaradigi KOD YAZILMADAN olculdu (kuyruk kipi,
        # ayni istem): Ephesus 8 sahnenin 5'inde, Borobudur 8'inde
        # `source_file_2` doldu — 16 sahnenin 13'u. Yedek kipteki karsiligi
        # yapisal olarak 0'di.
        yedek_capa = _yedek_capa_sec(
            eligible_anchors,
            bicim=bicim,
            envanter_sinir=envanter_sinir,
            sahne_sayisi=sahne_sayisi,
        )
        if yedek_capa:
            user += (
                "\n\nBuild this video about this exact subject, chosen because its "
                "public-domain archive was measured and is deep enough to illustrate "
                f"every scene:\n{json.dumps(yedek_capa, ensure_ascii=False)}\n"
                "Keep this subject and use it as the visual_anchor. You choose the "
                "angle, the title and the scenes."
            ) + _kaynak_ve_menu_blogu(
                yedek_capa,
                bicim=bicim,
                envanter_sinir=envanter_sinir,
                sahne_sayisi=sahne_sayisi,
                sahne_tavani=sahne_tavani,
            )
        else:
            # ⚠️ ESKI DAVRANIS AYNEN DURUYOR. Havuz tukendiginde ya da menu
            # cekilemediginde uretim DURMAMALI; menu bir iyilestirme, on
            # kosul degil. Havuz tukenmesinin kendi uyarisi yukarida basiliyor.
            user += (
                "\nChoose the visual_anchor from this unused editorial shortlist when it is non-empty:\n"
                + json.dumps(eligible_anchors, ensure_ascii=False)
            )
        user += "\nPreferred content pillars: ancient engineering, surviving historic places, ingenious inventions, archaeology, navigation, strange verified events, and visible historical mysteries."

    # Sahne sayisi sabitlendiyse istem de bunu SOYLEMELI: yalnizca
    # dogrulamaya birakmak, modelin 8 yazip her seferinde reddedilmesi ve
    # bes denemenin bosa gitmesi demek olurdu.
    if sahne_sayisi is not None:
        user += (
            f"\nThis video must have EXACTLY {sahne_sayisi} scenes, not more and not "
            "fewer. Fit the story to that number: fewer scenes means each one is on "
            "screen longer, so give each a distinct thing to show."
        )
    elif sahne_tavani is not None:
        # ⚠️ TAVAN kapi, HEDEF tavsiye. Tavana dayanan bir plan menudeki her
        # dosyayi kullanmak zorunda kalir ve anlatiya uymayan bir gorseli
        # bile atlayamaz; birkac yedek secim ozgurlugu birakiyor.
        hedef = max(bicim.sahne_araligi[0], sahne_tavani - ARZ_PAYI)
        user += (
            f"\nThis archive can support at most {sahne_tavani} scenes, so write "
            f"between {bicim.sahne_araligi[0]} and {sahne_tavani} scenes and never "
            f"more. Aim for about {hedef}: every scene must cite a different file, so "
            "a plan that uses the whole menu leaves you no room to skip an image that "
            "does not fit what the narration says."
        )

    # Gecmis KAPANISLAR da veriliyor — sebebi `_kapanis_tekrari`de: "geri
    # gelmek icin sebep ver" talimati modeli dogal olarak her videoda ayni
    # cumleye itiyor ve ust uste ayni kapanis, seri kimligi degil reklam
    # kusagi olur.
    if onceki_kapanislar := _son_kapanislar():
        user += (
            "\nThese closing lines were already used on this channel. Do not reuse them, "
            "and do not reuse their sentence pattern:\n"
            + json.dumps(onceki_kapanislar, ensure_ascii=False)
        )

    # Gecmis BASLIKLAR: modele yasagi degil, kacinmasi gereken BICIMI
    # gosteriyor. Yalnizca "tekrarlama" demek yetmiyordu (DW-94'un dersi).
    if onceki_basliklar := _son_basliklar():
        user += (
            "\nThese titles were already used on this channel. Keep writing the title as a "
            "search query, but do not open with the same question word or the same "
            "sentence shape:\n" + json.dumps(onceki_basliklar, ensure_ascii=False)
        )

    # Gecmis acilislar HER IKI kipte de veriliyor: konu disaridan gelse bile
    # kanca modelin kalemi ve kalibina saplanabiliyor (DW-94).
    if onceki_kancalar := _son_kancalar():
        user += (
            "\nThese opening lines were already used on this channel. Do not reuse them, "
            "and do not reuse their sentence pattern:\n"
            + json.dumps(onceki_kancalar, ensure_ascii=False)
        )

    # ⚠️ KAPILAR KATMANLI. Ust katman (dogrulama) HER denemede zorunlu; alt
    # katman (arsiv destegi, capa tekrari, kanca kalibi) yalnizca ilk
    # denemelerde. Sebebi olculdu (2026-08-13, Sutton Hoo koşumu): yumusak
    # kapilar bes denemeyi tuketince kosum `DistinctTopicUnavailableError`
    # ile oldu ve o saat icin HIC video uretilmedi. Kalite tercihini
    # kovalarken uretimin kendisini kaybetmek, kullanicinin duzeltmemi
    # istedigi istikrarsizligin ta kendisi.
    #
    # Yani: iyi bir plan icin ugrasilir, bulunamazsa gecerli bir plan
    # yayina degil RENDER'a gonderilir — kalite kapisi (skor + agir kusur)
    # zaten arkada duruyor ve kotu videoyu orada durduruyor.
    YUMUSAK_KAPI_DENEMESI = 3
    # Son dogrulama/kapi kusuru — hata mesajina giriyor (bkz. dongu sonu).
    son_kusur = ""
    for deneme in range(1, 6):
        yumusak_kapilar_acik = deneme <= YUMUSAK_KAPI_DENEMESI
        # ⚠️ Uzun kipte zaman asimi GENIS. Gerekce
        # `UZUN_CIKARIM_ZAMAN_ASIMI`nda: ~7.000 tokenlik bir cevap Shorts'un
        # 180 saniyesine sigmiyor ve koşum 188,4 saniyede oluyordu.
        data = _json_completion(
            system,
            user,
            zaman_asimi=(
                CIKARIM_ZAMAN_ASIMI if bicim.dikey else UZUN_CIKARIM_ZAMAN_ASIMI
            ),
        )
        plan = ContentPlan(
            topic=str(data.get("topic", "")).strip(),
            visual_anchor=str(data.get("visual_anchor", "")).strip(),
            title=tiresiz_baslik(str(data.get("title", "")).strip()),
            # ⚠️ Temizlik DOGRULAMADAN once: `validate_content_plan` kelime
            # sayiyor ve tire kaldirinca "single-handedly" bir kelimeden ikiye
            # cikiyor. Sonradan temizlemek, dogrulanan metinle uretilen metnin
            # farkli olmasi demekti.
            script=tiresiz_anlatim(str(data.get("script", "")).strip()),
            scenes=[
                {
                    "narration": tiresiz_anlatim(str(scene.get("narration", "")).strip()),
                    "search_term": str(scene.get("search_term", "")).strip(),
                    # Menuden secilen dosya. Bos kalabilir: menusu olmayan
                    # konularda hat eskisi gibi aramayla calisiyor.
                    "kaynak_dosya": str(scene.get("source_file", "")).strip(),
                    # Sahnenin IKINCI karesi. Bos kalabilir ve bu bir kusur
                    # degil: menu yetmediginde o sahne birincil kareyi iki
                    # yuvada gosterir (bkz. `kare_yerlesimi`).
                    "kaynak_dosya_2": str(scene.get("source_file_2", "")).strip(),
                }
                for scene in data.get("scenes", [])
                if isinstance(scene, dict)
            ],
            description=tiresiz_baslik(str(data.get("description", "")).strip()),
            tags=[str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()],
            # ⚠️ ISTEGE BAGLI. Yoksa ya da tanimiyorsak bos kalir; dogrulama
            # bunu kusur saymaz. Gerekce `_ruh_halini_coz`da.
            ruh_hali=_ruh_halini_coz(data.get("mood")),
        )
        for scene in plan.scenes:
            scene["search_term"] = _ensure_visual_anchor(
                scene["search_term"], plan.visual_anchor
            )
        # ⚠️ CAPA ONARIMI EN BASTA: terim onarimindan ONCE calismali, cunku
        # terimler capaya gore yeniden turetiliyor. Sirasi ters olsaydi
        # tekillestirilen terimler hemen ardindan uzerine yazilirdi.
        if not bicim.dikey and konu and (
            eski_capa := capayi_konuya_genislet(plan, konu)
        ):
            print(
                f"ℹ️ çapa {eski_capa!r} → {plan.visual_anchor!r} genişletildi "
                "(dar çapa arşivi tüketiyor)",
                flush=True,
            )
        # ⚠️ ONARIM DOGRULAMADAN ONCE ve yalnizca uzun kipte. Gerekce
        # `arama_terimlerini_tekillestir`de: tek bir yer hakkinda 30 sahnede
        # benzer terim kacinilmaz, ama sahne gorselini ALINTIDAN aldigi icin
        # bu gorsel tekrarina yol acmiyor. Shorts'ta kapi aynen sert kaliyor.
        if bicim.kare_yuvasi == 1 and (
            onarilan := arama_terimlerini_tekillestir(plan)
        ):
            print(
                f"ℹ️ {onarilan} tekrarlayan arama terimi alıntılanan dosyadan "
                "ayırt edildi",
                flush=True,
            )
        try:
            validate_content_plan(
                plan,
                sahne_sayisi,
                bicim=bicim,
                konu=konu or "",
                sahne_tavani=sahne_tavani,
            )
        except ValueError as exc:
            son_kusur = str(exc)
            # ⚠️ HER DENEME yaziliyor, yalnizca sonuncusu degil. Olculdu
            # (2026-08-15, sekizinci Herculaneum koşumu): koşum 8,6 dakika
            # surdu ve geriye TEK satir bilgi birakti ("son kusur: 48 sahne").
            # Diger dort denemenin neye taktigi kayboldu, yani bir sonraki
            # adim tahmine kaliyordu. Uzun koşumlar pahali; korlugun bedeli
            # her seferinde yeni bir koşum.
            print(
                f"⚠️ deneme {deneme}/5 reddedildi: {exc} "
                f"({len(plan.scenes)} sahne, {len(plan.script.split())} kelime, "
                f"capa {plan.visual_anchor!r})",
                flush=True,
            )
            user += (
                "\nThe last JSON plan was invalid: "
                f"{exc}. Return a completely corrected plan that follows every constraint."
            )
            continue
        # ⚠️ HER IKI KIPTE de calisiyor — ama sebebi 2026-08-17'de degisti.
        # Eskiden yedek kipte capayi model sectigi icin menu istemde HIC yoktu
        # ve ancak bu kapinin geri bildirimiyle geliyordu. Artik capayi kod
        # seciyor ve menu bastan veriliyor (bkz. `_yedek_capa_sec`), yani kapi
        # cogu koşumda "menuyu tanistiran" degil "menuye uymayani yakalayan"
        # rolde. Kaldirilamaz: havuz tukendiginde dal hala menusuz kaliyor ve o
        # durumda tek savunma bu. Gerekce `alinti_kusuru` docstring'inde.
        if yumusak_kapilar_acik and (
            kusur := alinti_kusuru(
                plan, konu or "", sinir=envanter_sinir, bicim=bicim
            )
        ):
            son_kusur = f"alinti kapisi: {kusur}"
            print(f"⚠️ deneme {deneme}/5 reddedildi — {son_kusur}", flush=True)
            user += f"\nThe last plan did not match the archive: {kusur}"
            continue
        # ⚠️ TEMIZLIK, KAPI DEGIL — ve kapilardan SONRA calisiyor ki
        # reddedilecek bir plan icin bosuna menu cozulmesin. Bozuk ya da
        # tekrarlayan ikinci alintilar siliniyor; plan yasiyor.
        if silinen := ikincil_alintilari_temizle(
            plan, konu or "", sinir=envanter_sinir, bicim=bicim
        ):
            print(
                f"ℹ️ {silinen} ikinci alıntı temizlendi (uydurma ya da tekrar); "
                "o sahneler birincil kareyi iki yuvada gösterecek",
                flush=True,
            )
        # ⚠️ ACILIS ve KAPANIS kapilari HER IKI KIPTE de calisiyor.
        #
        # Ikisi de 2026-08-14'e kadar `if konu:` dalinin ICINDEYDI, yani
        # yalnizca huni kipinde. Zamanlayici kurulunca bu sessiz bir bosluk
        # oldu: kuyruk neredeyse her zaman bos, koşumlarin tamamina yakini
        # YEDEK kipte calisiyor (`konu=None`) ve o dal hic girilmiyordu.
        # Yani gunde 4-6 video ureten kipte tekrar kontrolu YOKTU — tam da
        # tekrarin birikecegi yerde.
        #
        # Ikisi de konudan BAGIMSIZ kalite sorunlari: ayni kalip ayni
        # videoyu uretiyor, ayni kapanis seri kimligi degil reklam kusagi
        # oluyor. Konu benzerligi atlanmaya devam ediyor — gerekcesi
        # docstring'de: konuyu model degil, olculmus talep verisi ve onu
        # onaylayan insan sectI.
        if yumusak_kapilar_acik and _kapanis_tekrari(plan.script, onceki_kapanislar):
            son_kusur = "kapanis kalibi onceki videoyla ayni"
            print(f"⚠️ deneme {deneme}/5 reddedildi — {son_kusur}", flush=True)
            user += (
                "\nThe closing line repeats the sentence pattern of an earlier video. "
                "End on a different kind of note: a different part of the archive, a "
                "different unanswered question, a different consequence."
            )
            continue
        # ⚠️ Baslik bicimi kapisi da HER IKI KIPTE calisiyor. Baslik, kanal
        # sayfasinda ve arama sonucunda gorunen tek sey; ust uste ayni kalip
        # orada "hepsi ayni video" izlenimi veriyor — ve bu izlenim tam da
        # "toplu uretilmis, tekrar eden icerik" olcutunun baktigi sey.
        if yumusak_kapilar_acik and _baslik_bicimi_tekrari(plan.title, onceki_basliklar):
            son_kusur = f"baslik bicimi tekrari: {plan.title!r}"
            print(f"⚠️ deneme {deneme}/5 reddedildi — {son_kusur}", flush=True)
            user += (
                "\nThe title repeats the shape of a recent one. Keep it a search query, "
                "but change the shape: a different question word, or a statement that "
                "names the surprising fact instead of asking about it."
            )
            continue
        if yumusak_kapilar_acik and _kanca_tekrari(plan.script, onceki_kancalar):
            son_kusur = "kanca kalibi onceki videoyla ayni"
            print(f"⚠️ deneme {deneme}/5 reddedildi — {son_kusur}", flush=True)
            user += (
                "\nThe opening line repeats the sentence pattern of an earlier video. "
                "Open on a different kind of detail: an object, a number, a place, or "
                "an unfinished action."
            )
            continue
        if konu:
            # ⚠️ CAPA tekrari huni kipine OZEL kaliyor: yedek kipte capayi
            # zaten model seciyor ve asagidaki dal onu `is_duplicate_visual_anchor`
            # ile denetliyor. Buraya tasimak ayni kontrolu iki kez yapardi.
            #
            # ⚠️ `capa_tekrari_serbest` ISE KAPI KAPALI ve bu bilincli:
            # kanitlanmis bir konuyu uzun formatta yeniden ele alirken AYNI
            # capa isteniyor — amac o. Kapi acik kalsaydi uc denemenin ucu de
            # reddedilirdi ve her deneme ~2.000 kelimelik bir cikarim koşumu
            # demek. Tekrar politikasi da ihlal edilmiyor: 40 saniyelik bir
            # Short ile 10 dakikalik bir belgesel ayri eserler ("each video
            # has a distinct storyline, focus, or concept").
            if (
                yumusak_kapilar_acik
                and not capa_tekrari_serbest
                and is_duplicate_visual_anchor(plan.visual_anchor, previous_anchors)
            ):
                son_kusur = f"capa daha once kullanilmis: {plan.visual_anchor!r}"
                print(f"⚠️ deneme {deneme}/5 reddedildi — {son_kusur}", flush=True)
                user += (
                    f"\nThe visual anchor {plan.visual_anchor!r} was already used on this "
                    "channel. Keep the same subject but anchor the video on a different "
                    "concrete thing belonging to it."
                )
                continue
            if kusur := _capa_arzi_kusuru(plan, bicim=bicim, sahne_sayisi=sahne_sayisi):
                son_kusur = kusur
                print(f"⚠️ deneme {deneme}/5 reddedildi — {son_kusur}", flush=True)
                user += (
                    f"\nThe visual anchor {plan.visual_anchor!r} has too few usable "
                    "archive images, so half the scenes would be filled with unrelated "
                    "modern photographs. Keep the subject but anchor the video on a "
                    "different concrete thing belonging to it — a place, a fortification, "
                    "an object or a named site rather than a person, if the person's "
                    "archive is thin."
                )
                continue
            return plan
        if (
            not is_duplicate_topic(plan.topic, previous)
            and not is_duplicate_topic(plan.title, previous)
            and not is_duplicate_visual_anchor(plan.visual_anchor, previous_anchors)
        ):
            return plan
        user += "\nThe last suggestion was too similar. Choose a completely different event and era."
    # ⚠️ SON KUSUR MESAJA GIRIYOR. Eski hali her zaman "konu yeterince farkli
    # degil" diyordu — konu DISARIDAN sabitlenmisken bu cumle olgusal olarak
    # yanlis ve teshisi yanlis yone gonderiyor. Olculdu (2026-08-15): ilk
    # Herculaneum koşumu 9,6 dakika yandi ve log yalnizca bu cumleyi verdi;
    # gercek sebep (kelime sayisi ve terim tekrari) ancak kapilar elle
    # izlenerek bulundu. Ayni sinif korluk `parse_cli_result`te de vardi.
    raise DistinctTopicUnavailableError(
        f"5 denemede gecerli plan uretilemedi; son kusur: {son_kusur or 'bilinmiyor'}"
        if konu
        else "could not generate a sufficiently distinct topic"
    )


def refine_search_terms(
    plan: ContentPlan, review: QualityReview, *, bicim: VideoBicimi = SHORTS_BICIMI
) -> ContentPlan:
    """Hakemin onerdigi arama terimlerini plana isler ve plani yeniden dogrular.

    ⚠️ `bicim` GECMEZSE UZUN KOŞUM BURADA COKUYOR. Olculdu (2026-08-15,
    ikinci Herculaneum koşumu): plan uretimi gecti, gorseller indi, kaynak
    incelemesi kusur bildirdi ve bu fonksiyon cagrildi — sonundaki
    `validate_content_plan` VARSAYILAN Shorts biciminde calisip 1.208
    kelimelik gecerli uzun senaryoyu "80-120 words" diye reddetti; koşum
    10,8 dakikanin sonunda istisnayla oldu.

    Kusur sinsi, cunku bu fonksiyona YALNIZCA kaynak kapisi kusur
    bildirdiginde ugraniyor: temiz gecen bir koşumda hic calismiyor.
    """
    if len(review.revised_search_terms) == len(plan.scenes):
        terms = review.revised_search_terms
    else:
        data = _json_completion(
            "Return JSON only with a search_terms array. Each term must be a concrete 3-7 word Wikimedia Commons query, chronological, period-correct, visually distinct, and repeat at least one visual_anchor word.",
            json.dumps(
                {
                    "topic": plan.topic,
                    "visual_anchor": plan.visual_anchor,
                    "script": plan.script,
                    "scenes": plan.scenes,
                    "problems": review.issues,
                },
                ensure_ascii=False,
            ),
        )
        terms = [str(term).strip() for term in data.get("search_terms", [])]
    if len(terms) == len(plan.scenes):
        for scene, term in zip(plan.scenes, terms):
            if len(term.split()) >= 2:
                term = _ensure_visual_anchor(term, plan.visual_anchor)
                scene["search_term"] = term
    validate_content_plan(plan, bicim=bicim)
    return plan


SHORTS_EN = 1080
SHORTS_BOY = 1920
"""Shorts karesi. Kaynak gorseller buna getirilmezse ekranin bir kismi siyah kalir."""

UZUN_EN = 1920
UZUN_BOY = 1080
"""Uzun format karesi (16:9).

⚠️ Yatay kadraj, arsiv arzina Shorts'tan DAHA IYI uyuyor ve bu bir tesaduf
degil: arsiv fotograflarinin cogu yatay. Dikey hedefte bir 16:9 fotograf
%68 kirpilirdi (bkz. `AZAMI_KIRPMA`) ve bulanik bant yoluna duserdi; yatay
hedefte ayni fotograf neredeyse hic kirpilmadan tam ekran doluyor.
"""


def kare_olcusu(bicim: "VideoBicimi") -> tuple[int, int]:
    """Bicimin piksel karesi. Tek yerden okunur ki oran ile boyut ayrisamasin."""
    return (SHORTS_EN, SHORTS_BOY) if bicim.dikey else (UZUN_EN, UZUN_BOY)


def en_boy_orani(bicim: "VideoBicimi") -> str:
    """MPT CLI'nin `--video-aspect` degeri."""
    return "9:16" if bicim.dikey else "16:9"


def kare_orani(bicim: "VideoBicimi | None" = None) -> float:
    """Bicimin sayisal en/boy orani — arsiv suzgeci ve siralamasi icin.

    ⚠️ `kare_olcusu`den TURETILIYOR, ayri bir sabit degil: ikisi ayrisirsa
    retrieval kendi render'indan farkli bir kare varsayar ve bu, bu dosyada
    zaten olculmus bir kusur sinifi (`AZAMI_KIRPMA` iki modulde ayni olmak
    ZORUNDA, bkz. `wikimedia_materials.AZAMI_KIRPMA`).
    """
    en, boy = kare_olcusu(bicim or SHORTS_BICIMI)
    return en / boy

# Merkezden kirpma bu orandan fazlasini atacaksa kirpmak yerine bulanik arka
# plan kullanilir. 0.35 olculerek secildi: 2:3 AI gorselleri %16 kirpiliyor
# (sorunsuz), 16:9 arsiv fotograflari %68 kirpilirdi ve konu kadraj disinda
# kalirdi — bir akveduktun yalnizca bir kemeri gorunurdu.
AZAMI_KIRPMA = 0.35


def kirpma_orani(en: int, boy: int, hedef_en: int = 0, hedef_boy: int = 0) -> float:
    """Kirp-doldur uygulanirsa kaynagin ne kadari atilir (0-1).

    Hedef verilmezse tam Shorts karesi (1080x1920) varsayilir. `dikeye_yapistir`
    yarim kare (1080x960) icin ayni hesabi istiyor — iki ayri kopya olsaydi
    esikler zamanla birbirinden kayardi.
    """
    hedef_oran = (hedef_en or SHORTS_EN) / (hedef_boy or SHORTS_BOY)
    oran = en / boy
    if oran > hedef_oran:
        kalan = (boy * hedef_oran) / en  # genislikten kirpilir
    else:
        kalan = (en / hedef_oran) / boy  # yukseklikten kirpilir
    return 1 - kalan


def bant_ister(kaynak: Path, *, hedef_en: int = 0, hedef_boy: int = 0) -> bool:
    """Gorsel tam ekrana kirpilamiyor mu — yani bulanik bant yoluna mi duser.

    `dikeye_yapistir` kararinin girdisi: yalnizca BANT ISTEYEN iki gorsel
    alt alta konur. Kirpilabilen gorsel tek basina tam ekran daha iyi
    duruyor, ikiye bolmek onu kucultmek olurdu.

    ⚠️ `AZAMI_KIRPMA` esigi DIKEY hedefe gore olculmustu ama yatayda da dogru
    isi yapiyor, cunku esik oranin kendisine degil KAYBEDILEN ALANA bakiyor:
    16:9 arsiv fotografi yatay hedefte ~%0 kirpiliyor (tam ekran), dikey
    portre ise yatayda bant yoluna dusuyor — tam tersi ama ayni kural.
    """
    with Image.open(kaynak) as ham:
        en, boy = ham.size
    return kirpma_orani(en, boy, hedef_en, hedef_boy) > AZAMI_KIRPMA


def dikeye_yapistir(ust: Path, alt: Path, hedef: Path) -> Path:
    """Iki yatay gorseli ALT ALTA koyup 1080x1920'yi bant birakmadan doldurur.

    ⚠️ NEDEN — kanal sahibinin karari (2026-08-14): "oyle fotograflarda alt
    alta iki tane koyalim ekrana." Sikayet bulanik bantli karelerin "cok
    kalitesiz" durmasiydi.

    Bu, 11 Agustos'taki DW-123 kararinin (bantli gercek fotograf, tam ekran
    AI'a tercih edilir) yerini ALMIYOR — onu daha iyi bir cozumle asiyor.
    Tek bir 16:9 fotograf tam kareye kirpilamaz (%60'tan fazlasi gider), ama
    IKISI yarim kareye (1080x960) yalnizca ~%37 kirpmayla sigiyor. Yani
    ekran doluyor, iki gercek fotograf birden gorunuyor ve bant kalmiyor.

    ⚠️ Bant yolu TAMAMEN kalkmadi: eslesecek ikinci yatay gorsel
    bulunamayan sahnede `dikeye_uydur` eskisi gibi bulanik bant kullaniyor.
    Arsiv arzini cokertmemek icin bilincli (olculdu, DW-123: eski oran
    filtresi 80 kullanilabilir gorselden yalnizca 24'unu geciriyordu).
    """
    yarim = SHORTS_BOY // 2
    tuval = Image.new("RGB", (SHORTS_EN, SHORTS_BOY))
    for sira, kaynak in enumerate((ust, alt)):
        with Image.open(kaynak) as ham:
            parca = ImageOps.fit(
                ham.convert("RGB"), (SHORTS_EN, yarim), method=Image.Resampling.LANCZOS
            )
        tuval.paste(parca, (0, sira * yarim))

    # ⚠️ Parlaklik tabani BURADA da uygulaniyor — `dikeye_uydur` ile ayni
    # gerekce: her sahne karesi bu yollardan BIRINDEN geciyor ve yalnizca
    # birine koymak digerini acik birakir.
    tuval, gama = gorsel_olcum.karanligi_ac(tuval)
    if gama is not None:
        print(f"karanlik kare acildi: {hedef.name} (gama {gama})", flush=True)

    hedef.parent.mkdir(parents=True, exist_ok=True)
    tuval.save(hedef, format="JPEG", quality=92)
    return hedef


def dikeye_uydur(kaynak: Path, hedef: Path) -> Path:
    """Gorseli 1080x1920'ye (Shorts karesi) getirir. `kareye_uydur`in sarmalayicisi."""
    return kareye_uydur(kaynak, hedef, en=SHORTS_EN, boy=SHORTS_BOY)


def kareye_uydur(
    kaynak: Path, hedef: Path, *, en: int = SHORTS_EN, boy: int = SHORTS_BOY
) -> Path:
    """Gorseli hedef kareye getirir — siyah bant birakmadan.

    ⚠️ Olculdu (2026-08-06, DW-93): uretilen videolarin ustunde ve altinda
    150'ser piksel siyah bant vardi, yani ekranin **%15,6'si** bostaydi
    (`cropdetect` → `crop=1080:1620:0:150`). Sebep `app/services/video.py`:
    kaynak oran hedeften farkliysa siyah bir `ColorClip` uzerine gorseli
    ortaliyor (letterbox). Telefonda amatorce gorunuyor ve dikey alanin altida
    birini harciyor.

    Cekirdek video servisi degistirilmedi: webui de onu kullaniyor ve
    davranisi degistirmek bu hattin disina tasar. Bunun yerine gorseller
    **kaynagында** dogru orana getiriliyor; servis bir daha bant ekleyemiyor
    cunku oran zaten tutuyor.

    Iki yol var, hangisi secildigi kirpma miktarina bagli:

    - **Kirp-doldur** (2:3 AI gorselleri): kenarlardan %16 gider, konu kalir.
    - **Bulanik arka plan** (16:9 arsiv fotograflari): kirpmak konuyu kadraj
      disinda birakirdi, o yuzden gorselin buyutulmus bulanik kopyasi arka
      plana konur ve net gorsel ortada tam olarak gorunur. Shorts'ta yaygin
      ve siyah banttan cok daha iyi duruyor.

    ⚠️ HEDEF KARE PARAMETRE, cunku uzun format 1920x1080 istiyor. Ayri bir
    yatay kopya yazilmadi bilerek: parlaklik tabani (`karanligi_ac`) bu
    govdenin icinde ve her sahne karesi buradan geciyor — catallansaydi
    yatay koldaki karanlik kareler sessizce acilmadan kalirdi. Ayni gerekce
    `dikeye_yapistir` docstring'inde de yaziyor.
    """
    from PIL import ImageFilter

    with Image.open(kaynak) as ham:
        gorsel = ham.convert("RGB")
        # ⚠️ Kaynagin olcusu, HEDEF olcuyle ayni adi tasiyamaz: `en`/`boy`
        # artik parametre ve uzerine yazmak, her gorseli kendi boyutuna
        # "uydurup" hedefi sessizce yok sayardi.
        kaynak_en, kaynak_boy = gorsel.size
        kirpma = kirpma_orani(kaynak_en, kaynak_boy, en, boy)

        if kirpma <= AZAMI_KIRPMA:
            sonuc = ImageOps.fit(gorsel, (en, boy), method=Image.Resampling.LANCZOS)
        else:
            arka = ImageOps.fit(
                gorsel, (en, boy), method=Image.Resampling.LANCZOS
            ).filter(ImageFilter.GaussianBlur(radius=40))
            on = ImageOps.contain(gorsel, (en, boy), method=Image.Resampling.LANCZOS)
            arka.paste(on, ((en - on.width) // 2, (boy - on.height) // 2))
            sonuc = arka

        # ⚠️ Parlaklik tabani BURADA, cunku her sahne karesi — AI uretimi de
        # arsiv fotografi da — bu fonksiyondan geciyor. Uretim tarafina
        # konsaydi arsivden gelen karanlik kare kacardi.
        sonuc, gama = gorsel_olcum.karanligi_ac(sonuc)
        if gama is not None:
            print(
                f"karanlik kare acildi: {hedef.name} (gama {gama})",
                flush=True,
            )

        hedef.parent.mkdir(parents=True, exist_ok=True)
        sonuc.save(hedef, format="JPEG", quality=92)
    return hedef


def dikeye_uydur_hepsi(dosyalar: list[Path], hedef_dizin: Path) -> list[Path]:
    """Sahne gorsellerinin tamamini Shorts karesine getirir; sira korunur."""
    return [
        dikeye_uydur(dosya, hedef_dizin / f"sahne-{sira:02d}.jpg")
        for sira, dosya in enumerate(dosyalar, 1)
    ]


def kare_yerlesimi(
    birincil: list[Path],
    ikincil: list[Path | None],
    hedef_dizin: Path,
    *,
    bicim: VideoBicimi = SHORTS_BICIMI,
) -> tuple[list[Path], int]:
    """Sahne basina `bicim.kare_yuvasi` kare uretir; kareler ve tam dolan sahne doner.

    ⚠️ UZUN FORMATTA SAHNE BASINA TEK KARE ve bu sayi kritik: `klip_suresi`
    sesi KARE sayisina boluyor. Uzun kolda da `[A, A]` uretilseydi kare
    sayisi ikiye katlanir, her karenin suresi yariya inerdi — yani sessizce
    baska bir video cikardi. Cikan kare sayisi her zaman
    `len(birincil) * bicim.kare_yuvasi`.

    ⚠️ Alt alta yapistirma (`dikeye_yapistir`) uzun formatta YOK, cunku
    sorunu ortadan kalkiyor: o yol 16:9 fotografi dikey kareye sigdirmak
    icin vardi. Yatay hedefte ayni fotograf zaten tam ekran doluyor.

    ⚠️ NEDEN — kanal sahibinin sesli notu (2026-08-14): "Fotograflar cok uzun
    sure kaliyor ekranda, yazi degistikce fotografla degismesi gerekiyor" ve
    "kesinlikle gorsel sayisi artirilmali". Olculdu: sahne basina 1 gorsel,
    suresi `ses ÷ sahne` (~5 sn), altyazi ise ~2 sn'de bir degisiyordu —
    gorsel altyazinin 2,5 kati yavasti.

    Uc yol var ve secim GORSELIN KENDISINE bagli:

    - iki gorsel de kirpilabiliyor  -> [A, B] ardisik, ikisi de tam ekran
    - ikisi de bant isterdi         -> [AB, AB] alt alta yapistirilmis
    - ikinci gorsel yok             -> [A, A] bugunku davranis, tek fark yok

    ⚠️ Karisik durum (biri kirpilir digeri bant ister) ardisik gosteriliyor:
    yapistirmak kirpilabilen gorseli gereksiz yere yariya indirirdi.
    """
    en, boy = kare_olcusu(bicim)
    if bicim.kare_yuvasi == 1:
        # Uzun kol: her sahne kendi karesini alir, ikinci gorsel hic istenmez.
        kareler = [
            kareye_uydur(
                birinci, hedef_dizin / f"sahne-{sira:02d}a.jpg", en=en, boy=boy
            )
            for sira, birinci in enumerate(birincil, 1)
        ]
        return kareler, 0

    kareler: list[Path] = []
    tam_dolan = 0
    for sira, birinci in enumerate(birincil, 1):
        ikinci = ikincil[sira - 1] if sira - 1 < len(ikincil) else None
        if ikinci is None:
            tek = dikeye_uydur(birinci, hedef_dizin / f"sahne-{sira:02d}a.jpg")
            kareler.extend([tek, tek])
            continue
        tam_dolan += 1
        if bant_ister(birinci) and bant_ister(ikinci):
            birlesik = dikeye_yapistir(
                birinci, ikinci, hedef_dizin / f"sahne-{sira:02d}-yapistirma.jpg"
            )
            kareler.extend([birlesik, birlesik])
        else:
            kareler.append(dikeye_uydur(birinci, hedef_dizin / f"sahne-{sira:02d}a.jpg"))
            kareler.append(dikeye_uydur(ikinci, hedef_dizin / f"sahne-{sira:02d}b.jpg"))
    return kareler, tam_dolan


def kaynak_ornegi(
    material_files: list[Path],
    bicim: VideoBicimi = SHORTS_BICIMI,
    zorunlu: list[int] | None = None,
) -> list[int]:
    """Kontak sayfasina girecek malzeme numaralari (1-tabanli).

    ⚠️ OLCULDU (2026-08-15, DOKUZUNCU Herculaneum koşumu, 46,2 dakika): 45
    gorsel 4 sutuna dizilince kontak sayfasi 1600x3600 piksel oluyor ve
    model BOS cevap donduruyor — kapi hicbir sey goremeden dusuyor.

    ⚠️ Cozum zaten depoda vardi ve buraya uygulanmamisti: `hakem_kareleri`
    ayni dersi render SONRASI hakem kapisinda ogrenmisti. Ayni fonksiyon
    aynen kullaniliyor, ikinci bir orneklem kurali yazilmiyor — iki kapinin
    ayri sekilde ornekleme yapmasi teshisi imkansiz hale getirirdi.

    Shorts hic orneklenmiyor (`hakem_kareleri` gerekcesi): olculerek
    kalibre edilmis bir kapinin gorus alanini daraltmak, uzun formatin
    bedelini Shorts'a odetmek olurdu.

    ⚠️ `zorunlu` ONARILAN sahneler icin: kapi bir sahneyi kusurlu bulup
    gorseli degistirildikten sonra sayfa YENIDEN uretiliyor. Duzgun orneklem
    o sahneyi disarida birakabilirdi, yani hat gorseli degistirip
    degisikligin ise yarayip yaramadigina hic bakmamis olurdu. Onarilanlar
    her zaman iceride.
    """
    ornek = hakem_kareleri(len(material_files), bicim)
    if not zorunlu:
        return ornek
    gecerli = {n for n in zorunlu if 1 <= n <= len(material_files)}
    return sorted(set(ornek) | gecerli)


def create_source_montage(
    material_files: list[Path],
    attempt: int,
    konu: str = "",
    *,
    secilen: list[int] | None = None,
    ek: str = "",
) -> Path:
    # ⚠️ `konu` isteğe bagli ama uretimde HER ZAMAN veriliyor (DW-119):
    # materyal klasoru gibi bu dosya adi da saat anahtarliydi ve ayni saatte
    # uretilen ikinci video birincinin kontak sayfasini eziyordu. Hakemin ne
    # gorup ne onayladigi geriye donuk incelenemiyordu.
    if not material_files:
        raise ValueError("source montage requires at least one image")
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    # ⚠️ Hucrenin uzerine yazilan sayi, hucrenin SIRASI degil GERCEK sahne
    # numarasi. Boylece orneklem yapilinca bile hakem gercek sahne
    # numarasini bildiriyor ve geri cevrim gerekmiyor —
    # `problem_scene_numbers` dogrudan `plan.scenes`e denk dusuyor.
    numaralar = secilen or list(range(1, len(material_files) + 1))
    columns = 4
    cell_width, cell_height = 400, 300
    rows = (len(numaralar) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_width, rows * cell_height), "black")
    for hucre, numara in enumerate(numaralar):
        path = material_files[numara - 1]
        with Image.open(path) as source:
            tile = ImageOps.fit(
                source.convert("RGB"),
                (cell_width, cell_height),
                method=Image.Resampling.LANCZOS,
            )
        draw = ImageDraw.Draw(tile)
        draw.rectangle((0, 0, 54, 34), fill="black")
        draw.text((12, 8), str(numara), fill="white")
        canvas.paste(tile, ((hucre % columns) * cell_width, (hucre // columns) * cell_height))
    ayirt_edici = f"-{konu_slug(konu)}" if konu else ""
    # ⚠️ `ek` OLMADAN ikincil denetimi birincil kontak sayfasini EZERDI. O
    # dosya adli kayit: 01 slotundaki kusurun ikincil gorsellerden geldigi,
    # tam da birincil sayfanin TEMIZ olmasi karsilastirilarak bulundu.
    montage = (
        REVIEW_DIR
        / f"source-{publication_slot_key()}{ayirt_edici}-attempt-{attempt}{ek}.jpg"
    )
    canvas.save(montage, format="JPEG", quality=90)
    return montage


FOTOGRAF_OLMAYAN_TURLER = frozenset({"map", "diagram", "document"})
"""Sahneyi degistirmeyi gerektiren kare turleri.

⚠️ `artwork` BILEREK DISARIDA. Gravur, tablo ve cizim bu kanalin
gorsel dilinin merkezinde: fotografin var olmadigi donemlerde tek
gercek arsiv kaynagi onlar. Onlari elemek konu havuzunun yarisini
kapatirdi.

⚠️ Olculdu (2026-08-14): Tunguska menusunun **%50'si** fotograf degil
(3 harita, 2 pul/kapak, 2 diyagram), Persepolis'in %29'u harita.
Uretilen Tunguska videosunda 18 karenin 3'u harita, 2'si pul, biri
kitap kapagi cikti — kanal sahibinin sikayeti birebir buydu.
"""

KONU_TURU_ISTISNASI = re.compile(
    r"\bmap\b|\bmaps\b|\bchart\b|\batlas\b|\bmanuscript\b|\bcodex\b|\bscroll\b"
    r"|\bdocument\b|\bletter\b|\bdiagram\b|\bblueprint\b|\bstamp\b",
    re.IGNORECASE,
)
"""Konunun KENDISI bir harita/belge oldugunda tur kurali uygulanmaz.

⚠️ Bu istisna olmadan kural kanalin KENDI YAYINLADIGI videoyu
oldururdu: "Piri Reis Map: Did It Show Antarctica?" (2026-08-14,
`wzXuZKVGuro`) bastan sona bir haritayi anlatiyor ve karelerinin
harita olmasi DOGRU. Ayni sey Rosetta Stone, Voynich Manuscript,
Antikythera mekanizmasinin semasi icin de gecerli.
"""


def belge_kareleri(kareler: list[dict[str, Any]], plan: ContentPlan, sahne_sayisi: int) -> list[int]:
    """Turu fotograf/artwork olmayan sahne numaralari — KOD karar verir.

    ⚠️ Karar burada, hakemde degil (DW-87). Hakeme "bu kare ne" diye OLGU
    soruluyor; "harita kabul edilebilir mi" sorusu ona birakilirsa konudan
    konuya keyfi cevap verir.

    Konunun kendisi harita/belge ise (Piri Reis Map, Rosetta Stone) kural
    uygulanmiyor — bkz. `KONU_TURU_ISTISNASI`.
    """
    if KONU_TURU_ISTISNASI.search(f"{plan.topic} {plan.visual_anchor} {plan.title}"):
        return []
    numaralar = set()
    for kare in kareler:
        # ⚠️ Suzgec BURADA da var, cagiran tarafta oldugu halde: fonksiyon
        # dogrudan cagrildiginda (test, ileride baska bir kapi) bozuk bir
        # girdi onu patlatmamali. Kapinin isi yanlisi yakalamak, bicimi
        # bozuk veriyle koşumu oldurmek degil.
        if not isinstance(kare, dict):
            continue
        tur = str(kare.get("kind", "")).strip().lower()
        if tur not in FOTOGRAF_OLMAYAN_TURLER:
            continue
        try:
            numara = int(kare.get("n", 0))
        except (TypeError, ValueError):
            continue
        if 1 <= numara <= sahne_sayisi:
            numaralar.add(numara)
    return sorted(numaralar)


def review_source_materials(
    plan: ContentPlan,
    montage: Path,
    *,
    secilen: list[int] | None = None,
    bicim: VideoBicimi = SHORTS_BICIMI,
) -> QualityReview:
    # ⚠️ Isteme YALNIZCA sayfada gorunen sahneler konuyor. 45 sahnenin
    # tamamini verip 12 kare gostermek, modelden goremedigi 33 kare hakkinda
    # hukum istemek olurdu; kendi numaralandirmasi da kayardi.
    #
    # Numaralar KORUNUYOR (`n` alani): hucrenin uzerindeki sayi gercek sahne
    # numarasi, yani hakemin bildirdigi numara dogrudan `plan.scenes`e denk
    # dusuyor ve `belge_kareleri` bir cevrim yapmadan calisiyor.
    gorunen = [
        {"n": numara, **plan.scenes[numara - 1]}
        for numara in (secilen or range(1, len(plan.scenes) + 1))
        if 1 <= numara <= len(plan.scenes)
    ]
    prompt = {
        "topic": plan.topic,
        "visual_anchor": plan.visual_anchor,
        "scenes": gorunen,
        "instructions": (
            "Review this numbered source-image contact sheet before video rendering. "
            # ⚠️ Numaralar ARDISIK OLMAYABILIR: uzun formatta sayfa bir
            # ORNEKLEM (bkz. `kaynak_ornegi`) ve her hucrenin uzerindeki sayi
            # gercek sahne numarasi. Bu cumle olmazsa model numaralari 1'den
            # yeniden sayar ve bildirdigi her numara yanlis sahneyi gosterir.
            "The number printed on each image is its scene number, and the sheet may show "
            "a sample of the scenes rather than all of them, so the numbers can skip. "
            "Always report the number printed on the image, never its position on the sheet. "
            "Each numbered image must directly match the corresponding scene, visual anchor, and historical period. "
            "Historically grounded AI illustrations are acceptable; do not reject an image merely because it is an illustration, but reject misleading or historically inconsistent details. "
            "Reject generic modern people, vehicles, factories, schools, unrelated maps or plans, single-word coincidences, and misleading period substitutions. "
            # ⚠️ Iki soru 2026-08-10'da EKLENDI (DW-117). Ikisi de o gecenin
            # kusurlarini hakemin KACIRMASINDAN geliyor:
            #
            #   * Scanagatta'nin 2. karesinde kadraji kaplayan kazili levha
            #     ("THERESIANISCHES MILITÄRAKADEMIE...") vardi; hakem gormedi
            #     ve videoyu GECIRDI.
            #   * Hardham videosunda ekranda baska adamlarin adli portreleri
            #     vardi ("Temp. 2nd-Lieut. H. KELLY, V.C."); hakem videoyu
            #     dusurdu ama "modern goruntu" diyerek — yanlis ozneyi hic
            #     fark etmedi. Yani yakalamasi SANS eseriydi.
            #
            # Sorular ayri ayri soruluyor cunku "gorsel konuya uyuyor mu"
            # sorusu ikisini de kapsamiyor: yanlis kisinin portresi konuya
            # gayet uyuyor gorunur.
            "Read the frames, do not only glance at them. For each image answer two "
            "specific questions and report any failure in issues and problem_scene_numbers. "
            "First: is there readable lettering anywhere inside the picture — on a sign, "
            "plaque, carved stone, book, paper, caption strip or nameplate? If yes, quote "
            "the words you can read. Second: when the topic is a named person, is the human "
            "shown actually that person, or is it somebody else who merely shares the same "
            "medal, uniform, institution or era? A portrait captioned with a different "
            "person's name is always a problem scene. "
            "Return JSON with visual_alignment_score (0-100), issues (array), revised_search_terms, and problem_scene_numbers (1-based scene numbers that need replacement; empty only when no scene is problematic). "
            # ⚠️ Buraya bir gecme esigi YAZILMAZ — bkz. `yayina_uygun`. Esik
            # anilinca model olcmeyi birakip esigin bir tik altina oy yaziyor.
            "visual_alignment_score is a measurement of this contact sheet, not a verdict: 0 means no image matches its scene, 50 means about half of the images match, 100 means every image matches its scene cleanly. Score what you actually see. "
            "For every scene number in problem_scene_numbers, add one concrete anchor-specific replacement query to revised_search_terms, in the same order, and one concrete issue describing what is wrong."
            # ⚠️ TUR SORULUYOR, KARAR SORULMUYOR (DW-87). Hakem "bu kare ne"
            # diye olgu bildiriyor; harita/belge kabul edilebilir mi sorusuna
            # KOD karar veriyor (`belge_kareleri`). Modele "harita kotu mu"
            # diye sorulsaydi konuya gore keyfi cevap verirdi.
            " Additionally return a `frames` array with one object per scene: "
            '{"n": <scene number>, "kind": one of "photo", "map", "diagram", '
            '"artwork", "document" — what the image actually IS, not what it '
            "depicts. A photograph of a museum display case is a photo; a "
            "scanned page, book cover, postage stamp or printed label is a "
            'document; a drawn plan or cross-section is a diagram}.'
        ),
    }
    data = _vision_json(prompt, montage, bicim=bicim)
    gorsel_skor = int(data.get("visual_alignment_score", 0))
    kareler = data.get("frames")
    kareler = [k for k in kareler if isinstance(k, dict)] if isinstance(kareler, list) else []
    sorunlu = [
        int(number)
        for number in data.get("problem_scene_numbers", [])
        if str(number).isdigit() and 1 <= int(number) <= len(plan.scenes)
    ]
    # Hakemin isaretlemedigi ama TURU foto olmayan sahneler de sorunlu
    # sayiliyor; sirasi korunuyor ki asagidaki terim eslemesi bozulmasin.
    for numara in belge_kareleri(kareler, plan, len(plan.scenes)):
        if numara not in sorunlu:
            sorunlu.append(numara)
    return QualityReview(
        # ⚠️ `yayina_uygun` DEGIL — o, render SONRASI video kapisinin esigini
        # kullanir. Kaynak on-kapisi kendi (daha gevsek) sabitiyle karar
        # verir; gerekcesi sabitin tanimindadir. Cagiran kod da bu alani
        # degil skoru dogrudan karsilastirir, alan bilgi amaclidir.
        publishable=gorsel_skor >= MIN_SOURCE_VISUAL_SCORE,
        visual_alignment_score=gorsel_skor,
        subtitle_readability_score=100,
        issues=[str(issue) for issue in data.get("issues", [])],
        revised_search_terms=[str(term) for term in data.get("revised_search_terms", [])],
        problem_scene_numbers=sorunlu,
        kareler=kareler,
    )


def ikincil_gorselleri_denetle(
    plan: ContentPlan,
    ikincil: list[Path | None],
    attempt: int,
    *,
    bicim: VideoBicimi = SHORTS_BICIMI,
) -> list[int]:
    """Ikincil gorselleri render ONCESI denetler; DUSURULECEK sahne numaralari doner.

    ⚠️ NEDEN VAR — olculdu (2026-08-17, 01 slotu, IKI koşumun IKISINDE de).
    Kaynak kapisi (`review_source_materials`) yalnizca BIRINCIL gorselleri
    goruyordu; ikincil gorsel kapidan SONRA iniyor (bkz. `run_cycle`) ve
    hicbir denetimden gecmeden videonun yarisini dolduruyordu. Kapi
    calisiyordu, ona o kareler HIC GOSTERILMIYORDU:

        Palmyra    kaynak sayfasi 6/6 TEMIZ, alti agir kusurun ALTISI da
                   ikincil alan sahnelere dustu (3 ve 5). `scene-05b`
                   askeri hava ussunde bayrakli cocuklar (20. yy),
                   `scene-04b` deveye binmis modern turist.
        Gobekli    tek agir kusur "kare 12" = 6. sahne; `scene-06b` bir
                   PowerPoint slaydi ("Legacy of Strong Female Symbols in
                   Anatolia", MO 9500 - MS 110).

    ⚠️ Kok neden `ikincil_gorseller`in esleme yedegi: aday bulunamayinca
    `_kategori_adaylari(...)[0]` aliniyor, yani kategori havuzunun ILK
    dosyasi — alaka kontrolu YOK. Oradaki varsayim ("kategori uyeligi ozneyi
    garanti eder") yalnizca YER icin dogru: Commons'in Palmyra kategorisi
    Palmyra'nin modern turist fotograflarini da icerir. Ozne dogru, ANLATIM
    ve DONEM yanlis.

    ⚠️ DUSURME, REDDETME DEGIL. Ikincil gorsel bir iyilestirme: dusunce
    `kare_yerlesimi` o sahneyi `[A, A]`ya cevirir, yani kapidan GECMIS
    birincil kareye. Bozuk ikincil yuzunden butun plani copa atmak, iyi bes
    sahneyi de yakardi.

    ⚠️ Ag/cikarim hatasi uretimi DURDURMAZ: bos liste doner, hat bugunku
    davranisina (denetimsiz ikincil) duser. Kapinin kendisi bir
    IYILESTIRME; onu on kosula cevirmek tek bir 429'un koşumu oldurmesi
    demek olurdu (bkz. `arsiv_envanteri` ayni gerekce).

    ⚠️ KAPI, YAZILDIKTAN SONRA KAYITLI DOSYALARA KOSULDU (render yok, tek
    gorü cagrisi). Ayrim yapiyor, toptan reddetmiyor:

        Palmyra  ikincil alan sahneler 3,4,5 -> UCU DE dusuruldu. Uclu de
                 gercekten bozuktu: 03b/04b ayni modern turist (yesil polo,
                 deve), 05b hava ussu. Render SONRASI hakem de 3 ve 5'i
                 agir kusurlu saymisti — yani ortusuyor.
        Gobekli  ikincil alan sahneler 2,3,4,5,6 -> YALNIZCA 6 dusuruldu
                 (PowerPoint slaydi); dordu korundu.

    Bedel 4-10 sn ve TEK cagri; karsiliginda yanan sey tam bir render +
    indirme + hakem cagrisi. `kare_yerlesimi` ritmi ise kotu ikincil zaten
    ritim degil kusur uretiyordu.
    """
    # ⚠️ Numaralar SAHNE numarasi: `create_source_montage` hucreyi
    # `material_files[numara - 1]` diye okuyor. Sikistirilmis bir liste
    # ([03b, 04b, 05b]) yanlis hucreyi gosterirdi; tam boy liste veriliyor ve
    # None'lar zaten `secilen` disinda kaldigi icin hic indekslenmiyor.
    secilen = [numara for numara, yol in enumerate(ikincil, 1) if yol is not None]
    if not secilen:
        return []
    try:
        montaj = create_source_montage(
            cast(list[Path], ikincil), attempt, plan.topic, secilen=secilen, ek="-ikincil"
        )
        inceleme = review_source_materials(plan, montaj, secilen=secilen, bicim=bicim)
    except Exception as hata:  # noqa: BLE001 - kapi bir iyilestirme, on kosul degil
        print(f"⚠️ ikincil gorsel denetimi atlandi: {hata}", flush=True)
        return []
    # ⚠️ TOPLAM SKORA BAKILMIYOR, sahne sahne bakiliyor. Dusuk bir sayfa
    # skoru iyi ikincilleri de silerdi; buradaki eylem "yeniden ara" degil
    # "dusur", yani esik yanlis kaldirac.
    uygun = set(secilen)
    return [numara for numara in inceleme.problem_scene_numbers if numara in uygun]


GORSEL_DIL = (
    "Render this as a real photograph, not as artwork: "
    "(a) if the subject survives today — a standing monument, a ruin, a landscape, a museum "
    "object — photograph it as it exists now, in true-to-life colour, with the real colours of "
    "its stone, metal, wood or earth; "
    "(b) if the scene shows people, work or an event from the past, photograph a museum-quality "
    "living-history reconstruction: real people in accurate costume, real materials, shot on "
    "location today; "
    "(c) only use a monochrome or sepia archival look when the scene is genuinely about the "
    "early photographic era or an aged document. "
    "Never a painting, never an illustration, never a digital render, never a concept-art or "
    "matte-painting look."
)
"""Sahne basina gorsel dil — tek bir estetige sabitlenmez.


⚠️ Olculdu (2026-08-06, DW-97): prompt "realistic archival-documentary
aesthetic" diyordu ve **her sahne sepya** cikiyordu. Uretilen videolarin
gorsellerinin %60'i AI (Commons her sahneyi besleyemiyor), dolayisiyla bu tek
cumle butun kanalin gorsel kimligini tek bir soluk tona kilitliyordu:
Chartres, Colosseum, Karnak ve Viking videolari yan yana konunca ayirt
edilemiyordu.

"Archival" kelimesi modele "eski fotograf" dedirtiyor, eski fotograf da
tanim geregi sepya/monokrom. Oysa sahnelerin cogu bugun **ayakta duran** bir
yapiyi anlatiyor ve onun gercek rengi var.

Cozum tek estetigi yasaklamak degil, secimi sahnenin konusuna baglamak:
ayakta duran sey → gercek renkli fotograf, gecmisteki olay → canlandirma
fotografi, gercekten arsivlik olan → sepya.

⚠️ Ikinci olcum (2026-08-09): (b) sikki once "richly coloured historical
painting or a detailed period illustration" diyordu ve kullanicinin
"sanki cartoon gibi" tarifi tam olarak buydu — model kusuru degil, promptun
KENDI istegi. Gecmisteki sahneler Commons'ta nadiren fotografla karsilandigi
icin AI dolgusunun cogu bu sikka dusuyor, yani cizim kanalin varsayilan
gorunumu haline geliyordu. Sikk, muze kalitesinde bir CANLANDIRMA fotografina
cevrildi; "no invented event presented as a surviving photograph" guvencesi
prompt govdesinde yerinde birakildi, cunku canlandirma bugun cekilmis bir
fotograf gibi durmali, hayatta kalmis bir arsiv belgesi gibi degil.

Isik artik burada tarif EDILMIYOR — o `ISIK_DILI`nin isi. Bu cumlenin
"vary lighting between scenes" istegi sahneler birbirinden habersiz
uretildigi icin hicbir zaman islememisti.
"""

KARE_DILI = (
    "a wide establishing shot with the subject small in a large landscape, horizon visible",
    "a tight close-up on surface texture and craftsmanship, filling the frame, shallow depth",
    "a human figure inside the frame for scale, seen from behind or in profile, mid-distance",
    "a low angle from ground level looking steeply up, sky behind the subject",
    "an elevated or overhead view looking down, showing layout and pattern",
    "a two-layer composition with something in the near foreground partly overlapping the subject",
    "a view from inside or through an opening — a doorway, an arch, a gap — framing the subject",
    "an off-centre composition with the subject at one edge and open space beside it",
    "a detail of a single object held, carried or worked on by hands",
    "a receding perspective down a street, corridor or row, leading far into the distance",
)
"""Sahne basina kadraj — sahne numarasina gore donusumlu.

⚠️ Olculdu (2026-08-08, Nazca kosumu): 8 sahnenin ikisi %84 benzer cikti
(algisal parmak izi) ve ton yayilimi 0,121'de kaldi — DW-97'nin ulastigi
0,17'nin altinda.

Sebep promptun KENDI ICINDEKI celiskiydi: `GORSEL_DIL` "ardisik iki kare
birbirine benzememeli" diyor, ama hemen ardindan HER sahneye ayni cumle
gidiyordu — "One clear focal subject, strong vertical composition". Modelden
cesitlilik isteyip tek bir kompozisyon tarif etmek.

Cozum "cesitli ol" demeyi tekrarlamak degil, her sahneye BASKA bir kadraj
vermek. Liste bir kurgucunun cekim listesi gibi: genel plan, doku detayi,
olcek icin insan figuru, alt aci, tepeden gorunum, yan isik, cerceve icinden.

Donusumlu secildigi icin ek maliyet yok. Liste 10 uzunlukta ve sahne sayisi
6-10; ortak bolen olmadigi icin ayni sahne numarasi her videoda ayni kadraji
almiyor.

⚠️ Maddeler yalnizca KADRAJ tarif eder, isik DEGIL. Isik `ISIK_DILI`nin isi.
Iki liste ayni cumlede isiktan bahsederse birbiriyle celisir — bu modulun
zaten bir kez dustugu tuzak (bkz. yukarisi). Ilk surumde 6. madde "golden
hour ... warm side light", 10. madde "overcast ... cool light" diyordu;
`ISIK_DILI` eklenirken ikisi de kadraj tarifine cevrildi.
"""

ISIK_DILI = (
    "cold overcast daylight just after rain, wet surfaces, desaturated blue-grey tones",
    "hard midday sun from overhead, deep black shadows and bleached bright highlights",
    "golden hour side light with long warm shadows",
    "blue hour just after sunset, deep indigo sky, cool shadows",
    "flat even light under a bright white overcast sky, neutral true colours",
    "green filtered light under vegetation or through a canopy",
    "misty dawn, pale silver light, low contrast, cool haze in the distance",
    "clear high-altitude daylight, deep blue sky, crisp shadows, saturated colour",
    "interior light from a single opening, a bright pool of light in a darker space",
    "storm light, dark grey-violet sky with one bright shaft breaking through",
    "warm firelight or torchlight against the deep blue of open shade",
)
"""Sahne basina isik ve hava — kadrajdan BAGIMSIZ ikinci bir donusum.

⚠️ Olculdu (2026-08-09, Mohenjo-Daro kosumu): 7 karenin **hepsi** 25°-47° ton
araliginda cikti, dairesel ton yayilimi 0,007 (0 = tek renk). Video tek renkli
gorunuyordu. Kadraj cesitliligi (DW-107) yapisal tekrari cozdu ama palet
sorununa dokunmadi: ayni yeri farkli acilardan cekmek, hepsi ayni kehribar
tonundaysa yine tek bir goruntu hissi veriyor.

Sebep iki katmanli. Konu zaten tek renkli (kerpic sehir), ve model her
gorsele varsayilan olarak sicak bir renk katmani ekliyor. `GORSEL_DIL`
"vary lighting, time of day, weather" diyordu ama bu sahne ICINDE bir istek;
sahneler birbirinden habersiz uretildigi icin her biri ayni "sicak tarih
belgeseli" ortalamasina dusuyordu.

Cozum kadrajdaki ile ayni: modelden cesitlilik istemek yerine her sahneye
BASKA bir isigi acikca vermek. Olculdu (ayni 5 sahne, yalnizca prompt
degisti): ton yayilimi 0,002 → 0,433, ton araligi 25°-34° → 31°-202°.

Liste 11 (asal) uzunlukta: hem sahne sayisiyla (6-10) hem `KARE_DILI` ile
(10) ortak boleni yok, boylece kadraj-isik ciftleri videodan videoya kayiyor.
"""


def isik_dili(sahne_no: int, tohum: int = 0) -> str:
    """`sahne_no` icin isik tarifi (1'den baslar).

    `tohum` videoya ozgu bir kaydirma — konudan turetiliyor. Kaydirma olmasa
    her videonun 1. sahnesi ayni isigi alirdi ve kanal genelinde her video
    ayni yagmurlu gri kareyle acilirdi.
    """
    return ISIK_DILI[(sahne_no - 1 + tohum) % len(ISIK_DILI)]


def isik_tohumu(konu: str) -> int:
    """Konudan kararli bir kaydirma uretir.

    ⚠️ `hash()` KULLANILMIYOR: Python surec basina rastgele tohumluyor, ayni
    konu farkli kosumlarda farkli isik alirdi ve bir kosumu yeniden uretmek
    imkansiz olurdu.
    """
    return zlib.crc32(konu.strip().lower().encode("utf-8")) % len(ISIK_DILI)


ACILIS_KARELERI = (
    "a close three-quarter view of the main subject filling most of the frame, "
    "sharp and immediately readable at phone size",
    "a tight shot on a single person's face and shoulders, eyes visible, "
    "the setting soft behind them",
    "a low camera close behind a person's shoulder as they face the subject, "
    "the subject large in front of them",
    "a hands-and-object close-up at the moment of doing something, "
    "the object large and the action unmistakable",
    "a doorway or gap in the near foreground with the subject large and lit "
    "just beyond it, the viewer placed inside the scene",
)
"""1. sahneye ozel kadrajlar (DW-121).

⚠️ Olculdu (2026-08-10, Chaco Canyon'un ilk 11 saati): 374 goruntuleme,
trafigin %97,3'u Shorts akisi — YouTube videoyu dagitiyor. Ama izleyicilerin
%73'u IZLEMEDEN geciyor, yalnizca %27'si kaliyor. Kalanlar iyi izliyor: 33
saniyelik videoda ortalama 0:20, yani %61. Govde tutuyor, ACILIS tutmuyor.

Sebep kodda: `kare_dili` listeyi sahne numarasina gore donduruyordu ve
`KARE_DILI[0]` "a wide establishing shot with the subject small in a large
landscape". Yani HER videonun 1. sahnesi, tanim geregi, oznenin minicik
oldugu genis bir plan. Canyon'un ilk 3 saniyesi tam boyle: mavi saat, sonuk,
figur kadrajin kucuk bir noktasi ve neredeyse hic hareket yok. Telefonda,
akista, bakilacak bir sey yok.

1. sahnenin isi digerlerinden FARKLI: merak boslugu acmak. Bu yuzden kadraj
listesinin ilk elemanini miras almiyor, kendi kumesi var — hepsi yakin ve
telefonda okunakli.

Kume 5 uzunlukta ve konuya gore tohumlaniyor (`isik_tohumu` deseni), yoksa
kanalin butun videolari ayni kareyle acilir ve tekduzelik bu kez acilista
olusur.
"""


def acilis_karesi(konu: str) -> str:
    """1. sahnenin kadraji — konuya gore kararli sekilde secilir."""
    tohum = zlib.crc32(konu.strip().lower().encode("utf-8")) % len(ACILIS_KARELERI)
    return ACILIS_KARELERI[tohum]


def kare_dili(sahne_no: int, konu: str = "") -> str:
    """`sahne_no` icin kadraj tarifi (1'den baslar).

    ⚠️ 1. sahne AYRI (DW-121) — gerekce `ACILIS_KARELERI` docstring'inde.
    `konu` verilmezse eski davranis suruyor; testler ve eski cagrilar
    bozulmasin diye isteğe bagli birakildi.
    """
    if sahne_no == 1 and konu:
        return acilis_karesi(konu)
    return KARE_DILI[(sahne_no - 1) % len(KARE_DILI)]


SES_ADI = "en-US-BrianMultilingualNeural-Male"
SES_HIZI = 1.08
"""Anlatim sesi ve hizi — `anlatim_suresi` ile CLI ayni degeri kullanmali.

Ikisi ayrisirsa olculen sure gercek sesin suresi olmaz ve klip hesabi bozulur.
"""

VARSAYILAN_KLIP_SURESI = 5
"""Ses HIC tahmin edilemediginde kullanilan sure — eski sabit davranis.

⚠️ Bu sabit uzun formatta TEK BASINA yeterli degil ve sessizce bozuyor:
45 kare × 5 sn = 225 sn gorsel, ses ise 775 sn. `itertools.cycle` acigi
gorselleri 3,4 KEZ tekrarlayarak kapatir; hata firlatilmaz, log temiz
gorunur, video sacmalar. Bu yuzden `klip_suresi` once senaryodan tahmin
ediyor ve buraya ancak senaryo da yoksa dusuyor.
"""

KELIME_HIZI = 170
"""Anlatim hizi, kelime/dakika — `SES_ADI` ve `SES_HIZI` ile OLCULDU.

Uc ayri koşumda ayni deger cikti (bkz. `:760`). Ses olcumu agdan dondugu
icin basarisiz olabilir; kelime sayisi olamaz.
"""

RENDER_ZAMAN_ASIMI = 1800
"""Render alt sureci icin ust sinir, saniye — SHORTS olcusu.

⚠️ Bu sayinin Shorts'a gore oldugunu soyleyen bir yorum YOKTU; olculdu
(2026-08-15, `logs/2026-08-15-15-attempt-1.log`): 33,4 saniyelik bir Short
115 saniyede render ediliyor, yani 1800 sn 15 kat pay demek. Kimse bunun
uzun formata bakmadigini yazmamis cunku hic bakilmamis.
"""

UZUN_RENDER_ZAMAN_ASIMI = 5400
"""Uzun formatta render siniri.

Ayni koşumdan cikan olcum: render GERCEK ZAMANIN 3,4 KATI suruyor
(115 sn / 33,4 sn). Uc gecis var ve her biri yeniden kodluyor —
`preprocess_video` her kareyi ayri mp4 yaziyor, `combine_videos` her klibi
`temp-clip-N.mp4` olarak birlestiriyor, `generate_video` altyaziyla final'i
uretiyor.

Uzun formatta ayni butceye giren yuk:
    ses      423-775 sn  (`UZUN_BICIMI.kelime_araligi`, 170 kelime/dk)
    kodlama  3,4 x 775 ≈ 2.635 sn
    TTS      ayni surecin ICINDE, en kotu 3 x 660 = 1.980 sn

⚠️ Yani bugunku TTS duzeltmesi (30 sn -> kelime x 0,3) tek basina eski
1800'u tasiriyordu. Iki sabit birbirine bagli ve ayri ayri degistirilemez.

⚠️ Bu sayi `KILIT_BAYATLAMA` ile BIRLIKTE dusunulmeli: zaman asimini
yukseltip kilidi 4 saatte birakmak, iki koşumun ayni `state.json` uzerinde
paralel calismasi demekti.
"""


def ffmpeg_is_parcaciklari() -> int:
    """FFmpeg'e verilecek is parcacigi sayisi.

    MPT varsayilani 2 ve hat bunu hic gecmiyordu. Bir cekirdek bilerek
    birakiliyor: koşum zamanlayiciyla arka planda calisiyor.
    """
    return max((os.cpu_count() or 2) - 1, 2)


def render_zaman_asimi(bicim: "VideoBicimi | None" = None) -> int:
    """Bicime gore render siniri.

    ⚠️ Varsayilan `None`: bu fonksiyon `SHORTS_BICIMI`den once cagrilabilir
    ve varsayilan degerler `def` aninda hesaplaniyor.
    """
    if bicim is None or bicim.dikey:
        return RENDER_ZAMAN_ASIMI
    return UZUN_RENDER_ZAMAN_ASIMI

KLIP_PAYI = 1.02
"""Klip suresine eklenen kucuk pay.

Neden 1,02: `n × klip >= ses` olmali (yoksa MPT acigi kapatmak icin bastan bir
klibi TEKRAR ediyor) ama ayni anda `(n-1) × klip < ses` olmali (yoksa dongu
sure dolunca erken kirilir ve SON SAHNE videoya hic girmez). Pay `p` icin ikinci
kosul `p·(n-1)/n < 1`, yani `n < p/(p-1)`; %2 payda `n < 51`.

⚠️ Buradaki `n` KLIP sayisi, sahne sayisi degil — 2026-08-14'te ikisi
ayristi. Sahne basina iki kare var (`KARE_YUVASI`), yani `n` artik 12-20
(6-10 sahne × 2). Sinir hala fazlasiyla uzak, ama gerekce "sahne sayisi
6-10" diye yazili kalsaydi biri sahne sayisini artirmaya bakip guvende
sanirdi; asil kisit kare sayisi.

MPT'nin ses suresine ekledigi 0,10 sn emniyet payi da kapsanir
(`0,02 × ses >= 0,10` → ses >= 5 sn; bizim videolar ~36 sn).
"""


def anlatim_suresi(script: str) -> float:
    """Anlatimin GERCEK suresi — tahmin degil, olcum.

    ⚠️ Tahmin denendi ve birakildi. Olculdu (2026-08-09): ayni ses ve hizda
    kelime/saniye 2,05 ile 2,79 arasinda degisiyor — tarih ve sayi yogun metin
    en yavasi ("1900 BCE" seslendirilirken uc kelimeye aciliyor) ve bu kanalin
    metinleri tam olarak oyle. %30'luk bir hata payi, klip hesabini anlamsiz
    kilardi.

    Olcum ucuz ve tekrarlanabilir: edge-tts yerel, ucretsiz ve deterministik.
    Dogrulandi (2026-08-09): Mohenjo-Daro metni burada 35,88 sn olculdu, gercek
    kosumun sesi de 35,88 sn'ydi. CLI ayni metni yeniden seslendirecek; ayni
    ses + ayni hiz + ayni metin ayni sureyi veriyor.

    Olcum basarisiz olursa (ag yok, servis dustu) 0 doner ve cagiran taraf
    varsayilan klip suresine geri duser — ses olculemedi diye video uretmemek
    yanlis olurdu.
    """
    import asyncio
    import tempfile

    import edge_tts
    from moviepy.audio.io.AudioFileClip import AudioFileClip

    from app.services import voice as voice_service

    async def _seslendir(hedef: Path) -> None:
        iletisim = edge_tts.Communicate(
            text=script,
            # ⚠️ Ses adi ve hiz MPT'nin KENDI donusturucusundan geciyor. Elle
            # "+8%" yazmak, CLI bir gun baska bicim kullanirsa olcumu sessizce
            # yanlis yapardi.
            voice=voice_service.parse_voice_name(SES_ADI),
            rate=voice_service.convert_rate_to_percent(SES_HIZI),
        )
        await iletisim.save(str(hedef))

    yol: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as gecici:
            yol = Path(gecici.name)
        asyncio.run(_seslendir(yol))
        klip = AudioFileClip(str(yol))
        try:
            return float(klip.duration)
        finally:
            klip.close()
    except Exception as hata:  # noqa: BLE001 — olcum uretimi durduramaz
        print(f"anlatim suresi olculemedi, varsayilan klip suresi: {hata}", flush=True)
        return 0.0
    finally:
        if yol is not None:
            yol.unlink(missing_ok=True)


def klip_suresi(ses_saniye: float, sahne_sayisi: int, senaryo: str = "") -> float:
    """Her sahnenin ekranda kalacagi sure.

    ⚠️ Olculdu (2026-08-09, Mohenjo-Daro): 7 sahne × 5 sn = 35,00 sn, ses
    35,88 sn. MPT acigi `itertools.cycle` ile TAM bir klip ekleyerek kapatiyor,
    yani video SAHNE 1'IN TEKRARIYLA bitiyordu: kapanis cumlesi ("the unanswered
    questions linger") geri donusturulmus acilis karesine dusuyordu. Son alti
    kosumun ucunde ayni sey var.

    Sabit 5 sn yerine sure sahne sayisina bolunuyor, boylece hem tekrar hem de
    son sahnenin dusmesi imkansiz hale geliyor (bkz. `KLIP_PAYI`).

    ⚠️ SES OLCUMU BASARISIZ OLABILIR — `anlatim_suresi` agdan TTS cekiyor ve
    hatayi yutup 0.0 donuyor (uretimi durdurmamak icin, bilincli). O durumda
    sabit 5 sn'ye dusmek Shorts'ta zararsizdi (8 kare × 5 = 40 sn, ses 33 sn)
    ama uzun formatta videoyu sessizce mahvediyor: 45 kare × 5 = 225 sn
    gorsele karsi 775 sn ses, yani gorseller 3,4 kez tekrar eder.

    Cozum sabiti yukseltmek DEGIL — dogru sure bicime degil SENARYOYA bagli.
    Kelime sayisi zaten elde ve hiz olculdu (`KELIME_HIZI`), yani ses
    olcumu dustugunde bile suresi ±%10 dogrulukla bilinebilir.
    """
    if sahne_sayisi <= 0:
        return float(VARSAYILAN_KLIP_SURESI)
    if ses_saniye <= 0:
        kelime = len(senaryo.split())
        if not kelime:
            return float(VARSAYILAN_KLIP_SURESI)
        ses_saniye = kelime / KELIME_HIZI * 60
        print(
            f"⚠️ ses olculemedi — senaryodan tahmin: {kelime} kelime ≈ "
            f"{ses_saniye:.0f} sn ({KELIME_HIZI} kelime/dk)",
            flush=True,
        )
    return round(ses_saniye / sahne_sayisi * KLIP_PAYI, 2)


BENZERLIK_ESIGI = gorsel_olcum.BENZERLIK_ESIGI

# ⚠️ Olcumler `gorsel_olcum`'da: `wikimedia_materials` de ayni parmak izini
# kullaniyor (arsiv tekrarini yakalamak icin) ama bu modulu import edemez —
# tersi zaten var, dairesel olurdu. Tek uygulama orada, buradakiler baglanti.
_parmak_izi = gorsel_olcum.parmak_izi
ton_yayilimi = gorsel_olcum.ton_yayilimi


def benzer_kareler(dosyalar: list[Path], esik: float = BENZERLIK_ESIGI) -> list[dict[str, Any]]:
    """Birbirine fazla benzeyen sahne ciftleri.

    ⚠️ Bu bir KAPI degil, bir OLCUM. Sahneyi reddetmiyor; benzerligi kayda
    yaziyor ki sorun montaja gozle bakmakla degil sayiyla izlensin.

    Kapi yapmamanin sebebi: esigin dogru degeri henuz bilinmiyor. Nazca
    kosumunda %84'luk cift gercekten fazla benzerdi, ama ayni anitin iki
    farkli acisi da yuksek skor alabilir ve onu reddetmek videoyu konusundan
    uzaklastirirdi. Once birkac kosumda dagilim olculecek.
    """
    import numpy as np

    izler: dict[int, Any] = {}
    for sira, yol in enumerate(dosyalar, 1):
        if yol is None or not Path(yol).exists():
            continue
        try:
            izler[sira] = _parmak_izi(Path(yol))
        except OSError:
            continue

    bulunanlar: list[dict[str, Any]] = []
    numaralar = sorted(izler)
    for i, a in enumerate(numaralar):
        for b in numaralar[i + 1 :]:
            oran = float(np.mean(izler[a] == izler[b]))
            if oran >= esik:
                bulunanlar.append({"sahneler": [a, b], "benzerlik": round(oran, 3)})
    return bulunanlar


def _benzerligi_kaydet(dosyalar: list[Path], hedef_dizin: Path) -> None:
    """Gorsel olcumleri kosumun yanina yazar.

    Olcum bir YAN IS: basarisiz olursa video uretimi durmamali. Bu yuzden
    her istisna yutuluyor — kaydin yoklugu, videonun yoklugundan iyidir.

    ⚠️ Iki AYRI eksen olculuyor ve biri iyilesirken digeri kotulesebilir:
    Mohenjo-Daro kosumunda yapisal tekrar sifirdi ama ton yayilimi 0,007'ydi.
    Tek sayiya bakmak "duzeldi" yanilgisi verirdi.
    """
    try:
        gecerli = [d for d in dosyalar if d is not None]
        kayit = {
            "benzer_kareler": benzer_kareler(gecerli),
            "ton_yayilimi": ton_yayilimi(gecerli),
        }
        hedef_dizin.mkdir(parents=True, exist_ok=True)
        (hedef_dizin / "benzerlik.json").write_text(
            json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"ton yayilimi: {kayit['ton_yayilimi']}", flush=True)
        if kayit["benzer_kareler"]:
            print(f"benzer kareler: {kayit['benzer_kareler']}", flush=True)
    except Exception as hata:  # noqa: BLE001 — olcum uretimi durduramaz
        print(f"gorsel olcum yapilamadi: {hata}", flush=True)


GORSEL_DENEME_SAYISI = 4
"""Gecici OpenAI hatasinda kac kez denenecek."""

GORSEL_BEKLEME_SN = 20.0
"""Ilk bekleme; her denemede ikiye katlaniyor (20 → 40 → 80)."""


def _gorsel_uret_tekrarli(
    client: OpenAI,
    request: dict[str, Any],
    *,
    sahne: int,
    uyu: Callable[[float], None] = time.sleep,
) -> Any:
    """Gorsel uretir; GECICI sunucu hatalarinda tekrar dener.

    ⚠️ Olculdu (2026-08-09, DW-115): bes konuluk bir kosumda api.openai.com
    Cloudflare uzerinden DORT kez 520 dondu ("origin returned an unknown
    error"). OpenAI'nin durum sayfasi ayni anda "All Systems Operational"
    diyordu, yani kesinti aralikliydi ve hatanin kendisi
    `"retryable": true, "retry_after": 60` tasiyordu.

    Tekrar YOKKEN bedeli agirdi: hata 8 sahnenin ortasinda gelince o ana kadar
    uretilmis gorseller VE senaryo/plan icin harcanan para copе gidiyordu.
    Kosumun ikisi tam da boyle dustu.

    Bu, deponun `wikimedia_materials._get_with_retry` icin zaten yazdigi
    gerekcenin aynisi: "gecici bir ag hatasinin bedeli harcanan LLM/gorsel
    parasi oluyor". Ayni koruma gorsel ucunda yoktu.

    ⚠️ Yalnizca GECICI hatalar tekrarlanir. `BadRequestError` (moderasyon)
    ve kredi tukenmesi tekrarlanmaz: ikisi de tekrar denemekle degismez,
    tekrarlamak yalnizca gecikme uretir.
    """
    son_hata: Exception | None = None
    for deneme in range(GORSEL_DENEME_SAYISI):
        try:
            return client.images.generate(**request)
        except (InternalServerError, APIConnectionError, APITimeoutError) as hata:
            son_hata = hata
            if deneme == GORSEL_DENEME_SAYISI - 1:
                break
            bekleme = GORSEL_BEKLEME_SN * (2**deneme)
            print(
                f"gorsel {sahne}: gecici hata ({type(hata).__name__}), "
                f"{bekleme:.0f} sn sonra yeniden deneniyor "
                f"({deneme + 2}/{GORSEL_DENEME_SAYISI})",
                flush=True,
            )
            uyu(bekleme)
    assert son_hata is not None
    raise son_hata


def generate_ai_scene_materials(
    plan: ContentPlan,
    target_dir: Path,
    revised_search_terms: list[str] | None = None,
    scene_numbers: list[int] | None = None,
) -> list[Path]:
    client, _ = _openai_client()
    model = str(config.app.get("openai_image_model", "gpt-image-1")).strip() or "gpt-image-1"
    target_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    selected_numbers = list(scene_numbers or range(1, len(plan.scenes) + 1))
    selected = set(selected_numbers)
    revised_by_scene: dict[int, str] = {}
    if revised_search_terms:
        if scene_numbers and len(revised_search_terms) == len(selected_numbers):
            revised_by_scene = dict(zip(selected_numbers, revised_search_terms, strict=True))
        elif len(revised_search_terms) == len(plan.scenes):
            revised_by_scene = {
                index: term for index, term in enumerate(revised_search_terms, 1)
            }
    for index, scene in enumerate(plan.scenes, 1):
        if index not in selected:
            continue
        visual_detail = scene.get("search_term", "")
        if index in revised_by_scene:
            visual_detail = revised_by_scene[index]
        # ⚠️ Ozel ad buradan SONRA gorsel modeline gitmiyor (DW-116).
        # Arsiv aramasi adi kullanmaya devam ediyor; kesilen yalnizca
        # GORSEL URETIM kanali. Gerekce `adsiz_gorsel_ifadesi`de.
        visual_detail = adsiz_sahne_tarifi(visual_detail, plan.visual_anchor)
        capa_ifadesi = adsiz_gorsel_ifadesi(plan.visual_anchor)
        prompt = (
            # ⚠️ Olculdu (2026-08-09, DW-112): bu cumle eskiden "Create a vertical
            # image for a YouTube Short about history" idi ve model 7 gorselin
            # 2'sine BASLIK YAZISI bastI — "CHACO CANYON DISAPPEARANCE MYSTERY"
            # ve "what happened to them?" goruntunun ICINE gomulu geldi.
            #
            # Promptun sonunda zaten "no captions, no text, no watermark" yaziyordu
            # ve ISE YARAMADI. Sebep olumsuz talimatIn zayifligI degil, acilis
            # cumlesinin kurdugu CERCEVE: "image for a YouTube Short" modele
            # kucuk-resim (thumbnail) turunu isaret ediyor ve o turun tanimi
            # zaten uzerinde iri baslik yazan bir gorsel. Model tur talimatini
            # izliyordu, yasak listesini degil.
            #
            # Cozum turu degistirmek: istenen sey bir fotograf, bir kapak gorseli
            # degil. "YouTube Short" ifadesi prompttan tamamen cikarildi; dikeylik
            # ve kullanim yeri tur adI vermeden tarif ediliyor.
            "Create a single vertical documentary photograph, 2:3 portrait framing. "
            "This is one frame of footage inside a film, never a poster, never a "
            "thumbnail, never a title card, never a book or album cover. "
            # ⚠️ Buraya OZEL AD YAZILMAZ (DW-116). Eskiden
            # `Visual anchor: {plan.visual_anchor}` idi ve model adi kadrajin
            # icine kazidi. Gerekce `adsiz_gorsel_ifadesi` docstring'inde.
            + (f"Setting: {capa_ifadesi}. " if capa_ifadesi else "")
            + f"Scene {index}: {scene.get('narration', '')}. "
            f"Required visible detail: {visual_detail}. "
            # ⚠️ Gorsel dil sahnenin KONUSUNA gore secilir, tek bir estetige
            # sabitlenmez — bkz. `GORSEL_DIL`.
            + GORSEL_DIL
            # ⚠️ Kadraj sahne basina DEGISIYOR. Burada eskiden HER sahneye ayni
            # sabit kompozisyon cumlesi gidiyor ve `GORSEL_DIL`in cesitlilik
            # istegini bozuyordu — gerekce `KARE_DILI` docstring'inde.
            + f" Frame this scene as {kare_dili(index, plan.topic)}. "
            # ⚠️ Isik kadrajdan AYRI donuyor ve palet kurali bunun tamamlayicisi:
            # tek basina isik vermek yetmiyordu, model yine her seyin uzerine
            # tek bir sicak katman koyuyordu — gerekce `ISIK_DILI` docstring'inde.
            + f"Light and weather for this scene: {isik_dili(index, isik_tohumu(plan.topic))}. "
            "Keep this lighting unless the scene's real setting makes it impossible, and in "
            "that case choose a time of day clearly different from golden hour. "
            "Do not apply a single global warm colour grade to the whole image, and do not "
            "render everything in one amber, ochre or sepia tone: let the real colours of sky, "
            "shadow, vegetation, water, metal, cloth and skin stay distinct from the colour of "
            "the stone or earth. "
            # ⚠️ Olculdu (2026-08-09): isik donusumu eklendiginde iki kare 0,21-0,22
            # parlakliga dustu. Shorts telefonda ve cogu zaman disarida izleniyor;
            # karanlik kare orada okunmuyor. Isik cesitliligi okunabilirligin
            # onune gecmemeli.
            "Whatever the light, the main subject must stay clearly visible and readable at "
            "small size on a phone screen — no crushed shadows, no silhouette-only frame. "
            + "Strong vertical composition, period-appropriate "
            "architecture, clothing, tools, and materials. No modern objects unless the scene is "
            "explicitly set today, and no invented event presented as a surviving photograph. "
            # ⚠️ Yasak MUAFIYETSIZ (DW-112). Uc asamada olculdu:
            #
            #   1. "no captions, no text, no watermark"
            #      → model 7 gorselin 2'sine iri BASLIK bastI (bindirme yazi).
            #   2. Yasak somutlastirildi + "sahnedeki gercek yazi serbest"
            #      muafiyeti eklendi (oyma, el yazmasi sayfasi)
            #      → model basligi MUAFIYETIN ICINE tasidI: bir sahnede
            #        "CHACO CANYON DISAPPERANCE MYSTERY" yazan oyulmus tas
            #        levha, digerinde adamin elinde "THE QUESTION REMAINS:
            #        WHAT HAPPENED TO THEM?" yazan kagit. Tastaki yazim hatasi
            #        ("DISAPPERANCE") isin ne kadar uydurma oldugunun kanIti.
            #   3. Muafiyet kaldirildi → burasi.
            #
            # Ders: modelin istedigi sey basligi GOSTERMEK. Ona yazi icin
            # herhangi bir mesru zemin birakilirsa basligi oraya koyuyor;
            # yasak dar degil, **kacamaksiz** olmali.
            #
            # Antik isaretler (petroglif, hiyeroglif) ayri tutuluyor ve bu
            # guvenli: onlar okunabilir Latin sozcugu degil, yani baslik
            # tasiyamiyorlar. Chaco'nun spiral petroglifi videonun en iyi
            # karesiydi — onu kaybetmek bedava degil.
            "The photograph must contain no readable words anywhere in the frame. "
            "No title text, no headline, no caption, no subtitle, no lower third, no logo, "
            "no watermark, no signature, no border. Equally forbidden inside the scene: "
            "signs, placards, plaques, inscribed slabs, banners, posters, labels, open books "
            "or sheets of paper turned towards the camera — anything that could carry the "
            "video's title as an object. Ancient carved symbols and petroglyphs that genuinely "
            "belong to the monument are welcome, but they must never spell out modern words. "
            # ⚠️ Kalan tek sizinti kanali (DW-116). Ozel ad artik `Setting:`
            # cumlesinden ve arama teriminden CIKARILDI, ama ANLATIM
            # cumlesinin icinde hala gecebiliyor ("she enrolled in the
            # Theresian Military Academy") ve anlatim kaldirilamaz — sahnenin
            # ne oldugunu soyleyen tek sey o.
            #
            # Bu yuzden kalan kanal icin kural ADI ISARET EDIYOR: ad senin
            # icin baglam, cizilecek icerik degil. Onceki yasaklar nesne
            # turlerini sayiyordu; bu, adin kendisini hedefliyor.
            "Any proper name that appears in this description is context for you, never "
            "content for the picture: no personal name, institution name, place name or "
            "date may be rendered as letters or numerals on any surface in the frame."
        )
        request = {
            "model": model,
            "prompt": prompt,
            "size": "1024x1536",
            # `medium` ile `high` arasindaki fark Shorts'ta tam ekran izlenen
            # bir goruntude gorunur: doku, kenar netligi, yuz detayi. Gorsel
            # basina birkac kurus fark, videonun tamamini tasiyan sey.
            "quality": "high",
            "n": 1,
        }
        try:
            response = _gorsel_uret_tekrarli(client, request, sahne=index)
        except BadRequestError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            code = str(body.get("code", getattr(exc, "code", "")))
            if code != "moderation_blocked" and "safety_violations" not in str(exc):
                raise
            safe_prompt = (
                "Create a non-violent museum-safe historical reconstruction for a vertical documentary. "
                # ⚠️ Burada da ozel ad YOK (DW-116). Moderasyon yedegi nadiren
                # calisiyor ama calistiginda ayni kusuru uretebilir; iki
                # istemin ayni kurala uymamasi kusurun geri donus yolu olur.
                f"Show only this neutral subject: {capa_ifadesi or visual_detail}; {visual_detail}. "
                "Focus on architecture, artifact, landscape, materials, or peaceful daily activity. "
                "No battle, injury, death, weapons, threat, distressed people, modern objects, text, logo, or watermark."
            )
            try:
                response = _gorsel_uret_tekrarli(
                    client, {**request, "prompt": safe_prompt}, sahne=index
                )
            except BadRequestError as retry_exc:
                retry_body = retry_exc.body if isinstance(retry_exc.body, dict) else {}
                retry_code = str(
                    retry_body.get("code", getattr(retry_exc, "code", ""))
                )
                if (
                    retry_code != "moderation_blocked"
                    and "safety_violations" not in str(retry_exc)
                ):
                    raise
                raise AIVisualUnavailableError(
                    f"AI image moderation blocked scene {index} after a non-violent retry"
                ) from retry_exc
        item = response.data[0]
        if getattr(item, "b64_json", None):
            image_bytes = base64.b64decode(item.b64_json)
        elif getattr(item, "url", None):
            download = requests.get(item.url, timeout=120)
            download.raise_for_status()
            image_bytes = download.content
        else:
            raise RuntimeError(f"AI image generation returned no image for scene {index}")
        destination = target_dir / f"scene-{index:02d}.png"
        with Image.open(io.BytesIO(image_bytes)) as image:
            vertical = ImageOps.fit(
                image.convert("RGB"),
                (1024, 1536),
                method=Image.Resampling.LANCZOS,
            )
            vertical.save(destination, format="PNG", optimize=True)
        files.append(destination)
    return files


def _delikleri_doldur(
    plan: ContentPlan, dosyalar: list[Path | None], material_dir: Path
) -> list[Path]:
    """Arsivin besleyemedigi sahneleri AI ile doldurur; bulunanlara dokunmaz.

    Onceki davranis "hep ya da hic"ti: tek sahne eksik olunca butun video AI
    ile uretiliyordu ve bulunmus gercek fotograflar cope gidiyordu (DW-97).
    Karisik video hem daha inandirici hem gorsel olarak daha zengin.
    """
    eksik = [sira for sira, yol in enumerate(dosyalar, 1) if yol is None]
    if not eksik:
        return [yol for yol in dosyalar if yol is not None]

    print(
        f"ℹ️ {len(dosyalar) - len(eksik)}/{len(dosyalar)} sahne arşivden geldi; "
        f"{len(eksik)} sahne AI ile dolduruluyor: {eksik}"
    )
    uretilenler = _generate_ai_or_reject(
        plan, material_dir / "ai-dolgu", scene_numbers=eksik
    )
    tamamlanmis = list(dosyalar)
    for sira, uretilen in zip(eksik, uretilenler, strict=True):
        tamamlanmis[sira - 1] = uretilen
    return [yol for yol in tamamlanmis if yol is not None]


def _generate_ai_or_reject(*args: Any, **kwargs: Any) -> list[Path]:
    try:
        return generate_ai_scene_materials(*args, **kwargs)
    except AIVisualUnavailableError as exc:
        raise SourceMaterialRejected(
            QualityReview(False, 0, 100, [str(exc)], [])
        ) from exc


def run_generator(
    plan: ContentPlan, attempt: int, *, bicim: VideoBicimi = SHORTS_BICIMI
) -> tuple[str, Path, Path, list[dict[str, Any]]]:
    # ⚠️ Klasor adinda KONU da var (DW-119). Eskiden yalnizca
    # `publication_slot_key()`-`attempt` idi, yani YYYY-MM-DD-HH: ayni saat
    # icinde uretilen iki video AYNI klasoru paylasiyordu.
    #
    # Olculdu (2026-08-10): 4 video uretildi, geriye 2 klasor kaldi.
    # `2026-08-10-10-attempt-1` icinde Anita'nin `credits.json`'u duruyor ama
    # klasorde credits'te gecmeyen `scene-01.jpg` ve `scene-07.jpg` de var —
    # Jacopo'dan kalanlar.
    #
    # Render bugun karismiyor cunku `dikeye_uydur_hepsi` acik listeyle
    # calisiyor, klasoru taramiyor. Zarar baska yerde: (a) adli iz siliniyor,
    # Scanagatta'daki levha kusurunun materyalleri incelenemedi; (b) tek
    # satirlik bir degisiklik downstream'i klasor taramaya cevirirse hat
    # sessizce YANLIS videoyu uretir. Ad ayrildi ki bu ikisi de imkansiz olsun.
    material_dir = (
        ROOT
        / "storage"
        / "youtube_automation"
        / "commons_materials"
        / f"{publication_slot_key()}-{konu_slug(plan.topic)}-attempt-{attempt}"
    )
    try:
        # Havuz BIR KEZ cozuluyor: hem birincil gecis hem ikinci gorsel
        # gecisi ayni kategoriye bakiyor, iki kez sorgulamak bosuna istek.
        kategori_havuzu = wikimedia_materials.kategori_havuzunu_coz(
            plan.visual_anchor, plan.topic
        )
        material_files, credits = download_scene_materials(
            plan.topic,
            plan.scenes,
            material_dir,
            visual_anchor=plan.visual_anchor,
            # AI yedegi acikken tek eksik sahne yuzunden butun arsivi atmak
            # yanlis: bulunan gercek fotograflar korunur, yalnizca delikler
            # AI ile doldurulur (DW-97).
            kismi=AI_VISUAL_FALLBACK_ENABLED,
            kategori_havuzu=kategori_havuzu,
            # ⚠️ Arsiv suzgeci ve SIRALAMASI kareye gore. Verilmezse yatay
            # bir belgesel icin portre gorseller ustte gelir (bkz.
            # `wikimedia_materials.UZUN_ORANI`).
            hedef_oran=kare_orani(bicim),
            # ⚠️ Uzun formatta capa BASLIKTA aranir. Gerekce ve olcum
            # `wikimedia_materials._puanli_adaylar` icinde: aciklamada gecen
            # capa, gorselin onu gosterdigi anlamina gelmiyor (adas kasaba,
            # modern kopya, gecerken anma). Shorts'ta dar capa KASITLI ve
            # cogu zaman baslikta gecmez — bu yuzden orada kapali.
            capa_baslikta=not bicim.dikey,
        )
    except MaterialsUnavailableError as exc:
        if not AI_VISUAL_FALLBACK_ENABLED:
            raise SourceMaterialRejected(
                QualityReview(False, 0, 100, [str(exc)], [])
            ) from exc
        material_files = _generate_ai_or_reject(plan, material_dir / "ai-fallback")
        credits = []
    else:
        material_files = _delikleri_doldur(plan, material_files, material_dir)
    _benzerligi_kaydet(material_files, material_dir)
    secilen = kaynak_ornegi(material_files, bicim)
    source_montage = create_source_montage(
        material_files, attempt, plan.topic, secilen=secilen
    )
    source_review = review_source_materials(
        plan, source_montage, secilen=secilen, bicim=bicim
    )
    # ⚠️ ARSIV ONCE — bu blok artik AI yedeginden BAGIMSIZ calisiyor (DW-118).
    #
    # Kosul eskiden `not AI_VISUAL_FALLBACK_ENABLED` idi. Yani yedek acikken
    # (uretimdeki hal) kaynak incelemesi dustugunde hat arsivde daha iyi bir
    # arama HIC denemeden dogruca `ai-refinement`'a gidiyordu. Arsivi
    # iyilestiren kod uretimde olu koddu.
    #
    # Sonuc olculdu (2026-08-10): Scanagatta 6/6 sahne AI. Kanal sahibinin
    # geri bildirimi "AI resim biraz cok, internetten bulup uretmeye calis
    # daha cok" — asil kaldirac burasiydi.
    #
    # Sira su: once revize edilmis terimlerle arsiv, hala dusuyorsa AI. Bedeli
    # basarisiz sahne basina birkac Commons/Met sorgusu; kazanci gercek
    # fotograf. AI hala orada, ama artik ILK degil SON care.
    if (
        not source_review.publishable
        or source_review.visual_alignment_score < MIN_SOURCE_VISUAL_SCORE
    ):
        problem_scenes = source_review.problem_scene_numbers
        revised_terms = source_review.revised_search_terms
        terms_by_scene: dict[int, str] = {}
        if problem_scenes and len(revised_terms) == len(problem_scenes):
            terms_by_scene = dict(zip(problem_scenes, revised_terms, strict=True))
        elif len(revised_terms) == len(plan.scenes):
            terms_by_scene = {
                scene_number: revised_terms[scene_number - 1]
                for scene_number in problem_scenes
            }
        if problem_scenes and not terms_by_scene:
            refined_plan = refine_search_terms(plan, source_review, bicim=bicim)
            terms_by_scene = {
                scene_number: refined_plan.scenes[scene_number - 1]["search_term"]
                for scene_number in problem_scenes
            }
        if terms_by_scene:
            refinement_scenes = [
                {
                    **plan.scenes[scene_number - 1],
                    "search_term": terms_by_scene[scene_number],
                }
                for scene_number in problem_scenes
            ]
            try:
                replacements, replacement_credits = download_scene_materials(
                    plan.topic,
                    refinement_scenes,
                    material_dir / "archive-refinement",
                    visual_anchor=plan.visual_anchor,
                    excluded_titles={
                        str(credit["title"])
                        for credit in credits
                        if credit.get("title")
                    },
                    excluded_met_ids={
                        int(credit["object_id"])
                        for credit in credits
                        if credit.get("object_id") is not None
                    },
                    hedef_oran=kare_orani(bicim),
                )
            except MaterialsUnavailableError:
                # Arsiv bu sahneleri besleyemedi; asagida AI devralir.
                arsiv_degisimi = None
            else:
                # ⚠️ Sayi tutmuyorsa arsiv denemesi BASARISIZ sayilir, hat
                # COKMEZ (DW-118). Bu blok `strict=True` zip ile dogrudan
                # eslestiriyor; arsiv beklenenden farkli sayida dosya
                # dondurdugunde ValueError firlatip butun uretimi dusururdu.
                # Yedek acikken bu yol artik her kosumda calistigi icin
                # sessiz bir carpisma noktasiydi. Arsiv YARDIMCI bir yol;
                # basarisizligi AI'ya devretmeli, kosumu bitirmemeli.
                if (
                    len(replacements) == len(problem_scenes)
                    and len(replacement_credits) == len(problem_scenes)
                ):
                    arsiv_degisimi = (replacements, replacement_credits)
                else:
                    arsiv_degisimi = None
                    print(
                        f"⚠️ arşiv {len(problem_scenes)} sahne için "
                        f"{len(replacements)} görsel döndürdü; "
                        "bu deneme atlanıyor",
                        flush=True,
                    )
            if arsiv_degisimi is not None:
                replacements, replacement_credits = arsiv_degisimi
                refined_materials = list(material_files)
                for scene_number, replacement in zip(
                    problem_scenes, replacements, strict=True
                ):
                    refined_materials[scene_number - 1] = replacement
                material_files = refined_materials
                replaced_scene_numbers = set(problem_scenes)
                credits = [
                    credit
                    for credit in credits
                    if int(credit.get("scene", 0)) not in replaced_scene_numbers
                ]
                for scene_number, credit in zip(
                    problem_scenes, replacement_credits, strict=True
                ):
                    credits.append({**credit, "scene": scene_number})
                credits.sort(key=lambda credit: int(credit.get("scene", 0)))
                secilen = kaynak_ornegi(material_files, bicim, problem_scenes)
                source_montage = create_source_montage(
                    material_files, attempt, plan.topic, secilen=secilen
                )
                source_review = review_source_materials(
                    plan, source_montage, secilen=secilen, bicim=bicim
                )
    if AI_VISUAL_FALLBACK_ENABLED and (
        not source_review.publishable
        or source_review.visual_alignment_score < MIN_SOURCE_VISUAL_SCORE
    ):
        # ⚠️ `problem_scene_numbers`'a TEK BASINA guvenilmiyor — bkz.
        # `sorunlu_sahneler`. Olculdu: bildirilen liste ile `issues` metninin
        # isaret ettigi sahneler farkli cikabiliyor ve yanlis sahne yeniden
        # uretiliyor.
        problem_scenes = sorunlu_sahneler(source_review, len(plan.scenes))
        # `revised_search_terms` bildirilen listeye gore hazirlanmis olabilir;
        # sahne kumesi genisledigi icin eslesmiyorsa gonderilmiyor. Yanlis
        # eslenmis bir arama terimi, terim vermemekten daha kotu.
        revize = source_review.revised_search_terms
        if revize and len(revize) not in (len(problem_scenes), len(plan.scenes)):
            revize = []
        replacements = _generate_ai_or_reject(
            plan,
            material_dir / "ai-refinement",
            revised_search_terms=revize,
            scene_numbers=problem_scenes,
        )
        refined_materials = list(material_files)
        for scene_number, replacement in zip(problem_scenes, replacements, strict=True):
            refined_materials[scene_number - 1] = replacement
        material_files = refined_materials
        secilen = kaynak_ornegi(material_files, bicim, problem_scenes)
        source_montage = create_source_montage(
            material_files, attempt, plan.topic, secilen=secilen
        )
        source_review = review_source_materials(
            plan, source_montage, secilen=secilen, bicim=bicim
        )
    if (
        not source_review.publishable
        or source_review.visual_alignment_score < MIN_SOURCE_VISUAL_SCORE
    ):
        raise SourceMaterialRejected(source_review, credits)

    # ⚠️ Render'dan HEMEN once, kalite kapisindan SONRA. Sira bilincli: kapi
    # kaynak gorselin kendisini degerlendirmeli, kirpilmis halini degil. Ama
    # render'a giden dosyalar Shorts oraninda olmali, yoksa video servisi
    # siyah bant ekliyor (DW-93).
    # ⚠️ IKINCI GORSEL burada indiriliyor — kaynak kapisindan SONRA. Kapi
    # birincil kareleri yargiliyor; ikincil gorsel bir iyilestirme ve
    # reddedilen bir plan icin indirilmesi bosa istek olurdu.
    # ⚠️ UZUN FORMATTA HIC INDIRILMIYOR ve bu bir DUZELTME, iyilestirme degil.
    # Blok kipten bagimsiz calisirken uc sey oluyordu:
    #   1. `bant_ister` DIKEY hedefe bakiyor, yani her 16:9 arsiv fotografi
    #      "bant ister" cikiyor ve 45 sahnenin neredeyse hepsi icin yedek
    #      gorsel indiriliyordu — 45 bosa ag istegi.
    #   2. Gelen dosyalar `credits`e ekleniyordu, yani ACIKLAMADA KAYNAK
    #      GOSTERILIYORDU.
    #   3. Uzun kipte `kare_yerlesimi` ikincil listeyi HIC KULLANMIYOR.
    # Yani video hic gostermedigi fotograflara atif yapardi. Yanlis atif
    # sessiz ve duzeltilmesi zor bir kusur: lisans metni yayinlanmis oluyor.
    ikincil_dosyalar: list[Path | None] = [None] * len(material_files)
    if bicim.kare_yuvasi >= 2:
        ikincil_dosyalar, ikincil_krediler = wikimedia_materials.ikincil_gorseller(
            plan.scenes,
            material_dir / "ikincil",
            kategori_havuzu,
            used_titles={str(k.get("title", "")) for k in credits},
            # Yalnizca bant isteyen sahnelere esleme yedegi aciliyor; gerekcesi
            # `ikincil_gorseller`de. Eksik sahne (kismi kip) False sayiliyor.
            esleme_gerekli=[bool(p) and bant_ister(p) for p in material_files],
        )
        # ⚠️ IKINCIL DENETIMI — gerekcesi `ikincil_gorselleri_denetle`de.
        # Kaynak kapisi bu dosyalari HIC gormuyordu ve 01 slotunda iki
        # koşumun ikisinde de agir kusurlarin TAMAMI buradan geldi.
        if dusen := ikincil_gorselleri_denetle(
            plan, ikincil_dosyalar, attempt, bicim=bicim
        ):
            for numara in dusen:
                ikincil_dosyalar[numara - 1] = None
            print(
                f"ikincil gorsel dusuruldu: {dusen} — o sahneler birincil kareye "
                "([A, A]) doner",
                flush=True,
            )
        # ⚠️ KREDI DENETIMDEN SONRA ekleniyor. Dusurulen gorselin kredisi
        # kalirsa video GOSTERMEDIGI bir fotografa atif yapar; yanlis atif
        # sessiz ve duzeltilmesi zor (ayni gerekce bu blogun ustunde).
        dusen_kume = set(dusen)
        credits = list(credits) + [
            kredi
            for kredi in ikincil_krediler
            if int(kredi.get("scene", 0)) not in dusen_kume
        ]
    material_files, tam_dolan_sahne = kare_yerlesimi(
        material_files, ikincil_dosyalar, material_dir / "dikey", bicim=bicim
    )
    print(
        f"kare duzeni [{bicim.ad}]: {len(plan.scenes)} sahne × {bicim.kare_yuvasi} "
        f"yuva = {len(material_files)} kare · {tam_dolan_sahne} sahnede iki AYRI gorsel",
        flush=True,
    )

    # ⚠️ Klip suresi ARTIK SABIT DEGIL. Sabit 5 sn, sahne sayisi × 5 < ses
    # oldugunda MPT'ye bastan bir klibi tekrar ettiriyordu — gerekce
    # `klip_suresi` docstring'inde.
    ses_saniye = anlatim_suresi(plan.script)
    # ⚠️ Bolen KARE sayisi, sahne sayisi degil. Sahne basina iki yuva var
    # (`KARE_YUVASI`) ve MPT her materyale ESIT sure veriyor; sahneye
    # bolmek her kareyi iki kat uzun tutar ve videonun yarisini kaybederdik.
    # ⚠️ Senaryo GECILIYOR: ses olcumu agdan dondugu icin dusebilir ve o
    # zaman tek gercek kaynak senaryonun kelime sayisi kalir.
    klip = klip_suresi(ses_saniye, len(material_files), plan.script)
    print(
        f"anlatim {ses_saniye:.2f} sn · {len(plan.scenes)} sahne × "
        f"{bicim.kare_yuvasi} yuva · klip {klip} sn "
        f"(toplam {klip * len(material_files):.2f} sn)",
        flush=True,
    )

    # ⚠️ Secim LOGA basiliyor (DW-120). Bu satir olmadigi icin hangi videoda
    # hangi parcanin caldigini ogrenmek ses korelasyonu olcmeyi gerektirdi.
    secilen_muzik = muzik_sec(ruh_hali=plan.ruh_hali)
    # ⚠️ Kazanc LOGA basiliyor. Ayni gerekce parca adinda da vardi (DW-120):
    # kayit tutulmadigi icin "hepsinde ayni muzik var" iddiasini sinamak
    # korelasyon olcmeyi gerektirmisti. Seviye de olculebilir kalmali.
    muzik_sesi = round(MUZIK_SES_TABANI * muzik_kazanci(secilen_muzik), 3)
    print(
        f"muzik: {secilen_muzik or 'yok (parca bulunamadi)'}"
        + (
            f" · ruh hali {plan.ruh_hali or 'belirtilmemis'}"
            f" · ses {muzik_sesi} (taban {MUZIK_SES_TABANI}"
            f" × kazanc {muzik_kazanci(secilen_muzik)})"
            if secilen_muzik
            else ""
        ),
        flush=True,
    )

    command = [
        sys.executable,
        "cli.py",
        "--video-subject",
        plan.topic,
        "--video-script",
        plan.script,
        "--video-language",
        "en-US",
        "--video-source",
        "local",
        "--video-materials",
        ",".join(str(path) for path in material_files),
        "--video-count",
        "1",
        "--video-aspect",
        # ⚠️ Uzun format 16:9 OLMAK ZORUNDA. Dikey kalirsa YouTube videoyu
        # Shorts sayar ve IZLENME SAATI YAZMAZ — uzun formatin butun amaci
        # o saatler (YPP'nin Shorts yolu 90 gunde 10M izlenme istiyor).
        en_boy_orani(bicim),
        "--video-concat-mode",
        "sequential",
        "--video-transition-mode",
        "none",
        "--video-clip-duration",
        str(klip),
        # ⚠️ Is parcacigi sayisi ACIKCA veriliyor. MPT varsayilani 2
        # (`app/models/schema.py`) ve hat bunu HIC gecmiyordu: 13 dakikalik
        # bir 1080p video iki cekirdekle kodlaniyordu. Olculdu: render
        # gercek zamanin 3,4 kati suruyor (`RENDER_ZAMAN_ASIMI`).
        #
        # ⚠️ Cekirdek sayisinin TAMAMI degil, biri BIRAKILIYOR: koşum
        # zamanlayiciyla arka planda calisiyor ve makineyi tamamen doldurmak
        # kanal sahibinin kendi isini yavaslatir.
        "--n-threads",
        str(ffmpeg_is_parcaciklari()),
        # ⚠️ Zoom GERI ACILDI, ama DONUSUMLU olarak (2026-08-17).
        #
        # 14 Agustos'ta tamamen kapatilmisti (sesli not: "su zoom olayi hosuma
        # gitmiyor"). Kod okununca asil kusurun zoom'un KENDISI degil YONU
        # oldugu gorüldü: her klip 1,00'dan basliyor, yani onceki klip
        # 1,00+Δ'da biterken sinirda ani bir kucultme oluyordu. `kare_duzeni`
        # uc durumdan ikisinde ayni gorseli iki ardisik yuvaya koyuyor
        # ([A,A] ve [AB,AB]), yani sicrama piksel birebir ayniyken oluyordu —
        # en gorunur hali.
        #
        # Donusumlu kipte tek numarali kare iceri, cift numarali kare disari
        # zoomluyor; olcek HER sinirda surekli kaliyor ve ayni gorselin iki
        # yuvaya kondugu durum bir kesme gibi degil yavas bir nefes gibi
        # gorunuyor.
        #
        # Bayrak yalnizca bu hatti etkiliyor; webui varsayilani (duz zoom)
        # degismedi.
        "--video-zoom-alternating",
        "--voice-name",
        SES_ADI,
        "--voice-rate",
        str(SES_HIZI),
        # ⚠️ Arka plan muzigi (DW-112, karar: Mirza 2026-08-09).
        #
        # Burasi eskiden "none" idi ve bu bilincli bir politikaydi:
        # VIDEO_STYLE.md → "Arka plan muzigi: Telif riski belirsizse
        # kullanilmaz. Yalnizca lisansi dogrulanmis muzik kullanilabilir."
        #
        # ⚠️ `resource/songs/` altindaki 29 parca bu sarti KARSILAMIYOR: hepsi
        # `outputNNN.mp3` diye isimsiz, lisans dosyasi ve kunye yok, ve MPT'nin
        # kendi README'si onlar icin "YouTube videolarindan alinmistir, telif
        # sorunu olursa silin" diyor. Yani kaynak belirsiz.
        #
        # Risk kullaniciya acikca soylendi ve kullanici paketteki parcalarla
        # devam etme karari verdi. Karar burada yaziyor ki telif talebi gelirse
        # sebep aranmasin: donus yolu tek satir, `"random"` → `"none"`.
        #
        # ⚠️ Parca ARTIK BURADA seciliyor, MPT'nin icinde degil (DW-120).
        # Eskiden `--bgm-type random` idi: secim iadeli yapiliyor ve hicbir
        # yere yazilmiyordu — gerekce `muzik_sec` docstring'inde.
        #
        # Telifsiz bir parcaya gecilirse dogru yol yine burasi: `muzik_sec`
        # yerine tek bir dogrulanmis dosya adi konur.
        *(
            ["--bgm-type", "custom", "--bgm-file", secilen_muzik]
            if secilen_muzik
            else ["--bgm-type", "none"]
        ),
        # Anlatim onde kalmali: taban 0.2, konusma uzerinde muzigi duyulur
        # ama bastirmaz seviyede tutuyor.
        #
        # ⚠️ ARTIK SABIT DEGIL — parca basina kazancla carpiliyor (2026-08-17).
        # Olculdu: havuzun ilk 40 saniyeleri 15,0 dB'ye yayilmisti ve
        # karistirma duz bir carpan, yani sabit 0,2 her parcada BASKA bir sey
        # demekti. Gerekcenin tamami `muzik_kazanci` docstring'inde.
        "--bgm-volume",
        str(muzik_sesi),
        "--subtitle-enabled",
        "--subtitle-position",
        "custom",
        # ⚠️ Konum ve font birlikte ayarlanir; biri digerini bozar (DW-93).
        # Olculdu: en uzun altyazi blogu 82 karakter ve 72px fontta 1080
        # genislige **4-5 satir** sigiyor. Blok o kadar buyuyor ki %72'lik
        # konumdan yukari tasip gorselin ana oznesini kapatiyordu — Viking
        # gemisinin govdesi, akveduktcunun eli.
        #
        # 56px'te ayni blok 3 satira iniyor ve %78 konumla alt ucte birde
        # kaliyor. Daha da kucultmek Shorts'ta okunabilirligi bozar; asil
        # cozum satiri kisaltmak degil, blogu kucultmek.
        "--custom-position",
        "78",
        "--text-fore-color",
        "#FFFFFF",
        "--font-size",
        "56",
        "--stroke-color",
        "#000000",
        # ⚠️ Kontur artik arka planin YERINE okunabilirligi sagliyor, o yuzden
        # kalinlastirildi (3 → 5). Siyah serit kalkinca beyaz metnin acik
        # zeminde (mavi gokyuzu, kum tasi, bulut) kaybolmamasi yalnizca
        # kontura bagli.
        # ⚠️ 5 -> 7 (2026-08-17). Olculdu (16-17 Agu, 7 render): altyazi
        # kapisi 7 koşumun DORDUNDE dustu — 65, 70, 72, 78; kapi 80. Hakem
        # gerekceyi her seferinde ayni yazdi:
        #
        #   "white text lacks sufficient contrast against cloudy skies"
        #   "light text on light uniform details / on light paper background"
        #
        # Yani kontur 5 acik zeminde (bulut, kum tasi, kagit) tek basina
        # yetmiyor ve serit kalkinca okunabilirligi ayakta tutan tek sey o.
        #
        # ⚠️ SERIT ACILMADI ve acilmayacak — kanal sahibinin istegi (DW-103):
        # "metin dogrudan goruntunun uzerinde dursun". Yari saydam kutu
        # secenegi (`--rounded-subtitle-background`, kod hazir) 17 Agu'da
        # ACIKCA soruldu ve REDDEDILDI. Tek kaldirac kontur; golge destegi
        # bu hatta yok (`cli.py`de shadow parametresi yok).
        #
        # ⚠️ 7 bilincli bir TAVAN: 56px fontta 7px kontur ~%12,5 ve bunun
        # ustu harflerin ic bosluklarini (a, e, o) kapatmaya baslar. Sonraki
        # koşumda altyazi skoru olculecek; harfler bozulursa 6'ya inilir,
        # yukari CIKILMAZ.
        "--stroke-width",
        "7",
        # Siyah serit yok: metin dogrudan goruntunun uzerinde durur (DW-103).
        # Serit alt ucte biri kapatiyordu ve Shorts'ta goruntuden calinan her
        # piksel pahali.
        "--no-subtitle-background-enabled",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=render_zaman_asimi(bicim),
    )
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{publication_slot_key()}-attempt-{attempt}.log"
    log_path.write_text(result.stdout + "\n--- STDERR ---\n" + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"video generation failed; see {log_path}")
    payload = parse_cli_result(result.stdout)
    task_id = str(payload["task_id"])
    videos = payload.get("result", {}).get("videos", [])
    if not videos:
        raise RuntimeError("video generation returned no final video")
    video_path = Path(videos[0])
    if not video_path.is_absolute():
        video_path = (ROOT / video_path).resolve()
    script_path = ROOT / "storage" / "tasks" / task_id / "script.json"
    # `tam_dolan_sahne` telemetri icin doner: kac sahnede IKI AYRI arsiv
    # gorseli bulunabildi. Kayda yazilmazsa hangi videonun hangi duzende
    # uretildigi sonradan bilinemez.
    return task_id, video_path, script_path, credits, tam_dolan_sahne


HAKEM_ORNEK_TAVANI = 12
"""Hakeme en fazla kac kare gosterilir.

⚠️ Uzun formatin bedeli BURADA odeniyor ve durustce yazilmali: 45 karelik
bir videoda HER SAHNE DENETLENMIYOR, esit aralikli bir ORNEKLEM
denetleniyor. Alternatif denetimi tamamen kaybetmekti — `montaj_izgarasi`
45 kareyi 23x2'lik bir serit yapardi ve hakem o seritte hicbir seyi
okuyamazdi (kareler 480 piksel genisliginde, toplam ~11.000 piksel).

12 secildi cunku Shorts montajlari 12-20 kareyle calisiyor ve hakem orada
kare basina okunabilir yargi veriyor — yani bu, olculmus bir calisma
noktasi.
"""


def hakem_kareleri(kare_sayisi: int, bicim: VideoBicimi = SHORTS_BICIMI) -> list[int]:
    """Montaja girecek KARE numaralari (1-tabanli), videodaki sirayla.

    ⚠️ SHORTS HIC ORNEKLENMIYOR, tavanin altinda kalsa bile. 10 sahnelik bir
    Short 20 kare demek ve bugun hakem o 20 karenin HEPSINI goruyor; tavani
    Shorts'a da uygulamak, olculerek kalibre edilmis bir kapinin gorus
    alanini sessizce daraltmak olurdu. Orneklem uzun formatin bedeli, Shorts
    icin bir iyilestirme degil.

    Uzun formatta da tavanin altinda kalan videolar (24 sahne = 24 kare
    degil, 12'den az kare) tam denetleniyor. Ilk ve son kare her zaman
    iceride: kanca ve kapanis videonun en cok izlenen iki ani.
    """
    toplam = max(int(kare_sayisi), 1)
    if bicim.dikey or toplam <= HAKEM_ORNEK_TAVANI:
        return list(range(1, toplam + 1))
    adim = (toplam - 1) / (HAKEM_ORNEK_TAVANI - 1)
    return sorted({round(1 + sira * adim) for sira in range(HAKEM_ORNEK_TAVANI)})


def montaj_izgarasi(kare_sayisi: int, dikey: bool = True) -> tuple[int, int]:
    """Kare sayisina gore sutun/satir.

    Dikey kareler yan yana dizilince iki satir yetiyor. YATAY kareler icin
    ayni duzen cok genis bir serit uretirdi (12 kare = 6x2 = 2880 piksel),
    o yuzden uc sutuna bolunuyor.
    """
    if not dikey:
        return 3, max(math.ceil(kare_sayisi / 3), 1)
    return max(math.ceil(kare_sayisi / 2), 1), 2


def create_review_montage(
    video_path: Path,
    task_id: str,
    scene_count: int,
    *,
    bicim: VideoBicimi = SHORTS_BICIMI,
) -> Path:
    """Sahne BASINA bir kare — 8 sabit degil.

    ⚠️ Montaj 2026-08-13'e kadar senaryoda kac sahne olursa olsun HER ZAMAN
    8 kare orneklerdi (`fps=8/sure`, `tile=4x2`). Ama plan 6-10 sahneye izin
    veriyor, yani 6 sahnelik bir videoda 8 kare iki sahneyi IKI KEZ
    ornekliyordu ve hakem bunu "agir tekrar" diye cezalandiriyordu.

    Kusur olcum yonteminde, videoda degil. Kaniti hakemin KENDI etiketleri
    (Murad III koşumu): kare 2 -> sahne 2, kare 3 -> sahne 2; kare 6, 7, 8 ->
    ucu de sahne 6. Ardindan "frames 2-3 are duplicates, frames 6-8 reuse the
    same engraving" yazip skoru dusurdu.

    Kareler sahnenin ORTASINDAN aliniyor: kesme noktasina denk gelen bir kare
    bir onceki sahneyi gosterebilir. Kare numaralari videonun kendi fps'inden
    hesaplaniyor, boylece secim kayan noktaya bagli kalmiyor.
    """
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    montage = REVIEW_DIR / f"{task_id}-montage.jpg"
    with VideoFileClip(str(video_path)) as clip:
        duration = max(float(clip.duration), 1.0)
        fps = float(clip.fps or 30.0) or 30.0
    kare_sayisi = max(int(scene_count), 1)
    klip = duration / kare_sayisi
    # ⚠️ Dilim genisligi TOPLAM kare sayisindan hesaplaniyor, orneklem
    # boyutundan degil: orneklenen kare hala kendi diliminin ORTASINDAN
    # alinmali. Orneklem sayisina bolunseydi kareler videonun yanlis
    # anlarindan cikardi ve hakem hicbir kusuru dogru sahneye baglayamazdi.
    secilen = hakem_kareleri(kare_sayisi, bicim)
    kare_numaralari = [
        max(int(round((sira - 0.5) * klip * fps)), 0) for sira in secilen
    ]
    secim = "+".join(rf"eq(n\,{numara})" for numara in kare_numaralari)
    sutun, satir = montaj_izgarasi(len(secilen), bicim.dikey)
    # ⚠️ Olcek DIKEY sabitti (270:480). Yatay karede o deger goruntuyu
    # ezerdi — hakem bozuk en-boy oranini "kotu gorsel" diye cezalandirir,
    # kusur ise videoda degil montajda olurdu.
    olcek = "270:480" if bicim.dikey else "480:270"
    command = [
        get_ffmpeg_exe(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"select='{secim}',scale={olcek},tile={sutun}x{satir}",
        "-frames:v",
        "1",
        # ⚠️ `select` ile birlikte sart: varsayilan kip eksik kareleri
        # cogaltip zaman tabanini duzler, yani ayni kare tekrar tekrar
        # dizilir — tam da kaldirmaya calistigimiz tekrar.
        "-fps_mode",
        "passthrough",
        str(montage),
    ]
    subprocess.run(command, check=True, timeout=180)
    if not montage.exists() or montage.stat().st_size == 0:
        raise RuntimeError("quality-control montage was not created")
    return montage


def review_video(
    plan: ContentPlan, montage: Path, *, bicim: VideoBicimi = SHORTS_BICIMI
) -> QualityReview:
    # ⚠️ ORNEKLEM HAKEME SOYLENIYOR. Uzun videoda montaj butun kareleri
    # tasimiyor (`HAKEM_ORNEK_TAVANI`); soylenmezse hakem 12 karelik bir
    # montaji 45 sahnelik senaryoyla eslestirmeye calisir ve "gorseller
    # anlatimi takip etmiyor" der — kusur videoda degil, bizim ona
    # verdigimiz eslemede olur.
    toplam_kare = len(plan.scenes) * bicim.kare_yuvasi
    ornekler = hakem_kareleri(toplam_kare, bicim)
    ornek_sahneler = [kareden_sahneye(k, bicim.kare_yuvasi) for k in ornekler]
    if bicim.kare_yuvasi >= 2:
        kare_aciklamasi = (
            f"The image is a {len(ornekler)}-frame chronological montage from a "
            "vertical Short, read left to right and top to bottom. There are exactly "
            f"{bicim.kare_yuvasi} frames per scene: frames 1-2 are scene 1, frames 3-4 "
            "are scene 2, and so on. The two frames of a scene both illustrate that "
            "scene's narration, so they show the same subject twice — that is "
            "intended, not repetition. "
            "If the two frames of one scene are identical, that is a deliberate layout "
            "choice, not duplicated footage; do not report it as repetition. A frame "
            "that shows two stacked photographs is also deliberate. "
        )
    else:
        kare_aciklamasi = (
            f"The image is a {len(ornekler)}-frame chronological montage from a "
            "horizontal documentary, read left to right and top to bottom. The video "
            f"has {len(plan.scenes)} scenes and this montage samples "
            f"{len(ornekler)} of them, evenly spaced. Frame n shows scene "
            f"{ornek_sahneler} respectively, so frame 1 is scene {ornek_sahneler[0]}, "
            f"frame 2 is scene {ornek_sahneler[1] if len(ornek_sahneler) > 1 else ornek_sahneler[0]}, "
            "and so on. Scenes that are not in this list were not sampled: do not "
            "report them as missing, and do not treat the jump between sampled scenes "
            "as a break in the story. Each frame illustrates its own scene's "
            "narration and every frame shows a different scene, so any two frames "
            "showing the same image ARE a real repetition defect. "
        )
    prompt = {
        "topic": plan.topic,
        "script": plan.script,
        "scenes": plan.scenes,
        "instructions": (
            # ⚠️ Kare sayisi SABIT DEGIL — sahne basina bir kare aliniyor
            # (bkz. `create_review_montage`). Eslemeyi soylemek onemli:
            # soylenmediginde hakem ayni sahnenin iki ornegini "duplicate"
            # sanip skoru dusuruyordu.
            kare_aciklamasi
            # ⚠️ ALTYAZI KARE SINIRINA HIZALANMAZ ve bunu soylemek zorunlu.
            +
            # Olculdu (2026-08-14, Lycurgus Cup): istem "iki kare AYNI
            # CUMLEYI resmediyor" diyordu; hakem bunu dogrulamaya calisti ve
            # "frame 2 already reads 'Made in fourth century Rome'" diye
            # kusur yazdi. Kusur videoda degil ISTEMDEYDI: altyazi sese gore
            # zamanlaniyor, kare suresi ise `ses ÷ kare` — ikisi tanim
            # geregi ortusmuyor. Istem tutamayacagi bir soz verince hakem
            # onu bozuk sayiyor.
            "Subtitles are timed to the spoken audio, not to these frame boundaries, so a "
            "caption often starts or ends part-way through a frame. That is normal; judge "
            "captions only on whether they are readable. "
            # ⚠️ Ayni karenin iki yuvada gorunmesi KASITLI: ikinci arsiv
            # gorseli bulunamadigi ya da iki yatay fotograf tek kareye alt
            # alta yapistirildigi durumlarda oyle oluyor. Soylenmezse hakem
            # bunu "agir tekrar" sayip skoru dusuruyor — ayni kusur sahne
            # basina tek kare orneklenirken de olculmustu. Kipe bagli kismi
            # `kare_aciklamasi` icinde; asagisi iki kipte de gecerli.
            "Only report repetition when DIFFERENT scenes reuse the same image. "
            "Any trailing blank cell is padding. "
            "Judge whether visuals match the narration and historical period, whether captions are readable, and whether footage is repetitive. "
            "Historically grounded AI illustrations are acceptable; do not reject them merely for not being archival photographs, but reject misleading or historically inconsistent details. "
            "Return JSON with visual_alignment_score (0-100), subtitle_readability_score (0-100), issues (array), and revised_search_terms (one concrete replacement query per problematic scene). "
            # ⚠️ Kaynak incelemesiyle ayni kural: esik burada da ANILMAZ.
            "Both scores are measurements of this montage, not verdicts. visual_alignment_score: 0 means nothing matches the narration, 50 means about half the frames match, 100 means every frame matches cleanly. subtitle_readability_score: 0 means captions are unreadable, 100 means every caption is comfortably legible. Score what you actually see. "
            "Report modern or unrelated footage, heavy repetition, unreadable captions, or a weak/missing curiosity hook in the first 2-3 seconds as issues. "
            # ⚠️ Ayni iki soru burada da soruluyor (DW-117). Kaynak kapisi
            # ile video kapisi FARKLI goruntuler goruyor: kaynak kapisi ham
            # gorseli, bu kapi kirpilmis ve altyazili nihai kareyi. Yalnizca
            # birine koymak digerini acik birakir.
            "Also answer two specific questions for every frame. First: is there readable "
            "lettering inside the picture itself — not the subtitle burned along the bottom, "
            "which is intended — but words on a sign, plaque, carved stone, book, paper or "
            "nameplate? Quote what you can read. Second: when the narration is about a named "
            "person, is the human on screen actually that person, or somebody else sharing "
            "the same medal, uniform, institution or era? Report either as an issue."
            # ⚠️ Kare basina OLGU soruluyor, karar degil. Duzyazi `issues`
            # alani bu olgulari zaten tasiyordu ama serbest metin olarak;
            # kod onu guvenilir bicimde okuyamiyordu. Esik ya da "yayina
            # uygun mu" HALA sorulmuyor (DW-87) — yalnizca karede ne
            # goruldugu.
            " Additionally return a `frames` array with one object per frame: "
            '{"n": <frame number>, '
            '"person": "correct" when the human shown is the person the narration names, '
            '"wrong" when it is a DIFFERENT identifiable person, "unclear" when the '
            'figures are too small, too stylised or too obscured to tell, "none" when the '
            'narration names no person, '
            '"period": "correct" when the thing shown belongs to the era the narration '
            'describes, "wrong" when it belongs to a different era and is presented as '
            'this one, "unclear" when you cannot tell, '
            '"authentic_subject": <true when the thing shown IS the real subject, its '
            "surviving remains, or a genuine historical depiction of it, even if the "
            'photograph itself was taken recently>, '
            '"modern": <true when the frame is a present-day photograph or footage>, '
            # ⚠️ Bu iki alan TELEMETRI, kapi degil (2026-08-14). Yazi
            # sorusu istemde ZATEN vardi ama cevap duzyazi `issues`a
            # gidiyordu; kod onu guvenilir okuyamiyor, dolayisiyla
            # olcemiyordu. Kanal sahibinin sesli notundaki iki madde tam
            # da bunlar: "cok fazla harita, ustune yazi olan fotograf".
            #
            # Olculdu (2026-08-14, Tunguska koşumu): 18 karenin 3'u harita,
            # 1'i kitap kapagi, 2'si pul, birkaci muze etiketi — hepsi
            # yazili. Video reddedildi ama SKOR uzerinden; hangi karenin
            # neden kotu oldugu sayiyla degil duzyaziyla biliniyordu.
            #
            # Esik veri birikince konacak. Once olc, sonra kapi kur.
            '"lettering": <true when readable words appear INSIDE the picture — a sign, '
            "plaque, caption, book cover, stamp, map label or nameplate — not counting the "
            'subtitle burned along the bottom, which is intended>, '
            '"kind": one of "photo", "map", "diagram", "artwork", "document" — what the '
            "frame actually is}. "
            "Answer what you can actually see. A recent photograph of the genuine "
            "surviving object is authentic_subject true and period correct; a recent "
            "photograph of something else entirely is not."
        ),
    }
    data = _vision_json(prompt, montage, bicim=bicim)
    gorsel_skor = int(data.get("visual_alignment_score", 0))
    altyazi_skor = int(data.get("subtitle_readability_score", 0))
    kareler = data.get("frames")
    agir = agir_kusurlari_ayikla(kareler)
    return QualityReview(
        publishable=yayina_uygun(gorsel_skor, altyazi_skor) and not agir,
        visual_alignment_score=gorsel_skor,
        subtitle_readability_score=altyazi_skor,
        issues=[str(issue) for issue in data.get("issues", [])],
        revised_search_terms=[str(term) for term in data.get("revised_search_terms", [])],
        agir_kusurlar=agir,
        kareler=[k for k in kareler if isinstance(k, dict)] if isinstance(kareler, list) else [],
    )


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"published": [], "rejected": [], "completed_slots": []}
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    state.setdefault("published", [])
    state.setdefault("rejected", [])
    state.setdefault("completed_slots", [])
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE_FILE)


def _seconds_until_not_before(not_before: str, now: datetime) -> float:
    try:
        hour_text, minute_text = not_before.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("not-before must use HH:MM format") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("not-before must use a valid 24-hour time")
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return max((target - now).total_seconds(), 0.0)


def _wait_until_not_before(not_before: str) -> None:
    now = datetime.now(ZoneInfo(TIMEZONE_NAME))
    delay = _seconds_until_not_before(not_before, now)
    if delay > 0:
        time.sleep(delay)


KILIT_BAYATLAMA = 12 * 3600
"""Kilit dosyasinin PID'i CANLIYKEN bile bayat sayilma suresi, saniye.

⚠️ Eski deger 4 saatti ve mantik `expired or pid_is_dead` idi: sure dolunca
kilit, sahibi CALISIYOR OLSA BILE siliniyordu. `macos_zamanlama.py`
slotlari da tam 4 saat arayla (9, 13, 17, 21).

Shorts koşumu dakikalar surdugu icin 4 saat erisilemez bir tavandi. Uzun
formatta oyle degil: olculen dokuzuncu koşum tek basina 46,2 dakika surdu
ve o render'a bile ulasmadi. `RENDER_ZAMAN_ASIMI`nin uzun karsiligiyla
birlikte bir koşum saatlerce surebilir.

⚠️ Bu yuzden zaman asimini yukseltmek TEK BASINA yapilamaz: 4 saatlik
kilitle birlikte iki koşumun ayni `state.json` ve ayni `storage/` uzerinde
paralel calismasi demekti.

Yeni mantik: CANLI bir surecten kilit ASLA calinmaz. Koşum slot araligini
asiyorsa bir sonraki tetikleme zaten "another cycle is already running"
diyerek dusmeli — dogru davranis bu. Sure yalnizca PID GERI DONUSUMUNE
karsi duruyor: 12 saat sonra ayni numarayi tasiyan surec, bizim koşumumuz
olamayacak kadar eski demektir.
"""


def _acquire_lock() -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        expired = time.time() - LOCK_FILE.stat().st_mtime > KILIT_BAYATLAMA
        try:
            recorded_pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
            try:
                os.kill(recorded_pid, 0)
                pid_is_dead = False
            except ProcessLookupError:
                pid_is_dead = True
            except PermissionError:
                pid_is_dead = False
            except OSError:
                pid_is_dead = True
        except (OSError, ValueError):
            pid_is_dead = True
        # ⚠️ Kosul AYNI kaldi, degisen SURE. Gerekce `KILIT_BAYATLAMA`da:
        # 4 saat gercek bir uzun koşumun ULASABILECEGI bir sureydi, yani
        # kilit sahibi calisirken siliniyordu. 12 saat yalnizca PID geri
        # donusumune karsi duruyor.
        if pid_is_dead or expired:
            LOCK_FILE.unlink(missing_ok=True)
    try:
        descriptor = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("another YouTube automation cycle is already running") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))


def run_cycle(
    *,
    dry_run: bool = False,
    privacy: str = "public",
    not_before: str | None = None,
    kuyruktan: bool = False,
    yedek_konu: bool = False,
    sahne_sayisi: int | None = None,
    bicim: VideoBicimi = SHORTS_BICIMI,
    konu_override: str | None = None,
) -> dict[str, Any]:
    slot = publication_slot_key()
    state = load_state()
    if slot in state.get("completed_slots", []):
        return {"status": "skipped", "reason": "slot already completed", "slot": slot}

    # Kuyruk kipinde konu trend hunisinden gelir. Aday YOKSA kosum durur —
    # modelin kendi konusuna DUSMEZ. Sessiz geri dusus, kuyruga bagli
    # oldugunu sanan ama aslinda kendi konusunu ureten bir hat demek olurdu;
    # bu, hic baglanmamis olmaktan daha kotu cunku fark edilmiyor.
    aday: notion_kuyrugu.Aday | None = None
    kaynak = "huni" if kuyruktan else "model"
    # ⚠️ ACIK KONU — kuyruga da modele de sorulmuyor. Kullanim yeri olculmus:
    # kanalin en cok izlenen videolari zaten talebi KANITLANMIS konular ve
    # arsiv arzlari uretildikleri icin biliniyor. Kuyruk o konulari yeniden
    # onermez (`benzeri uretilmis` kapisi), o yuzden uzun formatta yeniden
    # ele almanin tek yolu konuyu dogrudan vermek.
    #
    # ⚠️ Uydurma guvencesi KORUNUYOR: `--uzun`un istedigi sey Notion degil
    # KONUNUN VERILMIS olmasiydi — kaynak metin ve arsiv menusu ancak konu
    # varken isteme giriyor. Acik konu bu kosulu birebir sagliyor.
    if konu_override:
        kaynak = "acik-konu"
        kuyruktan = False
    elif kuyruktan:
        adaylar = notion_kuyrugu.kuyrugu_oku(ytoto_path=YTOTO_PATH)
        # ⚠️ LISTE ILE KAPMA CELISEBILIYOR, ve bu koşumu OLDURMEMELI.
        #
        # Olculdu (2026-08-14): Notion'un veritabani sorgu indeksi bayat
        # kalabiliyor. `Durum = Seçildi` filtresi, sayfasi okununca `Elendi`
        # gorunen adaylari donduruyordu — Talaat Pasha ve Murad III, ikisi de
        # saatler once elenmis konular. Dogrudan Notion'a sorulunca her ikisi
        # icin de TEK sayfa var ve durumu `Elendi`; yani mukerrer kayit degil,
        # indeks gecikmesi. Birkac dakika icinde ayni filtre 2 sayfadan 1'e
        # dustu, yani indeks yavasca yetisiyor.
        #
        # Eski kod `adaylar[0]`i alip kapiyor, kapayamazsa `KopruHatasi` ile
        # butun koşumu dusuruyordu. Saat basi calisan bir zamanlayicida bu,
        # bayat TEK bir kayit yuzunden uretimin tamamen durmasi demek.
        #
        # ⚠️ "Kapmadan uretme" guvencesi KORUNUYOR: kapilamayan aday
        # uretilmiyor, yalnizca ATLANIYOR. Tehlikeli olan tersiydi.
        #
        # Soguma yuzunden atlananlar AYRICA tutuluyor: aday bulunamadiginda
        # gerekce "kuyruk bos" demek yanlis olur — kuyruk dolu, yalnizca
        # bekliyor. Insan Notion'a bakip "aday duruyor, neden uretmiyor"
        # dememeli.
        sogumada: list[str] = []
        for sirasiyla in adaylar:
            # ⚠️ SOGUMA KAPISI ONCE — bedavaya eleyen kapi, agdan okuyan
            # kapinin ONUNDE durmali. Asagidaki menu olcumu `arsiv_envanteri`
            # cagiriyor; sogumadaki bir adayi once olcup sonra atlamak bos
            # yere ag trafigi demek. Ayni sira `huni_besle.besle` icinde de
            # var (tekrar kapisi olcum tavanindan once).
            kalan_saat = aday_sogumada_mi(sirasiyla.baslik, state)
            if kalan_saat > 0:
                print(
                    f"ℹ️ aday atlandı ({sirasiyla.baslik}): son red üstünden "
                    f"{ADAY_SOGUMA_SAATI - kalan_saat:.1f} saat geçti, "
                    f"{kalan_saat:.1f} saat daha soğumada",
                    flush=True,
                )
                sogumada.append(sirasiyla.baslik)
                continue
            # ⚠️ KAPMADAN ONCE OLC. Olculdu (2026-08-16, iki koşum arka arkaya):
            # `Ernst Hanfstaengl` `Secildi`de duruyordu ve uretim onu her
            # slotta kuyrugun basinda buldu; 18:00 ve 18:57 koşumlarinin
            # ALTI denemesi de yandi (ikisi tam render).
            #
            #     Ernst Hanfstaengl  menu  8   <- konu, kapi 12: GECEMEZ
            #     Franz Hanfstaengl  menu 40   <- DEDESI, 19. yy fotografcisi
            #
            # Uretim arsivi zengin olan dedeyi capa secti, ama bir
            # fotografcinin kategorisi kendi resimleriyle degil CEKTIGI
            # kisilerle dolu: hakem her karede baskasini gordu (Wagner,
            # Rietschel, Ludwig II) ve "anlatilan kisi degil" yazdi.
            #
            # ⚠️ Huni terfide olcuyordu (`huni_besle.uretilebilir_mi`) ama
            # kuyruga BASKA yollardan da aday giriyor: insan elle `Secildi`
            # yapabiliyor, ve takilan aday kurtarilabiliyor. Terfi kapisi tek
            # basina yetmiyor — tuketen uc de olcmeli.
            #
            # Esik huninin esigiyle ayni tanim (6 sahne x kare yuvasi) ve
            # olcum uretimin KENDI envanteriyle yapiliyor; `arsiv_envanteri`
            # onbellekli, yani bu cagri hattin ilerisinde yeniden kullaniliyor
            # ve ek ag maliyeti getirmiyor.
            #
            # ⚠️ Menu kurulamazsa `arsiv_envanteri` BOS donuyor (kendi
            # sozlesmesi) ve aday atlaniyor. Bu bilincli: yedek capa havuzu
            # saglikli (50 uygun capa), yani atlamanin bedeli bir yedek kip
            # videosu; kapmanin bedeli ise yanmis bir slot.
            asgari_menu = 6 * bicim.kare_yuvasi
            envanter = arsiv_envanteri(sirasiyla.baslik, bicim=bicim)
            if len(envanter) < asgari_menu:
                print(
                    f"ℹ️ aday atlandı ({sirasiyla.baslik}): arşiv menüsü "
                    f"{len(envanter)} < {asgari_menu} — üretim slotu yakardı",
                    flush=True,
                )
                continue
            try:
                notion_kuyrugu.adayi_kap(sirasiyla, ytoto_path=YTOTO_PATH)
            except notion_kuyrugu.KopruHatasi as hata:
                print(f"ℹ️ aday atlandı ({sirasiyla.baslik}): {hata}", flush=True)
                continue
            aday = sirasiyla
            break
        if aday is None and not yedek_konu:
            return {
                "status": "no-candidate",
                "slot": slot,
                "reason": (
                    "`Seçildi` kuyrugunda kapilabilir aday yok — Notion'da bir adayi "
                    "bu duruma alin. Konu uydurulmadi."
                    + (
                        # Kuyruk BOS DEGIL, bekliyor. Ayrimi soylemezsek insan
                        # Notion'da duran adaya bakip hattin bozuldugunu sanar.
                        f" ⏳ {len(sogumada)} aday soğumada "
                        f"({', '.join(sogumada[:3])}) — son redlerinin üstünden "
                        f"{ADAY_SOGUMA_SAATI} saat geçmedi."
                        if sogumada
                        else ""
                    )
                ),
            }
        if aday is None:
            # ⚠️ Geri dusus ACIK ve KAYITLI. Yukaridaki itiraz gecerli ve
            # korunuyor: sessiz geri dusus, kuyruga bagli oldugunu sanan ama
            # kendi konusunu ureten bir hat demek olurdu. Bu yuzden
            # (a) yalnizca `--yedek-konu` verilirse calisir — varsayilan
            #     davranis degismedi, bayrak yoksa kosum eskisi gibi durur,
            # (b) kaynak koşum kaydina yazilir ve stdout'a basilir, yani
            #     hangi kipin urettigi sonradan sayilabilir.
            #
            # Neden bu kip degerli: olculdu (2026-08-13), model-secimli
            # anit/yer konulari 70-90 skor ve 0-3 kusurla gecti; ayni
            # donemde huniden gelen kisi konulari 68-84 ve 9-11 kusur.
            # Bos kuyrukta slotu bos birakmak, iyi calisan kipi
            # kullanmamak demek.
            kaynak = "yedek"
            print(
                "ℹ️ `Seçildi` kuyrugunda kapilabilir aday yok — "
                "yedek konu kipi (anit/yer) devrede",
                flush=True,
            )
    aday_kapatildi = False

    _acquire_lock()
    try:
        exclusions: list[str] = []
        reviews: list[dict[str, Any]] = []
        # ⚠️ Arsiv uzun formati besleyemiyorsa koşum SHORTS'A DUSUYOR, olmuyor.
        # Konu zaten kuyruktan kapilmis durumda; burada durmak o adayi ve o
        # uretim slotunu birlikte yakmak olurdu. Uzun format bir IYILESTIRME,
        # uretimin on kosulu degil.
        #
        # ⚠️ Geri dusus DONGUYLE yaziliyor, ic ice `try` ile degil: ilk hali
        # yedek cagriyi `except` govdesinin ICINE koymustu ve oradan cikan
        # `DistinctTopicUnavailableError` kardes `except`e ugramadan disari
        # kacardi — yani nazikce reddedilecek bir koşum izlenmeyen bir
        # istisnayla olurdu.
        # Konu tek yerden okunuyor: acik konu > kuyruk adayi > yok (model secer).
        etkin_konu = konu_override or (aday.baslik if aday else None)
        # ⚠️ Acik konuda capa tekrari SERBEST: kanitlanmis bir konuyu uzun
        # formatta yeniden ele alirken AYNI capa isteniyor, amac o. Kapi acik
        # kalsaydi uc denemenin ucu de reddedilir, her biri ~2.000 kelimelik
        # bir cikarim koşumu yakardi.
        capa_serbest = bool(konu_override)
        plan: ContentPlan | None = None
        planlama_hatasi: DistinctTopicUnavailableError | None = None
        # ⚠️ KONUSUZ UZUN PLAN OLMAZ ve burada durmak yerine Shorts'a
        # dusuluyor. `--uzun --yedek-konu` ile bos kuyrukta konu None
        # kaliyor; `generate_content_plan` o durumda `ValueError` atiyor ve
        # bu dongu onu yakalamiyordu, yani nazikce reddedilecek bir koşum
        # izlenmeyen bir istisnayla olurdu.
        if not bicim.dikey and etkin_konu is None:
            print(
                "ℹ️ uzun format icin kuyruk adayi yok (yedek konu kipi), "
                "Shorts'a dusuluyor",
                flush=True,
            )
            bicim = SHORTS_BICIMI
        denecek_uzun = not bicim.dikey
        denenecek = [bicim, SHORTS_BICIMI] if denecek_uzun else [bicim]
        for aday_bicim in denenecek:
            try:
                plan = generate_content_plan(
                    exclusions,
                    konu=etkin_konu,
                    sahne_sayisi=sahne_sayisi,
                    bicim=aday_bicim,
                    capa_tekrari_serbest=capa_serbest,
                )
                bicim = aday_bicim
                break
            except UzunFormatUygunDegilError as exc:
                print(f"ℹ️ uzun format atlandi, Shorts'a dusuluyor: {exc}", flush=True)
                continue
            except DistinctTopicUnavailableError as exc:
                # Konu sorunu bicim degistirerek cozulmez; denemeye devam
                # etmek bes cikarim koşumunu daha yakmak olurdu.
                planlama_hatasi = exc
                break
        if plan is None:
            hata = planlama_hatasi or DistinctTopicUnavailableError(
                "hicbir bicim icin plan uretilemedi"
            )
            reviews.append(
                {
                    "stage": "planning",
                    "topic": "",
                    "visual_anchor": "",
                    "task_id": None,
                    "review": asdict(QualityReview(False, 0, 100, [str(hata)], [])),
                    "video": "",
                }
            )
            # ⚠️ PLANLAMA REDDI DE KAYDA GECIYOR — olculdu (2026-08-18) ve
            # #38'in sogumasindaki delik tam buydu.
            #
            # Soguma `state["rejected"]` okuyor; bu yol ise yalnizca
            # `reviews`e yaziyordu. Yani plan uretilemeden dusen bir koşum
            # adayi HIC sogutmuyordu ve aday ertesi koşumda yine kuyrugun
            # basindaydi — kapatmaya calistigimiz dongunun aynisi, yalnizca
            # baska bir kapidan.
            #
            # Canli ornek: 01:10 koşumu `Orkhon Yazıtları` adayini kapti, bes
            # denemenin dordu "capa arzi yetersiz" ile yandi (konu arsiv
            # fakiri) ve aday kayitsiz kaldi. Iki tur once ayni kusuru video
            # asamasi icin kapatmistik; bu ucuncu cikis yolu atlanmisti.
            #
            # ⚠️ `visual_anchor` BOS biraliyor: burada gecerli bir capa YOK
            # (plan hic kurulamadi). Bos capa `engellenen_capalar`a girmiyor,
            # yani bu kayit bir CAPAYI yakmiyor — yalnizca ADAYI sogutuyor.
            # Ikisinin ayri kalmasi bilincli: capa butcesi (`RET_DENEME_BUTCESI`)
            # kalici kapatir, soguma yalnizca erteler.
            if not dry_run:
                state.setdefault("rejected", []).append(
                    {
                        "stage": "planning",
                        "slot": slot,
                        "kaynak": kaynak,
                        "aday_basligi": aday.baslik if aday else None,
                        "topic": "",
                        "visual_anchor": "",
                        "task_id": None,
                        "visual_alignment_score": 0,
                        "issues": [str(hata)],
                        "agir_kusurlar": [],
                        "rejected_at": datetime.now(ZoneInfo(TIMEZONE_NAME)).isoformat(),
                    }
                )
                save_state(state)
            return {
                "status": "rejected",
                "slot": slot,
                "topic": "",
                "reviews": reviews,
            }
        selected: tuple[
            str, Path, Path, QualityReview, list[dict[str, Any]]
        ] | None = None
        for attempt in range(1, 4):
            try:
                (
                    task_id,
                    video_path,
                    script_path,
                    credits,
                    tam_dolan_sahne,
                ) = run_generator(plan, attempt, bicim=bicim)
            except SourceMaterialRejected as exc:
                review = exc.review
                rejected_topic = plan.topic
                exclusions.extend([rejected_topic, plan.visual_anchor])
                reviews.append(
                    {
                        "stage": "source_materials",
                        "topic": rejected_topic,
                        "visual_anchor": plan.visual_anchor,
                        "task_id": None,
                        "review": asdict(review),
                        "video": "",
                    }
                )
                state.setdefault("rejected", []).append(
                    {
                        "stage": "source_materials",
                        # ⚠️ `slot` ve `kaynak` eklendi (2026-08-13): 120
                        # reddedilmis kaydin hicbiri zaman dilimiyle
                        # iliskilendirilemiyordu, yani "hangi saatte ne
                        # oldu" sorusu cevaplanamiyordu.
                        "slot": slot,
                        "kaynak": kaynak,
                        # ⚠️ HANGI NOTION ADAYI. `topic` bu soruyu
                        # cevaplamiyor: model konuyu yeniden yaziyor.
                        # Olculdu — Ernst Hanfstaengl'in dort reddinde dort
                        # AYRI `topic` var, King Philip's War'un sekizinde
                        # ise aday basligiyla birebir ayni. Yani ikisini
                        # ayirt etmenin yolu yoktu ve soguma kapisi
                        # (`aday_sogumada_mi`) tam da bu alani okuyor.
                        "aday_basligi": aday.baslik if aday else None,
                        "topic": rejected_topic,
                        "visual_anchor": plan.visual_anchor,
                        "task_id": None,
                        "visual_alignment_score": review.visual_alignment_score,
                        "issues": review.issues,
                        "agir_kusurlar": review.agir_kusurlar,
                        "sahneler": sahne_kaydi(plan, exc.credits),
                        "rejected_at": datetime.now(ZoneInfo(TIMEZONE_NAME)).isoformat(),
                    }
                )
                save_state(state)
                if attempt < 3:
                    try:
                        plan = generate_content_plan(
                            exclusions,
                            konu=etkin_konu,
                            sahne_sayisi=sahne_sayisi,
                            bicim=bicim,
                            capa_tekrari_serbest=capa_serbest,
                        )
                    except DistinctTopicUnavailableError as planning_error:
                        reviews.append(
                            {
                                "stage": "planning",
                                "topic": "",
                                "visual_anchor": "",
                                "task_id": None,
                                "review": asdict(
                                    QualityReview(
                                        False, 0, 100, [str(planning_error)], []
                                    )
                                ),
                                "video": "",
                            }
                        )
                        break
                continue
            # ⚠️ Sahne degil KARE sayisi: sahne basina iki kare var ve
            # sahneye gore ornekleyen montaj her sahnenin TAM ORTASINDAN
            # kare alirdi — yani iki gorselin EK YERINDEN.
            montage = create_review_montage(
                video_path, task_id, len(plan.scenes) * bicim.kare_yuvasi, bicim=bicim
            )
            review = review_video(plan, montage, bicim=bicim)
            reviews.append(
                {
                    "topic": plan.topic,
                    "task_id": task_id,
                    "review": asdict(review),
                    "video": str(video_path),
                }
            )
            if should_publish(review):
                selected = (task_id, video_path, script_path, review, credits)
                break
            if should_abandon_topic(review):
                rejected_topic = plan.topic
                exclusions.extend([rejected_topic, plan.visual_anchor])
                state.setdefault("rejected", []).append(
                    {
                        "stage": "video",
                        "slot": slot,
                        "kaynak": kaynak,
                        # Gerekce yukaridaki kaynak asamasi kaydinda.
                        "aday_basligi": aday.baslik if aday else None,
                        "topic": rejected_topic,
                        "visual_anchor": plan.visual_anchor,
                        "task_id": task_id,
                        "visual_alignment_score": review.visual_alignment_score,
                        "subtitle_readability_score": review.subtitle_readability_score,
                        "issues": review.issues,
                        "agir_kusurlar": review.agir_kusurlar,
                        "sahneler": sahne_kaydi(plan, credits),
                        "rejected_at": datetime.now(ZoneInfo(TIMEZONE_NAME)).isoformat(),
                    }
                )
                save_state(state)
                if attempt < 3:
                    try:
                        plan = generate_content_plan(
                            exclusions,
                            konu=etkin_konu,
                            sahne_sayisi=sahne_sayisi,
                            bicim=bicim,
                            capa_tekrari_serbest=capa_serbest,
                        )
                    except DistinctTopicUnavailableError as planning_error:
                        reviews.append(
                            {
                                "stage": "planning",
                                "topic": "",
                                "visual_anchor": "",
                                "task_id": None,
                                "review": asdict(
                                    QualityReview(
                                        False, 0, 100, [str(planning_error)], []
                                    )
                                ),
                                "video": "",
                            }
                        )
                        break
            else:
                # ⚠️ ONCE KAREYI ONAR. Hakem hangi karenin bozuk oldugunu
                # zaten soyluyor; videoyu bastan uretmek yerine o karenin
                # gorselini degistirmek hem ucuz hem de olculmus kazanc:
                # Roman Dodecahedron 89 aldi ve sekiz karenin YEDISI temizdi.
                # Gerekce `kareyi_onar` docstring'inde.
                # ⚠️ `ornekler` SART: uzun formatta hakem yalnizca 12 kare
                # goruyor ve "kare 7" dedigi sey videonun 7. karesi degil,
                # orneklemin 7. elemani. Gecirilmezse her onarim YANLIS
                # sahnenin gorselini degistirir (bkz. `hakem_karesinden_sahne`).
                if onarilan := kareyi_onar(
                    plan,
                    review,
                    etkin_konu or "",
                    bicim=bicim,
                    ornekler=hakem_kareleri(
                        len(plan.scenes) * bicim.kare_yuvasi, bicim
                    ),
                ):
                    print(
                        f"ℹ️ kare onarımı: sahne {onarilan} görseli menüden değiştirildi",
                        flush=True,
                    )
                else:
                    plan = refine_search_terms(plan, review, bicim=bicim)

        if not selected:
            result = {"status": "rejected", "slot": slot, "topic": plan.topic, "reviews": reviews}
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            (LOG_DIR / f"{slot}-rejected.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return result

        task_id, video_path, _, review, credits = selected
        credits_text = format_commons_credits(credits)
        # ⚠️ Seri imzasi EN USTTE. Gerekcesi `SERI_IMZASI`nda: dagitim
        # calisiyor ama donusum calismiyor ve izleyicinin gordugu hicbir
        # yerde kanalin ne yaptigi yazmiyordu. YouTube aciklamanin yalnizca
        # ilk satirlarini katlanmamis gosteriyor, o yuzden alta koymak
        # yazmamakla ayni sey.
        # ⚠️ Kirpma YUKLEMEDEN once. Uzun formatta 24-45 kunye satiri
        # aciklamayi YouTube'un 5.000 karakter sinirinin ustune tasiyor ve
        # `videos.insert` 400 doner — render ile iki kalite kapisindan SONRA,
        # yani en pahali anda. Gerekce `aciklamayi_kirp`ta.
        description = aciklamayi_kirp(
            f"{SERI_IMZASI}\n\n{plan.description}", credits_text
        )
        if dry_run:
            url = ""
            status = "dry-run"
        else:
            if not_before:
                _wait_until_not_before(not_before)
            url = upload_video(video_path, plan.title, description, plan.tags, privacy)
            status = "published"

        record = {
            "slot": slot,
            "status": status,
            # Hangi kip uretti: huni adayi mi, model-secimli yedek mi.
            # Arayuz ve `uretim rapor` bu alanla kirilim yapiyor.
            "kaynak": kaynak,
            # Hangi Notion adayi bu videoyu uretti. Red kayitlarindaki ayni
            # alanla eslesiyor, yani bir adayin kac deneme sonunda tuttugu
            # geriye donuk sayilabiliyor.
            "aday_basligi": aday.baslik if aday else None,
            # ⚠️ DENEY KOLU. Sahne sayisi, klip suresini (`ses ÷ sahne`) ve
            # dolayisiyla ilk kesmenin ne zaman geldigini belirliyor. Bu alan
            # yazilmazsa hangi videonun hangi kolda oldugu SONRADAN
            # bilinemez ve tutunma karsilastirmasi yapilamaz — ayni korluk
            # bu oturumda bir kez yasandi (sahne duzeyi telemetri yoktu).
            "sahne_sayisi": len(plan.scenes),
            # ⚠️ Sahne basina kac kare yuvasi ve kacinda IKI AYRI gorsel
            # oldugu. Yazilmazsa hangi videonun hangi duzende uretildigi
            # sonradan bilinemez — ayni korluk sahne sayisi deneyinde bir
            # kez yasandi ve kollar geriye donuk ayirt edilemedi.
            # ⚠️ HANGI KOL. Yazilmazsa izlenme saati raporunda uzun videoyla
            # Short'u ayirt etmek imkansiz olur — ve uzun formatin varlik
            # sebebi tam olarak o saatler, yani olcemezsek denemeyi
            # degerlendiremeyiz. Ayni korluk sahne sayisi deneyinde bir kez
            # yasandi ve kollar geriye donuk ayirt edilemedi.
            "bicim": bicim.ad,
            "kare_duzeni": bicim.kare_yuvasi,
            "iki_gorselli_sahne": tam_dolan_sahne,
            "topic": plan.topic,
            "visual_anchor": plan.visual_anchor,
            "title": plan.title,
            # Bir sonraki kosum bunu okuyup ayni acilisi tekrarlamayacak.
            # Kaydedilmezse `_son_kancalar` hep bos doner ve kalip kirilmaz.
            "hook": kanca(plan.script),
            # Kancanin ikizi: `_son_kapanislar` bunu okuyup ayni kapanisi
            # tekrarlatmiyor. Yazilmazsa kapanis kapisi hep bos liste gorur
            # ve hicbir seyi engellemez.
            "kapanis": kapanis(plan.script),
            # ⚠️ TELEMETRI, kapi degil. Kanca (ilk cumle) ve kapanis (son
            # cumle) olculuyor; ARADAKI 4-8 cumle icin hicbir tekrar olcusu
            # yok — ve senaryo kaydedilmedigi icin GERIYE DONUK olcmek de
            # mumkun degildi. Once kaydet, kapiyi veri birikince kur: bu
            # oturumda agir kusur kapisinda tam tersi yapildi ve o alan
            # kayitlarda hic olmadan "olculdu" denmisti.
            "script": plan.script,
            "url": url,
            "task_id": task_id,
            "video_path": str(video_path),
            "quality": asdict(review),
            "published_at": datetime.now(ZoneInfo(TIMEZONE_NAME)).isoformat(),
        }
        if not dry_run:
            state.setdefault("completed_slots", []).append(slot)
            state.setdefault("published", []).append(record)
            save_state(state)
        if aday is not None and url:
            notion_kuyrugu.adayi_kapat(
                aday,
                video_url=url,
                uretim_notu=f"görsel uyum {review.visual_alignment_score}/100",
                ytoto_path=YTOTO_PATH,
            )
            aday_kapatildi = True
        # Onceki kosumlarin artiklari — bu kosumunkiler DURUYOR (montaja ve
        # sahne gorsellerine cikan videoya bakarken ihtiyac var). Boylece
        # diskte her zaman en fazla tek kosumluk artik kaliyor.
        try:
            bosalan = temizlik.kosum_sonrasi_temizle(task_id, f"{slot}-attempt-1")
            record["temizlenen_bayt"] = bosalan
        except temizlik.TemizlikHatasi as hata:
            # Temizlik bir YAN IS. Basarisiz olmasi, uretilmis ve yayinlanmis
            # bir videoyu raporlanmamis hale getirmemeli.
            record["temizlik_hatasi"] = str(hata)
        return record
    finally:
        LOCK_FILE.unlink(missing_ok=True)
        # Kapmanin karsiligi TEK yerde: hangi cikis yolundan donulurse
        # donulsun (planlama hatasi, red, beklenmedik istisna) aday kuyruga
        # geri konur. Her `return`'e ayri ayri yazilsaydi biri unutulur ve o
        # yol adayi `Uretiliyor`da birakirdi — sessizce, kimse gormeden.
        if aday is not None and not aday_kapatildi:
            notion_kuyrugu.adayi_birak(
                aday,
                gerekce=f"{slot} koşumu video üretemedi; kuyruğa geri kondu",
                ytoto_path=YTOTO_PATH,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate, review, and publish one YouTube Short")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public")
    parser.add_argument("--not-before", metavar="HH:MM")
    parser.add_argument(
        "--from-notion",
        action="store_true",
        help=(
            "Konuyu trend hunisinden al (`Seçildi` kuyruğu). Aday yoksa koşum "
            "durur; modelin kendi konusuna DÜŞMEZ (bkz. --yedek-konu)."
        ),
    )
    parser.add_argument(
        "--yedek-konu",
        action="store_true",
        help=(
            "Kuyruk boşsa modelin seçtiği anıt/yer konusuyla üret. Geri düşüş "
            "koşum kaydına `kaynak: yedek` diye yazılır ve stdout'a basılır; "
            "bayrak verilmezse davranış değişmez ve koşum durur."
        ),
    )
    parser.add_argument(
        "--sahne-sayisi",
        type=int,
        metavar="N",
        help=(
            "Sahne sayısını tam olarak N yap (varsayılan: model 6-10 arasında "
            "seçer). Klip süresi `ses ÷ sahne` olduğu için bu, ilk kesmenin ne "
            "zaman geldiğini belirler; tutunma deneyinin kolu budur."
        ),
    )
    parser.add_argument(
        "--uzun",
        action="store_true",
        help=(
            "8-13 dakikalık YATAY belgesel üret (varsayılan: dikey Shorts). "
            "İzlenme saati yalnızca bu koldan geliyor; Shorts saymıyor. Konu "
            "zorunlu (--from-notion ya da --konu) ve arşiv 24 görselden azsa "
            "koşum sessizce Shorts'a düşer."
        ),
    )
    parser.add_argument(
        "--konu",
        metavar="METİN",
        help=(
            "Konuyu doğrudan ver (kuyruğa sorma). Kullanım yeri ölçülmüş: "
            "kanalın en çok izlenen videoları talebi KANITLANMIŞ konular ve "
            "huni onları `benzeri üretilmiş` diye yeniden önermiyor, yani "
            "uzun formatta yeniden ele almanın tek yolu bu. Çapa tekrarı bu "
            "kipte serbest — aynı çapa zaten istenen şey."
        ),
    )
    args = parser.parse_args()
    if args.sahne_sayisi is not None and not 6 <= args.sahne_sayisi <= 10:
        parser.error("--sahne-sayisi 6 ile 10 arasında olmalı")
    bicim = UZUN_BICIMI if args.uzun else SHORTS_BICIMI
    # ⚠️ Sart olan sey Notion DEGIL, KONUNUN VERILMIS olmasi: kaynak metin ve
    # arsiv menusu ancak konu varken isteme giriyor, yani konusuz uzun plan
    # 2.000 kelimeyi hafizadan yazar (DW-114 riski, kelime SAYISIYLA
    # olcekleniyor). `--konu` bu kosulu birebir sagliyor.
    if args.uzun and not (args.from_notion or args.konu):
        parser.error(
            "--uzun için --from-notion ya da --konu gerekli: "
            "konusuz uzun plan uydurma riski taşır"
        )
    if args.konu and args.from_notion:
        parser.error("--konu ile --from-notion birlikte kullanılamaz")
    if args.uzun and args.sahne_sayisi is not None:
        parser.error("--uzun ile --sahne-sayisi birlikte kullanılamaz (deney Shorts koluna ait)")
    result = run_cycle(
        dry_run=args.dry_run,
        privacy=args.privacy,
        not_before=args.not_before,
        kuyruktan=args.from_notion,
        yedek_konu=args.yedek_konu,
        sahne_sayisi=args.sahne_sayisi,
        bicim=bicim,
        konu_override=args.konu,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "rejected":
        raise SystemExit(2)
    # Bos kuyruk bir hata degil ama basari da degil: cagiran taraf (gece stok
    # surucusu) bunu "uretilecek is yok" diye ayirt edebilmeli.
    if result.get("status") == "no-candidate":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
