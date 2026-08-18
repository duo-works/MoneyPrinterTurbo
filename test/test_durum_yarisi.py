"""Bir koşum, arada baska bir sürecin yazdigini SILMEMELI.

⚠️ NEDEN VAR — olculdu 2026-08-18, CANLI VERI KAYBIYLA. `load_state` koşum
BASINDA okuyor, `save_state` sonda BUTUN sozlugu yaziyordu ve bir koşum
saatlerce surebiliyor:

    11:17  Gobekli Tepe yayinlandi   (gorsel 78)
    11:48  soguma damgasi yazildi
    12:23  Cemal Pasha yayinlandi    (gorsel 75)
    15:12  eski anlik goruntuyu tutan bir koşum kaydetti
           -> yayin 21'den 19'a dustu, damga yok oldu

⚠️ Bedeli defter hatasindan buyuk: `engellenen_capalar` YAYINLANMIS capalari
okuyor, yani iki konu yeniden serbest kaldi ve hat ayni videoyu ikinci kez
yayinlayabilirdi. Tekrar politikasi ("each video has a distinct storyline")
sessizce ihlal edilirdi.

⚠️ `automation.lock` bunu ENGELLEMIYOR: o kilit koşumlari seri hale getiriyor
ama `state.json` uzerinde degil, ve elle baslatilan bir koşum onu hic almadan
yazabiliyor.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


@pytest.fixture
def durum_dosyasi(tmp_path, monkeypatch):
    """⚠️ Testler CANLI depoya yazmamali — `STATE_FILE` gecici dizine tasiniyor."""
    hedef = tmp_path / "state.json"
    monkeypatch.setattr(ya, "STATE_FILE", hedef)
    return hedef


def _yayin(url: str, capa: str, an: str) -> dict:
    return {"url": url, "visual_anchor": capa, "published_at": an, "quality": {}}


# --- Asil iddia -------------------------------------------------------------


def test_ESKI_anlik_goruntu_ARADAKI_yayini_SILMIYOR(durum_dosyasi):
    """Canli kaybin birebir taklidi."""
    # Koşum A basliyor ve durumu okuyor.
    ya.save_state({"published": [_yayin("eski", "Ellora", "2026-08-17T21:42")], "rejected": []})
    a_bellek = ya.load_state()

    # Koşum B arada bitiyor ve IKI yayin yaziyor.
    b = ya.load_state()
    b["published"].append(_yayin("gobekli", "Gobekli Tepe", "2026-08-18T11:17"))
    b["published"].append(_yayin("cemal", "Cemal Pasha", "2026-08-18T12:23"))
    ya.save_state(b)

    # Koşum A saatler sonra kendi reddini yaziyor.
    a_bellek["rejected"].append({"topic": "X", "rejected_at": "2026-08-18T15:12"})
    ya.save_state(a_bellek)

    son = json.loads(durum_dosyasi.read_text(encoding="utf-8"))
    urller = [k["url"] for k in son["published"]]

    assert "gobekli" in urller, "aradaki yayin silinmis — canli kaybin aynisi"
    assert "cemal" in urller, "aradaki yayin silinmis — canli kaybin aynisi"
    assert len(son["rejected"]) == 1, "A'nin kendi reddi yazilmali"


def test_capa_engeli_KURTULUYOR(durum_dosyasi):
    """⚠️ Asil bedel burada: kayit gidince capa yeniden serbest kaliyor ve
    hat ayni konuyu ikinci kez yayinlayabiliyor."""
    ya.save_state({"published": [], "rejected": []})
    eski = ya.load_state()

    yeni = ya.load_state()
    yeni["published"].append(_yayin("cemal", "Cemal Pasha", "2026-08-18T12:23"))
    ya.save_state(yeni)

    eski["rejected"].append({"topic": "X", "rejected_at": "2026-08-18T15:12"})
    ya.save_state(eski)

    assert "Cemal Pasha" in ya.engellenen_capalar(ya.load_state())


def test_SKALER_damga_silinmiyor(durum_dosyasi):
    """`soguma_gecerlilik` liste degil; onda da "diskte var bizde yok" durumu
    telafi edilmeli — canli kayipta damga da gitmisti."""
    ya.save_state({"published": [], "rejected": []})
    eski = ya.load_state()

    yeni = ya.load_state()
    yeni["soguma_gecerlilik"] = "2026-08-18T11:48:37+03:00"
    ya.save_state(yeni)

    ya.save_state(eski)

    assert ya.load_state().get("soguma_gecerlilik") == "2026-08-18T11:48:37+03:00"


def test_BELLEKTEKI_skaler_diski_EZIYOR(durum_dosyasi):
    """⚠️ Sinir bekcisi: `--sogumayi-sifirla` damgayi ILERLETIYOR ve bu
    bilincli bir yazma. Birlestirme onu eski degere geri dondurmemeli."""
    ya.save_state({"published": [], "rejected": [], "soguma_gecerlilik": "ESKI"})
    durum = ya.load_state()
    durum["soguma_gecerlilik"] = "YENI"

    ya.save_state(durum)

    assert ya.load_state()["soguma_gecerlilik"] == "YENI"


# --- Birlestirme dogru sayiyor ---------------------------------------------


def test_AYNI_kayit_iki_kez_yazilmiyor(durum_dosyasi):
    """Birlestirme kimlik olarak tam kaydi kullaniyor; kendi yazdigimiz kayit
    diskten geri okununca cogalmamali."""
    ya.save_state({"published": [_yayin("a", "A", "an")], "rejected": []})
    durum = ya.load_state()

    ya.save_state(durum)
    ya.save_state(durum)

    assert len(ya.load_state()["published"]) == 1


def test_SIRA_korunuyor_bizimkiler_once(durum_dosyasi):
    ya.save_state({"published": [_yayin("a", "A", "1")], "rejected": []})
    eski = ya.load_state()

    yeni = ya.load_state()
    yeni["published"].append(_yayin("b", "B", "2"))
    ya.save_state(yeni)

    eski["published"].append(_yayin("c", "C", "3"))
    ya.save_state(eski)

    urller = [k["url"] for k in ya.load_state()["published"]]
    assert set(urller) == {"a", "b", "c"}


def test_completed_slots_da_birlesiyor(durum_dosyasi):
    ya.save_state({"published": [], "rejected": [], "completed_slots": ["s1"]})
    eski = ya.load_state()

    yeni = ya.load_state()
    yeni["completed_slots"].append("s2")
    ya.save_state(yeni)

    eski["completed_slots"].append("s3")
    ya.save_state(eski)

    assert set(ya.load_state()["completed_slots"]) == {"s1", "s2", "s3"}


# --- Dayaniklilik: yazma HICBIR kosulda kaybolmamali ------------------------


def test_BOZUK_disk_dosyasi_yazmayi_ENGELLEMIYOR(durum_dosyasi):
    """⚠️ Uretilmis ve yayinlanmis bir videonun kaydi, okunamayan bir disk
    kopyasi yuzunden kaybolmamali."""
    durum_dosyasi.write_text("{ bu gecerli json degil", encoding="utf-8")

    ya.save_state({"published": [_yayin("x", "X", "an")], "rejected": []})

    assert len(ya.load_state()["published"]) == 1


def test_ilk_yazma_DOSYA_YOKKEN_calisiyor(durum_dosyasi):
    ya.save_state({"published": [], "rejected": []})

    assert durum_dosyasi.exists()


def test_gecici_dosya_SURECE_OZEL():
    """⚠️ Paylasilan tek bir `.tmp`, kilit alinamadiginda iki sürecin
    birbirinin yarim ciktisini `replace` etmesine yol acardi."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert 'with_suffix(f".{os.getpid()}.tmp")' in kaynak


