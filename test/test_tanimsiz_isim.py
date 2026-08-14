"""Uretim hattinda TANIMSIZ ISIM olmamali.

⚠️ NEDEN VAR — olculdu (2026-08-14, aci bicimde). `kareyi_onar` cagrisina
`konu` diye var olmayan bir degisken yazdim. Kod yalnizca video hakemi
"reddet" dedikten SONRA calisan bir dalda oldugu icin:

  · butun testler yesildi (1180),
  · uc uretim koşumu sirayla video RENDER ETTI ve tam da onarim satirinda
    `NameError` ile coktu — yani ~30 dakikalik render, seslendirme ve
    hakem cagrisi cope gitti, uc kez.

Yazdigim baglanti testi bunu goremezdi: kaynak metninde
`"kareyi_onar(plan, review"` arıyordu ve o dize DOGRUYDU. Birim testler de
goremezdi: fonksiyonu monkeypatch'liyorlar, cagri yerini degil.

Bu yuzden kapi statik: nadiren calisan dallardaki tanimsiz isimler ancak
boyle yakalanir. Hat kodunun her satiri her koşumda calismiyor.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

# Hattin cekirdek modulleri — uretim koşumunda calisan her sey.
MODULLER = [
    "youtube_automation.py",
    "wikimedia_materials.py",
    "met_materials.py",
    "europeana_materials.py",
    "notion_kuyrugu.py",
    "capa_eslesme.py",
    "gorsel_olcum.py",
    "uretim_rapor.py",
]


def _ruff() -> str | None:
    return shutil.which("ruff") or (
        str(KOK / ".venv/bin/ruff") if (KOK / ".venv/bin/ruff").exists() else None
    )


@pytest.mark.skipif(_ruff() is None, reason="ruff kurulu degil")
def test_hatta_tanimsiz_isim_yok():
    hedefler = [str(KOK / ad) for ad in MODULLER if (KOK / ad).exists()]

    sonuc = subprocess.run(
        [_ruff(), "check", "--select", "F821", "--no-cache", *hedefler],
        capture_output=True,
        text=True,
        cwd=str(KOK),
    )

    assert sonuc.returncode == 0, f"tanimsiz isim:\n{sonuc.stdout}"
