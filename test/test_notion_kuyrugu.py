"""Trend hunisi koprusu — video hatti konuyu kuyruktan alir.

Ayri dosya, cunku `test_youtube_automation.py` buyudu ve bu is kendi
sozlesmesine sahip: `ytoto` CLI'i cagrilir, Notion'a dogrudan dokunulmaz.
Testler gercek `ytoto`'yu calistirmaz — alt surec yamalanir.
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notion_kuyrugu as nk  # noqa: E402

ORNEK = {
    "kimlik": "abc123",
    "baslik": "Roma su kemerleri",
    "sayfa_url": "https://notion.so/abc123",
    "onerilen_format": "Shorts",
    "dil": "en",
    "bosluk_skoru": 0.41,
    "talep": 24000,
}


@pytest.fixture
def sahte_kos(monkeypatch):
    """`ytoto` cagrilarini yakalar; gercek surec calismaz."""
    cagrilar = []

    def kur(cikti="", hata="", kod=0):
        def kos(komut, **_kwargs):
            cagrilar.append(komut)
            return SimpleNamespace(returncode=kod, stdout=cikti, stderr=hata)

        monkeypatch.setattr(subprocess, "run", kos)
        monkeypatch.setattr(nk, "_ytoto_yolu", lambda _yol: "/sahte/ytoto")
        return cagrilar

    return kur


def test_kuyruk_secildi_durumunu_okuyor(sahte_kos):
    """Video hattinin okudugu kuyruk `Yeni` degil `Secildi` olmali.

    `Yeni` insanin daha bakmadigi ham liste; oradan uretmek insani devreden
    cikarir.
    """
    cagrilar = sahte_kos(cikti=json.dumps([ORNEK]))

    (aday,) = nk.kuyrugu_oku(ytoto_path="/sahte/ytoto")

    assert aday.baslik == "Roma su kemerleri"
    assert aday.kimlik == "abc123"
    (komut,) = cagrilar
    assert komut[1:4] == ["aday", "listele", "--durum"]
    assert "Seçildi" in komut


def test_bos_kuyruk_hata_degil(sahte_kos):
    """`ytoto` bos listede 1 donuyor — bu basarisizlik sayilmamali.

    ⚠️ Bos kuyrugun isareti cikis kodu DEGIL, stdout'a basilan "[]". Olculdu
    (2026-08-12): `ytoto aday listele --json` bos sonucta cikis 1 + "[]"
    veriyor.
    """
    sahte_kos(cikti="[]", kod=1)

    assert nk.kuyrugu_oku(ytoto_path="/sahte/ytoto") == []


def test_gercek_hata_yutulmuyor(sahte_kos):
    sahte_kos(cikti="", hata="token yok", kod=2)

    with pytest.raises(nk.KopruHatasi, match="cikti vermedi"):
        nk.kuyrugu_oku(ytoto_path="/sahte/ytoto")


def test_eksik_token_BOS_KUYRUK_sanilmiyor(sahte_kos):
    """⚠️ Uretimde yasandi (2026-08-12): NOTION_TOKEN cevrede yokken `ytoto`
    cikis 1 + BOS stdout donuyor, hatayi stderr'e yaziyor. Eski kod bunu
    "kuyruk bos" okuyordu ve hat "`Secildi` kuyrugu bos" diyerek duruyordu —
    yani YAPILANDIRMA BOZUKKEN insanin secim yapmadigini soyluyordu.

    Sessiz sifir: dogru davranan bir hattan ayirt edilemiyor. Kuyrukta dort
    aday dururken hat "aday yok" dedi.
    """
    sahte_kos(cikti="", hata="HATA: NOTION_TOKEN tanımlı değil.", kod=1)

    with pytest.raises(nk.KopruHatasi, match="NOTION_TOKEN"):
        nk.kuyrugu_oku(ytoto_path="/sahte/ytoto")


def test_bozuk_json_anlasilir_hata(sahte_kos):
    sahte_kos(cikti="<html>500</html>")

    with pytest.raises(nk.KopruHatasi, match="JSON vermedi"):
        nk.kuyrugu_oku(ytoto_path="/sahte/ytoto")


def test_kapma_basarisizligi_yutulmuyor(sahte_kos):
    """Kapamayan kosum, baska kosumun ayni adayi uretecegi anlamina gelir."""
    sahte_kos(hata="durum Üretiliyor, beklenen Seçildi", kod=1)
    aday = nk.Aday.sozlukten(ORNEK)

    with pytest.raises(nk.KopruHatasi, match="kapilamadi"):
        nk.adayi_kap(aday, ytoto_path="/sahte/ytoto")


def test_birakma_hatasi_kosumu_bir_kez_daha_patlatmiyor(sahte_kos, capsys):
    """Temizlik adimi asil hatayi gizlememeli — uyarir, firlatmaz."""
    sahte_kos(hata="baglanti yok", kod=1)
    aday = nk.Aday.sozlukten(ORNEK)

    nk.adayi_birak(aday, gerekce="test", ytoto_path="/sahte/ytoto")

    assert "kuyruga geri konamadi" in capsys.readouterr().out


def test_kapatma_video_url_gonderiyor(sahte_kos):
    cagrilar = sahte_kos()
    aday = nk.Aday.sozlukten(ORNEK)

    nk.adayi_kapat(
        aday, video_url="https://youtu.be/x", ytoto_path="/sahte/ytoto"
    )

    (komut,) = cagrilar
    assert komut[1:3] == ["aday", "bitir"]
    assert komut[komut.index("--video-url") + 1] == "https://youtu.be/x"


def test_ytoto_bulunamazsa_sessizce_gecilmiyor(monkeypatch):
    """Bulunamayan kopru, kendi konusunu ureten bir hattan daha iyidir.

    Sessiz geri dusus en kotu sonuc: hat kuyruga bagli SANILIR ama degildir.
    """
    monkeypatch.setattr(nk.shutil, "which", lambda _ad: None)

    with pytest.raises(nk.KopruYok, match="PATH'te yok"):
        nk.kuyrugu_oku(ytoto_path=None)


def test_yanlis_yapilandirilmis_yol_anlasilir_hata(tmp_path):
    yok = tmp_path / "olmayan-ytoto"

    with pytest.raises(nk.KopruYok, match="ytoto bulunamadi"):
        nk.kuyrugu_oku(ytoto_path=str(yok))


# --- run_cycle sozlesmesi: kuyruk kipi -----------------------------------


@pytest.fixture
def hat(monkeypatch, tmp_path):
    """`run_cycle`'i disariya hic dokunmadan kosturur."""
    import youtube_automation as ya

    monkeypatch.setattr(ya, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(ya, "LOCK_FILE", tmp_path / "lock")
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(ya, "YTOTO_PATH", "/sahte/ytoto")
    return ya


def test_kuyruk_bossa_konu_uydurulmuyor(hat, monkeypatch):
    """Sessiz geri dusus OLMAMALI.

    Kuyruga bagli oldugunu sanan ama kendi konusunu ureten bir hat, hic
    baglanmamis olmaktan daha kotu — cunku fark edilmiyor. 6 Agustos gecesi
    uretilen 6 videonun konusu tam olarak boyle secildi.
    """
    monkeypatch.setattr(nk, "kuyrugu_oku", lambda **_kwargs: [])
    cagrildi = []
    monkeypatch.setattr(
        hat, "generate_content_plan", lambda *a, **k: cagrildi.append(1)
    )

    sonuc = hat.run_cycle(kuyruktan=True, dry_run=True)

    assert sonuc["status"] == "no-candidate"
    assert not cagrildi, "kuyruk bosken plan uretilmemeli"


def test_kuyruktaki_konu_plana_gecuyor(hat, monkeypatch):
    """Adayin basligi `generate_content_plan`'a `konu` olarak gitmeli."""
    aday = nk.Aday.sozlukten(ORNEK)
    monkeypatch.setattr(nk, "kuyrugu_oku", lambda **_kwargs: [aday])
    monkeypatch.setattr(nk, "adayi_kap", lambda *a, **k: None)
    gecen = {}

    def sahte_plan(_exclusions=None, konu=None):
        gecen["konu"] = konu
        raise hat.DistinctTopicUnavailableError("dur")

    monkeypatch.setattr(hat, "generate_content_plan", sahte_plan)
    monkeypatch.setattr(nk, "adayi_birak", lambda *a, **k: None)

    hat.run_cycle(kuyruktan=True, dry_run=True)

    assert gecen["konu"] == "Roma su kemerleri"


def test_uretim_dusunce_aday_kuyruga_geri_konuyor(hat, monkeypatch):
    """Kapmanin karsiligi olmadan aday `Uretiliyor`da mahsur kalir."""
    aday = nk.Aday.sozlukten(ORNEK)
    monkeypatch.setattr(nk, "kuyrugu_oku", lambda **_kwargs: [aday])
    monkeypatch.setattr(nk, "adayi_kap", lambda *a, **k: None)
    monkeypatch.setattr(
        hat,
        "generate_content_plan",
        lambda *a, **k: (_ for _ in ()).throw(hat.DistinctTopicUnavailableError("yok")),
    )
    birakilan = []
    monkeypatch.setattr(
        nk, "adayi_birak", lambda a, **k: birakilan.append(a.kimlik)
    )

    hat.run_cycle(kuyruktan=True, dry_run=True)

    assert birakilan == ["abc123"]


def test_beklenmedik_istisnada_da_aday_birakiliyor(hat, monkeypatch):
    """`finally` tek cikis noktasi — hicbir yol adayi asili birakmamali."""
    aday = nk.Aday.sozlukten(ORNEK)
    monkeypatch.setattr(nk, "kuyrugu_oku", lambda **_kwargs: [aday])
    monkeypatch.setattr(nk, "adayi_kap", lambda *a, **k: None)
    monkeypatch.setattr(
        hat,
        "generate_content_plan",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk doldu")),
    )
    birakilan = []
    monkeypatch.setattr(nk, "adayi_birak", lambda a, **k: birakilan.append(a.kimlik))

    with pytest.raises(RuntimeError, match="disk doldu"):
        hat.run_cycle(kuyruktan=True, dry_run=True)

    assert birakilan == ["abc123"], "istisna yolunda da kuyruga geri konmali"


def test_kuyruksuz_kipte_kopru_hic_cagrilmiyor(hat, monkeypatch):
    """Varsayilan davranis degismemeli — `ytoto` kurulu olmayabilir."""
    def patla(**_kwargs):
        raise AssertionError("kuyruksuz kipte kopru cagrilmamali")

    monkeypatch.setattr(nk, "kuyrugu_oku", patla)
    monkeypatch.setattr(
        hat,
        "generate_content_plan",
        lambda *a, **k: (_ for _ in ()).throw(hat.DistinctTopicUnavailableError("dur")),
    )

    sonuc = hat.run_cycle(dry_run=True)

    assert sonuc["status"] == "rejected"
