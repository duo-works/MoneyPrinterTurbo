"""Uretim raporu — "standarda sabitledik" diyebilmek icin once olcmek gerek.

⚠️ Olculdu (2026-08-13): kayitlar bu soruyu cevaplayamiyordu. 120 red
kaydinin hicbiri zaman dilimi tasimiyordu, iki asamanin skorlari
ayrismiyordu, hangi kipin urettigi yazilmiyordu. Rapor o eksikleri
gorunur kiliyor ve ileride arayuz bu JSON'u okuyacak.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uretim_rapor  # noqa: E402


def _durum(monkeypatch, tmp_path: Path, govde: dict) -> None:
    """⚠️ UC yolu birden yonlendiriyor.

    Rapor 2026-08-23'ten beri `zamanlayici.log`u ve `<slot>-rejected.json`
    dosyalarini da okuyor. Yalnizca `STATE_FILE` yonlendirilseydi testler
    CANLI uretim loglarini okurdu: sonuc her koşumda degisir. Depoda bu
    kusurun bir ornegi zaten yasandi — sahte kontak sayfalari gercek hakem
    ciktilarinin arasina yazilmisti.
    """
    yol = tmp_path / "state.json"
    yol.write_text(json.dumps(govde), encoding="utf-8")
    monkeypatch.setattr(uretim_rapor, "STATE_FILE", yol)
    loglar = tmp_path / "logs"
    loglar.mkdir(exist_ok=True)
    monkeypatch.setattr(uretim_rapor, "LOG_DIZINI", loglar)
    monkeypatch.setattr(uretim_rapor, "ZAMANLAYICI_LOG", loglar / "zamanlayici.log")


ORNEK = {
    "published": [
        {
            "slot": "2026-08-13-15",
            "kaynak": "huni",
            "visual_anchor": "Mehmed II",
            "url": "https://y/1",
            "quality": {"visual_alignment_score": 84, "issues": ["a", "b"]},
        },
        {
            "slot": "2026-08-13-21",
            "kaynak": "yedek",
            "visual_anchor": "Sutton Hoo",
            "url": "https://y/2",
            "quality": {"visual_alignment_score": 90, "issues": []},
        },
    ],
    "rejected": [
        {
            "slot": "2026-08-13-16",
            "kaynak": "huni",
            "stage": "source_materials",
            "visual_alignment_score": 40,
            "agir_kusurlar": ["kare 2: anlatilan kisi degil"],
        },
        {
            "slot": "2026-08-13-17",
            "kaynak": "huni",
            "stage": "video",
            "visual_alignment_score": 60,
            "agir_kusurlar": ["kare 1: anlatilan kisi degil", "kare 3: modern goruntu"],
        },
    ],
}


def test_basari_orani_hesaplaniyor(monkeypatch, tmp_path):
    _durum(monkeypatch, tmp_path, ORNEK)

    veri = uretim_rapor.rapor()

    assert veri["kayit_sayisi"] == 4
    assert veri["yayinlanan"] == 2
    assert veri["kayit_basari_orani"] == 0.5


def test_asama_kirilimi(monkeypatch, tmp_path):
    """Redlerin cogu render'dan ONCE mi dusuyor — maliyet sorusu."""
    _durum(monkeypatch, tmp_path, ORNEK)

    assert uretim_rapor.rapor()["asama_kirilimi"] == {"source_materials": 1, "video": 1}


def test_kaynak_kirilimi(monkeypatch, tmp_path):
    """Huni mi yedek mi uretti — yedek hattinin ise yarayip yaramadigi buradan."""
    _durum(monkeypatch, tmp_path, ORNEK)

    assert uretim_rapor.rapor()["kaynak_kirilimi"] == {"huni": 1, "yedek": 1}


def test_agir_kusurlar_sayiliyor(monkeypatch, tmp_path):
    """Kare numarasi atilip TUR sayiliyor; "kare 2" ile "kare 3" ayni kusur."""
    _durum(monkeypatch, tmp_path, ORNEK)

    kusurlar = dict(uretim_rapor.rapor()["en_sik_agir_kusur"])

    assert kusurlar["anlatilan kisi degil"] == 2
    assert kusurlar["modern goruntu"] == 1


