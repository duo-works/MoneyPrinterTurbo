"""Europeana kaynagi — lisans, guvenlik siniri ve secim davranisi.

Bu dosyanin en onemli isi GUVENLIK SINIRINI kilitlemek. Depo teslim
adreslerinde sabit host beyaz listesi kullaniyor, ama Europeana bir
toplayici oldugu icin gorseller 100'den fazla kurumun sunucusunda duruyor
ve beyaz liste uygulanamiyor (olculdu: 12 konu, 1108 URL, 105 host). Yerine
konan telafi edici denetimler test ile bagli; gevserse burasi kirilir.
"""

from pathlib import Path

import pytest

import europeana_materials as EM


# --------------------------------------------------------------------------
# Lisans
# --------------------------------------------------------------------------
def test_yalnizca_kamu_mali_cc0_ve_cc_by_kabul_ediliyor():
    assert EM.lisans_uygun("http://creativecommons.org/publicdomain/mark/1.0/")
    assert EM.lisans_uygun("http://creativecommons.org/publicdomain/zero/1.0/")
    assert EM.lisans_uygun("http://creativecommons.org/licenses/by/4.0/")
    assert EM.lisans_uygun("http://creativecommons.org/licenses/by/3.0/")
    # Pay-benzer videonun TAMAMINI baglar — disarida (DW-99 ile ayni politika).
    assert not EM.lisans_uygun("http://creativecommons.org/licenses/by-sa/4.0/")
    assert not EM.lisans_uygun("http://creativecommons.org/licenses/by-nc/4.0/")
    assert not EM.lisans_uygun("http://creativecommons.org/licenses/by-nd/4.0/")
    assert not EM.lisans_uygun("http://rightsstatements.org/vocab/InC/1.0/")
    assert not EM.lisans_uygun("")


def test_lisans_adi_atif_icin_okunabilir_metne_cevriliyor():
    """`format_commons_credits` bu METNE bakip atif zorunlu mu diye karar
    veriyor; ad yanlis olursa CC BY gorseli atifsiz kalir."""
    from wikimedia_materials import is_safe_license

    assert is_safe_license(
        EM.lisans_adi("http://creativecommons.org/publicdomain/mark/1.0/")
    )
    assert is_safe_license(
        EM.lisans_adi("http://creativecommons.org/publicdomain/zero/1.0/")
    )
    # CC BY serbest DEGIL — atif zorunlu, baglanti ve lisans adi yazilmali.
    assert not is_safe_license(
        EM.lisans_adi("http://creativecommons.org/licenses/by/4.0/")
    )


# --------------------------------------------------------------------------
# Guvenlik siniri
# --------------------------------------------------------------------------
def test_guvenli_url_yalnizca_https_kabul_ediyor():
    with pytest.raises(ValueError):
        EM.guvenli_url("http://img.rmo.nl/foo.jpg")
    with pytest.raises(ValueError):
        EM.guvenli_url("ftp://example.com/foo.jpg")


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/gizli.jpg",
        "https://10.0.0.5/gizli.jpg",
        "https://192.168.1.10/gizli.jpg",
        "https://172.16.0.1/gizli.jpg",
        # Bulut ust veri ucu — SSRF'in klasik hedefi.
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/gizli.jpg",
    ],
)
def test_guvenli_url_ic_aglari_reddediyor(url):
    """Kaynak listesinden gelen bir adres ic aglara istek attiramamali."""
    with pytest.raises(ValueError):
        EM.guvenli_url(url)


def test_guvenli_url_beklenmeyen_portu_reddediyor():
    with pytest.raises(ValueError):
        EM.guvenli_url("https://example.com:8080/x.jpg")


def test_yonlendirme_her_adimda_yeniden_dogrulaniyor(monkeypatch, tmp_path: Path):
    """⚠️ Ilk adres genel olsa bile yonlendirme ic aga sapabilir.

    Denetim yalnizca ilk adrese uygulansaydi, disaridan gelen bir adres
    302 ile 127.0.0.1'e yonlendirip muhafizi tamamen atlatirdi.
    """

    class SahteYanit:
        status_code = 302
        headers = {"Location": "https://127.0.0.1/gizli.jpg"}

        def raise_for_status(self):  # pragma: no cover - cagrilmamali
            raise AssertionError("yonlendirme takip edilmemeliydi")

        def close(self):
            pass

    monkeypatch.setattr(EM.requests, "get", lambda *a, **k: SahteYanit())
    with pytest.raises(ValueError):
        EM._indir_goruntu("https://example.com/x.jpg", tmp_path / "x.jpg")


