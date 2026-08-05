from __future__ import annotations

import html
import itertools
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

import requests

from met_materials import download_met_scene_material

API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "MoneyPrinterTurbo-YouTubeAutomation/1.0"
SAFE_LICENSE_MARKERS = ("public domain", "pd-", "cc0")
REQUEST_INTERVAL_SECONDS = 1.0
DELIVERY_PROXY_URL = "https://images.weserv.nl/"
GENERIC_SEARCH_WORDS = {
    "ancient",
    "archival",
    "historic",
    "historical",
    "illustration",
    "old",
    "traditional",
}
RELEVANCE_STOPWORDS = GENERIC_SEARCH_WORDS | {
    "building",
    "historic",
    "photo",
    "scene",
    "setting",
    "stone",
    "structure",
    "view",
}
ANCHOR_GENERIC_WORDS = {
    "ancient",
    "egyptian",
    "great",
    "historic",
    "medieval",
    "roman",
}


class MaterialsUnavailableError(RuntimeError):
    pass


def _get_with_retry(
    url: str,
    *,
    timeout: int,
    params: dict[str, str] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_attempts: int = 5,
) -> requests.Response:
    for attempt in range(max_attempts):
        sleep_fn(REQUEST_INTERVAL_SECONDS)
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
        except (requests.Timeout, requests.ConnectionError):
            # ⚠️ Gecici ag hatasi 429 ile ayni sekilde tekrar denenmeli.
            # Onceden yalnizca 429 tekrarlaniyordu ve tek bir ReadTimeout
            # butun koshumu olduruyordu: konu secimi, senaryo, TTS ve uretilmis
            # gorseller bosa gidiyor — yani gecici bir ag hatasinin bedeli
            # harcanan LLM/gorsel parasi oluyor.
            #
            # Olculdu (2026-08-05): images.weserv.nl bir kez 60 saniyede
            # yanit vermedi ve tam bir uretim koshumu coptu. Ayni URL 20 saniye
            # sonra 200 ve 473 KB dondu, yani hata gercekten geciciydi.
            if attempt == max_attempts - 1:
                raise
            sleep_fn(float(2 ** (attempt + 1)))
            continue
        if response.status_code != 429:
            response.raise_for_status()
            return response
        if attempt == max_attempts - 1:
            response.raise_for_status()
        retry_after = response.headers.get("Retry-After", "")
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            delay = float(2 ** (attempt + 1))
        sleep_fn(max(delay, 0.0))
    raise RuntimeError("unreachable Wikimedia retry state")


def is_safe_license(value: str) -> bool:
    normalized = (value or "").strip().lower()
    return any(marker in normalized for marker in SAFE_LICENSE_MARKERS)


def delivery_url(source_url: str) -> str:
    """Map an allowlisted Wikimedia upload URL to a cache-backed delivery URL."""
    parsed = urllib.parse.urlsplit(source_url)
    if parsed.scheme != "https" or parsed.hostname != "upload.wikimedia.org":
        raise ValueError("Commons media URL must use https://upload.wikimedia.org")
    host_and_path = f"{parsed.hostname}{parsed.path}"
    query = urllib.parse.urlencode({"url": host_and_path, "w": "1280", "fit": "inside"})
    return f"{DELIVERY_PROXY_URL}?{query}"


def build_search_queries(topic: str, term: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9'-]+", term)
    meaningful = [word for word in words if word.lower() not in GENERIC_SEARCH_WORDS]
    candidates = [term.strip()]
    if meaningful != words:
        candidates.append(" ".join(meaningful))
    if len(meaningful) > 2:
        candidates.extend(" ".join(pair) for pair in itertools.combinations(meaningful, 2))

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = " ".join(candidate.split())
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique[:10]


def _metadata_value(image: dict[str, Any], key: str) -> str:
    metadata = image.get("extmetadata", {})
    value = metadata.get(key, {})
    if isinstance(value, dict):
        return str(value.get("value", ""))
    return str(value or "")


def _plain_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(value).split())


def _relevance_terms(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(word) >= 4 and word not in RELEVANCE_STOPWORDS
    }


