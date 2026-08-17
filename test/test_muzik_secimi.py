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
    # ⚠️ Satir 2026-08-17'de cok satira yayildi (ruh hali ve ses seviyesi de
    # basiliyor); aranan sey bicim degil BILGININ kendisi.
    assert 'f"muzik: {secilen_muzik' in kaynak


# --- Ses seviyesi esitleme (2026-08-17) ------------------------------------
#
# ⚠️ NEDEN — olculdu. Havuzdaki 22 parcanin ilk 40 saniyesi 44,1 dB'ye
# yayilmisti ve karistirma duz bir carpan, yani sabit 0,2 ayari her parcada
# BASKA bir sey demekti. Kanal sahibinin "muzikler BAZEN siritiyor" demesi
# teshisin kendisiydi: sabit degil, parcadan parcaya degisen bir kusur.


def test_kunyede_OLMAYAN_parca_kazanci_1_donuyor():
    """Bugunku davranis: kazanc bir iyilestirme, on kosul degil."""
    assert ya.muzik_kazanci("boyle-bir-parca-yok.mp3") == 1.0


def test_havuzun_TAMAMI_kazanc_tasiyor():
    """Kazanci olmayan parca sessizce eski seviyesinde calar."""
    kunye = ya.muzik_kunyesi()
    assert kunye, "kunye okunamadi"
    eksik = [ad for ad, bilgi in kunye.items() if "ses_kazanci" not in bilgi]
    assert not eksik, f"kazanci olmayan parca: {eksik}"


def test_kazanclar_seviyeleri_GERCEKTEN_esitliyor():
    """⚠️ Asil kabul olcutu — kunyedeki iki sayidan hesaplaniyor.

    `olculen_db` + kazancin dB karsiligi her parcada ayni hedefe cikmali.
    Olculdu: ham yayilim 15,0 dB → etkin yayilim 0,01 dB.
    """
    import math

    kunye = ya.muzik_kunyesi()
    etkin = [
        bilgi["olculen_db"] + 20 * math.log10(bilgi["ses_kazanci"])
        for bilgi in kunye.values()
        if "olculen_db" in bilgi and "ses_kazanci" in bilgi
    ]
    assert len(etkin) >= 10, "olculmus parca sayisi az, test bir sey gostermiyor"
    assert max(etkin) - min(etkin) < 3.0, (
        f"etkin seviye yayilimi {max(etkin) - min(etkin):.2f} dB — kapi 3 dB"
    )


def test_sacma_kunye_degeri_sesi_PATLATMIYOR(monkeypatch):
    monkeypatch.setattr(ya, "muzik_kunyesi", lambda: {"a.mp3": {"ses_kazanci": 9999}})
    assert ya.muzik_kazanci("a.mp3") <= 4.0

    monkeypatch.setattr(ya, "muzik_kunyesi", lambda: {"a.mp3": {"ses_kazanci": "abc"}})
    assert ya.muzik_kazanci("a.mp3") == 1.0


def test_ELENEN_parcalar_havuzda_yok():
    """⚠️ Sarki sozlu, donem disi ve yapay zeka destekli parcalar ayiklandi."""
    kunye = ya.muzik_kunyesi()
    for ad in (
        "ia-v-disc-no-2.mp3",                         # Crosby/Shore, sarki sozlu
        "ia-henpecked-blues-by-ben-bernie-orches.mp3",  # 1921 caz
        "ia-LamentViPartIi-AndanteLamentoso.mp3",     # -56,9 dB, kullanilamaz
        "ia-ecos-de-plate-op.-42.mp3",                # yapay zeka destekli beste
    ):
        assert ad not in kunye, f"{ad} kunyede kalmis"
        assert ad not in ya.muzik_secenekleri(), f"{ad} havuzda kalmis"


# --- Ruh hali eslestirme ----------------------------------------------------


def _kunye(monkeypatch, esleme: dict[str, str]):
    monkeypatch.setattr(
        ya,
        "muzik_kunyesi",
        lambda: {ad: {"ruh_hali": rh} for ad, rh in esleme.items()},
    )


