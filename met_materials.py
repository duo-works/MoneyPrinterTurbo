from __future__ import annotations

import io
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests
from PIL import Image

SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
USER_AGENT = "MoneyPrinterTurbo-YouTubeAutomation/1.0"
_OBJECT_CACHE: dict[int, dict[str, Any]] = {}

RELEVANCE_STOPWORDS = {
    "ancient",
    "archival",
    "artifact",
    "historical",
    "history",
    "image",
    "museum",
    "object",
    "scene",
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


def _terms(value: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(word) >= 4 and word not in RELEVANCE_STOPWORDS
    }


def select_met_candidate(
    objects: list[dict[str, Any]],
    used_ids: set[int],
    query: str,
    required_anchor: str = "",
) -> dict[str, Any] | None:
    query_terms = _terms(query)
    anchor_terms = _terms(required_anchor)
    distinctive_anchor_terms = anchor_terms - ANCHOR_GENERIC_WORDS
    required_anchor_terms = distinctive_anchor_terms or anchor_terms
    candidates: list[tuple[int, dict[str, Any]]] = []
    for obj in objects:
        object_id = int(obj.get("objectID") or 0)
        if not object_id or object_id in used_ids:
            continue
        if obj.get("isPublicDomain") is not True:
            continue
        image_url = str(obj.get("primaryImage") or obj.get("primaryImageSmall") or "").strip()
        source_url = str(obj.get("objectURL") or "").strip()
        if not image_url or not source_url:
            continue
        evidence = " ".join(
            str(obj.get(field) or "")
            for field in (
                "title",
                "culture",
                "period",
                "dynasty",
                "reign",
                "objectName",
                "medium",
                "classification",
                "artistDisplayName",
            )
        )
        tags = obj.get("tags") or []
        evidence += " " + " ".join(
            str(tag.get("term") or "") for tag in tags if isinstance(tag, dict)
        )
        evidence_terms = _terms(evidence)
        if required_anchor_terms and not all(
            any(required in term or term in required for term in evidence_terms)
            for required in required_anchor_terms
        ):
            continue
        matched = query_terms & evidence_terms
        if query_terms and not matched:
            continue
        candidate = {
            "id": object_id,
            "title": str(obj.get("title") or f"Met object {object_id}"),
            "url": image_url,
            "source_url": source_url,
            "license": "CC0 / Public Domain",
            "artist": str(obj.get("artistDisplayName") or "The Metropolitan Museum of Art"),
        }
        candidates.append((len(matched), candidate))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def search_met(query: str, limit: int = 8) -> list[dict[str, Any]]:
    response = requests.get(
        SEARCH_URL,
        params={"q": query, "hasImages": "true"},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    object_ids = (response.json().get("objectIDs") or [])[:limit]
    objects: list[dict[str, Any]] = []
    for object_id in object_ids:
        object_id = int(object_id)
        if object_id in _OBJECT_CACHE:
            objects.append(_OBJECT_CACHE[object_id])
            continue
        time.sleep(0.1)
        try:
            detail = requests.get(
                OBJECT_URL.format(object_id=object_id),
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            detail.raise_for_status()
        except (requests.Timeout, requests.ConnectionError):
            # Gecici ag hatasi — bu nesne atlanir, arama devam eder.
            continue
        except requests.HTTPError:
            # ⚠️ Met arama indeksi, detay ucunda artik BULUNMAYAN nesne
            # kimlikleri donduruyor. Olculdu (2026-08-06, DW-95): nesne
            # 844492 aramada cikti, `/objects/844492` 404 verdi ve
            # `raise_for_status` butun uretim kosumunu oldurdu — konu,
            # icerik plani ve o ana kadar harcanan LLM parasi bosa gitti.
            #
            # Tek bir eksik nesne arama sonucunu gecersiz kilmaz: geri kalan
            # nesneler kullanilabilir durumda. Atlamak dogru davranis,
            # durmak degil. Ayni ders DW-86'da Wikimedia tarafinda ogrenildi;
            # bu modul o duzeltmenin disinda kalmis.
            continue
        obj = detail.json()
        _OBJECT_CACHE[object_id] = obj
        objects.append(obj)
    return objects


def _download_image(url: str, destination: Path) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "images.metmuseum.org":
        raise ValueError("Met image URL must use https://images.metmuseum.org")
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    with Image.open(io.BytesIO(response.content)) as image:
        if image.width < 720 or image.height < 720:
            raise RuntimeError("Met Open Access image is too small")
        image.convert("RGB").save(destination, format="JPEG", quality=92)


def download_met_scene_material(
    queries: list[str],
    *,
    scene_number: int,
    target_dir: Path,
    used_ids: set[int],
    required_anchor: str = "",
) -> tuple[Path, dict[str, Any]] | None:
    for query in queries[:2]:
        candidate = select_met_candidate(
            search_met(query), used_ids, query, required_anchor=required_anchor
        )
        if candidate is None:
            continue
        destination = target_dir / f"scene-{scene_number:02d}-met.jpg"
        _download_image(candidate["url"], destination)
        credit = {
            "scene": scene_number,
            "title": candidate["title"],
            "source_url": candidate["source_url"],
            "license": candidate["license"],
            "artist": candidate["artist"],
            "provider": "The Metropolitan Museum of Art",
            "object_id": candidate["id"],
        }
        return destination, credit
    return None
