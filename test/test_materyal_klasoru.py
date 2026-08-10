"""Materyal klasoru konuya gore ayrilir (DW-119).

⚠️ Olculdu (2026-08-10): tek gecede 4 video uretildi, geriye 2 materyal
klasoru kaldi. Klasor adi `publication_slot_key()` yani YYYY-MM-DD-HH idi;
ayni saat icindeki ikinci video birincinin klasorune yaziyordu.

`2026-08-10-10-attempt-1` icinde Anita Hemmings'in `credits.json`'u vardi ama
klasorde credits'te hic gecmeyen `scene-01.jpg` ve `scene-07.jpg` de duruyordu
— bir onceki videodan (Jacopo de' Pazzi) kalanlar.

Bugun render karismiyor cunku `dikeye_uydur_hepsi` acik listeyle calisiyor.
Test yine de gerekli, cunku korunan sey iki BASKA sey:

  * adli iz — Scanagatta'daki levha kusurunun materyalleri incelenemedi,
    cunku sonraki kosum uzerine yazmisti;
  * gelecekteki sessiz hata — downstream bir gun klasoru tararsa (glob),
    ayni saatteki iki videonun goruntuleri karisir ve kimse fark etmez.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402


def test_ayni_saatteki_iki_konu_ayri_klasor_alir():
    """Asil kosul: ayni saat + farkli konu → farkli yol."""
    saat = "2026-08-10-10"
    jacopo = ya.konu_slug("Jacopo de' Pazzi")
    anita = ya.konu_slug("Anita Florence Hemmings")
    assert f"{saat}-{jacopo}-attempt-1" != f"{saat}-{anita}-attempt-1"


def test_slug_dosya_adinda_guvenli():
    """Kesme isareti, aksan ve bosluk yol parcasini bozmamali."""
    for konu in ("Jacopo de' Pazzi", "Franziska Scanagatta", "Ömer/Test", "A  B"):
        slug = ya.konu_slug(konu)
        assert slug, f"bos slug: {konu!r}"
        assert "/" not in slug and " " not in slug and "'" not in slug
        assert not slug.startswith("-") and not slug.endswith("-")
        assert "--" not in slug


def test_slug_ayni_konu_icin_kararli():
    """Yeniden deneme ayni klasoru bulmali; slug rastgele olmamali."""
    assert ya.konu_slug("William Hardham") == ya.konu_slug("William Hardham")
    assert ya.konu_slug("William Hardham") == "william-hardham"


def test_slug_latin_disi_konuda_bos_donmez():
    """Yol parcasi hicbir zaman bos kalmamali, yoksa klasor bir ust dizine cikar."""
    assert ya.konu_slug("日本の城") == "konu"
    assert ya.konu_slug("   ") == "konu"


def test_materyal_klasoru_konuyu_iceriyor():
    """Kaynakta klasor adi gercekten konuyla kuruluyor mu."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    assert 'f"{publication_slot_key()}-{konu_slug(plan.topic)}-attempt-{attempt}"' in kaynak
    # Eski, cakisan bicim geri gelmemeli.
    assert 'f"{publication_slot_key()}-attempt-{attempt}"' not in kaynak


def test_kaynak_kontak_sayfasi_da_ayrisiyor():
    """Hakemin gordugu kontak sayfasi da ezilmemeli — ayni kok neden."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    assert 'f"source-{publication_slot_key()}-attempt-{attempt}.jpg"' not in kaynak
    assert "create_source_montage(material_files, attempt, plan.topic)" in kaynak
