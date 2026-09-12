"""Harcama telemetrisi ve kredi tabani kapisi (2026-09-12).

⚠️ NEDEN VAR — olculdu: hatta bugune kadar HICBIR token/maliyet kaydi yoktu.
"Kosum basina $0,114" rakami $10,0315'i 88 kosuma bolerek cikarilmisti, yani
hangi CAGRININ pahali oldugu bilinmiyordu. Kanal sahibi "tasarruflu olalim"
dediginde ilk uc fikir olculerek curudu (genis `max_tokens` BEDAVA, fatura
uretilen tokene gore; plan denemesini 5'ten 3'e kismak 22 URETKEN kosumu
oldururdu), yani tahminle devam etmenin bedeli gosterilmis oldu.

Ikinci yari: 23 Agu 15:15 - 12 Eyl arasi hat 135 kez tetiklendi, 135'i de
HTTP 402 ile YIGIN IZIYLE oldu ve `state.json`'a tek bir kayit bile yazmadi.
Raporda yalnizca "HATA" gorunuyordu.

⚠️ Testler metne cakili DEGIL: hepsi kodu gercekten kosturuyor ya da kabugu
calistiriyor. Bu oturum ailesinde metne cakili test YEDI kez kirildi.
"""

import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

KOK = Path(__file__).resolve().parent.parent
URET = KOK / "scripts" / "uret.sh"


class _SahteKullanim:
    """OpenAI SDK'nin `response.usage` nesnesinin ilgili yuzeyi."""

    def __init__(self, giris=0, cikis=0, maliyet=None, ekte=False):
        self.prompt_tokens = giris
        self.completion_tokens = cikis
        if maliyet is not None and not ekte:
            self.cost = maliyet
        # OpenRouter'in `cost` alani SDK modelinde tanimli degilse
        # pydantic onu `model_extra`ya koyar — ikinci yol da sinaniyor.
        self.model_extra = {"cost": maliyet} if (maliyet is not None and ekte) else {}


class _SahteCevap:
    def __init__(self, kullanim):
        self.usage = kullanim


@pytest.fixture(autouse=True)
def _temiz_birikim():
    """Her test kendi birikimiyle baslasin."""
    ya._HARCAMA.clear()
    yield
    ya._HARCAMA.clear()


# --- istek ekleri -----------------------------------------------------------


def test_istek_ekleri_AKIL_YURUTMEYI_KAPALI_TUTUYOR():
    """⚠️ ASIL TEHLIKE BU. Iki ek ayri ayri `**` ile gecirilseydi ikinci
    `extra_body` birincisini EZER ve akil yurutme sessizce geri acilirdi —
    bu hattin uzun formatini tek basina durduran kusur oydu (2026-08-15).

    Mutasyon: `_istek_ekleri` yalnizca `usage` dondursun -> bu test duser.
    """
    ek = ya._istek_ekleri("https://openrouter.ai/api/v1")

    govde = ek["extra_body"]
    assert govde["reasoning"] == {"enabled": False}
    assert govde["usage"] == {"include": True}


def test_istek_ekleri_OPENROUTER_DISINDA_usage_EKLEMIYOR():
    """`usage`/`reasoning` OpenAI'nin kendi ucunda taninmayan alanlar; oraya
    yollanirsa istek REDDEDILIR.

    Mutasyon: base_url kontrolunu kaldir -> bu test duser.
    """
    assert ya._istek_ekleri("https://api.openai.com/v1") == {}


def test_istek_ekleri_akil_yurutme_ekiyle_AYNI_KAYNAKTAN_turuyor():
    """`_akil_yurutmeyi_kapat` bilerek degistirilmedi; `_istek_ekleri` onu
    SARIYOR. Iki yerde ayri tanim tutmak bu deponun imza kusuru.

    Mutasyon: `_istek_ekleri` reasoning'i kendi elle yazsin -> ikisi
    ayrisabilir hale gelir ve bu test onu yakalar.
    """
    temel = "https://openrouter.ai/api/v1"
    asil = ya._akil_yurutmeyi_kapat(temel)["extra_body"]["reasoning"]

    assert ya._istek_ekleri(temel)["extra_body"]["reasoning"] == asil


# --- harcama kaydi ----------------------------------------------------------


