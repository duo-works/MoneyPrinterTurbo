from pathlib import Path

import requests

from wikimedia_materials import (
    _download,
    build_search_queries,
    delivery_url,
    download_scene_materials,
    is_safe_license,
    select_candidate,
)


def test_only_public_domain_and_cc0_licenses_are_accepted():
    assert is_safe_license("Public domain")
    assert is_safe_license("PD-old-100-expired")
    assert is_safe_license("CC0")
    assert not is_safe_license("CC BY-SA 4.0")
    assert not is_safe_license("All Rights Reserved")


def test_scene_download_uses_met_open_access_when_commons_has_no_candidate(
    monkeypatch, tmp_path
):
    met_path = tmp_path / "scene-01-met.jpg"
    met_path.write_bytes(b"met-image")
    met_credit = {
        "scene": 1,
        "title": "Roman Vault Fragment",
        "source_url": "https://www.metmuseum.org/art/collection/search/9",
        "license": "CC0 / Public Domain",
        "artist": "The Metropolitan Museum of Art",
        "provider": "The Metropolitan Museum of Art",
        "object_id": 9,
    }
    monkeypatch.setattr("wikimedia_materials.search_commons", lambda _query: [])
    monkeypatch.setattr(
        "wikimedia_materials.download_met_scene_material",
        lambda *_args, **_kwargs: (met_path, met_credit),
    )

    files, credits = download_scene_materials(
        "Roman engineering",
        [{"narration": "A Roman vault", "search_term": "Roman concrete vault"}],
        tmp_path,
    )

    assert files == [met_path]
    assert credits == [met_credit]


def test_select_candidate_requires_safe_bitmap_and_avoids_reuse():
    pages = [
        {
            "title": "File:unsafe.jpg",
            "imageinfo": [
                {
                    "mime": "image/jpeg",
                    "thumburl": "https://example.test/unsafe.jpg",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:unsafe.jpg",
                    "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}},
                }
            ],
        },
        {
            "title": "File:safe.jpg",
            "imageinfo": [
                {
                    "mime": "image/jpeg",
                    "url": "https://upload.wikimedia.org/original-safe.jpg",
                    "thumburl": "https://example.test/safe.jpg",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:safe.jpg",
                    "width": 2000,
                    "height": 3000,
                    "extmetadata": {"LicenseShortName": {"value": "Public domain"}},
                }
            ],
        },
    ]

    selected = select_candidate(pages, used_titles=set())

    assert selected["title"] == "File:safe.jpg"
    assert selected["url"] == "https://upload.wikimedia.org/original-safe.jpg"


def test_select_candidate_requires_scene_specific_terms_beyond_anchor_name():
    generic_anchor_only = {
        "title": "File:Trajan Column modern city view.jpg",
        "imageinfo": [
            {
                "mime": "image/jpeg",
                "url": "https://upload.wikimedia.org/trajan-city.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Trajan_city.jpg",
                "width": 1600,
                "height": 2400,
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "ImageDescription": {"value": "Trajan Column exterior in modern Rome"},
                },
            }
        ],
    }
    scene_specific = {
        "title": "File:Trajan Column spiral relief detail.jpg",
        "imageinfo": [
            {
                "mime": "image/jpeg",
                "url": "https://upload.wikimedia.org/trajan-relief.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Trajan_relief.jpg",
                "width": 1600,
                "height": 2400,
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "ImageDescription": {
                        "value": "Trajan Column spiral relief with soldiers and armor"
                    },
                },
            }
        ],
    }

    assert (
        select_candidate(
            [generic_anchor_only], set(), query="Trajan Column spiral relief armor"
        )
        is None
    )
    selected = select_candidate(
        [generic_anchor_only, scene_specific],
        set(),
        query="Trajan Column spiral relief armor",
    )

    assert selected is not None
    assert selected["url"].endswith("trajan-relief.jpg")


def test_select_candidate_requires_distinctive_visual_anchor_term():
    def page(title: str, description: str):
        return {
            "title": title,
            "imageinfo": [
                {
                    "mime": "image/jpeg",
                    "url": f"https://upload.wikimedia.org/{title}.jpg",
                    "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
                    "width": 1800,
                    "height": 2400,
                    "extmetadata": {
                        "LicenseShortName": {"value": "Public domain"},
                        "ImageDescription": {"value": description},
                    },
                }
            ],
        }

    selected = select_candidate(
        [
            page("Egyptian museum canopic jars photograph", "Egyptian museum photograph"),
            page("Egyptian scarab amulet", "Ancient Egyptian scarab amulet"),
        ],
        used_titles=set(),
        query="Egyptian scarab amulet museum photograph",
        required_anchor="Egyptian scarab",
    )

    assert selected is not None
    assert selected["title"] == "Egyptian scarab amulet"


def test_select_candidate_rejects_public_domain_image_unrelated_to_query():
    def page(title: str, width: int, height: int):
        return {
            "title": title,
            "imageinfo": [
                {
                    "mime": "image/jpeg",
                    "url": f"https://upload.wikimedia.org/{title}.jpg",
                    "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
                    "width": width,
                    "height": height,
                    "extmetadata": {
                        "LicenseShortName": {"value": "Public domain"},
                        "ImageDescription": {"value": title},
                    },
                }
            ],
        }

    selected = select_candidate(
        [
            page("FEMA workers building mitigation model", 4000, 3000),
            page("Roman aqueduct Via Appia", 1800, 2400),
        ],
        used_titles=set(),
        query="Roman aqueduct stone arches",
    )

    assert selected["title"] == "Roman aqueduct Via Appia"


