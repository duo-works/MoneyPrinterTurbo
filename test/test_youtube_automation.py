from datetime import datetime
import base64
import io
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import httpx
from openai import BadRequestError
from PIL import Image

from youtube_automation import (
    _seconds_until_not_before,
    _recent_titles,
    ContentPlan,
    DistinctTopicUnavailableError,
    QualityReview,
    SourceMaterialRejected,
    create_source_montage,
    format_commons_credits,
    generate_ai_scene_materials,
    generate_content_plan,
    is_duplicate_topic,
    is_duplicate_visual_anchor,
    parse_cli_result,
    publication_slot_key,
    refine_search_terms,
    review_source_materials,
    review_video,
    run_cycle,
    run_generator,
    should_abandon_topic,
    should_publish,
    validate_content_plan,
)


def test_not_before_gate_waits_until_2000_istanbul():
    now = datetime(2026, 7, 30, 19, 55, tzinfo=ZoneInfo("Europe/Istanbul"))

    assert _seconds_until_not_before("20:00", now) == 300


def test_not_before_gate_does_not_wait_after_2000():
    now = datetime(2026, 7, 30, 20, 5, tzinfo=ZoneInfo("Europe/Istanbul"))

    assert _seconds_until_not_before("20:00", now) == 0


def valid_plan() -> ContentPlan:
    script = " ".join(["history"] * 95)
    return ContentPlan(
        topic="The forgotten rescue that changed history",
        visual_anchor="historic rescue",
        title="The Rescue History Almost Forgot #Shorts",
        script=script,
        scenes=[
            {"narration": f"Scene {index}", "search_term": f"historic rescue scene {index}"}
            for index in range(1, 8)
        ],
        description="A remarkable true story.\n\n#Shorts #History",
        tags=["Shorts", "History", "Amazing Facts"],
    )


def test_validate_content_plan_accepts_short_english_script_and_concrete_scene_terms():
    plan = valid_plan()

    validate_content_plan(plan)


def test_validate_content_plan_rejects_too_few_scenes():
    plan = valid_plan()
    plan.scenes = plan.scenes[:3]

    with pytest.raises(ValueError, match="6-10 scenes"):
        validate_content_plan(plan)


def test_validate_content_plan_requires_visual_anchor_in_every_search_term():
    plan = valid_plan()
    plan.scenes[3]["search_term"] = "generic stone arches"

    with pytest.raises(ValueError, match="visual anchor"):
        validate_content_plan(plan)


def test_generate_content_plan_retries_when_first_llm_response_is_invalid(monkeypatch):
    invalid = {
        "topic": "Roman Roads",
        "visual_anchor": "Roman road",
        "title": "Why Roman Roads Survived #Shorts",
        "script": " ".join(["history"] * 95),
        "scenes": [{"narration": f"Scene {i}", "search_term": "road"} for i in range(7)],
        "description": "Roman engineering still shapes our world.\n\n#Shorts #History",
        "tags": ["Shorts", "History", "Rome"],
    }
    valid = {
        **invalid,
        "scenes": [
            {"narration": f"Scene {i}", "search_term": f"ancient roman road {i}"}
            for i in range(7)
        ],
    }
    responses = iter([invalid, valid])
    monkeypatch.setattr("youtube_automation._json_completion", lambda *_, **__: next(responses))
    monkeypatch.setattr("youtube_automation._recent_titles", lambda: [])
    monkeypatch.setattr(
        "youtube_automation.load_state",
        lambda: {"published": [], "rejected": [], "completed_slots": []},
    )

    plan = generate_content_plan()

    assert plan.scenes[0]["search_term"] == "ancient roman road 0"


def test_generate_content_plan_adds_missing_visual_anchor_to_scene_terms(monkeypatch):
    response = {
        "topic": "Roman Pantheon Concrete",
        "visual_anchor": "Roman Pantheon",
        "title": "Why the Pantheon Still Stands #Shorts",
        "script": " ".join(["history"] * 95),
        "scenes": [
            {"narration": f"Scene {i}", "search_term": f"volcanic concrete detail {i}"}
            for i in range(7)
        ],
        "description": "Ancient engineering survived.\n\n#Shorts #History",
        "tags": ["Shorts", "History", "Rome"],
    }
    monkeypatch.setattr("youtube_automation._json_completion", lambda *_, **__: response)
    monkeypatch.setattr("youtube_automation._recent_titles", lambda: [])
    monkeypatch.setattr(
        "youtube_automation.load_state",
        lambda: {"published": [], "rejected": [], "completed_slots": []},
    )

    plan = generate_content_plan()

    assert all("Roman Pantheon" in scene["search_term"] for scene in plan.scenes)
    validate_content_plan(plan)