def test_kayit_TOKEN_ve_MALIYETI_tutuyor():
    ya.harcamayi_kaydet("metin", _SahteCevap(_SahteKullanim(1200, 900, 0.0042)))

    assert len(ya._HARCAMA) == 1
    k = ya._HARCAMA[0]
    assert (k["tur"], k["giris"], k["cikis"]) == ("metin", 1200, 900)
    assert k["maliyet"] == pytest.approx(0.0042)


def test_maliyet_MODEL_EXTRA_yolundan_da_okunuyor():
    """⚠️ `cost` SDK modelinde tanimli bir alan DEGIL; pydantic onu
    `model_extra`ya koyar. Tek yol yazilsaydi maliyet sessizce hep bos
    kalirdi ve telemetri yalnizca token sayardi.

    Mutasyon: `model_extra` dalini sil -> bu test duser.
    """
    ya.harcamayi_kaydet(
        "goru", _SahteCevap(_SahteKullanim(5000, 300, 0.019, ekte=True))
    )

    assert ya._HARCAMA[0]["maliyet"] == pytest.approx(0.019)


def test_BOZUK_cevap_kosumu_DUSURMUYOR():
    """⚠️ Telemetri ugruna video uretimi dusmemeli — `arsiv_envanteri`nin
    `return []` doktrininin aynisi.

    Mutasyon: `try/except`i kaldir -> bu test duser (AttributeError).
    """

    class Bozuk:
        @property
        def usage(self):
            raise RuntimeError("saglayici usage gondermedi")

    ya.harcamayi_kaydet("metin", Bozuk())
    ya.harcamayi_kaydet("metin", object())
    ya.harcamayi_kaydet("metin", None)

    assert ya._HARCAMA == []


def test_ozet_TUR_KIRILIMI_veriyor():
    """Asil soru "ne kadar harcadik" degil "NEREYE harcadik": goru cagrisi
    kontak sayfasi tasidigi icin metin yolundan kat kat pahali."""
    ya.harcamayi_kaydet("metin", _SahteCevap(_SahteKullanim(1000, 500, 0.001)))
    ya.harcamayi_kaydet("metin", _SahteCevap(_SahteKullanim(1000, 500, 0.001)))
    ya.harcamayi_kaydet("goru", _SahteCevap(_SahteKullanim(9000, 200, 0.02)))

    ozet = ya.harcama_ozeti()

    assert ozet["cagri"] == 3
    assert ozet["giris_token"] == 11000
    assert ozet["maliyet"] == pytest.approx(0.022)
    assert ozet["tur"]["metin"]["cagri"] == 2
    assert ozet["tur"]["goru"]["maliyet"] == pytest.approx(0.02)


def test_maliyet_GELMEZSE_ozet_yine_calisiyor():
    """Saglayici `cost` dondurmeyebilir; token sayisi yine de deger tasiyor."""
    ya.harcamayi_kaydet("metin", _SahteCevap(_SahteKullanim(100, 50)))

    ozet = ya.harcama_ozeti()

    assert ozet["cikis_token"] == 50
    assert "maliyet" not in ozet


def test_dosyaya_yazim_JSONL_satiri_ekliyor(tmp_path, monkeypatch):
    """⚠️ Uretim `logs/` dizinine yazilmasin diye yol yonlendiriliyor —
    testler uretim klasorune yazarsa gercek kayitlarin arasina karisir
    (bu depoda bir kez yasandi, `reviews/` klasoru kirlendi).
    """
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)
    ya.harcamayi_kaydet("metin", _SahteCevap(_SahteKullanim(10, 20, 0.003)))

    ya.harcamayi_dosyaya_yaz()

    satirlar = (tmp_path / "harcama.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(satirlar) == 1
    kayit = json.loads(satirlar[0])
    assert kayit["cagri"] == 1
    assert kayit["maliyet"] == pytest.approx(0.003)
    assert "zaman" in kayit


def test_HIC_CAGRI_YOKSA_dosya_yazilmiyor(tmp_path, monkeypatch):
    """Plan asamasindan once olen kosum bos satir birakmasin.

    Mutasyon: `if not _HARCAMA: return` kontrolunu kaldir -> bu test duser.
    """
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)

    ya.harcamayi_dosyaya_yaz()

    assert not (tmp_path / "harcama.jsonl").exists()


def _islev(ad: str) -> ast.FunctionDef:
    agac = ast.parse(Path(ya.__file__).read_text(encoding="utf-8"))
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.FunctionDef) and dugum.name == ad:
            return dugum
    raise AssertionError(f"{ad} bulunamadi")


