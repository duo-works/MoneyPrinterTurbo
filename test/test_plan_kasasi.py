"""Odenmis plan kasasi (2026-09-12).

⚠️ NEDEN VAR — olculdu, `storage/youtube_automation/logs/hata-*.log` 156 dosya:

    plan KURULDUKTAN sonra traceback ile olen koşum : 117
    bunlarin yayin yapabilmis olani                 :   0

Yani hattin bugune kadarki her cokusu PARASI ODENMIS bir plani cope atti.
Ayni gun 16:05 koşumu bunun kalemi kalemine olculmus hali: dort metin cagrisi
($0,0217) Ayasofya planini kurdu, bir goru cagrisi ($0,0030) kaynaklari
onayladi, sonra `images.weserv.nl` DNS'i cozulemedi. Kaybin %88'i PLANDI.

⚠️ Testler metne cakili DEGIL: hepsi ya kodu gercekten kosturuyor ya da
`run_cycle`in AGACINI okuyor. Bu oturum ailesinde metne cakili test yedi kez
kirildi.

⚠️ En kritik iki davranis, birbirinin tersi ve IKISI DE test ediliyor:

  · UYMAYAN koşum kasayi YAKMAZ — 00:05 uzun kolu, kasadaki Shorts planini
    cope atarsa kasa tam da kurtarmak icin yazildigi parayi yakan sey olur.
  · KALITE REDDI kasayi YAKAR — yoksa tasarruf araci kalite kapisini deler.
"""