def test_generate_content_plan_prompt_targets_abundant_public_domain_archives(monkeypatch):
    response = {
        "topic": "Roman Pantheon Archive",
        "visual_anchor": "Roman Pantheon",
        "title": "Why the Pantheon Still Stands #Shorts",
        "script": " ".join(["history"] * 95),
        "scenes": [
            {"narration": f"Scene {i}", "search_term": f"Roman Pantheon archive {i}"}
            for i in range(7)
        ],
        "description": "Ancient engineering survived.\n\n#Shorts #History",
        "tags": ["Shorts", "History", "Rome"],
    }
    captured = {}

    def complete(system, user):
        captured["system"] = system
        captured["user"] = user
        return response

    monkeypatch.setattr("youtube_automation._json_completion", complete)
    monkeypatch.setattr("youtube_automation._recent_titles", lambda: [])
    monkeypatch.setattr(
        "youtube_automation.load_state",
        lambda: {"published": [], "rejected": [], "completed_slots": []},
    )

    generate_content_plan()

    assert "pre-1929" in captured["system"]
    assert "museum scans" in captured["system"]
    assert "Every planned scene" in captured["system"]
    assert "Met Open Access" in captured["system"]
    assert "hidden foundations" in captured["system"]
    assert "first 2-3 seconds" in captured["system"]
    assert "curiosity gap" in captured["system"]


def test_generate_content_plan_can_recover_after_three_duplicate_suggestions(monkeypatch):
    duplicate = {
        "topic": "Roman Pantheon duplicate",
        "visual_anchor": "Roman Pantheon",
        "title": "The Roman Pantheon Again #Shorts",
        "script": " ".join(["history"] * 95),
        "scenes": [
            {
                "narration": f"Scene {index}",
                "search_term": f"Roman Pantheon archive {index}",
            }
            for index in range(1, 8)
        ],
        "description": "Ancient history.\n\n#Shorts #History #Rome",
        "tags": ["Shorts", "History", "Rome", "Ancient", "Architecture", "Facts"],
    }
    distinct = {
        **duplicate,
        "topic": "How the Great Sphinx survived desert centuries",
        "visual_anchor": "Great Sphinx",
        "title": "The Sphinx Was Buried More Than Once #Shorts",
        "scenes": [
            {
                "narration": f"Scene {index}",
                "search_term": f"Great Sphinx archive {index}",
            }
            for index in range(1, 8)
        ],
    }
    responses = iter([duplicate, duplicate, duplicate, distinct])
    monkeypatch.setattr(
        "youtube_automation._json_completion", lambda *_args, **_kwargs: next(responses)
    )
    monkeypatch.setattr(
        "youtube_automation._recent_titles", lambda: ["Roman Pantheon"]
    )
    monkeypatch.setattr(
        "youtube_automation.load_state",
        lambda: {
            "published": [],
            "rejected": [{"visual_anchor": "Roman Pantheon"}],
            "completed_slots": [],
        },
    )

    plan = generate_content_plan()

    assert plan.visual_anchor == "Great Sphinx"


def test_duplicate_topic_matching_ignores_case_punctuation_and_hashtag_noise():
    history = ["The WWI Pigeon That Saved 194 Soldiers 🕊️ #Shorts"]

    assert is_duplicate_topic("wwi pigeon saved 194 soldiers", history)
    assert not is_duplicate_topic("The Dancing Plague of 1518", history)


def test_parse_cli_result_finds_the_last_json_object():
    stdout = 'progress line\n{"status": "ok", "task_id": "abc", "videos": ["final.mp4"]}\n'

    result = parse_cli_result(stdout)

    assert result["task_id"] == "abc"
    assert result["videos"] == ["final.mp4"]


def test_parse_cli_result_accepts_fenced_multiline_json():
    stdout = """session_id: abc
```json
{
  "topic": "Temple of Dendur",
  "scenes": [{"search_term": "Temple of Dendur stone"}]
}
```
"""

    result = parse_cli_result(stdout)

    assert result["topic"] == "Temple of Dendur"
    assert result["scenes"][0]["search_term"] == "Temple of Dendur stone"


def test_json_completion_uses_hermes_cli_and_parses_last_json(monkeypatch):
    monkeypatch.setattr("youtube_automation.INFERENCE_BACKEND", "hermes-cli")
    captured = {}

    def run(command, timeout):
        captured["command"] = command
        captured["timeout"] = timeout
        return SimpleNamespace(
            returncode=0,
            stdout='banner\nsession_id: abc\n{"ok": true, "provider": "oauth"}\n',
            stderr="",
        )

    monkeypatch.setattr("youtube_automation._run_hermes", run)

    data = __import__("youtube_automation")._json_completion("system", "user")

    assert data == {"ok": True, "provider": "oauth"}
    assert captured["command"][:3] == ["hermes", "--ignore-rules", "--safe-mode"]
    assert "-z" in captured["command"]
    assert "system" in captured["command"][-1]
    assert "user" in captured["command"][-1]
    assert captured["timeout"] == 180


def test_vision_json_uses_hermes_cli_with_native_image_path(monkeypatch, tmp_path):
    monkeypatch.setattr("youtube_automation.INFERENCE_BACKEND", "hermes-cli")
    image = tmp_path / "contact-sheet.jpg"
    image.write_bytes(b"image")
    captured = {}

    def run(command, timeout):
        captured["command"] = command
        captured["timeout"] = timeout
        return SimpleNamespace(
            returncode=0,
            stdout='session_id: abc\n{"publishable": false, "issues": ["mismatch"]}\n',
            stderr="",
        )

    monkeypatch.setattr("youtube_automation._run_hermes", run)

    data = __import__("youtube_automation")._vision_json(
        {"instructions": "review"}, image
    )

    assert data["issues"] == ["mismatch"]
    assert "chat" in captured["command"]
    assert captured["command"][captured["command"].index("--image") + 1] == str(image)
    assert captured["command"][captured["command"].index("--max-turns") + 1] == "1"
    assert captured["timeout"] == 360


