from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from imageio_ffmpeg import get_ffmpeg_exe
from moviepy.video.io.VideoFileClip import VideoFileClip
from openai import BadRequestError, OpenAI
from PIL import Image, ImageDraw, ImageOps
import requests

from app.config import config
import gorsel_olcum
import notion_kuyrugu
import temizlik
from wikimedia_materials import MaterialsUnavailableError, download_scene_materials
from youtube_upload import upload_video

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "storage" / "youtube_automation" / "state.json"
LOCK_FILE = ROOT / "storage" / "youtube_automation" / "automation.lock"
LOG_DIR = ROOT / "storage" / "youtube_automation" / "logs"
REVIEW_DIR = ROOT / "storage" / "youtube_automation" / "reviews"
ANALYSIS_FILE = ROOT / "storage" / "channel_analysis" / "latest.json"
TIMEZONE_NAME = "Europe/Istanbul"
MIN_VISUAL_SCORE = 50
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


class SourceMaterialRejected(RuntimeError):
    def __init__(self, review: QualityReview):
        super().__init__("source materials failed the pre-render visual quality gate")
        self.review = review


class AIVisualUnavailableError(RuntimeError):
    pass


class DistinctTopicUnavailableError(RuntimeError):
    pass


def _normalize_topic(value: str) -> set[str]:
    stopwords = {"a", "an", "and", "of", "the", "that", "to", "short", "shorts"}
    words = re.findall(r"[a-z0-9]+", value.lower())
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

THE CHANNEL HAS ONE FIXED EDITORIAL ANGLE, AND EVERY SCRIPT MUST HAVE IT: the gap between what people assume happened and what the surviving evidence actually shows. Not "here are facts about a place" — but "here is what the record says, and it is not what you were told."
Build each script on one of these moves: a widely believed story the evidence contradicts, a mystery where you name what is actually known and where the knowledge stops, a detail so specific it could only come from someone who read the source, or a consequence that outlived the event.
Say what is NOT known, out loud, at least once. "No one has found..." / "The record stops here." Certainty about everything is the signature of a shallow script; naming the edge of the evidence is what a real researcher does and what makes a viewer trust the channel.
Take a position in the final line. Not a summary of what was just said — a judgement, an implication, or a question the evidence leaves open. A script that ends by restating its own middle has no author.
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
NEVER open with "Did you know", "Have you ever wondered", "Imagine a world", or any other stock quiz-show phrasing; an opening that could be pasted onto a different topic is a failed hook. Open instead with the single most surprising concrete detail of THIS subject — a number, an object, a contradiction, or an unfinished action — so the first six words could belong to no other video.
Create 6-10 chronological scenes. Define visual_anchor as a specific named civilization, landmark, artifact, archaeological site, vessel, or invention in 1-4 words. Every scene needs narration and a concrete 3-7 word English Wikimedia Commons search term that repeats at least one distinctive visual_anchor word. Never use abstract terms alone.
Prefer subjects with visual evidence on Wikimedia Commons or Met Open Access — photographs of any era, engravings, archaeological plates, museum scans — but do not reject a strong story because its imagery is thin; scenes without an archive match are illustrated instead. Use the eligible visual-anchor shortlist in the user request rather than defaulting to famous examples from prior plans. Modern colour photographs of a surviving place or object are welcome; generic modern people, factories, vehicles, schools, water systems, maps, or buildings that merely share one broad word with the narration are forbidden.
Every planned scene must be illustratable either by a real view of the visual_anchor or by an honest historical illustration of the moment being described. Scenes may show a specific event, a named person, a discovery, a disappearance, or a legend as long as the narration stays truthful about what is known and what is only told.
TELL A STORY, DO NOT DESCRIBE AN OBJECT. A list of a monument's features is not a video; a specific thing that happened there is. Build every script around one of: a documented event with a beginning and an end, a discovery or a disappearance, a legend or myth the culture itself told about the place, a mystery that is still unsolved, or a person whose fate is tied to the anchor. Name people, dates, and outcomes when they are known.
When a legend or myth is used, say plainly that it is a legend — "the Inca told of...", "locals still claim..." — and separate it from the archaeological record. An honest legend is compelling; a legend presented as fact is not.
The subject may be a monument, civilization, artifact, invention, vessel, or site, but the SCRIPT must be about something that happened, not about how the thing was built or how large it is. Dimensions, construction techniques, and material lists belong in a single supporting sentence at most.
Avoid graphic violence, medical misinformation, politics, religion advocacy, copyrighted characters, and uncertain claims.
WRITE THE TITLE AS A SEARCH QUERY, NOT AS A HEADLINE. It must read like the phrase an English-speaking viewer would actually type into YouTube: usually a direct question ("What Happened to...", "Why Did...", "Who Built...") or the named subject followed by the hook. Put the searchable proper noun in the first three words. When a subject has a widely used popular name and a scholarly name, the TITLE takes the popular one because that is what people type; the description carries the scholarly one. Under 65 characters when practical, and contain #Shorts.
The description's FIRST sentence is what search indexes and what viewers see in results: restate the title's search phrase as a full sentence naming the place, the people, and the century. Then two or three sentences that deliver the answer the title promised — never leave the question unanswered in the description. Then 3-5 hashtags.
Tags must be an array of 6-10 concise strings mixing three kinds: exact named entities including the subject's alternative and popular spellings, broad category terms an interested viewer browses ("ancient history", "archaeology", "lost civilization"), and one format term. Tags are search terms, not a summary — never write a phrase nobody would type into a search box.
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


