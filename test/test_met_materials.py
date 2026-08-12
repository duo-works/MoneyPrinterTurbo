import pytest
import requests

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


# --- Eksik nesne dayanikliligi (DW-95) -----------------------------------


class _SahteYanit:
    def __init__(self, kod, govde=None):
        self.status_code = kod
        self._govde = govde or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error")

    def json(self):
        return self._govde


def test_silinmis_nesne_aramayi_oldurmuyor(monkeypatch):
    """Olculdu (2026-08-06): Met arama indeksi artik var olmayan nesne
    kimlikleri donduruyor. Nesne 844492 aramada cikti, detay ucu 404 verdi ve
    `raise_for_status` BUTUN uretim kosumunu oldurdu — konu, icerik plani ve o
    ana kadar harcanan LLM parasi bosa gitti.
    """
    import met_materials

    met_materials._OBJECT_CACHE.clear()

    def sahte_get(url, **_kwargs):
        if "search" in url:
            return _SahteYanit(200, {"objectIDs": [844492, 7]})
        if url.endswith("/844492"):
            return _SahteYanit(404)
        return _SahteYanit(200, {"objectID": 7, "title": "Roman Vault"})

    monkeypatch.setattr(met_materials.requests, "get", sahte_get)
    monkeypatch.setattr(met_materials.time, "sleep", lambda _s: None)

    sonuc = met_materials.search_met("roman vault")

    assert [o["objectID"] for o in sonuc] == [7], "eksik nesne atlanip digeri donmeli"


def test_gecici_ag_hatasi_da_atlaniyor(monkeypatch):
    """Zaman asimi tek nesneyi kaybettirir, arama sonucunu degil."""
    import met_materials

    met_materials._OBJECT_CACHE.clear()

    def sahte_get(url, **_kwargs):
        if "search" in url:
            return _SahteYanit(200, {"objectIDs": [1, 2]})
        if url.endswith("/1"):
            raise requests.Timeout("zaman asimi")
        return _SahteYanit(200, {"objectID": 2, "title": "Roman Vault"})

    monkeypatch.setattr(met_materials.requests, "get", sahte_get)
    monkeypatch.setattr(met_materials.time, "sleep", lambda _s: None)

    sonuc = met_materials.search_met("roman vault")

    assert [o["objectID"] for o in sonuc] == [2]


def test_arama_ucunun_kendisi_duserse_hata_yutulmuyor(monkeypatch):
    """Tek nesne baska, arama ucunun tamami baska: ikincisi gercek bir hata."""
    import met_materials

    met_materials._OBJECT_CACHE.clear()
    monkeypatch.setattr(
        met_materials.requests, "get", lambda url, **_k: _SahteYanit(500)
    )

    with pytest.raises(requests.HTTPError):
        met_materials.search_met("roman vault")


def test_arama_istegi_zaman_asimina_ugrarsa_bos_donuyor(monkeypatch):
    """Arama istegi TIMEOUT olursa kosum COKMEMELI, bos liste donmeli.

    Olculdu (2026-08-13): Met artik her sahnede ILK denenen kaynak
    (bkz. wikimedia_materials.py sira degisikligi), yani bu istek eskisinden
    cok daha sik atiliyor. collectionapi.metmuseum.org gecici read-timeout
    verdi ve yakalanmamis istisna butun uretim kosumunu (LLM plani, o ana
    kadar indirilen gorseller) coplulukle birlikte olduruyordu.
    """
    import met_materials

    met_materials._OBJECT_CACHE.clear()

    def sahte_get(url, **_kwargs):
        raise requests.Timeout("zaman asimi")

    monkeypatch.setattr(met_materials.requests, "get", sahte_get)

    sonuc = met_materials.search_met("roman vault")

    assert sonuc == []


def test_arama_istegi_baglanti_hatasinda_bos_donuyor(monkeypatch):
    """Ayni koruma ConnectionError icin de gecerli — DNS/ag kesintisi."""
    import met_materials

    met_materials._OBJECT_CACHE.clear()

    def sahte_get(url, **_kwargs):
        raise requests.ConnectionError("baglanti koptu")

    monkeypatch.setattr(met_materials.requests, "get", sahte_get)

    sonuc = met_materials.search_met("roman vault")

    assert sonuc == []