# --------------------------------------------------------------------------
# Secim
# --------------------------------------------------------------------------
def _oge(kimlik, baslik, hak, url, ek_kanit=""):
    return {
        "id": kimlik,
        "title": [baslik],
        "rights": [hak],
        "edmIsShownBy": [url],
        "dcDescription": [ek_kanit],
        "dataProvider": ["Bir Muze"],
    }


PDM = "http://creativecommons.org/publicdomain/mark/1.0/"


def test_capa_terimi_gecmeyen_aday_eleniyor():
    ogeler = [
        _oge("/1/a", "Tycho Brahe portrait", PDM, "https://example.com/a.jpg"),
        _oge("/1/b", "Rastgele bir manzara", PDM, "https://example.com/b.jpg"),
    ]
    adaylar = EM.select_europeana_candidates(
        ogeler, set(), "Tycho Brahe", required_anchor="Tycho Brahe"
    )
    assert [a["id"] for a in adaylar] == ["/1/a"]


def test_kullanilmis_kimlikler_tekrar_secilmiyor():
    ogeler = [_oge("/1/a", "Tycho Brahe", PDM, "https://example.com/a.jpg")]
    assert EM.select_europeana_candidates(
        ogeler, {"/1/a"}, "Tycho Brahe", required_anchor="Tycho Brahe"
    ) == []


def test_lisansi_gecmeyen_aday_secilmiyor():
    ogeler = [
        _oge(
            "/1/a",
            "Tycho Brahe",
            "http://creativecommons.org/licenses/by-sa/4.0/",
            "https://example.com/a.jpg",
        )
    ]
    assert (
        EM.select_europeana_candidates(
            ogeler, set(), "Tycho Brahe", required_anchor="Tycho Brahe"
        )
        == []
    )


def test_http_adresli_aday_secim_asamasinda_eleniyor():
    ogeler = [_oge("/1/a", "Tycho Brahe", PDM, "http://example.com/a.jpg")]
    assert (
        EM.select_europeana_candidates(
            ogeler, set(), "Tycho Brahe", required_anchor="Tycho Brahe"
        )
        == []
    )


def test_secim_tek_aday_degil_SIRALI_LISTE_donduruyor():
    """⚠️ Olculdu (2026-08-12, Tycho Brahe): 30 aday geciyordu ama en yuksek
    puanlinin sunucusu SSL hatasi verince sahne komple bos kaliyordu. Tek
    aday donduren bir seci, sahneyi tek bir kurumun arizasina bagliyor."""
    ogeler = [
        _oge("/1/a", "Tycho Brahe", PDM, "https://example.com/a.jpg"),
        _oge("/1/b", "Tycho Brahe astronomi", PDM, "https://example.com/b.jpg"),
        _oge("/1/c", "Tycho Brahe Uraniborg", PDM, "https://example.com/c.jpg"),
    ]
    adaylar = EM.select_europeana_candidates(
        ogeler, set(), "Tycho Brahe", required_anchor="Tycho Brahe"
    )
    assert len(adaylar) == 3


def test_cozulmemis_ic_kimlik_sanatci_adi_sayilmiyor():
    """dcCreator "22711_person" dondurebiliyor; bu deger video ACIKLAMASINA
    atif olarak basiliyordu."""
    assert not EM._sanatci_adi_mi("22711_person")
    assert not EM._sanatci_adi_mi("https://example.com/agent/5")
    assert not EM._sanatci_adi_mi("4471")
    assert EM._sanatci_adi_mi("Adriaen Matham")
    assert EM._sanatci_adi_mi("Rijksmuseum")


# --------------------------------------------------------------------------
# Kunye sozlesmesi
# --------------------------------------------------------------------------
def test_kunye_object_id_TASIMIYOR(monkeypatch, tmp_path: Path):
    """⚠️ Cagiran taraf yeniden deneme yolunda soyle yapiyor:

        excluded_met_ids={int(credit["object_id"]) for credit in credits
                          if credit.get("object_id") is not None}

    Europeana kimligi METIN ("/2020903/KKSgb7575"). `object_id` anahtari
    kullanilsaydi bu satir ValueError firlatip butun uretimi dusururdu.
    Kimlik bu yuzden `europeana_id` altinda tasiniyor.
    """
    monkeypatch.setattr(EM, "_anahtar", lambda: "sahte")
    monkeypatch.setattr(
        EM,
        "search_europeana",
        lambda _q, **_k: [
            _oge("/2020903/KKSgb7575", "Tycho Brahe", PDM, "https://example.com/a.jpg")
        ],
    )
    monkeypatch.setattr(
        EM, "_indir_goruntu", lambda _u, hedef: Path(hedef).write_bytes(b"jpg")
    )
    sonuc = EM.download_europeana_scene_material(
        ["Tycho Brahe"],
        scene_number=1,
        target_dir=tmp_path,
        used_ids=set(),
        required_anchor="Tycho Brahe",
    )
    assert sonuc is not None
    _, kunye = sonuc
    assert "object_id" not in kunye
    assert kunye["europeana_id"] == "/2020903/KKSgb7575"
    assert kunye["provider"] == "Europeana"
    # Cagiran tarafin satiri bu kunyeyle patlamamali:
    assert {
        int(k["object_id"]) for k in [kunye] if k.get("object_id") is not None
    } == set()


