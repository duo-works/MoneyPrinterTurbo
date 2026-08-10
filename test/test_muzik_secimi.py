"""Muzik secimi kayda gecer ve tekrar etmez (DW-120).

⚠️ Olculdu (2026-08-10): secim MPT'nin icinde `random.choice(29 parca)` ile
yapiliyordu — iadeli ve hicbir yere yazilmadan. Kullanici "hepsinde ayni
muzik var" dedi ve iddiayi sinamanin TEK yolu nihai sesten anlatimi cikarip
29 parcayla korelasyon olcmekti.

Olcum iddiayi cürüttü (4 video, 4 farkli parca; benzerlik 0,99'a karsi ikinci
sira 0,04) ama sorunun kendisini gosterdi: kayit yoktu. Ayrica iadeli secim
oldugu icin bir sonraki kosumda tekrar mumkundu.

Bu testler iki seyi tutuyor: secim diske yaziliyor mu, ve ust uste kosumlar
farkli parca aliyor mu.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

HAVUZ = [f"output{n:03d}.mp3" for n in range(10)]


def test_secim_diske_yaziliyor(tmp_path):
    gecmis = tmp_path / "muzik_gecmisi.json"
    secilen = ya.muzik_sec(HAVUZ, gecmis)
    assert secilen in HAVUZ
    assert json.loads(gecmis.read_text(encoding="utf-8")) == [secilen]


def test_ust_uste_kosumlar_tekrar_etmiyor(tmp_path):
    """Asil kosul: havuzun yarisi kadar geriye bakildigi icin yakin tekrar yok."""
    gecmis = tmp_path / "muzik_gecmisi.json"
    pencere = max(1, len(HAVUZ) // 2)
    secimler = [ya.muzik_sec(HAVUZ, gecmis) for _ in range(pencere)]
    assert len(set(secimler)) == len(secimler), f"tekrar var: {secimler}"


def test_havuz_tukenince_patlamiyor(tmp_path):
    """Havuzdan cok video uretilirse secim dursun degil, dongusun."""
    gecmis = tmp_path / "muzik_gecmisi.json"
    for _ in range(len(HAVUZ) * 3):
        assert ya.muzik_sec(HAVUZ, gecmis) in HAVUZ


def test_gecmis_sinirsiz_buyumuyor(tmp_path):
    """Dosya her kosumda bir satir uzayip sonsuza gitmemeli."""
    gecmis = tmp_path / "muzik_gecmisi.json"
    for _ in range(len(HAVUZ) * 3):
        ya.muzik_sec(HAVUZ, gecmis)
    assert len(json.loads(gecmis.read_text(encoding="utf-8"))) <= len(HAVUZ)


def test_bozuk_gecmis_uretimi_dusurmuyor(tmp_path):
    """Bozuk JSON en fazla bir tekrara mal olur, videoya degil."""
    gecmis = tmp_path / "muzik_gecmisi.json"
    gecmis.write_text("{bu json degil", encoding="utf-8")
    assert ya.muzik_sec(HAVUZ, gecmis) in HAVUZ


def test_parca_yoksa_bos_donuyor(tmp_path):
    """Muzik ugruna video uretimi dusmemeli."""
    assert ya.muzik_sec([], tmp_path / "muzik_gecmisi.json") == ""


def test_secenekler_ciplak_ad_donuyor():
    """CLI beyaz listede cozuyor; yol gondermek gereksiz ve daha riskli."""
    for ad in ya.muzik_secenekleri():
        assert "/" not in ad and not Path(ad).is_absolute()


def test_cli_cagrisi_artik_random_degil():
    """Kaynakta secim gercekten disariya alinmis mi."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    assert '"--bgm-type",\n        "random",' not in kaynak
    assert '"--bgm-file", secilen_muzik' in kaynak
    # Secim loga basilmali; DW-120'nin yarisi bu satir.
    assert 'print(f"muzik: {secilen_muzik' in kaynak