import ast
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(sahne: int = 8, capa: str = "Cutty Sark") -> ya.ContentPlan:
    """`validate_content_plan(plan, sahne)` kapisindan GECEN bir plan."""
    return ya.ContentPlan(
        topic="konu",
        visual_anchor=capa,
        title="baslik #Shorts",
        script=(
            "Cutty Sark was built for speed and outlived the trade that made her. "
            "She raced tea home from China until steamships took the route away. "
            "Her captain fitted a new rudder at sea after the old one broke apart. "
            "She was reconditioned at Falmouth and became a training ship instead. "
            "Today she sits in dry dock at Greenwich, the last of her kind afloat. "
            "No other clipper of that fleet survived the century intact. Her masts "
            "were rebuilt twice and her hull still carries the original iron frame "
            "that the Dumbarton yard riveted into place in 1869."
        ),
        scenes=[
            {
                "narration": f"sahne {sira}",
                # ⚠️ Arama terimi CAPAYI icermek zorunda (`plan_kusurlari`).
                # Sabit "Cutty Sark" yazilinca capa degisen testler kasayi
                # sahte bir sebeple yaktiriyordu — kapinin kendisi dogruydu.
                "search_term": f"{capa} detay {sira}",
                "kaynak_dosya": f"d-{sira}.jpg",
            }
            for sira in range(1, sahne + 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


@pytest.fixture
def kasa(tmp_path, monkeypatch):
    """Kasa DIZINI bagliyor, Shorts-8 dosyasinin yolunu donuyor.

    ⚠️ Dizin, tek dosya degil: ilk tasarim tek dosyaydi ve gecelik UZUN
    koşum, kasadaki Shorts planini ustune yazip oldururdu.
    """
    monkeypatch.setattr(ya, "PLAN_KASASI", tmp_path / "plan_kasasi")
    return ya.kasa_yolu(ya.SHORTS_BICIMI, 8)


def _koy(kasa_yolu, plan, *, bicim=None, sahne=8, konu=None):
    ya.plani_kasaya_koy(
        plan,
        bicim=bicim or ya.SHORTS_BICIMI,
        sahne_sayisi=sahne,
        konu=konu,
    )
    return kasa_yolu


def _al(*, bicim=None, sahne=8, konu=None, state=None):
    return ya.kasadan_plan_al(
        bicim=bicim or ya.SHORTS_BICIMI,
        sahne_sayisi=sahne,
        konu=konu,
        state=state if state is not None else {},
    )


def _yasini_geriye_al(kasa_yolu, saat: float) -> None:
    veri = json.loads(kasa_yolu.read_text(encoding="utf-8"))
    veri["yazildi"] = (
        datetime.now(ZoneInfo(ya.TIMEZONE_NAME)) - timedelta(hours=saat)
    ).isoformat()
    kasa_yolu.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")


# --- Gidis-donus -------------------------------------------------------------


def test_KASAYA_KONAN_PLAN_aynen_geri_geliyor(kasa):
    _koy(kasa, _plan())
    geri = _al()
    assert geri is not None
    assert geri == _plan()


def test_ISTEGE_BAGLI_ALAN_da_tasiniyor(kasa):
    """`ruh_hali` varsayilanli — sema sadakati burada kirilirdi."""
    plan = _plan()
    plan.ruh_hali = "agirbasli"
    _koy(kasa, plan)
    geri = _al()
    assert geri is not None
    assert geri.ruh_hali == "agirbasli"


def test_BOS_KASA_None_donuyor(kasa):
    assert _al() is None


# --- "Bu koşuma uymuyor" : kasa DURUYOR --------------------------------------


def test_BASKA_BICIM_kasayi_YAKMIYOR(kasa):
    """00:05 uzun kolu, kasadaki Shorts planini cope atamaz."""
    _koy(kasa, _plan())
    assert _al(bicim=ya.UZUN_BICIMI, sahne=None) is None
    assert kasa.exists(), "uymayan bicim kasayi yakmamali"
    assert _al() is not None, "Shorts koşumu plani hala bulmali"


def test_UZUN_PLAN_YAZMAK_Shorts_kasasini_EZMIYOR(kasa):
    """⚠️ ILK TASARIMIN KUSURU, tam olarak bu.

    Kasa tek dosyaydi. Izgarada bes tetik var (00:05 uzun + dort Shorts) ve
    gece yarisi kurulan uzun plan, kasadaki Shorts planini USTUNE YAZIYORDU.
    Yani "uymayan koşum kasayi yakmasin" kurali, kasanin kendi YAZMA yolundan
    deliniyordu: gecelik koşum her gece bir Shorts planini oldururdu ve kimse
    gormezdi, cunku kasa zaten bazen bos olabilen bir sey.
    """
    _koy(kasa, _plan(8, capa="Hagia Sophia"))
    ya.plani_kasaya_koy(
        _plan(6, capa="Petra"), bicim=ya.UZUN_BICIMI, sahne_sayisi=None, konu=None
    )

    geri = _al()
    assert geri is not None, "uzun plan yazmak Shorts kasasini silmis"
    assert geri.visual_anchor == "Hagia Sophia"


def test_BASKA_SAHNE_SAYISI_kasayi_YAKMIYOR(kasa):
    _koy(kasa, _plan(), sahne=8)
    assert _al(sahne=6) is None
    assert kasa.exists()


def test_BASKA_KONU_kasayi_YAKMIYOR(kasa):
    """Acik konu / kuyruk adayi baskaysa plan o koşuma ait degil, cop degil."""
    _koy(kasa, _plan(), konu="konu")
    assert _al(konu="bambaska konu") is None
    assert kasa.exists()


def test_AYNI_KONU_isteyen_kosum_plani_aliyor(kasa):
    _koy(kasa, _plan(), konu="konu")
    assert _al(konu="konu") is not None


def test_KONU_ISTENMEYEN_kosum_kasadakini_kabul_ediyor(kasa):
    """Model-secer kipinde kasadaki konu zaten ayni havuzdan secilmisti."""
    _koy(kasa, _plan(), konu="konu")
    assert _al(konu=None) is not None


# --- "Artik gecersiz" : kasa YANIYOR -----------------------------------------


def test_BAYAT_PLAN_yakiliyor(kasa):
    _koy(kasa, _plan())
    _yasini_geriye_al(kasa, ya.PLAN_KASASI_OMRU_SAAT + 1)
    assert _al() is None
    assert not kasa.exists()


def test_OMRUN_ICINDEKI_plan_duruyor(kasa):
    _koy(kasa, _plan())
    _yasini_geriye_al(kasa, ya.PLAN_KASASI_OMRU_SAAT - 1)
    assert _al() is not None


def test_ENGELLI_CAPA_yakiliyor(kasa):
    """Yayinlanan capa `engellenen_capalar`a girer — kasa o kapiyi OKUR."""
    _koy(kasa, _plan(capa="Cutty Sark"))
    state = {"published": [{"visual_anchor": "Cutty Sark"}]}
    assert _al(state=state) is None
    assert not kasa.exists()


def test_BUGUNUN_KAPILARINDAN_dusen_plan_yakiliyor(kasa):
    bozuk = _plan()
    bozuk.script = "cok kisa"
    _koy(kasa, bozuk)
    assert _al() is None
    assert not kasa.exists()


def test_SEMA_DEGISIRSE_yakiliyor(kasa):
    _koy(kasa, _plan())
    veri = json.loads(kasa.read_text(encoding="utf-8"))
    veri["plan"]["bilinmeyen_alan"] = 1
    kasa.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    assert _al() is None
    assert not kasa.exists()


def test_BOZUK_JSON_kosumu_dusurmuyor(kasa):
    kasa.parent.mkdir(parents=True, exist_ok=True)
    kasa.write_text("{ bu json degil", encoding="utf-8")
    assert _al() is None


# --- Emniyet subabi ----------------------------------------------------------


def test_DENEME_SAYACI_her_alista_artiyor(kasa):
    _koy(kasa, _plan())
    for beklenen in range(1, ya.PLAN_KASASI_AZAMI_DENEME + 1):
        assert _al() is not None
        veri = json.loads(kasa.read_text(encoding="utf-8"))
        assert veri["deneme"] == beklenen


def test_AZAMI_DENEMEDEN_sonra_yakiliyor(kasa):
    _koy(kasa, _plan())
    for _ in range(ya.PLAN_KASASI_AZAMI_DENEME):
        assert _al() is not None
    assert _al() is None
    assert not kasa.exists()


def test_SAYAC_OKUMADAN_ONCE_degil_SONRA_artiyor(kasa):
    """Sert olumde (SIGKILL) bile deneme sayilmis olmali."""
    _koy(kasa, _plan())
    _al()
    veri = json.loads(kasa.read_text(encoding="utf-8"))
    assert veri["deneme"] == 1


# --- Telemetri ---------------------------------------------------------------


def test_HARCAMA_kasaya_yaziliyor(kasa, monkeypatch):
    """Kurtarilan para olculemezse `boşa bakiye yok` iddia olarak kalir."""
    monkeypatch.setattr(ya, "harcama_ozeti", lambda: {"maliyet": 0.0217, "cagri": 4})
    _koy(kasa, _plan())
    veri = json.loads(kasa.read_text(encoding="utf-8"))
    assert veri["harcama"]["maliyet"] == 0.0217


def test_KURTARILAN_PARA_stdouta_yaziliyor(kasa, monkeypatch, capsys):
    monkeypatch.setattr(ya, "harcama_ozeti", lambda: {"maliyet": 0.0217})
    _koy(kasa, _plan())
    _al()
    cikti = capsys.readouterr().out
    assert "kasadan geldi" in cikti
    assert "0.0217" in cikti


# --- Hicbir kosulda firlatmaz ------------------------------------------------


def test_YAZILAMAYAN_KASA_kosumu_dusurmuyor(tmp_path, monkeypatch):
    monkeypatch.setattr(ya, "PLAN_KASASI", tmp_path / "olmayan" / "x" / "k.json")
    monkeypatch.setattr(
        Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("izin yok"))
    )
    ya.plani_kasaya_koy(_plan(), bicim=ya.SHORTS_BICIMI, sahne_sayisi=8, konu=None)


def test_OLMAYAN_DOSYAYI_bosaltmak_firlatmiyor(kasa):
    ya.kasayi_bosalt("deneme")


def test_TEMIZLIK_kasayi_SILEMEZ():
    """⚠️ Kasa, koşum sonrasi temizligin ERISEMEYECEGI yerde durmali.

    Temizlik `tasks/`, `commons_materials/` ve `reviews/` altini suporuyor ve
    KORUNAN_ADLAR disindaki her dosyayi siliyor. Kasa oraya konsaydi, plani
    kurtaran mekanizma yayinlanan HER koşumda kendi dosyasini sildirirdi —
    ve kimse fark etmezdi, cunku kasa zaten "bazen bos" olabilen bir sey.
    """
    import temizlik

    koklar = (temizlik.MALZEMELER, temizlik.GOREVLER, temizlik.INCELEMELER)
    for kok in koklar:
        assert kok not in ya.PLAN_KASASI.parents, (
            f"kasa temizligin sildigi {kok} altinda"
        )


def test_KASA_GIT_disinda():
    """Plan metni depoya sizmamali — `.gitignore` `/storage/` diyor."""
    import subprocess

    kok = Path(__file__).resolve().parent.parent
    sonuc = subprocess.run(
        ["git", "check-ignore", str(ya.PLAN_KASASI)],
        cwd=kok,
        capture_output=True,
        text=True,
    )
    assert sonuc.returncode == 0, "kasa git tarafindan yok sayilmiyor"


# --- `run_cycle` GERCEKTEN kullaniyor mu (davranis) --------------------------
#
# ⚠️ Asagidaki AST testleri cagrinin VAR oldugunu gosterir, CALISTIGINI degil.
# Bu depoda "fonksiyon dogru, cagri yolu kopuk" sinifi kusur uc uretim
# koşumunu oldurdu (`test_onarim_dali_calisiyor.py`). Bu iki test dongunun
# kendisini yurutuyor.


class _RenderEDILDI(Exception):
    """`run_generator`a ULASILDIGINI isaretler — sentinel, kusur degil."""


def _hat(monkeypatch, tmp_path):
    # ⚠️ `PLAN_KASASI` BURADA baglanmiyor — `kasa` fixture'i zaten dizini
    # bagladi. Ikinci kez baglamak dizini dosya yoluna cevirip kasayi
    # `.../shorts-8.json/shorts-8.json` yapardi.
    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "LOCK_FILE", tmp_path / "automation.lock")
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "save_state", lambda _s: None)

    def _ulasildi(plan, *_a, **_k):
        raise _RenderEDILDI(plan.topic)

    monkeypatch.setattr(ya, "run_generator", _ulasildi)