def test_run_hermes_kills_windows_process_tree_on_timeout(monkeypatch):
    class Process:
        pid = 4321
        returncode = None

        def communicate(self, timeout=None):
            if timeout == 180:
                raise __import__("subprocess").TimeoutExpired("hermes", timeout)
            self.returncode = -1
            return "", ""

    killed = []
    monkeypatch.setattr("youtube_automation.subprocess.Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(
        "youtube_automation.subprocess.run",
        lambda command, **_kwargs: killed.append(command)
        or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    # ⚠️ `os.name` YAMALANMAZ — bkz. `youtube_automation._windows`. Global `os`
    # modulunu "nt" yapmak `pathlib.Path()`'i POSIX'te patlatiyor ve pytest'in
    # kendi onbellegini de vurdugu icin butun oturumu `INTERNALERROR` ile
    # coturuyordu (DW-90).
    monkeypatch.setattr("youtube_automation._windows", lambda: True)

    with pytest.raises(RuntimeError, match="timed out"):
        __import__("youtube_automation")._run_hermes(["hermes", "-z", "prompt"], 180)

    assert killed == [["taskkill", "/PID", "4321", "/T", "/F"]]


def test_commons_credits_are_added_to_description_without_duplicate_links():
    credits = [
        {"source_url": "https://commons.wikimedia.org/wiki/File:A.jpg"},
        {"source_url": "https://commons.wikimedia.org/wiki/File:A.jpg"},
        {"source_url": "https://commons.wikimedia.org/wiki/File:B.jpg"},
        {"source_url": "https://www.metmuseum.org/art/collection/search/9"},
    ]

    text = format_commons_credits(credits)

    assert text.count("File:A.jpg") == 1
    assert "File:B.jpg" in text
    assert "metmuseum.org/art/collection/search/9" in text
    # ⚠️ Baslik DW-99'da degisti: artik CC BY gorselleri de kabul ediliyor,
    # "Public-domain / CC0" demek yaniltici olurdu. Ayrintili atif sozlesmesi
    # `test_lisans.py`'de kilitli.
    assert text.startswith("Visual sources (public domain, CC0 or CC BY):")


def test_should_publish_requires_visual_and_subtitle_quality_thresholds():
    good = QualityReview(True, 50, 80, [])
    bad_visuals = QualityReview(True, 49, 95, ["Modern footage conflicts with narration"])

    assert should_publish(good)
    assert not should_publish(bad_visuals)


def test_very_low_or_blocking_visual_review_abandons_topic():
    """Konu yalnizca OLCUM kotuyse terk edilir — modelin bayragiyla degil.

    Bu test eskiden tersini kilitliyordu: `publishable=False` gelen bir
    inceleme, skorlari esigin USTUNDE olsa bile konuyu terk ettiriyordu.
    DW-87 o kurali kaldirdi cunku bayrak artik skorlardan turetiliyor; modelin
    "hayir" demesi tek basina bir kanit degil. Skoru 68 olan bir kagit
    iyilestirilecek bir kagittir, cope atilacak bir konu degil.
    """
    badly_mismatched = QualityReview(False, 40, 90, ["Modern footage conflicts with narration"])
    modern_footage_above_threshold = QualityReview(
        False, 90, 90, ["Contains modern footage of a highway"]
    )
    fixable_above_threshold = QualityReview(False, 68, 90, ["One scene needs replacement"])
    unexplained_rejection = QualityReview(False, 80, 85, [])

    assert should_abandon_topic(badly_mismatched)
    # "modern footage" esikten bagimsiz bir engel — korunuyor.
    assert should_abandon_topic(modern_footage_above_threshold)
    # Esigi gecen ikisi artik terk EDILMIYOR; hat sahneleri yenileyip tekrar dener.
    assert not should_abandon_topic(fixable_above_threshold)
    assert not should_abandon_topic(unexplained_rejection)


def test_publication_slot_key_uses_istanbul_date_and_hour():
    moment = datetime(2026, 7, 30, 20, 15, tzinfo=ZoneInfo("Europe/Istanbul"))

    assert publication_slot_key(moment) == "2026-07-30-20"


def test_run_generator_does_not_render_rejected_source_materials(monkeypatch, tmp_path):
    plan = valid_plan()
    materials = [tmp_path / f"scene-{index}.jpg" for index in range(1, 8)]
    source_review = QualityReview(
        False, 40, 0, ["Modern and unrelated source images"], []
    )
    monkeypatch.setattr(
        "youtube_automation.download_scene_materials",
        lambda *_, **__: (materials, []),
    )
    monkeypatch.setattr(
        "youtube_automation.create_source_montage", lambda *_, **__: tmp_path / "sources.jpg"
    )
    monkeypatch.setattr(
        "youtube_automation.review_source_materials", lambda *_, **__: source_review
    )
    monkeypatch.setattr(
        "youtube_automation.generate_ai_scene_materials",
        lambda *_args, **_kwargs: materials,
    )

    def fail_if_rendered(*_args, **_kwargs):
        raise AssertionError("CLI render must not start for rejected sources")

    monkeypatch.setattr("youtube_automation.subprocess.run", fail_if_rendered)

    with pytest.raises(SourceMaterialRejected) as rejected:
        run_generator(plan, 1)

    assert rejected.value.review.visual_alignment_score == 40


def test_run_generator_refines_problem_scenes_once_with_archives_when_ai_disabled(
    monkeypatch, tmp_path
):
    monkeypatch.setattr("youtube_automation.AI_VISUAL_FALLBACK_ENABLED", False)
    plan = valid_plan()
    originals = [tmp_path / f"original-{index}.jpg" for index in range(1, 8)]
    replacements = [tmp_path / "replacement-2.jpg", tmp_path / "replacement-5.jpg"]
    download_calls = []

    def download(topic, scenes, target_dir, **kwargs):
        download_calls.append((topic, scenes, target_dir, kwargs))
        if len(download_calls) == 1:
            return originals, [
                {
                    "scene": index,
                    "title": f"File:Original-{index}.jpg",
                    "source_url": f"https://commons.example/{index}",
                }
                for index in range(1, 8)
            ]
        return replacements, [
            {
                "scene": index,
                "title": f"File:Replacement-{index}.jpg",
                "source_url": f"https://commons.example/replacement-{index}",
            }
            for index in range(1, 3)
        ]

    revised = ["historic rescue corrected scene 2", "historic rescue corrected scene 5"]
    reviews = iter(
        [
            QualityReview(False, 40, 100, ["mismatch"], revised, [2, 5]),
            QualityReview(False, 45, 100, ["still mismatched"], [], [5]),
        ]
    )
    montage_calls = []
    monkeypatch.setattr("youtube_automation.download_scene_materials", download)
    monkeypatch.setattr(
        "youtube_automation.create_source_montage",
        lambda files, *_: montage_calls.append(list(files)) or tmp_path / "sources.jpg",
    )
    monkeypatch.setattr(
        "youtube_automation.review_source_materials", lambda *_, **__: next(reviews)
    )
    monkeypatch.setattr(
        "youtube_automation.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("render must wait for refined source review")
        ),
    )

    with pytest.raises(SourceMaterialRejected) as rejected:
        run_generator(plan, 1)

    assert rejected.value.review.visual_alignment_score == 45
    assert len(download_calls) == 2
    assert [scene["search_term"] for scene in download_calls[1][1]] == revised
    assert download_calls[1][3]["excluded_titles"] == {
        f"File:Original-{index}.jpg" for index in range(1, 8)
    }
    expected = list(originals)
    expected[1] = replacements[0]
    expected[4] = replacements[1]
    assert montage_calls == [originals, expected]