def test_iki_ayri_skor_yeri_de_okunuyor(monkeypatch, tmp_path):
    """⚠️ Yayin kaydinda skor `quality` altinda, red kaydinda UST DUZEYDE.

    Tek yere bakan bir rapor yayinlari ya da redleri sessizce "skorsuz"
    sayardi.
    """
    _durum(monkeypatch, tmp_path, ORNEK)
    veri = uretim_rapor.rapor()

    assert veri["yayin_skoru"]["ortanca"] == 87
    assert veri["red_skoru_ortanca"] == 50


def test_bos_durum_patlamiyor(monkeypatch, tmp_path):
    _durum(monkeypatch, tmp_path, {"published": [], "rejected": []})

    veri = uretim_rapor.rapor()

    assert veri["kayit_sayisi"] == 0
    assert veri["kayit_basari_orani"] == 0.0
    assert veri["yayin_skoru"]["ortanca"] is None


def test_dosya_yoksa_patlamiyor(monkeypatch, tmp_path):
    _durum(monkeypatch, tmp_path, {"published": [], "rejected": []})
    monkeypatch.setattr(uretim_rapor, "STATE_FILE", tmp_path / "yok.json")

    assert uretim_rapor.rapor()["kayit_sayisi"] == 0


def test_json_ciktisi_arayuzun_alanlarini_tasiyor(monkeypatch, tmp_path):
    """Arayuz bu JSON'u okuyacak; alan adlari sozlesme."""
    _durum(monkeypatch, tmp_path, ORNEK)

    veri = uretim_rapor.rapor()

    for alan in (
        "kayit_sayisi", "yayinlanan", "reddedilen", "kayit_basari_orani",
        "asama_kirilimi", "kaynak_kirilimi", "yayin_skoru",
        "en_sik_agir_kusur", "son_yayinlar",
        "kosum_olcumu", "red_teshisi", "onarim",
    ):
        assert alan in veri, f"arayuz alani eksik: {alan}"
    assert json.dumps(veri)  # serilestirilebilir olmali


# --- DUSEN KOSUMLARIN RAPORU (2026-08-23) ------------------------------------
#
# ⚠️ NEDEN: rapor bugune kadar `state.json`daki KAYIT sayisini "koşum" diye
# yaziyordu. Iki hata ters yonde birikiyordu — bir koşum bese kadar kayit
# yazar, ama plan asamasinda olen koşum HIC yazmaz — ve ikisi birbirini
# gizliyordu. Canli olcum: 84 koşum / 336 kayit.


def _log(monkeypatch, tmp_path: Path, satirlar: list[str]) -> None:
    (tmp_path / "logs" / "zamanlayici.log").write_text(
        "\n".join(satirlar) + "\n", encoding="utf-8"
    )


ORNEK_LOG = [
    # ⚠️ 08:05 slotu IKI koşum kosuyor: TEK `kol` satiri, IKI bitis olayi.
    # Asimetri bilerek burada — `kol` sayan bir payda 3, dogru payda 4 der.
    # Ilk yazimda bu satirlar yoktu ve iki kural ayni sonucu veriyordu, yani
    # test hicbir seyi kanitlamiyordu (mutasyon M1 kacmisti).
    "2026-08-22 05:05:00 | kol | shorts",
    "2026-08-22 05:41:00 | YAYIN | https://y/9",
    "2026-08-22 08:05:00 | kol | shorts",
    "2026-08-22 08:20:00 | red | en son skor 55",
    "2026-08-22 08:21:00 | ikinci koşum | ilk koşum reddedildi",
    "2026-08-22 08:36:00 | red | en son skor 72",
    "2026-08-23 00:05:01 | kol | uzun",
    "2026-08-23 02:13:33 | HATA | cikis 1",
    "2026-08-23 05:05:00 | atlandi | onceki kosum suruyor",
    "bozuk satir — ayristirilamaz",
]