def test_KASADAKI_PLAN_cikarim_yapilmadan_uretime_giriyor(monkeypatch, tmp_path, kasa):
    """Kasa doluyken `generate_content_plan` HIC cagrilmamali — asil olcum."""
    _hat(monkeypatch, tmp_path)
    _koy(kasa, _plan(8, capa="Hagia Sophia"))

    def _asla(*_a, **_k):
        raise AssertionError("kasa doluyken cikarim parasi odendi")

    monkeypatch.setattr(ya, "generate_content_plan", _asla)

    with pytest.raises(_RenderEDILDI) as gorulen:
        ya.run_cycle(yedek_konu=True, sahne_sayisi=8, dry_run=True)

    assert str(gorulen.value) == "konu", "uretime giren plan kasadan gelmeli"


def test_KASA_BOSKEN_hat_normal_planliyor(monkeypatch, tmp_path, kasa):
    """Kasa bir YEDEK yol; bossa davranis birebir eskisi gibi kalmali."""
    _hat(monkeypatch, tmp_path)
    cagrildi: list[int] = []

    def _planla(*_a, **_k):
        cagrildi.append(1)
        return _plan(8, capa="Cutty Sark")

    monkeypatch.setattr(ya, "generate_content_plan", _planla)

    with pytest.raises(_RenderEDILDI):
        ya.run_cycle(yedek_konu=True, sahne_sayisi=8, dry_run=True)

    assert cagrildi, "kasa bossa model planlamali"
    # Ve o plan ODENDIGI icin kasaya yazilmis olmali: bir sonraki koşum
    # ag hatasi yuzunden olen bu koşumun parasini yeniden odemeyecek.
    assert kasa.exists(), "yeni plan kasaya yazilmadi"
    assert json.loads(kasa.read_text(encoding="utf-8"))["plan"]["topic"] == "konu"