def test_run_generator_generates_missing_refinement_terms_for_blocking_review(
    monkeypatch, tmp_path
):
    monkeypatch.setattr("youtube_automation.AI_VISUAL_FALLBACK_ENABLED", False)
    plan = valid_plan()
    originals = [tmp_path / f"original-{index}.jpg" for index in range(1, 8)]
    replacements = [tmp_path / "replacement-2.jpg", tmp_path / "replacement-5.jpg"]
    download_calls = []

    def download(_topic, scenes, _target_dir, **_kwargs):
        download_calls.append(scenes)
        if len(download_calls) == 1:
            return originals, []
        return replacements, [
            {"scene": 1, "title": "Replacement 2"},
            {"scene": 2, "title": "Replacement 5"},
        ]

    reviews = iter(
        [
            QualityReview(False, 50, 100, ["blocking mismatch"], [], [2, 5]),
            QualityReview(False, 45, 100, ["still mismatched"], [], [5]),
        ]
    )

    def supply_terms(candidate, _review):
        candidate.scenes[1]["search_term"] = "historic rescue corrected scene 2"
        candidate.scenes[4]["search_term"] = "historic rescue corrected scene 5"
        return candidate

    monkeypatch.setattr("youtube_automation.download_scene_materials", download)
    monkeypatch.setattr("youtube_automation.refine_search_terms", supply_terms)
    monkeypatch.setattr(
        "youtube_automation.create_source_montage", lambda *_, **__: tmp_path / "sources.jpg"
    )
    monkeypatch.setattr(
        "youtube_automation.review_source_materials", lambda *_, **__: next(reviews)
    )
    monkeypatch.setattr(
        "youtube_automation.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("render must wait for refined source review")
        ),
    )

    with pytest.raises(SourceMaterialRejected):
        run_generator(plan, 1)

    assert len(download_calls) == 2
    assert [scene["search_term"] for scene in download_calls[1]] == [
        "historic rescue corrected scene 2",
        "historic rescue corrected scene 5",
    ]


