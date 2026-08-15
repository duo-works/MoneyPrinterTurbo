"""Hermes sağlayici/modeli HAT TARAFINDAN geciliyor mu.

⚠️ NEDEN VAR — olculdu (2026-08-15). `~/.hermes/config.yaml` sağlayiciyi
`github-copilot` gosterirken iki yol FARKLI davrandi:

    hermes -z ...                     -> CALISTI (12,2 sn)
    hermes chat -Q --image ... -q ... -> HTTP 429 usage limit

`chat` alt komutu yapilandirmadaki sağlayiciyi dikkate almiyor ve kimlik
havuzundan kotasi DOLU olani (openai-codex) seciyor.

Bu asimetri sessiz ve tehlikeli: metin yolu calisir, senaryo uretilir, ama
görü yolu duser — yani KAYNAK ve VIDEO incelemeleri, kotu videoyu durduran
iki kapi, birden calismaz olur.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def test_bos_ayar_HICBIR_bayrak_eklemiyor(monkeypatch):
    """Onceki davranis birebir korunmali."""
    monkeypatch.setattr(ya, "HERMES_SAGLAYICI", "")
    monkeypatch.setattr(ya, "HERMES_MODEL", "")

    assert ya.hermes_temel_komut() == ["hermes"]


def test_saglayici_ve_model_bayraga_donusuyor(monkeypatch):
    monkeypatch.setattr(ya, "HERMES_SAGLAYICI", "github-copilot")
    monkeypatch.setattr(ya, "HERMES_MODEL", "gpt-4.1")

    assert ya.hermes_temel_komut() == [
        "hermes",
        "--provider",
        "github-copilot",
        "-m",
        "gpt-4.1",
    ]


def _yakala(monkeypatch) -> dict:
    yakalanan: dict = {}

    def sahte(command, timeout):
        yakalanan["command"] = command
        return type(
            "S", (), {"returncode": 0, "stdout": '{"ok": true}', "stderr": ""}
        )()

    monkeypatch.setattr(ya, "_run_hermes", sahte)
    monkeypatch.setattr(ya, "INFERENCE_BACKEND", "hermes-cli")
    monkeypatch.setattr(ya, "HERMES_SAGLAYICI", "github-copilot")
    monkeypatch.setattr(ya, "HERMES_MODEL", "gpt-4.1")
    return yakalanan


def test_METIN_yolu_bayraklari_tasiyor(monkeypatch):
    yakalanan = _yakala(monkeypatch)

    ya._json_completion("sistem", "kullanici")
    komut = yakalanan["command"]

    assert komut[:5] == ["hermes", "--provider", "github-copilot", "-m", "gpt-4.1"]
    assert "-z" in komut


def test_GORU_yolu_bayraklari_tasiyor(monkeypatch, tmp_path):
    """⚠️ ASIL TEL BU. Görü yolu bayraksiz kalirsa 429 alir ve iki kalite
    kapisi birden coker — ustelik metin yolu calismaya devam ettigi icin
    hat "uretiyor" gorunur."""
    yakalanan = _yakala(monkeypatch)
    gorsel = tmp_path / "montaj.jpg"
    gorsel.write_bytes(b"x")

    ya._vision_json({"instructions": "bak"}, gorsel)
    komut = yakalanan["command"]

    assert komut[:5] == ["hermes", "--provider", "github-copilot", "-m", "gpt-4.1"]
    assert "chat" in komut
    assert "--image" in komut


def test_IKI_YOL_da_ayni_modeli_kullaniyor(monkeypatch, tmp_path):
    """Metin ve görü ayrisirsa senaryoyu bir model yazar, onu baska bir
    model denetler — kapinin olctugu sey uretilen sey olmaz."""
    yakalanan = _yakala(monkeypatch)

    ya._json_completion("sistem", "kullanici")
    metin_oneki = yakalanan["command"][:5]

    gorsel = tmp_path / "m.jpg"
    gorsel.write_bytes(b"x")
    ya._vision_json({"instructions": "bak"}, gorsel)
    goru_oneki = yakalanan["command"][:5]

    assert metin_oneki == goru_oneki


def test_ORTAM_DEGISKENI_yapilandirmayi_eziyor():
    """Zamanlayici ve elle koşum ayni degeri kullanabilsin diye ikisi de
    destekleniyor; kaynak sirasi ortam > config.toml."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("HERMES_SAGLAYICI = (")
    blok = kaynak[i : i + 400]

    assert 'os.getenv("YT_HERMES_PROVIDER")' in blok
    assert "youtube_automation_hermes_provider" in blok
    assert blok.index("os.getenv") < blok.index("config.app.get")
