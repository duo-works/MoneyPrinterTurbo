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


def validate_content_plan(plan: ContentPlan) -> None:
    word_count = len(re.findall(r"\b[\w'-]+\b", plan.script))
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


def format_commons_credits(credits: list[dict[str, Any]]) -> str:
    links: list[str] = []
    for credit in credits:
        link = str(credit.get("source_url", "")).strip()
        if link and link not in links:
            links.append(link)
    if not links:
        return ""
    return "Public-domain / CC0 visual sources:\n" + "\n".join(
        f"- {link}" for link in links
    )


def should_publish(review: QualityReview) -> bool:
    return (
        review.publishable
        and review.visual_alignment_score >= MIN_VISUAL_SCORE
        and review.subtitle_readability_score >= MIN_SUBTITLE_SCORE
    )


def should_abandon_topic(review: QualityReview) -> bool:
    issue_text = " ".join(review.issues).lower()
    unexplained_or_blocking_rejection = (
        not review.publishable
        and review.visual_alignment_score >= MIN_VISUAL_SCORE
        and review.subtitle_readability_score >= MIN_SUBTITLE_SCORE
    )
    return (
        review.visual_alignment_score < 50
        or "modern footage" in issue_text
        or unexplained_or_blocking_rejection
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


def generate_content_plan(extra_exclusions: list[str] | None = None) -> ContentPlan:
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
    system = """You are the editorial producer of an English global-history YouTube Shorts channel.
Return valid JSON only. Create a factual, emotionally compelling, evergreen true story suitable for stock footage.
The script must be 80-120 spoken English words and end with a memorable line. The first 2-3 seconds must deliver a short, immediately understandable hook that creates a curiosity gap through a surprising factual claim, an unresolved question, or a strong contrast; do not begin with greetings, channel introductions, dates, or slow setup. Scene 1 narration and its visual must directly support that hook.
Create 6-10 chronological scenes. Define visual_anchor as a specific named civilization, landmark, artifact, archaeological site, vessel, or invention in 1-4 words. Every scene needs narration and a concrete 3-7 word English Wikimedia Commons search term that repeats at least one distinctive visual_anchor word. Never use abstract terms alone.
Choose only stories with abundant Public Domain or CC0 historical visual evidence on Wikimedia Commons or Met Open Access: prefer subjects documented by many pre-1929 photographs, public-domain engravings, archaeological plates, museum scans, or CC0 object photographs. Use the eligible visual-anchor shortlist in the user request instead of defaulting to famous examples from prior plans. Avoid Antikythera, Nazca, qanats, or other subjects whose useful Commons photos are mostly CC-BY/CC-BY-SA. Current footage of a surviving place or object is acceptable; generic modern people, factories, vehicles, schools, water systems, maps, or buildings that merely share one broad word with the narration are forbidden.
Every planned scene must be honestly illustratable by a readily available view, detail, engraving, archaeological plate, manuscript page, or museum object of the same visual_anchor. Build the narration around visible evidence rather than asking images to reenact invisible causes or one-time events. Do not require hidden foundations, buried soil layers, exact construction stages, named workers or crowds, closures, restoration procedures, process diagrams, or a specific historical moment unless abundant exact Public Domain or CC0 imagery is known to exist. Prefer multiple truthful views and details of one surviving anchor over loosely related contextual footage.
Prefer ancient engineering, surviving monuments, unusual inventions, archaeology, navigation, historic foods/crafts, natural phenomena, and locations with visible evidence. Avoid war rescues, named battles, period-specific crowds, disasters requiring reenactments, and stories where generic modern footage would falsely imply archival evidence.
Avoid graphic violence, medical misinformation, politics, religion advocacy, copyrighted characters, and uncertain claims.
The title must be natural, under 65 characters when practical, and contain #Shorts.
Description must contain a two-sentence summary followed by 3-5 hashtags.
Tags must be an array of 6-10 concise strings.
JSON keys: topic, visual_anchor, title, script, scenes, description, tags."""
    user = (
        "Create one new video plan. Do not repeat or closely paraphrase these existing topics/titles:\n"
        + json.dumps(previous[-50:], ensure_ascii=False)
        + "\nNever reuse any of these concrete visual anchors:\n"
        + json.dumps(previous_anchors, ensure_ascii=False)
        + "\nChoose the visual_anchor from this unused editorial shortlist when it is non-empty:\n"
        + json.dumps(eligible_anchors, ensure_ascii=False)
        + "\nPreferred content pillars: ancient engineering, surviving historic places, ingenious inventions, archaeology, navigation, strange verified events, and visible historical mysteries."
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
            "Return JSON with publishable, visual_alignment_score (0-100), issues (array), revised_search_terms, and problem_scene_numbers (1-based scene numbers that need replacement; empty only when no scene is problematic). Whenever publishable is false or visual_alignment_score is below 50, revised_search_terms must contain one concrete anchor-specific replacement query for each problem scene, in the same order as problem_scene_numbers. "
            "Set publishable true if and only if visual_alignment_score is at least 50 and there is no blocking mismatch. If publishable is false, include at least one concrete issue."
        ),
    }
    data = _vision_json(prompt, montage)
    return QualityReview(
        publishable=bool(data.get("publishable", False)),
        visual_alignment_score=int(data.get("visual_alignment_score", 0)),
        subtitle_readability_score=100,
        issues=[str(issue) for issue in data.get("issues", [])],
        revised_search_terms=[str(term) for term in data.get("revised_search_terms", [])],
        problem_scene_numbers=[
            int(number)
            for number in data.get("problem_scene_numbers", [])
            if str(number).isdigit() and 1 <= int(number) <= len(plan.scenes)
        ],
    )


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
            "Create a historically grounded vertical documentary illustration for a YouTube Short. "
            f"Visual anchor: {plan.visual_anchor}. Scene {index}: {scene.get('narration', '')}. "
            f"Required visible detail: {visual_detail}. "
            "Use a realistic archival-documentary aesthetic, one clear focal subject, strong vertical composition, "
            "and period-appropriate architecture, clothing, tools, and materials. No modern objects, no logos, "
            "no captions, no text, no watermark, and no invented event presented as a surviving photograph."
        )
        request = {
            "model": model,
            "prompt": prompt,
            "size": "1024x1536",
            "quality": "medium",
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
        )
    except MaterialsUnavailableError as exc:
        if not AI_VISUAL_FALLBACK_ENABLED:
            raise SourceMaterialRejected(
                QualityReview(False, 0, 100, [str(exc)], [])
            ) from exc
        material_files = _generate_ai_or_reject(plan, material_dir / "ai-fallback")
        credits = []
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
        problem_scenes = source_review.problem_scene_numbers or list(
            range(1, len(plan.scenes) + 1)
        )
        replacements = _generate_ai_or_reject(
            plan,
            material_dir / "ai-refinement",
            revised_search_terms=source_review.revised_search_terms,
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
        "5",
        "--voice-name",
        "en-US-BrianMultilingualNeural-Male",
        "--voice-rate",
        "1.08",
        "--bgm-type",
        "none",
        "--subtitle-enabled",
        "--subtitle-position",
        "custom",
        "--custom-position",
        "72",
        "--text-fore-color",
        "#FFFFFF",
        "--font-size",
        "72",
        "--stroke-color",
        "#000000",
        "--stroke-width",
        "3",
        "--subtitle-background-enabled",
        "--subtitle-background-color",
        "#000000",
        "--rounded-subtitle-background",
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
            "Return JSON with publishable, visual_alignment_score (0-100), subtitle_readability_score (0-100), issues (array), revised_search_terms (one per scene if visual score is below 50). "
            "Set publishable true if and only if visual_alignment_score is at least 50, subtitle_readability_score is at least 80, and there is no blocking issue. If publishable is false, include at least one concrete issue. "
            "Reject modern or unrelated footage, heavy repetition, unreadable captions, or a weak/missing curiosity hook in the first 2-3 seconds."
        ),
    }
    data = _vision_json(prompt, montage)
    return QualityReview(
        publishable=bool(data.get("publishable", False)),
        visual_alignment_score=int(data.get("visual_alignment_score", 0)),
        subtitle_readability_score=int(data.get("subtitle_readability_score", 0)),
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
) -> dict[str, Any]:
    slot = publication_slot_key()
    state = load_state()
    if slot in state.get("completed_slots", []):
        return {"status": "skipped", "reason": "slot already completed", "slot": slot}

    _acquire_lock()
    try:
        exclusions: list[str] = []
        reviews: list[dict[str, Any]] = []
        try:
            plan = generate_content_plan(exclusions)
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
                        plan = generate_content_plan(exclusions)
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
                        plan = generate_content_plan(exclusions)
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
        return record
    finally:
        LOCK_FILE.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate, review, and publish one YouTube Short")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public")
    parser.add_argument("--not-before", metavar="HH:MM")
    args = parser.parse_args()
    result = run_cycle(
        dry_run=args.dry_run,
        privacy=args.privacy,
        not_before=args.not_before,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "rejected":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
