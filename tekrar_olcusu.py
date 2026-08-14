"""Tekrar olculeri — kapinin ve raporun ORTAK dili.

⚠️ NEDEN AYRI MODUL. Ayni olcu iki yerde lazim: `youtube_automation` uretim
sirasinda KAPI olarak kullaniyor (tekrarlayan plani reddet), `kanal_rapor`
sonradan RAPOR olarak (kacan tekrar var mi). Ikisi ayri kopya olsaydi
esikler zamanla birbirinden kayar ve rapor, kapinin engelledigi seyden
baska bir sey olcerdi — yani rapora bakip "temiz" derken kapi baska bir
kurala gore calisiyor olurdu.

`kanal_rapor` bu yuzden `youtube_automation`i ICE AKTARMIYOR: o modul
config yukluyor ve MPT'nin yarisini ayaga kaldiriyor; salt okunur bir
raporun buna ihtiyaci yok.
"""

from __future__ import annotations

import re

ORTUSME_ESIGI = 0.6
"""Iki metin bu orandan fazla kelime paylasirsa "ayni cumle" sayiliyor.

⚠️ `youtube_automation.KAPANIS_ORTUSME_ORANI` ile AYNI sayi olmali —
rapor, kapinin engelledigi seyi olcsun diye. Esik SECILDI, olculmedi:
kapanislar 2026-08-14'te kaydedilmeye baslandi ve karsilastirilacak
gecmis henuz yoktu. Veri birikince `--tekrar` ciktisiyla gozden gecir.
"""

SORU_KELIMELERI = frozenset(
    {
        "why", "how", "who", "what", "when", "where", "which",
        "did", "was", "were", "is", "are", "do", "does", "can", "could", "will",
    }
)

# Bicim ve ortusme olcerken tasiyici olmayan kelimeler. Kisa liste bilerek:
# uzun bir durak kelime listesi ayirt edici kelimeleri de yer yer siliyor.
_DURAK = frozenset(
    {"the", "and", "but", "for", "was", "were", "that", "this", "with", "from", "into", "its", "his", "her", "their", "not"}
)


def _kelimeler(metin: str) -> set[str]:
    return {
        k for k in re.findall(r"[a-z']{3,}", str(metin).lower()) if k not in _DURAK
    }


def kelime_ortusmesi(birinci: str, ikinci: str) -> float:
    """Iki metnin paylastigi kelime orani — KISA olana gore.

    ⚠️ Bolen KISA metin (Jaccard degil). Sebebi: uzun bir kapanis, kisa bir
    kapanisi tamamen icerse Jaccard bunu dusuk gosterir ama izleyici icin
    o iki cumle aynidir. `_kapanis_tekrari` da ayni olcuyu kullaniyor.
    """
    a, b = _kelimeler(birinci), _kelimeler(ikinci)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def baslik_bicimi(baslik: str) -> str:
    """Basligin KALIBI — konusu degil bicimi.

    ⚠️ Olculdu (2026-08-14, yayindaki 15 video): ilk bes video "The ... of
    ..." tamlamasi, son dokuzu duz soru, son ALTISININ ALTISI da soru ve
    ucu "Why ...". Konu tekrari icin kapi vardi, bicim tekrari icin yoktu.

    ⚠️ Iki noktadan SONRAKI kelimeye bakiliyor: "Friedrich Hayek: Why Did
    He Win..." ile "Second Anglo-Dutch War: Why Did It End?" gozle farkli
    gorunuyor ama kalibi ayni; ayirt edici olan ozel ad degil soru kelimesi.
    """
    metin = str(baslik).replace("#Shorts", "").strip()
    if not metin:
        return "diger"
    if metin.endswith("?"):
        govde = metin.rsplit(":", 1)[-1] if ":" in metin else metin
        ilk = re.findall(r"[A-Za-z]+", govde)
        if not ilk:
            return "soru/diger"
        kelime = ilk[0].lower()
        return f"soru/{kelime}" if kelime in SORU_KELIMELERI else "soru/diger"
    if metin.lower().startswith("the "):
        return "tamlama"
    return "diger"