def test_KOSUM_sayisi_BITIS_olaylarindan_geliyor(monkeypatch, tmp_path):
    """⚠️ Asil duzeltme, ve UC sayma kurali burada AYRISIYOR:

        `state.json` kayitlari : 4  (ORNEK'te 2 yayin + 2 red)
        `kol` satirlari        : 3  (slot basina bir tane)
        BITIS olaylari         : 4  <- dogru; 08:05 slotu IKI koşum kostu

    Canli olcum ayni yonde: 10 `kol` satiri, 84 koşum, 336 kayit.

    Mutasyon: `kol` saymak ya da kayitlari saymak.
    """
    _durum(monkeypatch, tmp_path, ORNEK)
    _log(monkeypatch, tmp_path, ORNEK_LOG)

    olcum = uretim_rapor.kosum_olcumu()

    assert olcum["kosum"] == 4, "YAYIN + red + HATA"
    assert (olcum["yayin"], olcum["red"], olcum["hata"]) == (1, 2, 1)
    assert olcum["yayin_orani"] == 0.25
    assert olcum["olaylar"]["kol"] == 3, "kol satiri sayisi paydadan FARKLI olmali"


def test_ATLANAN_tetik_paydaya_GIRMIYOR(monkeypatch, tmp_path):
    """⚠️ "Slot yandi" ile "koşum reddedildi" ayri kusurlar; atlanan tetikte
    hicbir uretim denemesi yapilmadi, paydaya girerse oran duser ve hattin
    kalitesi oldugundan kotu gorunur.

    Mutasyon: `atlandi`yi `BITIS_OLAYLARI`na eklemek.
    """
    _durum(monkeypatch, tmp_path, ORNEK)
    _log(monkeypatch, tmp_path, ORNEK_LOG)

    olcum = uretim_rapor.kosum_olcumu()

    assert olcum["atlanan"] == 1
    assert olcum["kosum"] == 4, "atlanan tetik koşum degil"


def test_PENCERE_durustce_raporlaniyor(monkeypatch, tmp_path):
    """Kucuk n buyuk n gibi okunmasin: sayinin hangi araliktan geldigi yazili."""
    _durum(monkeypatch, tmp_path, ORNEK)
    _log(monkeypatch, tmp_path, ORNEK_LOG)

    assert uretim_rapor.kosum_olcumu()["pencere"] == ["2026-08-22", "2026-08-23"]


def test_GUN_suzgeci_yalnizca_son_gunu_sayiyor(monkeypatch, tmp_path):
    _durum(monkeypatch, tmp_path, ORNEK)
    _log(monkeypatch, tmp_path, ORNEK_LOG)

    olcum = uretim_rapor.kosum_olcumu(gun=1)

    assert olcum["pencere"] == ["2026-08-23", "2026-08-23"]
    assert olcum["kosum"] == 1 and olcum["hata"] == 1


def test_LOG_yoksa_rapor_PATLAMIYOR(monkeypatch, tmp_path):
    _durum(monkeypatch, tmp_path, ORNEK)

    assert uretim_rapor.kosum_olcumu()["kosum"] == 0


def _red_dosyasi(tmp_path: Path, ad: str, incelemeler: list[dict]) -> None:
    (tmp_path / "logs" / ad).write_text(
        json.dumps({"status": "rejected", "reviews": incelemeler}), encoding="utf-8"
    )


def test_RED_TESHISI_slot_dosyalarini_OKUYOR(monkeypatch, tmp_path):
    """⚠️ Bu dosyalari bugune kadar okuyan hicbir sey yoktu; her oturumda
    elle Python yazilarak cikariliyordu.

    Mutasyon: glob'u kaldirmak / `review` altina inmemek.
    """
    _durum(monkeypatch, tmp_path, ORNEK)
    _red_dosyasi(
        tmp_path,
        "2026-08-23-11-rejected.json",
        [
            {"stage": "source_materials", "review": {"visual_alignment_score": 25}},
            {"stage": "source_materials", "review": {"visual_alignment_score": 38}},
            {"stage": "planning", "review": {"visual_alignment_score": 0}},
        ],
    )

    t = uretim_rapor.red_teshisi()

    assert t["asama"] == {"source_materials": 2, "planning": 1}
    assert t["asama_ortanca_skor"]["source_materials"] == 31.5
    assert t["dosya"] == 1