def test_anahtar_yoksa_kaynak_devre_disi_ve_uretim_dusmuyor(monkeypatch, tmp_path: Path):
    """Anahtar yoksa uretim DUSMEMELI — kaynak yardimci bir yol.

    ⚠️ Ortam degiskenlerini silmek YETMIYOR: `_anahtar()` once config.toml'a
    bakiyor. Anahtar oraya eklendigi anda (ki eklenmesi gerekiyor) bu test
    GERCEK AGA cikip gercek anahtarla arama yapardi — yani testi, tarif
    ettigimiz kurulum adiminin kendisi kirardi. Bu yuzden config yolu da
    kapatiliyor.
    """
    monkeypatch.delenv("EUROPEANA_API_KEY", raising=False)
    monkeypatch.delenv("EUROPEAN_API_KEY", raising=False)
    from app.config import config

    for ad in ("europeana_api_key", "european_api_key"):
        monkeypatch.setitem(config.app, ad, "")

    assert (
        EM.download_europeana_scene_material(
            ["Tycho Brahe"],
            scene_number=1,
            target_dir=tmp_path,
            used_ids=set(),
        )
        is None
    )


def test_anahtar_config_tomldan_okunuyor(monkeypatch):
    """⚠️ Modul once yalnizca ORTAMA bakiyordu; deponun butun anahtarlari ise
    config.toml'da. Uretim kosumunda kaynak sessizce kapali kalirdi."""
    monkeypatch.delenv("EUROPEANA_API_KEY", raising=False)
    monkeypatch.delenv("EUROPEAN_API_KEY", raising=False)
    from app.config import config

    monkeypatch.setitem(config.app, "europeana_api_key", "config-anahtari")
    assert EM._anahtar() == "config-anahtari"


def test_ilk_aday_inmezse_sonrakine_geciliyor(monkeypatch, tmp_path: Path):
    # ⚠️ Adresler COZULEBILIR olmali: secici `guvenli_url`'i gercekten
    # calistiriyor ve cozulemeyen hostu daha secim asamasinda eliyor.
    monkeypatch.setattr(EM, "_anahtar", lambda: "sahte")
    monkeypatch.setattr(
        EM,
        "search_europeana",
        lambda _q, **_k: [
            _oge("/1/a", "Tycho Brahe", PDM, "https://example.com/bozuk.jpg"),
            _oge("/1/b", "Tycho Brahe", PDM, "https://example.com/saglam.jpg"),
        ],
    )

    def sahte_indir(url, hedef):
        if "bozuk" in url:
            raise RuntimeError("sunucu coktu")
        Path(hedef).write_bytes(b"jpg")

    monkeypatch.setattr(EM, "_indir_goruntu", sahte_indir)
    sonuc = EM.download_europeana_scene_material(
        ["Tycho Brahe"],
        scene_number=1,
        target_dir=tmp_path,
        used_ids=set(),
        required_anchor="Tycho Brahe",
    )
    assert sonuc is not None
    assert sonuc[1]["europeana_id"] == "/1/b"


def test_arama_govdesindeki_basarisizlik_sessizce_sonuc_yok_sayilmiyor(monkeypatch):
    """⚠️ Europeana hata durumunda da HTTP 200 donduruyor; `success` alanina
    bakilmazsa hata "sonuc yok" gibi gecer."""

    class SahteYanit:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": False, "error": "Invalid API key"}

    monkeypatch.setattr(EM, "_anahtar", lambda: "sahte")
    monkeypatch.setattr(EM.requests, "get", lambda *a, **k: SahteYanit())
    assert EM.search_europeana("Tycho Brahe") == []


# --------------------------------------------------------------------------
# Atif basligi
# --------------------------------------------------------------------------
def test_atif_basligi_gercek_saglayiciyi_yaziyor():
    """Baslik sabit "Wikimedia Commons" idi; Europeana'dan gelen bir gravuru
    Commons'a mal ediyordu."""
    from youtube_automation import format_commons_credits

    metin = format_commons_credits(
        [
            {
                "scene": 1,
                "title": "Tycho Brahe",
                "source_url": "https://www.europeana.eu/item/1/a",
                "license": "Public Domain Mark 1.0",
                "artist": "Bir Muze",
                "provider": "Europeana",
                "europeana_id": "/1/a",
            }
        ]
    )
    assert "Europeana" in metin
    assert "Wikimedia Commons" not in metin
