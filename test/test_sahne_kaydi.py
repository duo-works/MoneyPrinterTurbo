"""Koşum kaydi sahne duzeyinde NE ISTENDI / NE GELDI tutmali.

⚠️ NEDEN VAR — 2026-08-14. Darbogazi bulmak icin 12 koşumun hakem ciktisini
tek tek elle okumak gerekti, cunku `state.json` sahne duzeyinde hicbir sey
tutmuyordu: hangi terim arandi, hangi dosya alintilandi, karsiliginda ne
indirildi. Skor ve `issues` "kotu" diyor ama NEDEN demiyor.

Bu kayit olmadan bir sonraki "olcup degistir" turu ayni korlukle baslar.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan() -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="Cutty Sark",
        title="baslik",
        script="metin",
        scenes=[
            {
                "narration": "gemi tam yelken",
                "search_term": "Cutty Sark full sails",
                "kaynak_dosya": "Cutty-sark.png",
            },
            {
                "narration": "limanda bekliyor",
                "search_term": "Cutty Sark Sydney Harbour",
                "kaynak_dosya": "StateLibQld 1 146359.jpg",
            },
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def test_kayit_istenen_ve_geleni_yan_yana_koyuyor():
    kunyeler = [{"scene": 1, "title": "File:Cutty-sark.png"}]

    kayit = ya.sahne_kaydi(_plan(), kunyeler)

    assert kayit[0] == {
        "sahne": 1,
        "terim": "Cutty Sark full sails",
        "kaynak_dosya": "Cutty-sark.png",
        # ⚠️ 2026-08-20'de eklendi. Bu alan olmadan yayinlanmis bir plandan
        # `ContentPlan` yeniden kurulamiyor, yani turetme (`turetme.py`)
        # sahne basina tek kare tasiyan FARKLI bir video uretirdi ve fark
        # sessiz olurdu. Burada bos: `_plan()` sahneleri ikinci dosya
        # tasimiyor ve bos ikincil bir kusur DEGIL.
        "kaynak_dosya_2": "",
        "gelen": "File:Cutty-sark.png",
        # ⚠️ 2026-08-23'te eklendi. Bu sahnenin ikincil kunyesi yok, o yuzden
        # bos — ve bosluk bir kusur DEGIL.
        "gelen_2": "",
        "anlatim": "gemi tam yelken",
    }


def test_IKINCIL_kunye_birincilin_USTUNE_YAZMIYOR():
    """⚠️ SESSIZ OLCUM KUSURU, olculdu 2026-08-23.

    `credits` once birincil sonra IKINCIL kredileri tasiyor ve ikisi ayni
    `scene` numarasini kullaniyor. Eski kod tek bir sozluk kuruyordu, yani
    ikincil kredi birincilin USTUNE yaziyordu: iki gorselli sahnelerde
    `gelen`, `kaynak_dosya`nin degil `kaynak_dosya_2`nin karsiligiydi.

    Bedeli: "istenen dosya teslim edildi mi" sorusuna bakan her analiz
    birincil istegi IKINCIL teslimle karsilastiriyordu. Bu oturumda tam o
    karsilastirma yapildi ve %50 "teslim kacmasi" cikti — sayi yanlisti.

    Mutasyon: tek sozluge (`{scene: title}`) geri donmek bu testi dusurur.
    """
    kunyeler = [
        {"scene": 1, "title": "File:BIRINCIL.png"},
        {"scene": 1, "title": "File:IKINCIL.png"},
    ]

    kayit = ya.sahne_kaydi(_plan(), kunyeler)

    assert kayit[0]["gelen"] == "File:BIRINCIL.png", "birincil yuva ezilmis"
    assert kayit[0]["gelen_2"] == "File:IKINCIL.png"


def test_kunye_yoksa_alan_bos_kaliyor():
    """Kaynak kapisinda dusen kosumda bazi sahnelerin kunyesi olmayabilir."""
    kayit = ya.sahne_kaydi(_plan(), [])

    assert kayit[1]["gelen"] == ""
    assert kayit[1]["kaynak_dosya"] == "StateLibQld 1 146359.jpg"


def test_kayit_HER_IKI_red_yoluna_da_bagli():
    """⚠️ Baglanti testi — fonksiyon dogru olsa bile cagrilmazsa kayit bos kalir.

    Iki ayri red yolu var (kaynak kapisi ve video kapisi) ve bu oturumda
    maliyet farki tam da orada: 146 reddin 120'si render'a hic ulasmadan
    kaynak kapisinda dustu.

    ⚠️ KAYNAK AYRISTIRILIYOR, DIZE ARANMIYOR (2026-08-23). Eskiden
    `'"sahneler": sahne_kaydi('` dizesi SAYILIYORDU ve video yolu ayni kaydi
    bir yerel degiskenden (`sahneler`) yazmaya baslayinca test DAVRANIS
    DOGRUYKEN dustu. Olculecek sey ifade degil, kaydin ALANI.
    """
    import ast

    agac = ast.parse(Path(ya.__file__).read_text(encoding="utf-8"))
    bulunan: set[str] = set()
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Dict):
            continue
        anahtarlar = {
            k.value
            for k in dugum.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        if "stage" not in anahtarlar or "sahneler" not in anahtarlar:
            continue
        for anahtar, deger in zip(dugum.keys, dugum.values):
            if (
                isinstance(anahtar, ast.Constant)
                and anahtar.value == "stage"
                and isinstance(deger, ast.Constant)
            ):
                bulunan.add(str(deger.value))

    assert {"source_materials", "video"} <= bulunan, (
        f"iki red yolu da sahne kaydi tasimali; bulunan: {sorted(bulunan)}"
    )


def test_kaynak_kapisi_kunyeyi_tasiyor():
    """`SourceMaterialRejected` kunyeyi tasimazsa 'ne geldi' sutunu hep bos olur."""
    hata = ya.SourceMaterialRejected(
        ya.QualityReview(False, 0, 100, [], []), [{"scene": 1, "title": "File:x.jpg"}]
    )

    assert hata.credits == [{"scene": 1, "title": "File:x.jpg"}]


# --- YAYIN kaydinda da tutuluyor (2026-08-18) --------------------------------
#
# ⚠️ NEDEN VAR — kayit yalnizca RED yollarina bagliydi; YAYINLANAN videolarda
# sahne duzeyinde hicbir sey tutulmuyordu. Olculdu: iki yayinlanmis videonun
# kusurlarini teshis etmek `commons_materials` klasorlerini ve koşum loglarini
# elle kazmayi gerektirdi — ve o klasorler koşum sonrasi TEMIZLENIYOR, yani
# kayit kalici olarak kayboluyordu.


def test_YAYIN_kaydi_da_sahneleri_tutuyor():
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def run_cycle(")

    assert '"sahneler": [' in kaynak[i:], "yayin kaydinda sahne eslemesi YOK"
    assert "for kayit in sahne_kaydi(plan, credits)" in kaynak[i:]


def test_yayin_kaydi_KELIME_sayisi_tasiyor():
    """⚠️ #49'un esigini KALIBRE ETMEK icin. `ANLATIM_DENGESI` = 2,5 su an TEK
    bir olcume dayaniyor (Cemal Pasha, oran 3,57) cunku depo sahne
    anlatimlarini hic saklamiyordu. Birkac video birikince esik OLCUYLE
    guncellenmeli; bu alan o veriyi biriktiriyor."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def run_cycle(")

    assert '"kelime": len(re.findall' in kaynak[i:]