def test_STAGE_yoksa_VIDEO_sayiliyor(monkeypatch, tmp_path):
    """⚠️ `rapor()` ayni varsayimi yapiyor (`k.get("stage", "video")`).

    Iki taraf ayrisirsa ayni redler iki farkli asamaya yazilir ve "en pahali
    asama hangisi" sorusu iki farkli cevap verir. Olculdu: 104 kayitta alan
    yok ve `state.json` tarafi hepsini `video` sayiyor.

    Mutasyon: "bilinmiyor" demek.
    """
    _durum(monkeypatch, tmp_path, ORNEK)
    _red_dosyasi(tmp_path, "2026-08-23-08-rejected.json", [{"review": {}}])

    assert uretim_rapor.red_teshisi()["asama"] == {"video": 1}


def test_KUSUR_AILELERI_kare_numarasindan_ARINIYOR(monkeypatch, tmp_path):
    """"kare 3: donem uyusmuyor" ile "kare 7: donem uyusmuyor" ayni aile."""
    _durum(monkeypatch, tmp_path, ORNEK)
    _red_dosyasi(
        tmp_path,
        "2026-08-23-05-rejected.json",
        [
            {
                "stage": "video",
                "review": {
                    "agir_kusurlar": [
                        "kare 3: donem uyusmuyor",
                        "kare 7: donem uyusmuyor",
                        "kare 1: konuyla ilgisiz modern goruntu",
                    ],
                    "issues": ["Scene 2: bir sey"],
                },
            }
        ],
    )

    t = uretim_rapor.red_teshisi()

    assert dict(t["en_sik_agir_kusur"])["donem uyusmuyor"] == 2
    assert dict(t["en_sik_kusur"])["bir sey"] == 1


def test_BOZUK_dosya_raporu_DUSURMUYOR(monkeypatch, tmp_path):
    """⚠️ Teshis araci, teshis edecegi kusurdan olmemeli.

    Mutasyon: `except`i kaldirmak — yarim yazilmis tek bir JSON butun
    raporu goturur ve hattin neden dustugu tam o an ogrenilemez.
    """
    _durum(monkeypatch, tmp_path, ORNEK)
    (tmp_path / "logs" / "2026-08-23-99-rejected.json").write_text("{yarim", encoding="utf-8")
    _red_dosyasi(tmp_path, "2026-08-23-11-rejected.json", [{"stage": "planning", "review": {}}])

    t = uretim_rapor.red_teshisi()

    assert t["okunamayan"] == 1
    assert t["asama"] == {"planning": 1}, "saglam dosya yine okunmali"


def test_ONARIM_tutan_ve_tutmayan_AYRISIYOR(monkeypatch, tmp_path):
    """⚠️ Kapali dongunun okuma ucu: onarim calisti mi degil, TUTTU mu.

    Mutasyon: hepsini tuttu saymak.
    """
    _durum(
        monkeypatch,
        tmp_path,
        {
            "published": [{"onarim": [{"sahne": 1, "tuttu": True}]}],
            "rejected": [
                {"onarim": [{"sahne": 2, "tuttu": False}, {"sahne": 3, "tuttu": True}]}
            ],
        },
    )

    o = uretim_rapor.rapor()["onarim"]

    assert (o["denendi"], o["tuttu"], o["tutmadi"]) == (3, 2, 1)
    assert o["tutma_orani"] == round(2 / 3, 3)


def test_ONARIM_kaydi_yoksa_ORAN_None(monkeypatch, tmp_path):
    """Alan 2026-08-23'te eklendi; oncesi icin 0 demek "onarim tutmadi"
    diye okunurdu — bilinmiyor ile basarisiz ayri seyler."""
    _durum(monkeypatch, tmp_path, ORNEK)

    assert uretim_rapor.rapor()["onarim"]["tutma_orani"] is None