def test_build_search_queries_progressively_broadens_specific_scene_term():
    queries = build_search_queries(
        "How Romans kept food warm", "ancient Roman kitchen cooking"
    )

    assert queries[0] == "ancient Roman kitchen cooking"
    assert "Roman kitchen" in queries
    assert "Roman cooking" in queries
    assert len(queries) == len(set(queries))


def test_build_search_queries_does_not_fall_back_to_generic_topic():
    queries = build_search_queries(
        "Ancient Water Supply Systems", "Roman aqueduct gravity channel"
    )

    assert "Ancient Water Supply Systems" not in queries
    assert "Ancient Water Supply Systems historical" not in queries


def test_delivery_proxy_only_accepts_wikimedia_upload_host():
    result = delivery_url(
        "https://upload.wikimedia.org/wikipedia/commons/a/a1/example.jpg"
    )

    assert result.startswith("https://images.weserv.nl/?")
    assert "upload.wikimedia.org%2Fwikipedia%2Fcommons" in result

    try:
        delivery_url("https://upload.wikimedia.org.evil.test/example.jpg")
    except ValueError as error:
        assert "upload.wikimedia.org" in str(error)
    else:
        raise AssertionError("non-Wikimedia host must be rejected")


def test_download_retries_429_using_retry_after(monkeypatch, tmp_path: Path):
    class FakeResponse:
        def __init__(self, status_code: int, content: bytes = b""):
            self.status_code = status_code
            self.content = content
            self.headers = {"Retry-After": "2"} if status_code == 429 else {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code} error")

    responses = [FakeResponse(429), FakeResponse(200, b"x" * 12_000)]
    sleeps: list[float] = []

    requested_urls: list[str] = []

    def fake_get(url, *args, **kwargs):
        requested_urls.append(url)
        return responses.pop(0)

    monkeypatch.setattr("wikimedia_materials.requests.get", fake_get)
    destination = tmp_path / "scene.jpg"

    _download(
        "https://upload.wikimedia.org/example.jpg",
        destination,
        sleep_fn=sleeps.append,
    )

    assert destination.stat().st_size == 12_000
    assert sleeps == [1.0, 2.0, 1.0]
    assert responses == []
    assert all(url.startswith("https://images.weserv.nl/?") for url in requested_urls)


def test_scene_download_tries_next_relevant_candidate_after_proxy_404(
    monkeypatch, tmp_path: Path
):
    def page(title: str, width: int, height: int):
        return {
            "title": title,
            "imageinfo": [
                {
                    "mime": "image/jpeg",
                    "url": f"https://upload.wikimedia.org/{title}.jpg",
                    "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
                    "width": width,
                    "height": height,
                    "extmetadata": {
                        "LicenseShortName": {"value": "Public domain"},
                        "ImageDescription": {"value": title},
                    },
                }
            ],
        }

    pages = [
        page("Qanat underground channel broken", 4000, 5000),
        page("Qanat underground channel alternate", 1800, 2400),
    ]
    monkeypatch.setattr("wikimedia_materials.search_commons", lambda *_: pages)
    attempts = []

    def fake_download(url, destination):
        attempts.append(url)
        if len(attempts) == 1:
            response = requests.Response()
            response.status_code = 404
            error = requests.HTTPError("404 proxy error", response=response)
            raise error
        destination.write_bytes(b"x" * 12_000)

    monkeypatch.setattr("wikimedia_materials._download", fake_download)

    files, credits = download_scene_materials(
        "Qanat Engineering", [{"search_term": "Qanat underground channel"}], tmp_path
    )

    assert len(attempts) == 2
    assert files[0].exists()
    assert credits[0]["title"] == "Qanat underground channel alternate"


def test_download_scene_materials_honors_excluded_archive_items(monkeypatch, tmp_path):
    def page(title: str):
        return {
            "title": title,
            "imageinfo": [
                {
                    "mime": "image/jpeg",
                    "url": f"https://upload.wikimedia.org/{title}.jpg",
                    "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
                    "width": 1800,
                    "height": 2400,
                    "extmetadata": {
                        "LicenseShortName": {"value": "Public domain"},
                        "ImageDescription": {"value": title},
                    },
                }
            ],
        }

    pages = [page("Historic rescue archive used"), page("Historic rescue archive fresh")]
    monkeypatch.setattr("wikimedia_materials.search_commons", lambda *_: pages)
    monkeypatch.setattr(
        "wikimedia_materials._download",
        lambda _url, destination: destination.write_bytes(b"x" * 12_000),
    )

    files, credits = download_scene_materials(
        "Historic rescue",
        [{"search_term": "Historic rescue archive"}],
        tmp_path,
        excluded_titles={"Historic rescue archive used"},
    )

    assert len(files) == 1
    assert credits[0]["title"] == "Historic rescue archive fresh"
