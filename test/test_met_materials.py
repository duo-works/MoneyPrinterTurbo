from met_materials import download_met_scene_material, select_met_candidate


def test_select_met_candidate_requires_public_domain_image_and_semantic_match():
    objects = [
        {
            "objectID": 1,
            "title": "Modern Garden Painting",
            "isPublicDomain": True,
            "primaryImage": "https://images.metmuseum.org/CRDImages/modern.jpg",
            "objectURL": "https://www.metmuseum.org/art/collection/search/1",
            "culture": "Modern",
            "objectName": "Painting",
        },
        {
            "objectID": 2,
            "title": "Roman Architectural Fragment",
            "isPublicDomain": False,
            "primaryImage": "https://images.metmuseum.org/CRDImages/roman.jpg",
            "objectURL": "https://www.metmuseum.org/art/collection/search/2",
            "culture": "Roman",
            "objectName": "Architectural fragment",
        },
        {
            "objectID": 3,
            "title": "Roman Concrete Vault Fragment",
            "isPublicDomain": True,
            "primaryImage": "https://images.metmuseum.org/CRDImages/vault.jpg",
            "objectURL": "https://www.metmuseum.org/art/collection/search/3",
            "culture": "Roman",
            "period": "Imperial",
            "objectName": "Architectural fragment",
            "artistDisplayName": "",
        },
    ]

    selected = select_met_candidate(objects, used_ids=set(), query="Roman concrete vault")

    assert selected is not None
    assert selected["id"] == 3
    assert selected["license"] == "CC0 / Public Domain"


def test_select_met_candidate_requires_distinctive_visual_anchor_term():
    objects = [
        {
            "objectID": 10,
            "title": "Canopic Jar",
            "isPublicDomain": True,
            "primaryImage": "https://images.metmuseum.org/CRDImages/jar.jpg",
            "objectURL": "https://www.metmuseum.org/art/collection/search/10",
            "culture": "Egyptian",
            "objectName": "Canopic jar",
        },
        {
            "objectID": 11,
            "title": "Scarab Amulet",
            "isPublicDomain": True,
            "primaryImage": "https://images.metmuseum.org/CRDImages/scarab.jpg",
            "objectURL": "https://www.metmuseum.org/art/collection/search/11",
            "culture": "Egyptian",
            "objectName": "Scarab amulet",
        },
    ]

    selected = select_met_candidate(
        objects,
        used_ids=set(),
        query="Egyptian scarab amulet museum",
        required_anchor="Egyptian scarab",
    )

    assert selected is not None
    assert selected["id"] == 11


def test_select_met_candidate_rejects_duplicate_object():
    objects = [
        {
            "objectID": 3,
            "title": "Roman Concrete Vault Fragment",
            "isPublicDomain": True,
            "primaryImage": "https://images.metmuseum.org/CRDImages/vault.jpg",
            "objectURL": "https://www.metmuseum.org/art/collection/search/3",
            "culture": "Roman",
        }
    ]

    assert select_met_candidate(objects, used_ids={3}, query="Roman concrete") is None


def test_download_met_scene_material_returns_file_and_cc0_credit(monkeypatch, tmp_path):
    objects = [
        {
            "objectID": 9,
            "title": "Roman Vault Fragment",
            "isPublicDomain": True,
            "primaryImage": "https://images.metmuseum.org/CRDImages/vault.jpg",
            "objectURL": "https://www.metmuseum.org/art/collection/search/9",
            "culture": "Roman",
            "objectName": "Vault fragment",
        }
    ]
    monkeypatch.setattr("met_materials.search_met", lambda _query: objects)

    def download(_url, destination):
        destination.write_bytes(b"met-image")

    monkeypatch.setattr("met_materials._download_image", download)

    result = download_met_scene_material(
        ["Roman vault"], scene_number=2, target_dir=tmp_path, used_ids=set()
    )

    assert result is not None
    path, credit = result
    assert path.name == "scene-02-met.jpg"
    assert path.read_bytes() == b"met-image"
    assert credit["source_url"].endswith("/9")
    assert credit["license"] == "CC0 / Public Domain"
    assert credit["provider"] == "The Metropolitan Museum of Art"
