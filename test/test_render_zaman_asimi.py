"""Render zaman asimi artik LOGU YOK ETMIYOR ve koşumu OLDURMUYOR.

⚠️ OLCULDU 2026-08-23 00:05. Uzun format koşumu render'in son adiminda
`subprocess.TimeoutExpired` ile dustu ve UC sey birden kayboldu:

  1. 90 dakikalik render'in LOGU — deneme logu `subprocess.run` DONDUKTEN
     sonra yaziliyordu, yani zaman asimi yolunda hic calismiyordu. O
     koşumda `subtitle.srt` de yazilmamisti ve altyazinin neden dustugu
     bugun HALA cevaplanamiyor.
  2. KALAN DENEMELER — istisna `run_generator` -> deneme dongusu ->
     `run_cycle` -> `main` zincirinin hicbirinde yakalanmiyordu, koşum
     `cikis 1` ile oluyordu.
  3. TELEMETRI — `state.json`'a hicbir `rejected` kaydi yazilmiyordu, yani
     darbogaz siralamasinda bu vaka HIC gorunmuyordu.

⚠️ Bu dosyadaki testler ya kodu KOSTURUR ya cagrinin ICINI ayristirir.
Metne cakili test YAZILMIYOR: bu oturumda dort kez kirildi ve dordunde de
davranis DOGRUYDU, yalnizca ifade degismisti.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


# --- Log yazimi: str / bytes / None -----------------------------------------


def _oku(yol: Path) -> str:
    return yol.read_text(encoding="utf-8")


def test_log_STR_ciktiyi_yaziyor(monkeypatch, tmp_path):
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)

    yol = ya._deneme_logu_yaz(1, "cikti satiri", "hata satiri")

    icerik = _oku(yol)
    assert "cikti satiri" in icerik
    assert "hata satiri" in icerik


def test_log_BYTES_ciktiyi_cozuyor(monkeypatch, tmp_path):
    """⚠️ ASIL TUZAK, OLCULDU — varsayilmadi.

    `subprocess.run(..., text=True)` verilmis olmasina RAGMEN
    `TimeoutExpired.stdout` CPython'da ham BAYT olarak doluyor: zaman asimi
    yolunda `_translate_newlines` hic calismiyor. Eski koddaki gibi duz
    birlestirme (`result.stdout + "..."`) yazilsaydi burada `TypeError`
    atardi — yani teshis icin tutulan log, tam teshis gerektigi anda
    kendisi duserdi.
    """
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)

    yol = ya._deneme_logu_yaz(2, b"bayt cikti", b"bayt hata")

    icerik = _oku(yol)
    assert "bayt cikti" in icerik
    assert "bayt hata" in icerik


def test_log_NONE_ciktida_da_yaziliyor(monkeypatch, tmp_path):
    """Alt surec hic bir sey basmadan asarsa iki alan da `None` kaliyor —
    olculdu. Log yine yazilmali ki "dosya yok" ile "cikti yok" ayrilsin."""
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)

    yol = ya._deneme_logu_yaz(3, None, None)

    assert yol.exists(), "cikti bos diye log dosyasi ATLANMAMALI"
    assert "--- STDERR ---" in _oku(yol)


def test_log_BOZUK_bayti_dusurmuyor(monkeypatch, tmp_path):
    """UTF-8 olmayan bayt log yazimini dusurmemeli — `errors="replace"`."""
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)

    yol = ya._deneme_logu_yaz(4, b"iyi\xff\xfekotu", None)

    assert "iyi" in _oku(yol)


# --- `run_generator` zaman asimini CEVIRIYOR --------------------------------


def _sahte_plan() -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Ephesus",
        visual_anchor="Ephesus",
        title="baslik",
        script="metin",
        scenes=[{"narration": "x", "search_term": "y"} for _ in range(6)],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def _render_yolunu_kur(monkeypatch, tmp_path):
    """`run_generator`i aga ve cikarima cikmadan render adimina kadar goturur."""
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(ya, "MATERIAL_DIR", tmp_path / "malzeme", raising=False)

    # ⚠️ GERCEK jpeg: render yolu kareleri PIL ile aciyor (kare duzeni ve
    # klip sureleri boyutu okuyor). Sahte bayt `UnidentifiedImageError`
    # veriyor ve test olcmek istedigi seye HIC ulasmiyordu.
    from PIL import Image

    kareler = []
    for n in range(6):
        kare = tmp_path / f"kare-{n}.jpg"
        Image.new("RGB", (1920, 1080), (n * 20, 40, 60)).save(kare)
        kareler.append(kare)

    monkeypatch.setattr(ya, "download_scene_materials", lambda *_a, **_k: (kareler, []))
    monkeypatch.setattr(ya, "_benzerligi_kaydet", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ya, "create_source_montage", lambda *_a, **_k: tmp_path / "montaj.jpg"
    )
    monkeypatch.setattr(
        ya,
        "review_source_materials",
        lambda *_a, **_k: ya.QualityReview(True, 100, 100, [], []),
    )


def test_zaman_asimi_TIPLI_hataya_ceviriliyor(monkeypatch, tmp_path):
    """⚠️ Yakalanmazsa `run_cycle` ve `main` delinip koşum oluyor."""
    _render_yolunu_kur(monkeypatch, tmp_path)

    def _asan_run(*_a, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd="cli.py", timeout=kwargs.get("timeout", 0), output=b"faz 2 basladi"
        )

    monkeypatch.setattr(ya.subprocess, "run", _asan_run)

    with pytest.raises(ya.RenderZamanAsimi) as bilgi:
        ya.run_generator(_sahte_plan(), 1)

    assert bilgi.value.log_path.exists(), "zaman asiminda LOG YAZILMALI"
    assert "faz 2 basladi" in _oku(bilgi.value.log_path), (
        "alt surecin ciktisi loga GECMELI — teshis tam olarak bu"
    )


def test_zaman_asimi_BICIMIN_butcesini_kullaniyor(monkeypatch, tmp_path):
    """Uzun ve Shorts ayri butce almali; cagri yerinde sabit gomulu olmamali."""
    _render_yolunu_kur(monkeypatch, tmp_path)
    gorulen: dict[str, int] = {}

    def _asan_run(*_a, **kwargs):
        gorulen["timeout"] = kwargs["timeout"]
        raise subprocess.TimeoutExpired(cmd="cli.py", timeout=kwargs["timeout"])

    monkeypatch.setattr(ya.subprocess, "run", _asan_run)

    with pytest.raises(ya.RenderZamanAsimi):
        ya.run_generator(_sahte_plan(), 1, bicim=ya.UZUN_BICIMI)
    uzun = gorulen["timeout"]

    with pytest.raises(ya.RenderZamanAsimi):
        ya.run_generator(_sahte_plan(), 1, bicim=ya.SHORTS_BICIMI)
    shorts = gorulen["timeout"]

    assert uzun == ya.render_zaman_asimi(ya.UZUN_BICIMI)
    assert shorts == ya.render_zaman_asimi(ya.SHORTS_BICIMI)
    assert uzun > shorts, "uzun format Shorts'tan uzun surer"


def test_alt_surec_TAMPONSUZ_kosuyor(monkeypatch, tmp_path):
    """⚠️ OLCULDU: basarili bir koşumun logunda teshis iceriginin TAMAMI
    stdout'ta (2026-08-22 20:05: stdout 87 satir, stderr 3). Tamponlu
    stdout zaman asiminda alt surecin ICINDE kalir ve `TimeoutExpired`
    bos doner — yani log yazilsa bile ICI BOS olurdu."""
    _render_yolunu_kur(monkeypatch, tmp_path)
    gorulen: dict[str, list[str]] = {}

    def _asan_run(command, **kwargs):
        gorulen["command"] = list(command)
        raise subprocess.TimeoutExpired(cmd="cli.py", timeout=kwargs["timeout"])

    monkeypatch.setattr(ya.subprocess, "run", _asan_run)

    with pytest.raises(ya.RenderZamanAsimi):
        ya.run_generator(_sahte_plan(), 1)

    command = gorulen["command"]
    assert "-u" in command[: command.index("cli.py")], (
        "`-u` cli.py'den ONCE, yorumlayici bayragi olarak gecmeli"
    )


# --- Deneme dongusu: zaman asimi KALAN DENEMELERI yakmiyor ------------------
#
# ⚠️ Asagisi `run_cycle`i GERCEKTEN kosturuyor. Yukaridaki testler tek bir
# fonksiyonu olcuyor; buradaki kusur ise akista: istisna yakalansa bile
# `break`/`raise` yazilsaydi koşum yine tek denemede biterdi.


def _kur_dongu(monkeypatch, tmp_path, davranis: list[str]):
    """`run_cycle`i aga cikmadan kosturur; `davranis` deneme basina eylem.

    Kalip `test_onarilabilir_red.py::_kur`den aliniyor — ucuncu bir kosum
    duzenegi icat etmek, tam da olculmek istenen akisi bozardi.
    """
    durum: dict[str, list] = {"published": [], "rejected": [], "completed_slots": []}
    monkeypatch.setattr(ya, "load_state", lambda: durum)
    monkeypatch.setattr(ya, "save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)  # URETIM loglarina DOKUNMA
    monkeypatch.setattr(
        ya, "create_review_montage", lambda *_a, **_k: tmp_path / "m.jpg"
    )
    monkeypatch.setattr(ya, "kareyi_onar", lambda *_a, **_k: [1])
    monkeypatch.setattr(ya, "generate_content_plan", lambda *_a, **_k: _sahte_plan())
    monkeypatch.setattr(
        ya, "review_video", lambda *_a, **_k: ya.QualityReview(True, 95, 90, [], [])
    )

    sayac = {"n": 0}

    def _uret(*_a, **_k):
        sayac["n"] += 1
        eylem = davranis[min(sayac["n"] - 1, len(davranis) - 1)]
        if eylem == "zaman_asimi":
            log = tmp_path / f"deneme-{sayac['n']}.log"
            log.write_text("faz 2 basladi", encoding="utf-8")
            raise ya.RenderZamanAsimi("butce asildi", log_path=log)
        return (
            "gorev",
            tmp_path / "v.mp4",
            tmp_path / "s.txt",
            [],
            0,
            tmp_path / "malzeme",
        )

    monkeypatch.setattr(ya, "run_generator", _uret)

    ya.run_cycle(konu_override="Ephesus", dry_run=True)
    return durum, sayac["n"]


def test_zaman_asimi_KOSUMU_OLDURMUYOR(monkeypatch, tmp_path):
    """⚠️ 2026-08-23 00:05'te istisna `run_cycle`i ve `main`i delip gecti;
    koşum `cikis 1` ile oldu. `run_cycle` artik donmek zorunda."""
    durum, deneme = _kur_dongu(monkeypatch, tmp_path, ["zaman_asimi", "basari"])

    assert deneme >= 2, f"ikinci deneme HIC calismadi (deneme={deneme})"


def test_zaman_asimi_SONRAKI_deneme_yayina_gidebiliyor(monkeypatch, tmp_path):
    """Zaman asimi PLANIN kusuru degil — ayni plan yeniden render edilmeli."""
    durum, _ = _kur_dongu(monkeypatch, tmp_path, ["zaman_asimi", "basari"])

    zaman_asimlari = [
        k for k in durum["rejected"] if k.get("stage") == "render_timeout"
    ]
    assert len(zaman_asimlari) == 1, "yalnizca BIRINCI deneme asmisti"


def test_zaman_asimi_TELEMETRIYE_yaziliyor(monkeypatch, tmp_path):
    """⚠️ Eskiden hicbir kayit yazilmiyordu, yani darbogaz siralamasinda bu
    vaka HIC gorunmuyordu — `red-kayitlari-kosum-paydasi-degil` dersinin
    ta kendisi."""
    durum, _ = _kur_dongu(monkeypatch, tmp_path, ["zaman_asimi", "basari"])

    kayit = next(k for k in durum["rejected"] if k.get("stage") == "render_timeout")
    assert kayit["attempt"] == 1
    assert kayit["butce_sn"] == ya.render_zaman_asimi(ya.SHORTS_BICIMI)
    assert kayit["log"], "teshis icin log yolu kayda GECMELI"
    assert "aday_basligi" in kayit, "soguma bu alani okuyor"


def test_HER_deneme_asarsa_kayit_HER_BIRI_icin_var(monkeypatch, tmp_path):
    """Butce gercekten kucukse her deneme asar; hicbiri sessizce kaybolmamali."""
    durum, deneme = _kur_dongu(monkeypatch, tmp_path, ["zaman_asimi"])

    kayitlar = [k for k in durum["rejected"] if k.get("stage") == "render_timeout"]
    assert len(kayitlar) == deneme, (
        f"{deneme} deneme asti ama {len(kayitlar)} kayit yazildi"
    )
    assert deneme > 1, "dongu ilk asimda durmamali"


# --- Cagri yerinin ICI: butce sabit gomulu degil -----------------------------


def _run_generator_agaci() -> ast.FunctionDef:
    agac = ast.parse(Path(ya.__file__).read_text(encoding="utf-8"))
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.FunctionDef) and dugum.name == "run_generator":
            return dugum
    raise AssertionError("run_generator bulunamadi")


def _subprocess_run_cagrilari(govde: ast.AST) -> list[ast.Call]:
    return [
        d
        for d in ast.walk(govde)
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and d.func.attr == "run"
        and isinstance(d.func.value, ast.Name)
        and d.func.value.id == "subprocess"
    ]


def test_render_butcesi_CAGRI_YERINDE_sabit_degil():
    """⚠️ Bu test eskiden KAYNAK METNINDE
    `"timeout=render_zaman_asimi(bicim)"` ariyordu ve 2026-08-23'te davranis
    DOGRUYKEN dustu — ifade `butce = render_zaman_asimi(bicim)` +
    `timeout=butce` haline gelmisti. Metne cakili test gercek bir kusur
    bildirmedi, yalnizca yeniden yazimi engelledi. Artik cagrinin ICI
    ayristiriliyor: `timeout` bir SABIT olmasin yeter.
    """
    cagrilar = _subprocess_run_cagrilari(_run_generator_agaci())

    assert cagrilar, "run_generator icinde subprocess.run cagrisi yok"
    for cagri in cagrilar:
        butce = next((k for k in cagri.keywords if k.arg == "timeout"), None)
        assert butce is not None, "render cagrisinda `timeout` YOK"
        assert not isinstance(butce.value, ast.Constant), (
            "butce sabit gomulu — bicim dallanmasi hic calismazdi"
        )


def test_render_cagrisi_ZAMAN_ASIMINI_yakaliyor():
    """`subprocess.run` bir `try` icinde ve `TimeoutExpired` yakalaniyor mu.

    ⚠️ Cagrinin ICI ayristiriliyor cunku asil kusur "except yok"tu; sabitin
    dogru olmasi tek basina koşumu kurtarmiyor.
    """
    govde = _run_generator_agaci()
    korunan = [
        d
        for d in ast.walk(govde)
        if isinstance(d, ast.Try) and _subprocess_run_cagrilari(ast.Module(d.body, []))
    ]

    assert korunan, "subprocess.run hicbir `try` icinde degil"
    yakalanan = {
        ast.unparse(iscil.type)
        for dene in korunan
        for iscil in dene.handlers
        if iscil.type is not None
    }
    assert any("TimeoutExpired" in ad for ad in yakalanan), (
        f"`TimeoutExpired` yakalanmiyor; yakalananlar: {yakalanan}"
    )
