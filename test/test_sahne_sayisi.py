"""Sahne sayisi sabitlenebilmeli — tutunma deneyinin kolu bu.

⚠️ NEDEN — olculdu (2026-08-14, YouTube Analytics `audienceWatchRatio`).
Iki videonun tutunma egrisi birebir ayni kalibi verdi: ilk 5 saniyede
tutunma %100'un ustunde (kanca calisiyor, izleyici basa sariyor), sonraki
~4 saniyede ucte biri gidiyor.

Dususun yeri klip suresiyle ortusuyor. Klip = ses ÷ sahne:

    Anita  41 sn / 8 sahne = 5,1 sn   → dusus ~5-9 sn arasi
    Chaco  33 sn / 8 sahne = 4,1 sn   → dusus ~4-7 sn arasi

Yani kayip ILK SAHNE DEGISIMINDE basliyor. Sahne sayisini dusurmek butun
klipleri uzatir ve ilk kesmeyi geciktirir — `--video-clip-duration` tek ve
duzgun oldugu icin yalnizca ilk klibi uzatmak MPT katmaninda mumkun degil.

⚠️ Nedensellik HENUZ AYRISMADI: kesmenin kendisi mi kacirıyor, yoksa 2.
sahnenin anlatimi mi zayif. Bu secenek tam da onu ayiran deney icin var.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def _plan(sahne: int) -> ya.ContentPlan:
    return ya.ContentPlan(
        topic="konu",
        visual_anchor="Cutty Sark",
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
                "search_term": f"Cutty Sark detay {sira}",
                "kaynak_dosya": f"d-{sira}.jpg",
            }
            for sira in range(1, sahne + 1)
        ],
        description="aciklama",
        tags=["a", "b", "c"],
    )


def test_verilen_sayi_disi_reddediliyor():
    with pytest.raises(ValueError) as hata:
        ya.validate_content_plan(_plan(8), sahne_sayisi=6)

    assert "exactly 6 scenes" in str(hata.value)
    assert "got 8" in str(hata.value)


def test_verilen_sayi_geciyor():
    ya.validate_content_plan(_plan(6), sahne_sayisi=6)


def test_verilmezse_ESKI_aralik_geceli():
    """⚠️ Varsayilan davranis degismemeli: model 6-10 arasinda serbest."""
    ya.validate_content_plan(_plan(8))
    ya.validate_content_plan(_plan(6))
    ya.validate_content_plan(_plan(10))

    with pytest.raises(ValueError, match="6-10"):
        ya.validate_content_plan(_plan(11))


def test_istem_de_sayiyi_soyluyor(monkeypatch):
    """⚠️ Yalnizca dogrulamaya birakmak bes denemeyi bosa harcardi.

    Model aliskanlikla 8 yazar, dogrulama reddeder, dongu doner. Istem
    sayiyi soylerse ilk denemede tutar.
    """
    yakalanan: dict = {}

    def sahte(system: str, user: str) -> dict:
        yakalanan["user"] = user
        raise RuntimeError("dur")

    monkeypatch.setattr(ya, "_json_completion", sahte)
    monkeypatch.setattr(ya, "load_state", lambda: {})
    monkeypatch.setattr(ya, "_recent_titles", lambda: [])
    monkeypatch.setattr(ya, "_son_kancalar", lambda: [])
    monkeypatch.setattr(ya, "arsiv_envanteri", lambda _k: [])

    try:
        ya.generate_content_plan(sahne_sayisi=6)
    except Exception:
        pass

    assert "EXACTLY 6 scenes" in yakalanan.get("user", "")


def test_kol_kosum_kaydina_yaziliyor():
    """⚠️ Yazilmazsa hangi videonun hangi kolda oldugu SONRADAN bilinemez.

    Ayni korluk bu oturumda bir kez yasandi: sahne duzeyi telemetri yoktu ve
    teshis 12 koşumun hakem ciktisini elle okumayi gerektirdi.
    """
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def run_cycle(") :]

    assert '"sahne_sayisi": len(plan.scenes)' in govde


def test_secenek_hatta_bagli():
    """CLI bayragi `run_cycle`a gercekten geciyor mu."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("def main(") :]

    assert "--sahne-sayisi" in govde
    assert "sahne_sayisi=args.sahne_sayisi" in govde