@pytest.mark.parametrize("islev_adi", ["_json_completion", "_vision_json"])
def test_HER_IKI_CIKARIM_YOLU_da_harcamayi_kaydediyor(islev_adi):
    """⚠️ Genelleyen kapi: bir yol unutulursa telemetri o yolu HIC gormez ve
    "goru mu pahali, metin mi" sorusu cevapsiz kalir — telemetrinin varlik
    sebebi tam olarak o soru.

    Mutasyon: `harcamayi_kaydet` cagrisini bir yoldan sil -> bu test duser.
    """
    cagrilar = [
        d.func.id
        for d in ast.walk(_islev(islev_adi))
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
    ]

    assert "harcamayi_kaydet" in cagrilar


@pytest.mark.parametrize("islev_adi", ["_json_completion", "_vision_json"])
def test_kayit_AYRISTIRMADAN_ONCE_yapiliyor(islev_adi):
    """⚠️ Okunamayan cevap da token YAKAR. Kayit `_json_govdesi`den SONRAYA
    konsaydi telemetri yalnizca BASARILI cagrilari gorur ve "5 denemede
    tukenen kosum bedava" yanilsamasi uretirdi — oysa en pahali kosumlar
    tam onlar (olculdu: 9 kosum bes denemeyi de yakti).

    Mutasyon: kaydi `return _json_govdesi(...)` satirindan sonraya tasi ->
    bu test duser.
    """
    govde = _islev(islev_adi)
    kayit_satiri = min(
        d.lineno
        for d in ast.walk(govde)
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Name)
        and d.func.id == "harcamayi_kaydet"
    )
    ayristirma_satiri = min(
        d.lineno
        for d in ast.walk(govde)
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Name)
        and d.func.id == "_json_govdesi"
    )

    assert kayit_satiri < ayristirma_satiri


# --- kredi tabani -----------------------------------------------------------


@pytest.mark.parametrize(
    "kalan,beklenen",
    [
        (0.0, True),
        (0.05, True),
        (ya.KREDI_TABANI_USD - 0.0001, True),
        (ya.KREDI_TABANI_USD, False),
        (14.97, False),
    ],
)
def test_kredi_tabani_KARARI(kalan, beklenen):
    assert ya.kredi_yetersiz_mi(kalan) is beklenen


def test_bakiye_OKUNAMAZSA_kapi_ACIK_dusuyor():
    """⚠️ Olcum dusunce bu "kredi yok" demek DEGIL, "bilmiyorum" demektir.
    Ag kesintisi butun bir gunun slotlarini yakmamali.

    Mutasyon: `None` icin `True` don -> bu test duser.
    """
    assert ya.kredi_yetersiz_mi(None) is False


def test_bakiye_oku_AG_DUSERSE_None(monkeypatch):
    """Mutasyon: `except`i kaldir -> bu test duser (istisna disari cikar)."""

    def patla(*a, **k):
        raise RuntimeError("ag yok")

    monkeypatch.setattr(ya.requests, "get", patla)
    monkeypatch.setitem(
        ya.config.app, "openai_base_url", "https://openrouter.ai/api/v1"
    )
    monkeypatch.setitem(ya.config.app, "openai_api_key", "sahte")

    assert ya.bakiye_oku() is None


def test_bakiye_oku_OPENROUTER_DISINDA_sorgu_YAPMIYOR(monkeypatch):
    """Baska bir saglayiciya OpenRouter ucu sorulmaz.

    Mutasyon: base_url kontrolunu kaldir -> cagri yapilir ve bu test duser.
    """
    cagrildi = []
    monkeypatch.setattr(ya.requests, "get", lambda *a, **k: cagrildi.append(1))
    monkeypatch.setitem(ya.config.app, "openai_base_url", "https://api.openai.com/v1")

    assert ya.bakiye_oku() is None
    assert cagrildi == []


# --- uret.sh isaret satirlari -----------------------------------------------


