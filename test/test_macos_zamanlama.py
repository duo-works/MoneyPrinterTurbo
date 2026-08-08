"""macOS gunluk uretim zamanlamasi (DW-108).

Testler `launchctl` cagirmiyor; sozlesme plist govdesi.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import macos_zamanlama as mz  # noqa: E402


def test_varsayilan_gizlilik_private():
    """⚠️ Yayin acik bir karar olmali.

    Bu kanal "bot aktivitesi" gerekcesiyle kapatilan bir kanalin yerine
    acildi; otomatik yayin tam da o kanali kaybettiren desene benziyor. Yon
    de asimetrik: gec yayinlanani yayinlamak bir tik, erken yayinlanani geri
    almak izlenme ve oneri sinyali kaybi.
    """
    govde = mz.plist_govdesi(gizlilik="private")

    assert "--privacy" in govde["ProgramArguments"]
    i = govde["ProgramArguments"].index("--privacy")
    assert govde["ProgramArguments"][i + 1] == "private"


def test_yayin_acikca_secilebiliyor():
    govde = mz.plist_govdesi(gizlilik="public")
    i = govde["ProgramArguments"].index("--privacy")

    assert govde["ProgramArguments"][i + 1] == "public"


def test_gunde_dort_kosum():
    """YouTube kotasi gunde 6 yuklemeye yetiyor (1600 birim × 6 = 9600/10.000).

    Dort, tavanin altinda pay birakiyor: elle bir yukleme ya da bir yeniden
    deneme kotayi patlatmasin.
    """
    govde = mz.plist_govdesi(gizlilik="private")

    assert len(govde["StartCalendarInterval"]) == 4
    assert len(mz.SAATLER) == 4
    assert max(mz.SAATLER) - min(mz.SAATLER) >= 8, "saatler gune yayilmali"


def test_kosumlar_gunduze_yayilmis():
    """Bir kosum dusrse kullanici ayni gun gorup mudahale edebilsin.

    Gece kosumlari sabaha kadar sessizce olu kaliyordu.
    """
    assert all(7 <= saat <= 22 for saat in mz.SAATLER)


def test_acilista_calismiyor():
    """`RunAtLoad` acik olsa kurulum komutu aninda bir video uretirdi."""
    assert mz.plist_govdesi(gizlilik="private")["RunAtLoad"] is False


def test_calisma_dizini_proje_koku():
    """`config.toml`, `client_secret.json` ve `storage/` goreli okunuyor."""
    govde = mz.plist_govdesi(gizlilik="private")

    assert govde["WorkingDirectory"] == str(mz.KOK)


def test_gunluk_dosyaya_yaziliyor():
    """Zamanlanmis kosumun ciktisi kaybolursa hata sessiz kalir."""
    govde = mz.plist_govdesi(gizlilik="private")

    assert govde["StandardOutPath"].endswith("zamanlama.log")
    assert govde["StandardErrorPath"] == govde["StandardOutPath"]


def test_venv_python_tercih_ediliyor():
    """Sistem python'unda proje bagimliliklari yok — kosum ImportError verirdi."""
    yorumlayici = mz.plist_govdesi(gizlilik="private")["ProgramArguments"][0]

    assert yorumlayici.endswith("python")


def test_uretim_betigi_cagriliyor():
    govde = mz.plist_govdesi(gizlilik="private")

    assert govde["ProgramArguments"][1].endswith("youtube_automation.py")
