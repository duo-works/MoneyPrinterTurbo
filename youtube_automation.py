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
from pathlib import Path
from typing import Any, Callable
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
MIN_VISUAL_SCORE = 80
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
EDITORIAL_ANCHOR_POOL = [
    "Great Sphinx",
    "Moai",
    "Persepolis",
    "Palmyra",
    "Tikal",
    "Chichen Itza",
    "Sacsayhuaman",
    "Newgrange",
    "Notre Dame Cathedral",
    "Chartres Cathedral",
    "Hadrian's Wall",
    "Ellora Caves",
    "Ajanta Caves",
    "Sigiriya",
    "Rani ki Vav",
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
    "Masada",                   # 47
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


@dataclass
class QualityReview:
    publishable: bool
    visual_alignment_score: int
    subtitle_readability_score: int
    issues: list[str] = field(default_factory=list)
    revised_search_terms: list[str] = field(default_factory=list)
    problem_scene_numbers: list[int] = field(default_factory=list)
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
NEVER WRITE A SENTENCE WHOSE SUBJECT IS THE RECORD ITSELF. "No one can reconstruct every transition from this summary alone" and "the record here does not name each turning point" are not narration; they are padding you reach for when you do not know enough about the subject, and no archive image can illustrate them, so that scene is guaranteed to show something unrelated. If you cannot fill a scene with a concrete thing that happened, a named person, a place, an object, or a date, write fewer scenes. Honest uncertainty ABOUT THE WORLD stays welcome ("locals still claim...", "his body was never found").
Every planned scene must be illustratable either by a real view of the visual_anchor or by an honest historical illustration of the moment being described. Scenes may show a specific event, a named person, a discovery, a disappearance, or a legend as long as the narration stays truthful about what is known and what is only told.
TELL A STORY, DO NOT DESCRIBE AN OBJECT. A list of a monument's features is not a video; a specific thing that happened there is. Build every script around one of: a documented event with a beginning and an end, a discovery or a disappearance, a legend or myth the culture itself told about the place, a mystery that is still unsolved, or a person whose fate is tied to the anchor. Name people, dates, and outcomes when they are known.
When a legend or myth is used, say plainly that it is a legend ("the Inca told of...", "locals still claim...") and separate it from the archaeological record. An honest legend is compelling; a legend presented as fact is not.
The subject may be a monument, civilization, artifact, invention, vessel, or site, but the SCRIPT must be about something that happened, not about how the thing was built or how large it is. Dimensions, construction techniques, and material lists belong in a single supporting sentence at most.
Avoid graphic violence, medical misinformation, politics, religion advocacy, copyrighted characters, and uncertain claims.
WRITE THE TITLE AS A SEARCH QUERY, NOT AS A HEADLINE. It must read like the phrase an English-speaking viewer would actually type into YouTube: usually a direct question ("What Happened to...", "Why Did...", "Who Built...") or the named subject followed by the hook. Put the searchable proper noun in the first three words. When a subject has a widely used popular name and a scholarly name, the TITLE takes the popular one because that is what people type; the description carries the scholarly one. Under 65 characters when practical, and contain #Shorts.
What you write in `description` is placed UNDER a fixed one line channel signature that already exists, so do not write a channel description, a signature or a sign off yourself. Your own first sentence still carries the search: restate the title's search phrase as a full sentence naming the place, the people, and the century. Then two or three sentences that deliver the answer the title promised; never leave the question unanswered in the description. Then 3 to 5 hashtags.
END ON A REASON TO COME BACK, NOT ON A SUMMARY. The last sentence is the only moment a viewer decides whether this channel is worth following, and a closing that merely restates the video ("the mystery remains unsolved") gives them nothing. Close instead on what this channel keeps doing: the next thing in the archive, the pattern this story belongs to, the question the next one answers. Say it in the video's own voice and in a different shape every time; never write "subscribe", "follow", "like and comment" or any other stock call to action, and never repeat a closing line you have used before.
NEVER USE A DASH CHARACTER ANYWHERE IN THE SCRIPT OR THE SCENE NARRATION: no em dash, no en dash, no hyphen. Rephrase instead: write "single handedly", not "single-handedly"; use a comma or a full stop where you would reach for an em dash; write year ranges as "1652 to 1674". Titles and tags may keep an ordinary hyphen inside a proper name.
Tags must be an array of 6-10 concise strings mixing three kinds: exact named entities including the subject's alternative and popular spellings, broad category terms an interested viewer browses ("ancient history", "archaeology", "lost civilization"), and one format term. Tags are search terms, not a summary; never write a phrase nobody would type into a search box.
JSON keys: topic, visual_anchor, title, script, scenes, description, tags."""
"""Sozlesmenin geri kalani — kanal kimliginden AYRI tutuluyor.

⚠️ Ikisi de modul duzeyinde sabit. Testler eskiden prompt'u KAYNAK
METNINDEN dilimliyordu (`index("You are the editorial producer")` ile bir
sonraki uc-tirnak arasi). Kimlik ayri bir sabite tasininca o dilim koptu ve
11 test dustu — kusur promptta degil, testin onu okuma bicimindeydi.
"""


def editoryal_sistem_yonergesi() -> str:
    """Modele giden tam sistem yonergesi. Testler bunu okur, kaynagi degil."""
    return KANAL_SESI + EDITORYAL_YONERGE

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


def validate_content_plan(plan: ContentPlan, sahne_sayisi: int | None = None) -> None:
    word_count = len(re.findall(r"\b[\w'-]+\b", plan.script))
    if kusur := kanca_kusuru(plan.script):
        raise ValueError(kusur)
    if not 80 <= word_count <= 120:
        raise ValueError(f"script must contain 80-120 words, got {word_count}")
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
    elif not 6 <= len(plan.scenes) <= 10:
        raise ValueError("content plan must contain 6-10 scenes")
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
    if len(plan.title) > 100:
        raise ValueError("YouTube title must be at most 100 characters")
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
    raise ValueError("CLI output did not contain a complete JSON object")


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


def agir_kusurlu_kareler(review: QualityReview) -> list[int]:
    """Agir kusur metinlerinden kare numaralarini cikarir ("kare 6: ...")."""
    numaralar = {
        int(eslesme.group(1))
        for kusur in review.agir_kusurlar
        if (eslesme := re.match(r"kare (\d+):", kusur))
    }
    return sorted(numaralar)


def kareyi_onar(
    plan: ContentPlan, review: QualityReview, menu_konusu: str = ""
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
    """
    bozuk = agir_kusurlu_kareler(review)
    bozuk = [n for n in bozuk if 1 <= n <= len(plan.scenes)]
    if not bozuk:
        return []
    menu = arsiv_envanteri(menu_konusu.strip() or plan.visual_anchor)
    if not menu:
        return []
    kullanilan = {str(sahne.get("kaynak_dosya", "")).strip() for sahne in plan.scenes}
    aday_menu = [girdi for girdi in menu if girdi["dosya"] not in kullanilan]
    if not aday_menu:
        return []
    gecerli = {girdi["dosya"] for girdi in aday_menu}
    kusur_metni = {n: [] for n in bozuk}
    for kusur in review.agir_kusurlar:
        if eslesme := re.match(r"kare (\d+): (.+)", kusur):
            numara = int(eslesme.group(1))
            if numara in kusur_metni:
                kusur_metni[numara].append(eslesme.group(2))
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
        plan.scenes[numara - 1]["kaynak_dosya"] = dosya
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
    secenekler: list[str] | None = None, gecmis_yolu: Path | None = None
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
    uygun = [ad for ad in havuz if ad not in yakinda_kullanilan] or list(havuz)
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


def _json_completion(system: str, user: str) -> dict[str, Any]:
    if INFERENCE_BACKEND == "hermes-cli":
        prompt = (
            f"SYSTEM INSTRUCTIONS:\n{system}\n\n"
            f"USER REQUEST:\n{user}\n\n"
            "Return the requested JSON object only, with no markdown fences or commentary."
        )
        result = _run_hermes(
            ["hermes", "--ignore-rules", "--safe-mode", "-z", prompt], 180
        )
        if result.returncode:
            raise RuntimeError(
                f"Hermes CLI text inference failed with exit code {result.returncode}"
            )
        return parse_cli_result(result.stdout)
    if INFERENCE_BACKEND != "openai":
        raise RuntimeError(f"unsupported inference backend: {INFERENCE_BACKEND}")
    client, model = _openai_client()
    response = client.chat.completions.create(
        model=model,
        temperature=0.65,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    content = response.choices[0].message.content or ""
    return json.loads(content)


def _vision_json(prompt: dict[str, Any], image_path: Path) -> dict[str, Any]:
    if INFERENCE_BACKEND == "hermes-cli":
        query = (
            json.dumps(prompt, ensure_ascii=False)
            + "\nReturn the requested JSON object only, with no markdown fences or commentary."
        )
        result = _run_hermes(
            [
                "hermes",
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
            360,
        )
        if result.returncode:
            raise RuntimeError(
                f"Hermes CLI vision inference failed with exit code {result.returncode}"
            )
        return parse_cli_result(result.stdout)
    if INFERENCE_BACKEND != "openai":
        raise RuntimeError(f"unsupported inference backend: {INFERENCE_BACKEND}")
    client, model = _openai_client()
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
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
    )
    return json.loads(response.choices[0].message.content or "{}")


def _recent_titles() -> list[str]:
    titles: list[str] = []
    state = load_state()
    titles.extend(item.get("topic", "") for item in state.get("published", []))
    titles.extend(item.get("title", "") for item in state.get("published", []))
    titles.extend(item.get("visual_anchor", "") for item in state.get("published", []))
    titles.extend(item.get("topic", "") for item in state.get("rejected", []))
    titles.extend(item.get("visual_anchor", "") for item in state.get("rejected", []))
    if ANALYSIS_FILE.exists():
        analysis = json.loads(ANALYSIS_FILE.read_text(encoding="utf-8"))
        titles.extend(item.get("title", "") for item in analysis.get("all_shorts", []))
    return [title for title in titles if title]


SERI_IMZASI = (
    "Shemz — short documentaries built from public domain archives, "
    "one forgotten story at a time."
)
"""Aciklamanin ilk satiri: kanalin NE OLDUGUNU soyleyen sabit cumle.

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


KAPANIS_ORTUSME_ORANI = 0.6
"""Kapanis, onceki bir kapanisla bu orandan fazla kelime paylasirsa tekrar.

⚠️ Bu esik SECILDI, olculmedi — kapanislar yeni kaydedilmeye basladi ve
karsilastirilacak gecmis henuz yok. Veri birikince `kanal_rapor.py` ile
gozden gecirilmeli. Burada yazili olmasi, ileride "bu sayi nereden geldi"
sorusunun cevapsiz kalmamasi icin.
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
    kelimeler = _normalize_topic(kapanis_metni)
    if len(kelimeler) < 3:
        # Cok kisa kapanista ortusme orani gurultu; olcmeye degmez.
        return False
    for onceki in onceki_kapanislar:
        oncekiler = _normalize_topic(onceki or "")
        if not oncekiler:
            continue
        ortak = kelimeler & oncekiler
        if len(ortak) / min(len(kelimeler), len(oncekiler)) >= KAPANIS_ORTUSME_ORANI:
            return True
    return False


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
    # ⚠️ "diger" bir kalip degil, siniflandiramadigimiz sey. Onu tekrar
    # saymak birbirinden tamamen farkli iki basligi reddederdi.
    if bicim == "diger" or not onceki_basliklar:
        return False
    return any(_baslik_bicimi(onceki) == bicim for onceki in onceki_basliklar)


ARSIV_ENVANTER_SINIRI = 40
"""Menude en fazla kac dosya gosterilecek.

Havuzun tamami degil, `_kategori_adaylari` siralamasinin tepesi: model
secim yapabilsin diye genis, isteme sigsin diye sinirli. Olculdu
(2026-08-14): suzgecten gecen dosya sayisi konu basina 13-40 arasinda,
yani sinir cogu konuda zaten baglayici degil.
"""

_ENVANTER_ONBELLEGI: dict[str, list[dict[str, str]]] = {}
ACIKLAMA_SINIRI = 140


def arsiv_envanteri(konu: str, *, sinir: int = ARSIV_ENVANTER_SINIRI) -> list[dict[str, str]]:
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
    anahtar = konu.strip().casefold()
    if anahtar in _ENVANTER_ONBELLEGI:
        return _ENVANTER_ONBELLEGI[anahtar]
    try:
        adaylar = wikimedia_materials.arsiv_menusu(konu, sinir=sinir)
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
        menu.append(
            {
                "dosya": dosya,
                "gosterdigi": str(aday.get("aciklama") or "")[:ACIKLAMA_SINIRI],
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


def _menu_talimati(menu: list[dict[str, str]]) -> str:
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
        "different entry for every scene. Do not narrate a moment no entry depicts: if "
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


def alinti_kusuru(plan: ContentPlan, menu_konusu: str = "") -> str:
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
    menu = arsiv_envanteri(menu_konusu.strip() or plan.visual_anchor)
    if not menu:
        return ""
    if len(menu) < len(plan.scenes):
        return (
            f"the archive holds only {len(menu)} usable images for "
            f"{plan.visual_anchor!r}, fewer than the {len(plan.scenes)} scenes this "
            "plan needs. Anchor the video on a different concrete thing that archives "
            "actually photographed, and build the script around that."
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
    return ""


def generate_content_plan(
    extra_exclusions: list[str] | None = None,
    konu: str | None = None,
    sahne_sayisi: int | None = None,
) -> ContentPlan:
    """Video planini uretir; `konu` verilirse KONUYU SECMEZ, verileni isler.

    `konu` disaridan geldiginde (trend hunisinden, DW-89) benzerlik kontrolu
    uygulanmaz. Sebep: bu konuyu model degil, olculmus talep verisi ve onu
    onaylayan insan sectI. "Cok benziyor" diye reddetmek, insanin kararini
    modelin cagrisimina feda etmek olurdu.

    Bu ayrimin bedeli olculdu: 6 Agustos gecesi uretilen 6 videonun konusunu
    model kendi havuzundan sectI ve ayni gecede iki Roma muhendisligi videosu
    cikti. Huni beslemesinin varlik sebebi bu.
    """
    previous = _recent_titles() + list(extra_exclusions or [])
    state = load_state()
    previous_anchors = [
        str(item.get("visual_anchor", ""))
        for collection in (state.get("published", []), state.get("rejected", []))
        for item in collection
        if str(item.get("visual_anchor", "")).strip()
    ]
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
    system = editoryal_sistem_yonergesi()
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
        if kaynak := wikimedia_materials.vikipedi_ozeti(konu):
            user += (
                "\n\nAUTHORITATIVE SOURCE — this is the Wikipedia summary of the subject. "
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
            user += (
                "\n\nNo encyclopedia summary could be retrieved for this subject. Write only "
                "what you are confident is true of THIS specific subject and keep the claims "
                "few and general. Do not invent names, dates, professions or events to fill "
                "the script, and do not fill it with sentences about the record being thin "
                "either: write fewer scenes about what you do know."
            )
        # ⚠️ ARSIV MENUSU — gerekcesi `arsiv_envanteri`nde. Kaynak metni
        # modele NE ANLATACAGINI soyluyor; bu liste NEYI GOSTEREBILECEGINI.
        # Ikisi ayri bilgi ve ikisi de eksikse model tahmin ediyor.
        if envanter := arsiv_envanteri(konu):
            user += _menu_talimati(envanter)
    else:
        user = (
            "Create one new video plan. Do not repeat or closely paraphrase these existing topics/titles:\n"
            + json.dumps(previous[-50:], ensure_ascii=False)
            + "\nNever reuse any of these concrete visual anchors:\n"
            + json.dumps(previous_anchors, ensure_ascii=False)
            + "\nChoose the visual_anchor from this unused editorial shortlist when it is non-empty:\n"
            + json.dumps(eligible_anchors, ensure_ascii=False)
            + "\nPreferred content pillars: ancient engineering, surviving historic places, ingenious inventions, archaeology, navigation, strange verified events, and visible historical mysteries."
        )

    # Sahne sayisi sabitlendiyse istem de bunu SOYLEMELI: yalnizca
    # dogrulamaya birakmak, modelin 8 yazip her seferinde reddedilmesi ve
    # bes denemenin bosa gitmesi demek olurdu.
    if sahne_sayisi is not None:
        user += (
            f"\nThis video must have EXACTLY {sahne_sayisi} scenes, not more and not "
            "fewer. Fit the story to that number: fewer scenes means each one is on "
            "screen longer, so give each a distinct thing to show."
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
    for deneme in range(1, 6):
        yumusak_kapilar_acik = deneme <= YUMUSAK_KAPI_DENEMESI
        data = _json_completion(system, user)
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
                }
                for scene in data.get("scenes", [])
                if isinstance(scene, dict)
            ],
            description=tiresiz_baslik(str(data.get("description", "")).strip()),
            tags=[str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()],
        )
        for scene in plan.scenes:
            scene["search_term"] = _ensure_visual_anchor(
                scene["search_term"], plan.visual_anchor
            )
        try:
            validate_content_plan(plan, sahne_sayisi)
        except ValueError as exc:
            user += (
                "\nThe last JSON plan was invalid: "
                f"{exc}. Return a completely corrected plan that follows every constraint."
            )
            continue
        # ⚠️ HER IKI KIPTE de calisiyor. Huni kipinde menu zaten isteme
        # veriliyor; yedek kipte capayi model sectigi icin menu istemde HIC
        # yok ve ancak bu kapinin geri bildirimiyle geliyor. Gerekce
        # `alinti_kusuru` docstring'inde.
        if yumusak_kapilar_acik and (kusur := alinti_kusuru(plan, konu or "")):
            user += f"\nThe last plan did not match the archive: {kusur}"
            continue
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
            user += (
                "\nThe title repeats the shape of a recent one. Keep it a search query, "
                "but change the shape: a different question word, or a statement that "
                "names the surprising fact instead of asking about it."
            )
            continue
        if yumusak_kapilar_acik and _kanca_tekrari(plan.script, onceki_kancalar):
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
            if yumusak_kapilar_acik and is_duplicate_visual_anchor(
                plan.visual_anchor, previous_anchors
            ):
                user += (
                    f"\nThe visual anchor {plan.visual_anchor!r} was already used on this "
                    "channel. Keep the same subject but anchor the video on a different "
                    "concrete thing belonging to it."
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
    raise DistinctTopicUnavailableError(
        "could not generate a sufficiently distinct topic"
    )


def refine_search_terms(plan: ContentPlan, review: QualityReview) -> ContentPlan:
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
    validate_content_plan(plan)
    return plan


SHORTS_EN = 1080
SHORTS_BOY = 1920
"""Shorts karesi. Kaynak gorseller buna getirilmezse ekranin bir kismi siyah kalir."""

# Merkezden kirpma bu orandan fazlasini atacaksa kirpmak yerine bulanik arka
# plan kullanilir. 0.35 olculerek secildi: 2:3 AI gorselleri %16 kirpiliyor
# (sorunsuz), 16:9 arsiv fotograflari %68 kirpilirdi ve konu kadraj disinda
# kalirdi — bir akveduktun yalnizca bir kemeri gorunurdu.
AZAMI_KIRPMA = 0.35


def dikeye_uydur(kaynak: Path, hedef: Path) -> Path:
    """Gorseli 1080x1920'ye getirir — siyah bant birakmadan.

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
    """
    from PIL import ImageFilter

    with Image.open(kaynak) as ham:
        gorsel = ham.convert("RGB")
        en, boy = gorsel.size
        hedef_oran = SHORTS_EN / SHORTS_BOY
        oran = en / boy

        # Kirp-doldur uygulanirsa kaynagin ne kadari atilir?
        if oran > hedef_oran:
            kalan = (boy * hedef_oran) / en  # genislikten kirpilir
        else:
            kalan = (en / hedef_oran) / boy  # yukseklikten kirpilir
        kirpma = 1 - kalan

        if kirpma <= AZAMI_KIRPMA:
            sonuc = ImageOps.fit(
                gorsel, (SHORTS_EN, SHORTS_BOY), method=Image.Resampling.LANCZOS
            )
        else:
            arka = ImageOps.fit(
                gorsel, (SHORTS_EN, SHORTS_BOY), method=Image.Resampling.LANCZOS
            ).filter(ImageFilter.GaussianBlur(radius=40))
            on = ImageOps.contain(
                gorsel, (SHORTS_EN, SHORTS_BOY), method=Image.Resampling.LANCZOS
            )
            arka.paste(
                on,
                ((SHORTS_EN - on.width) // 2, (SHORTS_BOY - on.height) // 2),
            )
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


def create_source_montage(
    material_files: list[Path], attempt: int, konu: str = ""
) -> Path:
    # ⚠️ `konu` isteğe bagli ama uretimde HER ZAMAN veriliyor (DW-119):
    # materyal klasoru gibi bu dosya adi da saat anahtarliydi ve ayni saatte
    # uretilen ikinci video birincinin kontak sayfasini eziyordu. Hakemin ne
    # gorup ne onayladigi geriye donuk incelenemiyordu.
    if not material_files:
        raise ValueError("source montage requires at least one image")
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    columns = 4
    cell_width, cell_height = 400, 300
    rows = (len(material_files) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_width, rows * cell_height), "black")
    for index, path in enumerate(material_files, 1):
        with Image.open(path) as source:
            tile = ImageOps.fit(
                source.convert("RGB"),
                (cell_width, cell_height),
                method=Image.Resampling.LANCZOS,
            )
        draw = ImageDraw.Draw(tile)
        draw.rectangle((0, 0, 54, 34), fill="black")
        draw.text((12, 8), str(index), fill="white")
        canvas.paste(tile, (((index - 1) % columns) * cell_width, ((index - 1) // columns) * cell_height))
    ayirt_edici = f"-{konu_slug(konu)}" if konu else ""
    montage = (
        REVIEW_DIR
        / f"source-{publication_slot_key()}{ayirt_edici}-attempt-{attempt}.jpg"
    )
    canvas.save(montage, format="JPEG", quality=90)
    return montage


def review_source_materials(plan: ContentPlan, montage: Path) -> QualityReview:
    prompt = {
        "topic": plan.topic,
        "visual_anchor": plan.visual_anchor,
        "scenes": plan.scenes,
        "instructions": (
            "Review this numbered source-image contact sheet before video rendering. "
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
        ),
    }
    data = _vision_json(prompt, montage)
    gorsel_skor = int(data.get("visual_alignment_score", 0))
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
        problem_scene_numbers=[
            int(number)
            for number in data.get("problem_scene_numbers", [])
            if str(number).isdigit() and 1 <= int(number) <= len(plan.scenes)
        ],
    )


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
"""Ses olculemediginde kullanilan sure — eski sabit davranis."""

KLIP_PAYI = 1.02
"""Klip suresine eklenen kucuk pay.

Neden 1,02: `n × klip >= ses` olmali (yoksa MPT acigi kapatmak icin bastan bir
klibi TEKRAR ediyor) ama ayni anda `(n-1) × klip < ses` olmali (yoksa dongu
sure dolunca erken kirilir ve SON SAHNE videoya hic girmez). Pay `p` icin ikinci
kosul `p·(n-1)/n < 1`, yani `n < p/(p-1)`; %2 payda `n < 51` — sahne sayisi
6-10 oldugu icin fazlasiyla guvenli. MPT'nin ses suresine ekledigi 0,10 sn
emniyet payi da kapsanir (`0,02 × ses >= 0,10` → ses >= 5 sn; bizim videolar
~36 sn).
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


def klip_suresi(ses_saniye: float, sahne_sayisi: int) -> float:
    """Her sahnenin ekranda kalacagi sure.

    ⚠️ Olculdu (2026-08-09, Mohenjo-Daro): 7 sahne × 5 sn = 35,00 sn, ses
    35,88 sn. MPT acigi `itertools.cycle` ile TAM bir klip ekleyerek kapatiyor,
    yani video SAHNE 1'IN TEKRARIYLA bitiyordu: kapanis cumlesi ("the unanswered
    questions linger") geri donusturulmus acilis karesine dusuyordu. Son alti
    kosumun ucunde ayni sey var.

    Sabit 5 sn yerine sure sahne sayisina bolunuyor, boylece hem tekrar hem de
    son sahnenin dusmesi imkansiz hale geliyor (bkz. `KLIP_PAYI`).
    """
    if ses_saniye <= 0 or sahne_sayisi <= 0:
        return float(VARSAYILAN_KLIP_SURESI)
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
    plan: ContentPlan, attempt: int
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
        material_files, credits = download_scene_materials(
            plan.topic,
            plan.scenes,
            material_dir,
            visual_anchor=plan.visual_anchor,
            # AI yedegi acikken tek eksik sahne yuzunden butun arsivi atmak
            # yanlis: bulunan gercek fotograflar korunur, yalnizca delikler
            # AI ile doldurulur (DW-97).
            kismi=AI_VISUAL_FALLBACK_ENABLED,
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
    source_montage = create_source_montage(material_files, attempt, plan.topic)
    source_review = review_source_materials(plan, source_montage)
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
            refined_plan = refine_search_terms(plan, source_review)
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
                source_montage = create_source_montage(material_files, attempt, plan.topic)
                source_review = review_source_materials(plan, source_montage)
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
        source_montage = create_source_montage(material_files, attempt, plan.topic)
        source_review = review_source_materials(plan, source_montage)
    if (
        not source_review.publishable
        or source_review.visual_alignment_score < MIN_SOURCE_VISUAL_SCORE
    ):
        raise SourceMaterialRejected(source_review, credits)

    # ⚠️ Render'dan HEMEN once, kalite kapisindan SONRA. Sira bilincli: kapi
    # kaynak gorselin kendisini degerlendirmeli, kirpilmis halini degil. Ama
    # render'a giden dosyalar Shorts oraninda olmali, yoksa video servisi
    # siyah bant ekliyor (DW-93).
    material_files = dikeye_uydur_hepsi(material_files, material_dir / "dikey")

    # ⚠️ Klip suresi ARTIK SABIT DEGIL. Sabit 5 sn, sahne sayisi × 5 < ses
    # oldugunda MPT'ye bastan bir klibi tekrar ettiriyordu — gerekce
    # `klip_suresi` docstring'inde.
    ses_saniye = anlatim_suresi(plan.script)
    klip = klip_suresi(ses_saniye, len(plan.scenes))
    print(
        f"anlatim {ses_saniye:.2f} sn · {len(plan.scenes)} sahne · "
        f"klip {klip} sn (toplam {klip * len(plan.scenes):.2f} sn)",
        flush=True,
    )

    # ⚠️ Secim LOGA basiliyor (DW-120). Bu satir olmadigi icin hangi videoda
    # hangi parcanin caldigini ogrenmek ses korelasyonu olcmeyi gerektirdi.
    secilen_muzik = muzik_sec()
    print(f"muzik: {secilen_muzik or 'yok (parca bulunamadi)'}", flush=True)

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
        "9:16",
        "--video-concat-mode",
        "sequential",
        "--video-transition-mode",
        "none",
        "--video-clip-duration",
        str(klip),
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
        # Anlatim onde kalmali: 0.2 CLI varsayilani ve konusma uzerinde muzigi
        # duyulur ama bastirmaz seviyede tutuyor.
        "--bgm-volume",
        "0.2",
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
        "--stroke-width",
        "5",
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
        timeout=1800,
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
    return task_id, video_path, script_path, credits


def montaj_izgarasi(kare_sayisi: int) -> tuple[int, int]:
    """Kare sayisina gore sutun/satir. Iki satir sabit — dikey kareler yan yana."""
    return max(math.ceil(kare_sayisi / 2), 1), 2


def create_review_montage(video_path: Path, task_id: str, scene_count: int) -> Path:
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
    kare_numaralari = [
        max(int(round((sira + 0.5) * klip * fps)), 0) for sira in range(kare_sayisi)
    ]
    secim = "+".join(rf"eq(n\,{numara})" for numara in kare_numaralari)
    sutun, satir = montaj_izgarasi(kare_sayisi)
    command = [
        get_ffmpeg_exe(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"select='{secim}',scale=270:480,tile={sutun}x{satir}",
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


def review_video(plan: ContentPlan, montage: Path) -> QualityReview:
    prompt = {
        "topic": plan.topic,
        "script": plan.script,
        "scenes": plan.scenes,
        "instructions": (
            # ⚠️ Kare sayisi SABIT DEGIL — sahne basina bir kare aliniyor
            # (bkz. `create_review_montage`). Eslemeyi soylemek onemli:
            # soylenmediginde hakem ayni sahnenin iki ornegini "duplicate"
            # sanip skoru dusuruyordu.
            f"The image is a {len(plan.scenes)}-frame chronological montage from a vertical "
            "Short, read left to right and top to bottom. There is exactly ONE frame per "
            "scene: frame 1 is scene 1, frame 2 is scene 2, and so on, each sampled from the "
            "middle of its scene. Two frames are therefore never the same scene, and any "
            "trailing blank cell is padding, not a scene. "
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
            '"modern": <true when the frame is a present-day photograph or footage>}. '
            "Answer what you can actually see. A recent photograph of the genuine "
            "surviving object is authentic_subject true and period correct; a recent "
            "photograph of something else entirely is not."
        ),
    }
    data = _vision_json(prompt, montage)
    gorsel_skor = int(data.get("visual_alignment_score", 0))
    altyazi_skor = int(data.get("subtitle_readability_score", 0))
    agir = agir_kusurlari_ayikla(data.get("frames"))
    return QualityReview(
        publishable=yayina_uygun(gorsel_skor, altyazi_skor) and not agir,
        visual_alignment_score=gorsel_skor,
        subtitle_readability_score=altyazi_skor,
        issues=[str(issue) for issue in data.get("issues", [])],
        revised_search_terms=[str(term) for term in data.get("revised_search_terms", [])],
        agir_kusurlar=agir,
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


def _acquire_lock() -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        expired = time.time() - LOCK_FILE.stat().st_mtime > 4 * 3600
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
        if expired or pid_is_dead:
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
    if kuyruktan:
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
        for sirasiyla in adaylar:
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
        try:
            plan = generate_content_plan(
                exclusions,
                konu=aday.baslik if aday else None,
                sahne_sayisi=sahne_sayisi,
            )
        except DistinctTopicUnavailableError as exc:
            reviews.append(
                {
                    "stage": "planning",
                    "topic": "",
                    "visual_anchor": "",
                    "task_id": None,
                    "review": asdict(QualityReview(False, 0, 100, [str(exc)], [])),
                    "video": "",
                }
            )
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
                task_id, video_path, script_path, credits = run_generator(plan, attempt)
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
                            konu=aday.baslik if aday else None,
                            sahne_sayisi=sahne_sayisi,
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
            montage = create_review_montage(video_path, task_id, len(plan.scenes))
            review = review_video(plan, montage)
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
                            konu=aday.baslik if aday else None,
                            sahne_sayisi=sahne_sayisi,
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
                if onarilan := kareyi_onar(
                    plan, review, aday.baslik if aday else ""
                ):
                    print(
                        f"ℹ️ kare onarımı: sahne {onarilan} görseli menüden değiştirildi",
                        flush=True,
                    )
                else:
                    plan = refine_search_terms(plan, review)

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
        description = f"{SERI_IMZASI}\n\n{plan.description}"
        if credits_text:
            description = f"{description}\n\n{credits_text}"
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
            # ⚠️ DENEY KOLU. Sahne sayisi, klip suresini (`ses ÷ sahne`) ve
            # dolayisiyla ilk kesmenin ne zaman geldigini belirliyor. Bu alan
            # yazilmazsa hangi videonun hangi kolda oldugu SONRADAN
            # bilinemez ve tutunma karsilastirmasi yapilamaz — ayni korluk
            # bu oturumda bir kez yasandi (sahne duzeyi telemetri yoktu).
            "sahne_sayisi": len(plan.scenes),
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
    args = parser.parse_args()
    if args.sahne_sayisi is not None and not 6 <= args.sahne_sayisi <= 10:
        parser.error("--sahne-sayisi 6 ile 10 arasında olmalı")
    result = run_cycle(
        dry_run=args.dry_run,
        privacy=args.privacy,
        not_before=args.not_before,
        kuyruktan=args.from_notion,
        yedek_konu=args.yedek_konu,
        sahne_sayisi=args.sahne_sayisi,
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
