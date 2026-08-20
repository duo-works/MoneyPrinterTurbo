"""Temizlige verilen KORUNACAK AD, dizinin gercek adi mi.

⚠️ NEDEN VAR — olculdu 2026-08-21. `run_cycle` temizligi soyle cagiriyordu:

    temizlik.kosum_sonrasi_temizle(task_id, f"{slot}-attempt-1")

Yorumu "bu kosumunkiler DURUYOR" diyordu. Duruyor DEGILDI: ad UC noktada
gercekten sapiyor.

    korunmak istenen : 2026-08-20-21-attempt-1
    gercek dizin     : 2026-08-20-23-alhambra-nasrid-...-attempt-3
                       └ indirme saati  └ DW-119 slug'i  └ gercek deneme

`material_dir` adi `publication_slot_key()`-`konu_slug(plan.topic)`-
`attempt` ile kuruluyor. `slot` YAYIN slotu ve indirme saatinden farkli
olabiliyor (olculdu: 21 vs 23), DW-119 konu slug'ini eklediginde bu dize
guncellenmemis, deneme numarasi da 1'e sabitlenmis. Yani koruma DW-119'dan
beri hicbir seyi korumuyordu: her koşum KENDI malzemesini siliyordu.

Kanit diskte: yayinlanan uzun videonun klasorunde 25 kunye vardi, 0 kare.

⚠️ NEDEN `test_temizlik.py` BUNU YAKALAYAMAZDI: orasi `temizlik`in kendi
davranisini olcuyor ve DOGRU adi elle veriyor
(`test_kosum_sonrasi_malzeme_klasorunu_de_koruyor` -> "2026-08-08-18-
attempt-1"). Yani test, kusurlu ad kalibini SABITLIYORDU. Kusur cagiran
tarafta ve ancak BAGLANTI testiyle gorunur: uretenin kurdugu ad ile
temizlige verilen ad ayni mi.

⚠️ Bu deponun imza kusuru: koruma, tuketicinin URETTIGINDEN baska bir ad
soyluyor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import temizlik  # noqa: E402
import youtube_automation as ya  # noqa: E402

# Gercek uretimde gorulen ad: indirme saati + DW-119 konu slug'i + deneme.
GERCEK_DIZIN = "2026-08-20-23-alhambra-nasrid-palaces-built-as-self-co-attempt-3"


def _plan() -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="Alhambra Nasrid palaces built as self-contained city",
        visual_anchor="Alhambra",
        title="Alhambra #Shorts",
        script=" ".join(f"word{i}" for i in range(100)),
        scenes=[
            {
                "narration": f"sahne {n}",
                "search_term": f"Alhambra detay {n}",
                "kaynak_dosya": f"dosya-{n}.jpg",
                "kaynak_dosya_2": "",
            }
            for n in range(1, 7)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def _yayina_kadar(monkeypatch, tmp_path) -> list[tuple]:
    """`run_cycle`i YAYINA kadar goturur; temizlige giden argumanlari doner."""
    plan = _plan()
    video = tmp_path / "final-1.mp4"
    video.write_bytes(b"x")
    malzeme = tmp_path / "commons_materials" / GERCEK_DIZIN
    malzeme.mkdir(parents=True)

    monkeypatch.setattr(ya, "_acquire_lock", lambda: None)
    monkeypatch.setattr(ya, "LOCK_FILE", tmp_path / "automation.lock")
    monkeypatch.setattr(ya, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        ya,
        "load_state",
        lambda: {"published": [], "rejected": [], "completed_slots": []},
    )
    monkeypatch.setattr(ya, "save_state", lambda _s: None)
    monkeypatch.setattr(ya.notion_kuyrugu, "kuyrugu_oku", lambda **_k: [])
    monkeypatch.setattr(ya, "generate_content_plan", lambda *_a, **_k: plan)
    monkeypatch.setattr(
        ya,
        "run_generator",
        lambda _p, _a, **_k: (
            "gorev-1",
            video,
            tmp_path / "s.txt",
            [],
            0,
            malzeme,
        ),
    )
    monkeypatch.setattr(
        ya, "create_review_montage", lambda *_a, **_k: tmp_path / "m.jpg"
    )
    monkeypatch.setattr(
        ya,
        "review_video",
        lambda *_a, **_k: ya.QualityReview(True, 92, 90, [], agir_kusurlar=[]),
    )

    cagrilar: list[tuple] = []

    def _temizle(*args):
        cagrilar.append(args)
        return 0

    monkeypatch.setattr(temizlik, "kosum_sonrasi_temizle", _temizle)
    return cagrilar


def test_temizlige_verilen_ad_URETILEN_dizinin_ADI(monkeypatch, tmp_path):
    """⚠️ MUTASYON: `malzeme_dizini.name` -> `f"{slot}-attempt-1"` bunu duser."""
    cagrilar = _yayina_kadar(monkeypatch, tmp_path)

    sonuc = ya.run_cycle(dry_run=True, kuyruktan=True, yedek_konu=True)

    assert sonuc["status"] == "dry-run"
    assert cagrilar, "temizlik hic cagrilmadi"
    korunan = cagrilar[-1]
    assert GERCEK_DIZIN in korunan, (
        f"korunacak adlar {korunan} — uretilen dizin {GERCEK_DIZIN!r} yok. "
        "Bu koşum kendi malzemesini silerdi."
    )


def test_gorev_kimligi_de_korunuyor(monkeypatch, tmp_path):
    """Iki ayri sey korunmali: gorev dizini (`tasks/`) ve malzeme dizini.

    ⚠️ Malzeme adini duzeltirken gorev kimligini dusurmek, `final-1.mp4`in
    yaninda duran `combined-1.mp4`i ve montaji silerdi.
    """
    cagrilar = _yayina_kadar(monkeypatch, tmp_path)

    ya.run_cycle(dry_run=True, kuyruktan=True, yedek_konu=True)

    assert "gorev-1" in cagrilar[-1]