def test_run_generator_requires_source_publishable_even_when_score_passes(monkeypatch, tmp_path):
    plan = valid_plan()
    materials = [tmp_path / f"scene-{index}.jpg" for index in range(1, 8)]
    source_review = QualityReview(False, 80, 100, [], [])
    monkeypatch.setattr(
        "youtube_automation.download_scene_materials",
        lambda *_, **__: (materials, []),
    )
    monkeypatch.setattr(
        "youtube_automation.create_source_montage", lambda *_, **__: tmp_path / "sources.jpg"
    )
    monkeypatch.setattr(
        "youtube_automation.review_source_materials", lambda *_, **__: source_review
    )
    monkeypatch.setattr(
        "youtube_automation.generate_ai_scene_materials",
        lambda *_args, **_kwargs: materials,
    )

    def fail_if_rendered(*_args, **_kwargs):
        raise AssertionError("CLI render must not start when source publishable is false")

    monkeypatch.setattr("youtube_automation.subprocess.run", fail_if_rendered)

    with pytest.raises(SourceMaterialRejected) as rejected:
        run_generator(plan, 1)

    assert not rejected.value.review.publishable
    assert rejected.value.review.visual_alignment_score == 80


def test_generate_ai_scene_materials_writes_one_vertical_image_per_scene(monkeypatch, tmp_path):
    image_buffer = io.BytesIO()
    Image.new("RGB", (1024, 1536), (90, 60, 30)).save(image_buffer, format="PNG")
    encoded = base64.b64encode(image_buffer.getvalue()).decode("ascii")
    calls = []

    class Images:
        def generate(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded, url=None)])

    client = SimpleNamespace(images=Images())
    monkeypatch.setattr("youtube_automation._openai_client", lambda: (client, "text-model"))

    files = generate_ai_scene_materials(valid_plan(), tmp_path)

    assert len(files) == 7
    assert len(calls) == 7
    assert all(path.exists() for path in files)
    with Image.open(files[0]) as generated:
        assert generated.width < generated.height
    assert "historic rescue" in calls[0]["prompt"]


def test_generate_ai_scene_materials_can_regenerate_only_problem_scenes(monkeypatch, tmp_path):
    image_buffer = io.BytesIO()
    Image.new("RGB", (1024, 1536), (30, 60, 90)).save(image_buffer, format="PNG")
    encoded = base64.b64encode(image_buffer.getvalue()).decode("ascii")
    calls = []

    class Images:
        def generate(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded, url=None)])

    client = SimpleNamespace(images=Images())
    monkeypatch.setattr("youtube_automation._openai_client", lambda: (client, "text-model"))

    files = generate_ai_scene_materials(
        valid_plan(),
        tmp_path,
        revised_search_terms=["corrected second scene", "corrected fifth scene"],
        scene_numbers=[2, 5],
    )

    assert [path.name for path in files] == ["scene-02.png", "scene-05.png"]
    assert len(calls) == 2
    assert "corrected second scene" in calls[0]["prompt"]
    assert "corrected fifth scene" in calls[1]["prompt"]


def test_generate_ai_scene_materials_retries_moderation_with_nonviolent_prompt(
    monkeypatch, tmp_path
):
    image_buffer = io.BytesIO()
    Image.new("RGB", (1024, 1536), (50, 50, 50)).save(image_buffer, format="PNG")
    encoded = base64.b64encode(image_buffer.getvalue()).decode("ascii")
    calls = []
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/images/generations"),
        json={"error": {"code": "moderation_blocked", "message": "safety_violations=[violence]"}},
    )

    class Images:
        def generate(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise BadRequestError(
                    "moderation blocked",
                    response=response,
                    body={"code": "moderation_blocked"},
                )
            return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded, url=None)])

    plan = valid_plan()
    plan.scenes[0]["narration"] = "Soldiers were killed in a violent battle."
    client = SimpleNamespace(images=Images())
    monkeypatch.setattr("youtube_automation._openai_client", lambda: (client, "text-model"))

    files = generate_ai_scene_materials(plan, tmp_path, scene_numbers=[1])

    assert len(files) == 1
    assert len(calls) == 2
    assert "non-violent museum-safe" in calls[1]["prompt"]
    assert "killed" not in calls[1]["prompt"].lower()


def test_run_generator_converts_repeated_image_moderation_to_source_rejection(
    monkeypatch, tmp_path
):
    monkeypatch.setattr("youtube_automation.AI_VISUAL_FALLBACK_ENABLED", True)
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/images/generations"),
        json={"error": {"code": "moderation_blocked", "message": "safety_violations=[violence]"}},
    )

    class Images:
        def generate(self, **_kwargs):
            raise BadRequestError(
                "moderation blocked",
                response=response,
                body={"code": "moderation_blocked"},
            )

    monkeypatch.setattr(
        "youtube_automation.download_scene_materials",
        lambda *_, **__: (_ for _ in ()).throw(
            __import__("youtube_automation").MaterialsUnavailableError("missing scene")
        ),
    )
    monkeypatch.setattr(
        "youtube_automation._openai_client",
        lambda: (SimpleNamespace(images=Images()), "text-model"),
    )
    monkeypatch.setattr(
        "youtube_automation.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("render must not start after repeated moderation block")
        ),
    )

    with pytest.raises(SourceMaterialRejected) as rejected:
        run_generator(valid_plan(), 1)

    assert "moderation" in rejected.value.review.issues[0].lower()
    assert rejected.value.review.visual_alignment_score == 0