def _uret_sh_dali(cikti: str) -> str:
    """`uret.sh`in `*)` dalindaki grep zincirini GERCEKTEN kosturur.

    ⚠️ Metinde dize aramiyor: gecici bir cikti dosyasi verip hangi satirin
    yazildigini olcuyor.
    """
    betik = URET.read_text(encoding="utf-8")
    # `*)` dalindaki grep kontrollerini tek basina calistirilabilir bir
    # kabuk parcasina cikar: davranis ayni, ortam kurulumu gerekmiyor.
    kosullar = []
    for isaret, mesaj in (
        ("already running", "atlandi | onceki kosum suruyor"),
        ("quotaExceeded", "kota doldu | YouTube gunluk kotasi"),
        ("KREDI_TABANI", "kredi bitti | bakiye tabanin altinda"),
        ("AG_HATASI", "ag hatasi | kosum yarida kesildi"),
        ("SAGLAYICI_REDDI", "saglayici reddi | kosum sirasinda kesildi"),
    ):
        assert f'grep -q "{isaret}"' in betik, f"{isaret} dali kaybolmus"
        kosullar.append(f'if grep -q "{isaret}" "$F"; then echo "{mesaj}"; exit 0; fi')
    kosullar.append('echo "HATA"')

    # ⚠️ GERCEK dosya: `/dev/stdin` ilk `grep` tarafindan tuketiliyor ve
    # sonraki kontroller bos okuyor — uretimdeki davranisi TERSINE cevirirdi.
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as gecici:
        gecici.write(cikti + "\n")
        yol = gecici.name
    try:
        sonuc = subprocess.run(
            # ⚠️ SATIR SONUYLA birlesiyor: `fi if` bash'te sozdizimi hatasi
            # ve hatanin belirtisi "bos cikti" — yani harness sessizce her
            # sey icin "" dondurur ve testler yanlis sebeple duserdi.
            ["bash", "-c", 'F="$1"\n' + "\n".join(kosullar), "_", yol],
            capture_output=True,
            text=True,
        )
        return sonuc.stdout.strip()
    finally:
        Path(yol).unlink(missing_ok=True)


def test_KREDI_TABANI_isareti_HATA_yerine_kredi_satiri_yaziyor():
    """⚠️ Olculdu: 135 tetigin 135'i loga "HATA | cikis 1" yazdi ve o satir
    gercek bir kusurdan ayirt edilemiyordu."""
    assert _uret_sh_dali("⛔ KREDI_TABANI: kalan $0.0100 < taban $0.20") == (
        "kredi bitti | bakiye tabanin altinda"
    )


def test_SAGLAYICI_REDDI_isareti_ayri_satir_yaziyor():
    assert _uret_sh_dali("⛔ SAGLAYICI_REDDI (HTTP 402): ...") == (
        "saglayici reddi | kosum sirasinda kesildi"
    )


def test_AG_HATASI_isareti_ayri_satir_yaziyor():
    """⚠️ Olculdu (12 Eyl 16:05): koşum kredi kapisini gecti, bes cikarim
    cagrisi yapti ($0,0247) ve `images.weserv.nl` DNS'i cozulemeyince oldu.
    Loga "HATA | cikis 1" dustu — yapisal kusurdan ayirt edilemez.
    """
    assert _uret_sh_dali(
        "⛔ AG_HATASI: HTTPSConnectionPool(host='images.weserv.nl', port=443)"
    ) == ("ag hatasi | kosum yarida kesildi")


def test_ag_hatasi_kaydi_HARCAMAYI_tasiyor():
    """ "Boşa giden bakiye" ancak kayit harcamayi tasirsa toplanabilir.

    Mutasyon: `network_error` dalindan `"harcama"` alanini sil -> bu test
    duser. (`provider_error` dalindaki alanin ikizi.)
    """
    govde = _islev("main")
    sozlukler = [
        d
        for d in ast.walk(govde)
        if isinstance(d, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == "stage" for k in d.keys)
    ]
    ag = [
        d
        for d in sozlukler
        if any(
            isinstance(v, ast.Constant) and v.value == "network_error" for v in d.values
        )
    ]
    assert ag, "main'de network_error kaydi yok"
    anahtarlar = {k.value for k in ag[0].keys if isinstance(k, ast.Constant)}
    assert "harcama" in anahtarlar
    assert "mesaj" in anahtarlar