def test_ruh_hali_UYAN_parca_tercih_ediliyor(tmp_path, monkeypatch):
    _kunye(monkeypatch, {"a.mp3": "gorkemli", "b.mp3": "agirbasli", "c.mp3": "merak"})

    secimler = {
        ya.muzik_sec(["a.mp3", "b.mp3", "c.mp3"], tmp_path / f"g{i}.json", ruh_hali="gorkemli")
        for i in range(12)
    }

    assert secimler == {"a.mp3"}


def test_ruh_hali_YOKSA_havuz_geneli(tmp_path, monkeypatch):
    """Bugunku davranis korunuyor: alan istege bagli."""
    _kunye(monkeypatch, {"a.mp3": "gorkemli", "b.mp3": "agirbasli"})

    secimler = {
        ya.muzik_sec(["a.mp3", "b.mp3"], tmp_path / f"g{i}.json") for i in range(12)
    }

    assert secimler == {"a.mp3", "b.mp3"}


def test_TANIMAYAN_ruh_hali_kosumu_dusurmuyor(tmp_path, monkeypatch):
    """⚠️ Model uydurursa muzik havuz genelinden secilir, hata verilmez."""
    _kunye(monkeypatch, {"a.mp3": "gorkemli", "b.mp3": "agirbasli"})

    secim = ya.muzik_sec(["a.mp3", "b.mp3"], tmp_path / "g.json", ruh_hali="hüzünlü")

    assert secim in {"a.mp3", "b.mp3"}


def test_eslesen_yoksa_ETIKETSIZ_parcaya_dusuluyor(tmp_path, monkeypatch):
    """"Bilmiyorum" ne odul ne ceza almali — `sinifa_gore_sirala` ile ayni ilke."""
    _kunye(monkeypatch, {"etiketli.mp3": "agirbasli", "etiketsiz.mp3": ""})

    secimler = {
        ya.muzik_sec(
            ["etiketli.mp3", "etiketsiz.mp3"], tmp_path / f"g{i}.json", ruh_hali="gorkemli"
        )
        for i in range(12)
    }

    assert secimler == {"etiketsiz.mp3"}, "etiketsiz parca, YANLIS etiketliye yeglenmeli"


def test_hicbiri_uymuyorsa_havuzun_TAMAMINA_dusuluyor(tmp_path, monkeypatch):
    """Muziksiz video, ruh hali tutmayan muzikten kotu."""
    _kunye(monkeypatch, {"a.mp3": "agirbasli", "b.mp3": "agirbasli"})

    secim = ya.muzik_sec(["a.mp3", "b.mp3"], tmp_path / "g.json", ruh_hali="gorkemli")

    assert secim in {"a.mp3", "b.mp3"}


def test_ruh_hali_TEKRAR_KORUMASINI_bozmuyor(tmp_path, monkeypatch):
    """⚠️ Iki koruma birbirini yemeyecek: ayni etiketten dort parca varsa
    ust uste ayni parca gelmemeli."""
    havuz = [f"{h}.mp3" for h in "abcd"]
    _kunye(monkeypatch, {ad: "merak" for ad in havuz})
    gecmis = tmp_path / "g.json"

    secimler = [ya.muzik_sec(havuz, gecmis, ruh_hali="merak") for _ in range(2)]

    assert len(set(secimler)) == 2, f"tekrar var: {secimler}"


def test_plan_MOOD_alanini_okuyor_ve_ISTEGE_BAGLI():
    """⚠️ Zorunlu alan eklemek bu depoda bes denemenin dordunu yakmisti."""
    import dataclasses

    alanlar = {a.name: a for a in dataclasses.fields(ya.ContentPlan)}
    assert alanlar["ruh_hali"].default == "", "alan varsayilansiz olmamali"
    assert ya._ruh_halini_coz("GORKEMLI ") == "gorkemli"
    assert ya._ruh_halini_coz("bilinmeyen") == ""
    assert ya._ruh_halini_coz(None) == ""


def test_uretim_hatti_kazanci_ve_ruh_halini_GECIRIYOR():
    """⚠️ Zincirin kopabilecegi yer: kazanc hesaplanip CLI'ya verilmezse
    bayrak sessizce etkisiz kalir."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")

    assert "muzik_sec(ruh_hali=plan.ruh_hali)" in kaynak
    assert "MUZIK_SES_TABANI * muzik_kazanci(secilen_muzik)" in kaynak
    assert 'str(muzik_sesi)' in kaynak
    assert '"--bgm-volume",\n        "0.2",' not in kaynak, "ses hala sabit"