def test_run_generator_rejects_exhausted_archives_without_calling_disabled_ai(
    monkeypatch,
):
    monkeypatch.setattr("youtube_automation.AI_VISUAL_FALLBACK_ENABLED", False)
    monkeypatch.setattr(
        "youtube_automation.download_scene_materials",
        lambda *_, **__: (_ for _ in ()).throw(
            __import__("youtube_automation").MaterialsUnavailableError(
                "no public-domain or CC0 archive image found for scene 3"
            )
        ),
    )
    monkeypatch.setattr(
        "youtube_automation._generate_ai_or_reject",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled AI fallback must not be called")
        ),
    )

    with pytest.raises(SourceMaterialRejected) as rejected:
        run_generator(valid_plan(), 1)

    assert "archive image" in rejected.value.review.issues[0]
    assert rejected.value.review.visual_alignment_score == 0


def test_visual_anchor_duplicate_detection_uses_distinctive_entity_words():
    assert is_duplicate_visual_anchor(
        "Antikythera Shipwreck", ["Antikythera Mechanism"]
    )
    assert is_duplicate_visual_anchor("Pyramids of Giza", ["Giza Pyramids"])
    assert not is_duplicate_visual_anchor("Roman Pantheon", ["Roman Concrete"])


def test_run_generator_reviews_ai_fallback_before_render(monkeypatch, tmp_path):
    monkeypatch.setattr("youtube_automation.AI_VISUAL_FALLBACK_ENABLED", True)
    plan = valid_plan()
    generated = [tmp_path / f"generated-{index}.png" for index in range(1, 8)]
    monkeypatch.setattr(
        "youtube_automation.download_scene_materials",
        lambda *_, **__: (_ for _ in ()).throw(
            __import__("youtube_automation").MaterialsUnavailableError("missing scene")
        ),
    )
    monkeypatch.setattr(
        "youtube_automation.generate_ai_scene_materials", lambda *_args, **_kwargs: generated
    )
    monkeypatch.setattr(
        "youtube_automation.create_source_montage", lambda *_, **__: tmp_path / "ai-sources.jpg"
    )
    monkeypatch.setattr(
        "youtube_automation.review_source_materials",
        lambda *_, **__: QualityReview(False, 70, 100, ["AI scene mismatch"], []),
    )

    def fail_if_rendered(*_args, **_kwargs):
        raise AssertionError("CLI render must wait for AI source quality review")

    monkeypatch.setattr("youtube_automation.subprocess.run", fail_if_rendered)

    with pytest.raises(SourceMaterialRejected) as rejected:
        run_generator(plan, 1)

    assert rejected.value.review.visual_alignment_score == 70


def test_run_generator_regenerates_rejected_wikimedia_set_with_ai(monkeypatch, tmp_path):
    monkeypatch.setattr("youtube_automation.AI_VISUAL_FALLBACK_ENABLED", True)
    plan = valid_plan()
    commons = [tmp_path / f"commons-{index}.jpg" for index in range(1, 8)]
    generated = [tmp_path / "generated-2.png", tmp_path / "generated-5.png"]
    revised = [f"historic rescue corrected scene {index}" for index in range(1, 8)]
    reviews = iter(
        [
            QualityReview(False, 65, 100, ["Commons mismatch"], revised, [2, 5]),
            QualityReview(False, 70, 100, ["AI mismatch"], []),
        ]
    )
    ai_calls = []
    montage_calls = []
    monkeypatch.setattr(
        "youtube_automation.download_scene_materials",
        lambda *_, **__: (commons, [{"source_url": "https://commons.wikimedia.org"}]),
    )

    def generate_ai(*args, **kwargs):
        ai_calls.append((args, kwargs))
        return generated

    monkeypatch.setattr("youtube_automation.generate_ai_scene_materials", generate_ai)
    monkeypatch.setattr(
        "youtube_automation.create_source_montage",
        lambda files, *_: montage_calls.append(files) or tmp_path / "sources.jpg",
    )
    monkeypatch.setattr("youtube_automation.review_source_materials", lambda *_, **__: next(reviews))

    def fail_if_rendered(*_args, **_kwargs):
        raise AssertionError("CLI render must wait for regenerated AI source review")

    monkeypatch.setattr("youtube_automation.subprocess.run", fail_if_rendered)

    with pytest.raises(SourceMaterialRejected) as rejected:
        run_generator(plan, 1)

    assert len(ai_calls) == 1
    assert ai_calls[0][1]["revised_search_terms"] == revised
    assert ai_calls[0][1]["scene_numbers"] == [2, 5]
    expected = list(commons)
    expected[1] = generated[0]
    expected[4] = generated[1]
    assert montage_calls == [commons, expected]
    assert rejected.value.review.issues == ["AI mismatch"]