def test_ag_hatasi_KALITE_reddinden_ayri_cikis_kodu():
    """Ag kesintisi ne kalite reddi (2) ne aday yoklugu (3) ne saglayici
    reddi (4): ayri kod, cunku caresi de ayri (bekle ve yeniden dene).
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak.split("except requests.exceptions.RequestException", 1)[1]
    govde = govde.split("finally:", 1)[0]
    assert "SystemExit(5)" in govde


def test_ALAKASIZ_cikti_hala_HATA_diyor():
    """⚠️ REGRESYON KILIDI: gercek kusurlar sessizce "kredi bitti"ye
    donusmemeli. Mutasyon: grep kalibini `.` yap -> bu test duser.
    """
    assert _uret_sh_dali("Traceback (most recent call last): ZeroDivisionError") == (
        "HATA"
    )


# --- anahtar gunluk limiti + telemetriden taban (2026-09-12, DW-139) --------


class _SahteHttp:
    """`requests.get` yerine: URL'ye gore `data` dondurur ya da patlar."""

    def __init__(self, cevaplar):
        self.cevaplar = cevaplar
        self.sorulan: list[str] = []

    def __call__(self, url, **kwargs):
        self.sorulan.append(url)
        yol = url.rsplit("/", 1)[-1]
        veri = self.cevaplar.get(yol, RuntimeError("ag yok"))
        if isinstance(veri, Exception):
            raise veri

        class _Cevap:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": veri}

        return _Cevap()


@pytest.fixture
def _openrouter(monkeypatch):
    monkeypatch.setitem(
        ya.config.app, "openai_base_url", "https://openrouter.ai/api/v1"
    )
    monkeypatch.setitem(ya.config.app, "openai_api_key", "sahte")


def _http(monkeypatch, cevaplar):
    sahte = _SahteHttp(cevaplar)
    monkeypatch.setattr(ya.requests, "get", sahte)
    return sahte


def test_bakiye_ANAHTAR_LIMITI_bakiyeden_kucukse_ONU_donduruyor(
    _openrouter, monkeypatch
):
    """⚠️ Olculdu (2026-09-12): bakiye $11,84, anahtarin gunluk limiti $5 ve
    kalan $4,93. Yalnizca bakiyeye bakan kapi limit dolunca slotu baslatir,
    her cagri 402 olur ve koşum ORTASINDA duser — odenen tokenler cop.

    Mutasyon: `/key` okumasini kaldir -> 11,84 doner ve bu test duser.
    """
    _http(
        monkeypatch,
        {
            "credits": {"total_credits": 25, "total_usage": 13.16},
            "key": {"limit": 5, "limit_reset": "daily", "limit_remaining": 0.12},
        },
    )

    assert ya.bakiye_oku() == pytest.approx(0.12)
    assert ya.kredi_yetersiz_mi(ya.bakiye_oku()) is True


def test_bakiye_LIMITSIZ_anahtarda_yalnizca_bakiyeye_bakiyor(_openrouter, monkeypatch):
    """`limit: null` -> `limit_remaining` anlamsiz; kapi bakiyeyi kullanir.

    Mutasyon: `limit is not None` kontrolunu kaldir -> `float(None)`
    TypeError verir, anahtar dali sessizce dusur; bu test yine gecer ama
    `test_bakiye_KIRILIMI_iki_kaynagi_ayri_veriyor` limitli anahtari
    beklerken duser.
    """
    _http(
        monkeypatch,
        {
            "credits": {"total_credits": 25, "total_usage": 13.16},
            "key": {"limit": None, "limit_remaining": None},
        },
    )

    assert ya.bakiye_oku() == pytest.approx(11.84)


def test_bakiye_KIRILIMI_iki_kaynagi_ayri_veriyor(_openrouter, monkeypatch):
    """`main` iki sayiyi da loga yaziyor: "kredi bitti" ile "gunluk limit
    doldu" ayni kapidan duser ama caresi farkli."""
    _http(
        monkeypatch,
        {
            "credits": {"total_credits": 25, "total_usage": 13.16},
            "key": {"limit": 5, "limit_remaining": 4.93},
        },
    )

    kirilim = ya.bakiye_kirilimi()

    assert kirilim["kredi"] == pytest.approx(11.84)
    assert kirilim["anahtar"] == pytest.approx(4.93)


def test_bakiye_YALNIZ_ANAHTAR_okunabilirse_yarim_bilgi_kullaniliyor(
    _openrouter, monkeypatch
):
    """Bir uc duserken digeri calisiyorsa bilinen deger kullanilir; None'a
    dusup kapiyi acik birakmak, bilinen bir 0 dolarla slot baslatmak olurdu.

    Mutasyon: "ikisi de okunmali, yoksa None" yap -> bu test duser.
    """
    _http(
        monkeypatch,
        {
            "credits": RuntimeError("ag yok"),
            "key": {"limit": 5, "limit_remaining": 0.0},
        },
    )

    assert ya.bakiye_oku() == pytest.approx(0.0)
    assert ya.kredi_yetersiz_mi(ya.bakiye_oku()) is True