# --- Gercek eszamanlilik ----------------------------------------------------


YAZAN_BETIK = '''
import sys, time
sys.path.insert(0, {kok!r})
import youtube_automation as modul
from pathlib import Path

modul.STATE_FILE = Path(sys.argv[1])
etiket, bekleme = sys.argv[2], float(sys.argv[3])
durum = modul.load_state()
time.sleep(bekleme)          # koşumun uzun surdugu pencere
durum["rejected"].append({{"topic": etiket, "rejected_at": etiket}})
modul.save_state(durum)
'''
"""⚠️ AYRI SUREC, `multiprocessing` DEGIL.

Ilk surumum `multiprocessing.get_context("spawn")` kullaniyordu ve tek basina
kosunca gecip TAM SUITTE dusuyordu: spawn, hedef fonksiyonu modul adiyla geri
import ediyor ve o adin ne oldugu pytest'in dosyayi nasil topladigina bagli.
Yani test, olcmek istedigi seyi degil pytest'in import mekanigini olcuyordu.

Gercek uretim zaten ayri `python youtube_automation.py` sürecleri koşuyor
(zamanlayici + elle baslatilan koşumlar); `subprocess` o sekli birebir taklit
ediyor ve hicbir pytest ayrintisina bagli degil.
"""


def test_GERCEK_eszamanli_yazmada_kayit_kaybolmuyor(durum_dosyasi, tmp_path):
    """⚠️ Bu test SURECLERI gercekten calistiriyor — kilit ancak boyle sinanir.

    Sekiz sürec durumu neredeyse ayni anda okuyor, FARKLI surelerde bekliyor
    ve yaziyor. Bekleme farki sart: uzun koşumun kisa koşumu ezmesi durumunu
    (canli kaybin sekli) garanti ediyor. Beklemesiz ilk surumum ESKI
    `save_state` ile de yesil geciyordu — pencereler hic ortusmuyordu.
    """
    kok = str(Path(ya.__file__).resolve().parent)
    betik = tmp_path / "yazan.py"
    betik.write_text(YAZAN_BETIK.format(kok=kok), encoding="utf-8")

    ya.save_state({"published": [], "rejected": []})

    surecler = [
        subprocess.Popen(
            [sys.executable, str(betik), str(durum_dosyasi), f"s{i}", str(0.2 + i * 0.1)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(8)
    ]
    for surec in surecler:
        _, hata = surec.communicate(timeout=120)
        # ⚠️ Cikis kodu ONCE kontrol ediliyor: sessizce olen bir sürec
        # "kayit kaybolmadi" gibi gorunurdu ve test hicbir sey kanitlamazdi.
        assert surec.returncode == 0, f"yazan sürec dustu:\n{hata}"

    etiketler = {k["topic"] for k in ya.load_state()["rejected"]}
    assert etiketler == {f"s{i}" for i in range(8)}, f"kayip var: {etiketler}"