# --- `run_cycle` gercekten baglanmis mi (AST) --------------------------------


def _run_cycle_agaci() -> ast.FunctionDef:
    kaynak = (
        Path(__file__).resolve().parent.parent / "youtube_automation.py"
    ).read_text(encoding="utf-8")
    for dugum in ast.walk(ast.parse(kaynak)):
        if isinstance(dugum, ast.FunctionDef) and dugum.name == "run_cycle":
            return dugum
    raise AssertionError("run_cycle bulunamadi")


def _cagri_satirlari(agac: ast.AST, ad: str) -> list[int]:
    return [
        d.lineno
        for d in ast.walk(agac)
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == ad
    ]


def test_KASA_CIKARIMDAN_ONCE_okunuyor():
    """Kasa, `generate_content_plan`den SONRA okunursa hicbir sey kurtarmaz."""
    agac = _run_cycle_agaci()
    okuma = _cagri_satirlari(agac, "kasadan_plan_al")
    planlama = _cagri_satirlari(agac, "generate_content_plan")
    assert okuma, "run_cycle kasayi hic okumuyor"
    assert planlama
    assert min(okuma) < min(planlama)


def test_HER_PLAN_URETIMI_kasaya_yaziyor():
    """Yeniden planlama dallari da yazmali; yoksa reddedilmis plan kasada kalir."""
    agac = _run_cycle_agaci()
    planlama = _cagri_satirlari(agac, "generate_content_plan")
    yazma = _cagri_satirlari(agac, "plani_kasaya_koy")
    assert len(yazma) == len(planlama), (
        f"{len(planlama)} plan uretimi var ama {len(yazma)} kasa yazimi"
    )


def test_KALITE_REDDI_ve_YAYIN_kasayi_bosaltiyor():
    agac = _run_cycle_agaci()
    gerekceler = [
        d.args[0].value
        for d in ast.walk(agac)
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Name)
        and d.func.id == "kasayi_bosalt"
        and d.args
        and isinstance(d.args[0], ast.Constant)
    ]
    assert any("kalite reddi" in g for g in gerekceler), gerekceler
    assert any("yayınlandı" in g for g in gerekceler), gerekceler


def test_AG_HATASI_kasayi_BOSALTMIYOR():
    """Altyapi olumu kasanin VARLIK SEBEBI — orada bosaltmak mekanizmayi siler."""
    kaynak = (
        Path(__file__).resolve().parent.parent / "youtube_automation.py"
    ).read_text(encoding="utf-8")
    for dugum in ast.walk(ast.parse(kaynak)):
        if not (isinstance(dugum, ast.FunctionDef) and dugum.name == "main"):
            continue
        assert not _cagri_satirlari(dugum, "kasayi_bosalt"), (
            "main() altyapi hatalarini yakaliyor; orada kasa bosaltilmamali"
        )
        return
    raise AssertionError("main bulunamadi")