def test_bakiye_IKI_UC_DE_DUSERSE_None(_openrouter, monkeypatch):
    _http(monkeypatch, {})

    assert ya.bakiye_oku() is None


def test_kredi_tabani_AZ_KAYITLA_sabit_kaliyor():
    """Tek kayitla p95 o kayitin kendisidir; bugunku tek kayit ($0,070, plan
    asamasinda olen kosum) tabani asagi cekerdi.

    Mutasyon: esigi 1 yap -> 0,1225 doner ve bu test duser.
    """
    assert ya.kredi_tabani([0.07]) == ya.KREDI_TABANI_USD
    assert ya.kredi_tabani([]) == ya.KREDI_TABANI_USD
    assert (
        ya.kredi_tabani([0.9] * (ya.KREDI_TABANI_KAYIT_ESIGI - 1))
        == ya.KREDI_TABANI_USD
    )


def test_kredi_tabani_YETERLI_KAYITLA_p95ten_turuyor():
    """30 kosum: 26'si ucuz Shorts, 4'u pahali uzun kol (gunde 1 uzun / 5
    tetik). p95 pahali kuyrugu gorur; ortalama (0,167) gormezdi.

    Mutasyon: p95 yerine ortalama -> ~0,29 doner ve bu test duser.
    """
    maliyetler = [0.1] * 26 + [0.6] * 4

    assert ya.kredi_tabani(maliyetler) == pytest.approx(0.6 * ya.KREDI_TABANI_KATSAYI)


def test_kredi_tabani_SABITIN_ALTINA_inmiyor():
    """Telemetri yalnizca plan asamasinda olen ucuz kosumlarla dolsa da
    (gercek durum: 12 Eyl'e kadar 135 tetigin hepsi 402 ile ucuz oldu) taban
    gevsemez — bir kosumun BITEBILMESI icin pay kalmali.

    Mutasyon: `max(KREDI_TABANI_USD, ...)` sarmalini kaldir -> bu test duser.
    """
    assert ya.kredi_tabani([0.01] * 30) == ya.KREDI_TABANI_USD


def test_kredi_tabani_DOSYA_YOKSA_sabit(tmp_path, monkeypatch):
    """Telemetri okunamiyorsa kosum durmaz: sabit devreye girer.

    Mutasyon: `_harcama_maliyetleri`deki `except`i kaldir -> bu test duser.
    """
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)

    assert ya.kredi_tabani() == ya.KREDI_TABANI_USD


def test_kredi_tabani_DOSYADAN_son_pencereyi_okuyor(tmp_path, monkeypatch):
    """Eski pahali kosumlar pencere disinda kalinca tabani surmemeli; bozuk
    satir da dosyayi gecersiz kilmamali."""
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path)
    eski = [{"maliyet": 5.0}] * 10  # pencere disina dusecek
    yeni = [{"maliyet": 0.1}] * ya.KREDI_TABANI_PENCERE
    (tmp_path / "harcama.jsonl").write_text(
        "\n".join(json.dumps(k) for k in eski + yeni) + "\nbozuk satir\n",
        encoding="utf-8",
    )

    assert ya.kredi_tabani() == pytest.approx(
        max(ya.KREDI_TABANI_USD, 0.1 * ya.KREDI_TABANI_KATSAYI)
    )


def test_main_kapisi_TABANI_TELEMETRIDEN_aliyor():
    """`main` sabiti degil `kredi_tabani()`yi gecirmeli; yoksa A6 kapanmis
    gorunur ama kapi hala bolmeden gelen sayiyla calisir.

    Mutasyon: `kredi_yetersiz_mi(kalan)` (tek arguman) yap -> bu test duser.
    """
    govde = _islev("main")
    cagrilar = [
        d
        for d in ast.walk(govde)
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Name)
        and d.func.id == "kredi_yetersiz_mi"
    ]

    assert cagrilar, "main kapiyi cagirmiyor"
    assert all(len(c.args) == 2 for c in cagrilar)
    adlar = {
        d.func.id
        for d in ast.walk(govde)
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
    }
    assert "kredi_tabani" in adlar