def select_candidate(
    pages: list[dict[str, Any]],
    used_titles: set[str],
    query: str = "",
    required_anchor: str = "",
) -> dict[str, Any] | None:
    candidates: list[tuple[float, dict[str, Any]]] = []
    query_terms = _relevance_terms(query)
    anchor_terms = _relevance_terms(required_anchor)
    distinctive_anchor_terms = anchor_terms - ANCHOR_GENERIC_WORDS
    required_anchor_terms = distinctive_anchor_terms or anchor_terms
    for order, page in enumerate(pages):
        title = str(page.get("title", ""))
        if not title or title in used_titles:
            continue
        image_infos = page.get("imageinfo") or []
        if not image_infos:
            continue
        image = image_infos[0]
        evidence = " ".join(
            [title, _plain_text(_metadata_value(image, "ImageDescription"))]
        ).lower()
        if required_anchor_terms and not all(
            term in evidence for term in required_anchor_terms
        ):
            continue
        matched_terms = {term for term in query_terms if term in evidence}
        if len(query_terms) >= 5:
            minimum_matches = 3
        elif len(query_terms) >= 3:
            minimum_matches = 2
        else:
            minimum_matches = 1
        if query_terms and len(matched_terms) < minimum_matches:
            continue
        mime = str(image.get("mime", "")).lower()
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        license_name = _metadata_value(image, "LicenseShortName")
        if not is_safe_license(license_name):
            continue
        url = image.get("url")
        if not url:
            continue
        width = int(image.get("width") or image.get("thumbwidth") or 0)
        height = int(image.get("height") or image.get("thumbheight") or 0)
        if width < 720 or height < 720:
            continue
        orientation_score = 2.0 if height >= width else 1.0
        resolution_score = min(width * height / 1_000_000, 4.0)
        search_order_score = max(0.0, 2.0 - order * 0.1)
        candidate = {
            "title": title,
            "url": str(url),
            "source_url": str(image.get("descriptionurl", "")),
            "license": license_name,
            "artist": _plain_text(_metadata_value(image, "Artist")),
            "credit": _plain_text(_metadata_value(image, "Credit")),
            "width": width,
            "height": height,
            "mime": mime,
        }
        relevance_score = len(matched_terms) * 2.0
        candidates.append(
            (
                orientation_score
                + resolution_score
                + search_order_score
                + relevance_score,
                candidate,
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def search_commons(query: str, limit: int = 20) -> list[dict[str, Any]]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "1080",
        "format": "json",
        "formatversion": "2",
        "origin": "*",
    }
    response = _get_with_retry(
        API_URL,
        params=params,
        timeout=30,
    )
    payload = response.json()
    return payload.get("query", {}).get("pages", [])


def _download(
    url: str,
    destination: Path,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    response = _get_with_retry(delivery_url(url), timeout=60, sleep_fn=sleep_fn)
    destination.write_bytes(response.content)
    if destination.stat().st_size < 10_000:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded Commons image is unexpectedly small: {url}")


def download_scene_materials(
    topic: str,
    scenes: list[dict[str, str]],
    target_dir: Path,
    *,
    visual_anchor: str = "",
    excluded_titles: set[str] | None = None,
    excluded_met_ids: set[int] | None = None,
) -> tuple[list[Path], list[dict[str, Any]]]:
    target_dir.mkdir(parents=True, exist_ok=True)
    used_titles: set[str] = set(excluded_titles or set())
    used_met_ids: set[int] = set(excluded_met_ids or set())
    files: list[Path] = []
    credits: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, 1):
        term = scene.get("search_term", "").strip()
        queries = build_search_queries(topic, term)
        selected = None
        destination = None
        failed_titles: set[str] = set()
        for query in queries:
            pages = search_commons(query)
            while True:
                candidate = select_candidate(
                    pages,
                    used_titles | failed_titles,
                    query=query,
                    required_anchor=visual_anchor,
                )
                if not candidate:
                    break
                suffix = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                }[candidate["mime"]]
                candidate_destination = target_dir / f"scene-{index:02d}{suffix}"
                try:
                    _download(candidate["url"], candidate_destination)
                except requests.HTTPError as exc:
                    status = exc.response.status_code if exc.response is not None else 0
                    if status not in {403, 404}:
                        raise
                    failed_titles.add(candidate["title"])
                    continue
                selected = candidate
                destination = candidate_destination
                break
            if selected:
                break
        if not selected or destination is None:
            met_result = download_met_scene_material(
                queries,
                scene_number=index,
                target_dir=target_dir,
                used_ids=used_met_ids,
                required_anchor=visual_anchor,
            )
            if met_result is None:
                raise MaterialsUnavailableError(
                    f"no public-domain or CC0 archive image found for scene {index}: {term}"
                )
            met_path, met_credit = met_result
            used_met_ids.add(int(met_credit["object_id"]))
            files.append(met_path)
            credits.append(met_credit)
            continue
        used_titles.add(selected["title"])
        files.append(destination)
        credits.append(
            {
                "scene": index,
                "title": selected["title"],
                "source_url": selected["source_url"],
                "license": selected["license"],
                "artist": selected["artist"],
            }
        )
    (target_dir / "credits.json").write_text(
        json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return files, credits