def test_create_source_montage_tiles_all_scene_images(monkeypatch, tmp_path):
    materials = []
    for index in range(1, 9):
        path = tmp_path / f"scene-{index}.jpg"
        Image.new("RGB", (320 + index, 240), (index * 20, 40, 80)).save(path)
        materials.append(path)
    monkeypatch.setattr("youtube_automation.REVIEW_DIR", tmp_path / "reviews")

    montage = create_source_montage(materials, 2)

    with Image.open(montage) as image:
        assert image.size == (1600, 600)
    assert montage.name.endswith("attempt-2.jpg")


def test_review_source_materials_parses_visual_gate_response(monkeypatch, tmp_path):
    monkeypatch.setattr("youtube_automation.INFERENCE_BACKEND", "openai")
    montage = tmp_path / "sources.jpg"
    montage.write_bytes(b"jpeg-bytes")
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(
                content=(
                    '{"publishable": true, "visual_alignment_score": 82, '
                    '"issues": [], "revised_search_terms": [], '
                    '"problem_scene_numbers": [2, 5]}'
                )
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr("youtube_automation._openai_client", lambda: (client, "vision-model"))

    review = review_source_materials(valid_plan(), montage)

    assert review.publishable
    assert review.visual_alignment_score == 82
    assert review.subtitle_readability_score == 100
    assert review.problem_scene_numbers == [2, 5]
    prompt_text = captured["messages"][0]["content"][0]["text"]
    assert "historic rescue" in prompt_text
    assert "before video rendering" in prompt_text
    # ⚠️ Esik promptta ANILMAZ — bkz. `yayina_uygun`. Model esigi okuyunca
    # olcmeyi birakip esigin bir tik altina oy yaziyordu (45/45/45'e karsi
    # 75/75/70). Skor bir olcek olarak tarif ediliyor, karar kodda veriliyor.
    assert "at least 50" not in prompt_text
    assert "publishable" not in prompt_text
    assert "measurement of this contact sheet, not a verdict" in prompt_text
    assert "problem_scene_numbers" in prompt_text
    assert "historically grounded ai illustrations are acceptable" in prompt_text.lower()


def test_review_video_prompt_requires_consistent_publishable_decision(monkeypatch, tmp_path):
    monkeypatch.setattr("youtube_automation.INFERENCE_BACKEND", "openai")
    montage = tmp_path / "video-montage.jpg"
    montage.write_bytes(b"jpeg-bytes")
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(
                content=(
                    '{"publishable": false, "visual_alignment_score": 80, '
                    '"subtitle_readability_score": 85, "issues": ["Blocking mismatch"], '
                    '"revised_search_terms": []}'
                )
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr("youtube_automation._openai_client", lambda: (client, "vision-model"))

    review_video(valid_plan(), montage)

    prompt_text = captured["messages"][0]["content"][0]["text"]
    # Ayni kural video incelemesinde de gecerli: burada IKI esik birden
    # yaziliydi (50 ve 80). Ikisi de kaldirildi; skorlar olcek olarak tarif
    # ediliyor, gecti/kaldi karari `yayina_uygun`'da.
    assert "at least 50" not in prompt_text
    assert "at least 80" not in prompt_text
    assert "publishable" not in prompt_text
    assert "measurements of this montage, not verdicts" in prompt_text
    assert "first 2-3 seconds" in prompt_text
    assert "historically grounded ai illustrations are acceptable" in prompt_text.lower()


def test_source_review_requests_revisions_for_blocking_publishable_false(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("youtube_automation.INFERENCE_BACKEND", "hermes-cli")

    def vision(prompt, _image):
        captured.update(prompt)
        return {
            "publishable": False,
            "visual_alignment_score": 50,
            "subtitle_readability_score": 100,
            "issues": ["blocking mismatch"],
            "revised_search_terms": [],
            "problem_scene_numbers": [2],
        }

    monkeypatch.setattr("youtube_automation._vision_json", vision)

    review_source_materials(valid_plan(), tmp_path / "sources.jpg")

    # Niyet ayni kaliyor: sorunlu her sahne icin somut bir yenileme sorgusu
    # istenmeli. Degisen, bunun ESIGE baglanmamasi — kosul artik "skor 50'nin
    # altindaysa" degil, "problem_scene_numbers'ta olan her sahne icin".
    yonerge = captured["instructions"]
    assert "for every scene number in problem_scene_numbers" in yonerge.lower()
    assert "revised_search_terms" in yonerge
    assert "below 50" not in yonerge


def test_run_cycle_records_source_rejections_and_tries_new_topics(monkeypatch, tmp_path):
    plans = []
    for index in range(1, 4):
        plan = valid_plan()
        plan.topic = f"Specific historic subject {index}"
        plan.title = f"Specific historic subject {index} #Shorts"
        plans.append(plan)
    generated = iter(plans)
    monkeypatch.setattr("youtube_automation.STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr("youtube_automation.LOCK_FILE", tmp_path / "automation.lock")
    monkeypatch.setattr("youtube_automation.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("youtube_automation.publication_slot_key", lambda *_, **__: "2026-07-30-02")
    exclusion_calls = []

    def next_plan(exclusions=None, konu=None):
        exclusion_calls.append(list(exclusions or []))
        # Kuyruksuz kipte konu HER ZAMAN None olmali; aksi halde hat sessizce
        # huniye baglanmis demektir (DW-89).
        assert konu is None
        return next(generated)

    monkeypatch.setattr("youtube_automation.generate_content_plan", next_plan)
    monkeypatch.setattr(
        "youtube_automation.run_generator",
        lambda *_, **__: (_ for _ in ()).throw(
            SourceMaterialRejected(
                QualityReview(False, 35, 100, ["Unrelated source images"], [])
            )
        ),
    )

    result = run_cycle(dry_run=True)

    assert result["status"] == "rejected"
    assert [item["stage"] for item in result["reviews"]] == [
        "source_materials",
        "source_materials",
        "source_materials",
    ]
    state = __import__("json").loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert len(state["rejected"]) == 3
    assert state["rejected"][0]["task_id"] is None
    assert state["rejected"][0]["visual_anchor"] == "historic rescue"
    assert "historic rescue" in exclusion_calls[1]


def test_run_cycle_returns_quality_rejection_when_distinct_topics_are_exhausted(
    monkeypatch, tmp_path
):
    plan = valid_plan()
    calls = 0

    def next_plan(_exclusions=None, konu=None):
        nonlocal calls
        calls += 1
        assert konu is None, "kuyruksuz kipte konu disaridan gelmemeli"
        if calls == 1:
            return plan
        raise DistinctTopicUnavailableError("no distinct topic")

    monkeypatch.setattr("youtube_automation.STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr("youtube_automation.LOCK_FILE", tmp_path / "automation.lock")
    monkeypatch.setattr("youtube_automation.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        "youtube_automation.publication_slot_key", lambda *_, **__: "2026-07-30-20"
    )
    monkeypatch.setattr("youtube_automation.generate_content_plan", next_plan)
    monkeypatch.setattr(
        "youtube_automation.run_generator",
        lambda *_, **__: (_ for _ in ()).throw(
            SourceMaterialRejected(
                QualityReview(False, 0, 100, ["archive image unavailable"], [])
            )
        ),
    )

    result = run_cycle(dry_run=True)

    assert result["status"] == "rejected"
    assert [review["stage"] for review in result["reviews"]] == [
        "source_materials",
        "planning",
    ]
    assert "distinct" in result["reviews"][-1]["review"]["issues"][0]


def test_recent_titles_includes_rejected_visual_anchor(monkeypatch, tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        '{"published": [], "completed_slots": [], "rejected": '
        '[{"topic": "Ancient Architecture", "visual_anchor": "Pyramids of Giza"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr("youtube_automation.STATE_FILE", state_file)
    monkeypatch.setattr("youtube_automation.ANALYSIS_FILE", tmp_path / "missing.json")

    history = _recent_titles()

    assert "Ancient Architecture" in history
    assert "Pyramids of Giza" in history


def test_refine_search_terms_restores_missing_visual_anchor():
    plan = valid_plan()
    review = QualityReview(
        False,
        65,
        90,
        ["One scene is unrelated"],
        [f"distinct archival object {index}" for index in range(1, 8)],
    )

    refined = refine_search_terms(plan, review)

    assert all("historic rescue" in scene["search_term"] for scene in refined.scenes)
    validate_content_plan(refined)


def test_acquire_lock_reclaims_lock_when_recorded_pid_is_dead(monkeypatch, tmp_path):
    lock = tmp_path / "automation.lock"
    lock.write_text("99999", encoding="utf-8")
    monkeypatch.setattr("youtube_automation.LOCK_FILE", lock)

    def dead_pid(_pid, _signal):
        raise ProcessLookupError

    monkeypatch.setattr("youtube_automation.os.kill", dead_pid)

    __import__("youtube_automation")._acquire_lock()

    assert lock.read_text(encoding="utf-8") == str(__import__("os").getpid())


def test_hicbir_test_global_os_name_yamalamiyor():
    """Global `os.name` yamasi geri sizmasin — DW-90'in kapattigi kusur.

    Bu bir davranis degil bir SATIR sorunu oldugu icin testi de satira
    baktiriyoruz. `monkeypatch.setattr("...os.name", ...)` tek basina butun
    pytest oturumunu `INTERNALERROR` ile coturuyor: `os.name == "nt"` oldugu
    surece `pathlib.Path()` POSIX'te `WindowsPath` uretmeye calisiyor ve
    pytest'in kendi onbellegi de `Path()` cagiriyor.

    Belirti tek bir kirmizi test degil, TUM koshumun cokmesi oldugu icin
    yakalamasi zor; Linux CI 3 Agustos'tan 6 Agustos'a kadar kirmizi kaldi ve
    dort PR'i bloke etti. Platform yamasi icin `_windows` kullanilir.
    """
    import pathlib as _pathlib

    # Igne parcali kuruluyor: tek parca yazilsaydi bu testin KENDI kaynagi
    # desene uyar ve test kendini suclardi.
    igne = 'setattr("youtube_automation.' + 'os.name"'
    kok = _pathlib.Path(__file__).resolve().parent
    suclular = sorted(
        dosya.name
        for dosya in kok.glob("**/*.py")
        if igne in dosya.read_text(encoding="utf-8")
    )

    assert suclular == [], (
        f"global `os.name` yamalayan test(ler): {suclular} — `_windows` yamalayin"
    )