def validate_content_plan(plan: ContentPlan) -> None:
    word_count = len(re.findall(r"\b[\w'-]+\b", plan.script))
    if kusur := kanca_kusuru(plan.script):
        raise ValueError(kusur)
    if not 80 <= word_count <= 120:
        raise ValueError(f"script must contain 80-120 words, got {word_count}")
    if not 6 <= len(plan.scenes) <= 10:
        raise ValueError("content plan must contain 6-10 scenes")
    if not plan.topic.strip() or not plan.title.strip():
        raise ValueError("topic and title are required")
    anchor_words = _normalize_topic(plan.visual_anchor)
    if not 1 <= len(anchor_words) <= 4:
        raise ValueError("visual anchor must contain 1-4 concrete words")
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
        satirlar.append("• " + " — ".join(p for p in parcalar if p))
    if not satirlar:
        return ""
    baslik = "Images — Wikimedia Commons"
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


def should_publish(review: QualityReview) -> bool:
    # `review.publishable` bilerek OKUNMUYOR: karar skorlardan yeniden
    # turetiliyor ki modelden gelen bir bayrak ileride sessizce geri sizmasin.
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


def kanca(metin: str) -> str:
    """Anlatimin ilk cumlesi — videonun izlenip izlenmeyecegini belirleyen yer."""
    ilk = re.split(r"(?<=[.!?])\s", metin.strip(), maxsplit=1)[0]
    return ilk.strip()


def _son_kancalar(adet: int = 12) -> list[str]:
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


def generate_content_plan(
    extra_exclusions: list[str] | None = None, konu: str | None = None
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

    # Gecmis acilislar HER IKI kipte de veriliyor: konu disaridan gelse bile
    # kanca modelin kalemi ve kalibina saplanabiliyor (DW-94).
    if onceki_kancalar := _son_kancalar():
        user += (
            "\nThese opening lines were already used on this channel. Do not reuse them, "
            "and do not reuse their sentence pattern:\n"
            + json.dumps(onceki_kancalar, ensure_ascii=False)
        )

    for _ in range(5):
        data = _json_completion(system, user)
        plan = ContentPlan(
            topic=str(data.get("topic", "")).strip(),
            visual_anchor=str(data.get("visual_anchor", "")).strip(),
            title=str(data.get("title", "")).strip(),
            script=str(data.get("script", "")).strip(),
            scenes=[
                {
                    "narration": str(scene.get("narration", "")).strip(),
                    "search_term": str(scene.get("search_term", "")).strip(),
                }
                for scene in data.get("scenes", [])
                if isinstance(scene, dict)
            ],
            description=str(data.get("description", "")).strip(),
            tags=[str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()],
        )
        for scene in plan.scenes:
            scene["search_term"] = _ensure_visual_anchor(
                scene["search_term"], plan.visual_anchor
            )
        try:
            validate_content_plan(plan)
        except ValueError as exc:
            user += (
                "\nThe last JSON plan was invalid: "
                f"{exc}. Return a completely corrected plan that follows every constraint."
            )
            continue
        if konu:
            # Benzerlik kapisi atlaniyor — gerekcesi docstring'de. Dogrulama
            # (`validate_content_plan`) yukarida zaten uygulandI.
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


def create_source_montage(material_files: list[Path], attempt: int) -> Path:
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
    montage = REVIEW_DIR / f"source-{publication_slot_key()}-attempt-{attempt}.jpg"
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
        publishable=yayina_uygun(gorsel_skor, 100),
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


def kare_dili(sahne_no: int) -> str:
    """`sahne_no` icin kadraj tarifi (1'den baslar)."""
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
            f"Visual anchor: {plan.visual_anchor}. Scene {index}: {scene.get('narration', '')}. "
            f"Required visible detail: {visual_detail}. "
            # ⚠️ Gorsel dil sahnenin KONUSUNA gore secilir, tek bir estetige
            # sabitlenmez — bkz. `GORSEL_DIL`.
            + GORSEL_DIL
            # ⚠️ Kadraj sahne basina DEGISIYOR. Burada eskiden HER sahneye ayni
            # sabit kompozisyon cumlesi gidiyor ve `GORSEL_DIL`in cesitlilik
            # istegini bozuyordu — gerekce `KARE_DILI` docstring'inde.
            + f" Frame this scene as {kare_dili(index)}. "
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
            "belong to the monument are welcome, but they must never spell out modern words."
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
            response = client.images.generate(**request)
        except BadRequestError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            code = str(body.get("code", getattr(exc, "code", "")))
            if code != "moderation_blocked" and "safety_violations" not in str(exc):
                raise
            safe_prompt = (
                "Create a non-violent museum-safe historical reconstruction for a vertical documentary. "
                f"Show only this neutral subject: {plan.visual_anchor}; {visual_detail}. "
                "Focus on architecture, artifact, landscape, materials, or peaceful daily activity. "
                "No battle, injury, death, weapons, threat, distressed people, modern objects, text, logo, or watermark."
            )
            try:
                response = client.images.generate(**{**request, "prompt": safe_prompt})
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
    material_dir = (
        ROOT
        / "storage"
        / "youtube_automation"
        / "commons_materials"
        / f"{publication_slot_key()}-attempt-{attempt}"
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
    source_montage = create_source_montage(material_files, attempt)
    source_review = review_source_materials(plan, source_montage)
    if not AI_VISUAL_FALLBACK_ENABLED and (
        not source_review.publishable
        or source_review.visual_alignment_score < MIN_VISUAL_SCORE
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
                pass
            else:
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
                source_montage = create_source_montage(material_files, attempt)
                source_review = review_source_materials(plan, source_montage)
    if AI_VISUAL_FALLBACK_ENABLED and (
        not source_review.publishable
        or source_review.visual_alignment_score < MIN_VISUAL_SCORE
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
        source_montage = create_source_montage(material_files, attempt)
        source_review = review_source_materials(plan, source_montage)
    if (
        not source_review.publishable
        or source_review.visual_alignment_score < MIN_VISUAL_SCORE
    ):
        raise SourceMaterialRejected(source_review)

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
        # Telifsiz bir parcaya gecilirse dogru yol `--bgm-file` ile tek bir
        # dogrulanmis dosyayi sabitlemek; "random" 29 parca arasindan seciyor
        # ve hangi videoda hangisinin cikacagi onceden bilinmiyor.
        "--bgm-type",
        "random",
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


def create_review_montage(video_path: Path, task_id: str) -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    montage = REVIEW_DIR / f"{task_id}-montage.jpg"
    with VideoFileClip(str(video_path)) as clip:
        duration = max(float(clip.duration), 1.0)
    fps_value = 8.0 / duration
    command = [
        get_ffmpeg_exe(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps_value:.8f},scale=270:480,tile=4x2",
        "-frames:v",
        "1",
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
            "The image is an 8-frame chronological montage from a vertical Short. "
            "Judge whether visuals match the narration and historical period, whether captions are readable, and whether footage is repetitive. "
            "Historically grounded AI illustrations are acceptable; do not reject them merely for not being archival photographs, but reject misleading or historically inconsistent details. "
            "Return JSON with visual_alignment_score (0-100), subtitle_readability_score (0-100), issues (array), and revised_search_terms (one concrete replacement query per problematic scene). "
            # ⚠️ Kaynak incelemesiyle ayni kural: esik burada da ANILMAZ.
            "Both scores are measurements of this montage, not verdicts. visual_alignment_score: 0 means nothing matches the narration, 50 means about half the frames match, 100 means every frame matches cleanly. subtitle_readability_score: 0 means captions are unreadable, 100 means every caption is comfortably legible. Score what you actually see. "
            "Report modern or unrelated footage, heavy repetition, unreadable captions, or a weak/missing curiosity hook in the first 2-3 seconds as issues."
        ),
    }
    data = _vision_json(prompt, montage)
    gorsel_skor = int(data.get("visual_alignment_score", 0))
    altyazi_skor = int(data.get("subtitle_readability_score", 0))
    return QualityReview(
        publishable=yayina_uygun(gorsel_skor, altyazi_skor),
        visual_alignment_score=gorsel_skor,
        subtitle_readability_score=altyazi_skor,
        issues=[str(issue) for issue in data.get("issues", [])],
        revised_search_terms=[str(term) for term in data.get("revised_search_terms", [])],
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
    if kuyruktan:
        adaylar = notion_kuyrugu.kuyrugu_oku(ytoto_path=YTOTO_PATH)
        if not adaylar:
            return {
                "status": "no-candidate",
                "slot": slot,
                "reason": (
                    "`Seçildi` kuyrugu bos — Notion'da bir adayi bu duruma alin. "
                    "Konu uydurulmadi."
                ),
            }
        aday = adaylar[0]
        notion_kuyrugu.adayi_kap(aday, ytoto_path=YTOTO_PATH)
    aday_kapatildi = False

    _acquire_lock()
    try:
        exclusions: list[str] = []
        reviews: list[dict[str, Any]] = []
        try:
            plan = generate_content_plan(exclusions, konu=aday.baslik if aday else None)
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
                        "topic": rejected_topic,
                        "visual_anchor": plan.visual_anchor,
                        "task_id": None,
                        "visual_alignment_score": review.visual_alignment_score,
                        "issues": review.issues,
                        "rejected_at": datetime.now(ZoneInfo(TIMEZONE_NAME)).isoformat(),
                    }
                )
                save_state(state)
                if attempt < 3:
                    try:
                        plan = generate_content_plan(exclusions, konu=aday.baslik if aday else None)
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
            montage = create_review_montage(video_path, task_id)
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
                        "topic": rejected_topic,
                        "visual_anchor": plan.visual_anchor,
                        "task_id": task_id,
                        "visual_alignment_score": review.visual_alignment_score,
                        "issues": review.issues,
                        "rejected_at": datetime.now(ZoneInfo(TIMEZONE_NAME)).isoformat(),
                    }
                )
                save_state(state)
                if attempt < 3:
                    try:
                        plan = generate_content_plan(exclusions, konu=aday.baslik if aday else None)
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
        description = plan.description
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
            "topic": plan.topic,
            "visual_anchor": plan.visual_anchor,
            "title": plan.title,
            # Bir sonraki kosum bunu okuyup ayni acilisi tekrarlamayacak.
            # Kaydedilmezse `_son_kancalar` hep bos doner ve kalip kirilmaz.
            "hook": kanca(plan.script),
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
            "durur; modelin kendi konusuna DÜŞMEZ."
        ),
    )
    args = parser.parse_args()
    result = run_cycle(
        dry_run=args.dry_run,
        privacy=args.privacy,
        not_before=args.not_before,
        kuyruktan=args.from_notion,
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
