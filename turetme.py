"""Yayinlanmis UZUN videodan dikey Shorts turetme — plan tarafi.

Kanal sahibinin karari (2026-08-20): gunde 1 uzun + 2 Shorts, ve Shorts'lar
**ayni gunun uzun videosundan** ciksin.

⚠️ BU KIRPMA DEGIL. Uzun format yatay (`dikey=False`) ve 9:16 kapisi ayri bir
suzgec; ucuz olan sey videoyu kirpmak degil **plani yeniden kullanip sahne
altkumesini dikey kapidan yeniden render etmek**. Bu modul o altkumeyi
kuruyor; render ve kapilar degismeden `run_generator`in isi.

⚠️ IKI BICIMIN SAHNE YOGUNLUGU UYUSMUYOR ve bu olculmeden fark edilmezdi:

    uzun   : 28 sahne · 1.170 kelime · sahne basina 41,8 kelime
    shorts : 6-10 sahne · 80-150 kelime TOPLAM

Yani ardisik uzun sahneleri oldugu gibi almak imkansiz: 4 sahne bile 150-187
kelime yapiyor, yani tavanin ustunde. Olculen cozum **sahne basina TEK
CUMLE**:

    uzun sahnelerin 27/28'i tam iki cumle (biri uc)
    ilk cumleler: 14-29 kelime, ortalama 21,5

    6 sahne x ilk cumle : 112-145 kelime  ->  23/23 pencere ARALIKTA
    7 sahne x ilk cumle : 133-162 kelime  ->   9/22
    8 sahne x ilk cumle : 159-187 kelime  ->   0/21

6 ayni zamanda Shorts sahne TABANI, yani pencere hem kelime hem sahne
kapisini tek degerle geciyor. Bu yuzden `TURETME_SAHNE_SAYISI` sabit.

⚠️ Her sahne KENDI gorseliyle geliyor. Alternatif tasarim (3 uzun sahne x 2
cumle) ayni kelime araligini tutturuyordu ama 6 sahneye yalnizca 3 ayri
dosya dusuyordu — yani ayni gorsel arka arkaya iki sahnede. Deponun tekrar
kapisi (`_tekrar_mi`) onu zaten reddederdi; daha onemlisi izleyici gorurdu.
"""

from __future__ import annotations

import re
from typing import Any

TURETME_SAHNE_SAYISI = 6
"""Bir Shorts'a giren ardisik UZUN sahne sayisi. Gerekce modul basliginda."""

KAYNAK_BICIMI = "uzun"

_CUMLE_SINIRI = re.compile(r"(?<=[.!?])\s+")


def cumleler(anlatim: str) -> list[str]:
    """Anlatimi cumlelere boler. Bos girdi bos liste dondurur."""
    return [parca for parca in _CUMLE_SINIRI.split(str(anlatim or "").strip()) if parca]


def ilk_cumle(anlatim: str) -> str:
    """Sahnenin ILK cumlesi — turetilen Shorts sahnesinin anlatimi.

    ⚠️ Neden ilki ve neden yalnizca biri: modul basligindaki olcum. Ikinci
    cumle ayrinti tasiyor, ilki sahnenin ONERMESI; alti tanesi yan yana
    uzun videonun sikistirilmis hali oluyor.
    """
    parcalar = cumleler(anlatim)
    return parcalar[0] if parcalar else ""


def pencere_sayisi(sahne_sayisi: int, *, pencere: int = TURETME_SAHNE_SAYISI) -> int:
    """Bir uzun videodan kac AYRISIK Shorts turetilebilir.

    ⚠️ Ayrisik (ortusmeyen) pencereler: ayni sahneyi iki Shorts'ta kullanmak
    hem izleyiciye tekrar hem `is_duplicate_visual_anchor` icin gercek bir
    tekrar olurdu. 28 sahne / 6 = 4 pencere; artan 4 sahne kullanilmaz.
    """
    if pencere <= 0:
        return 0
    return max(0, int(sahne_sayisi)) // pencere


def turetilebilir_yayinlar(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Turetmeye uygun uzun yayinlar — EN YENIDEN eskiye.

    ⚠️ Olcut `bicim == "uzun"` DEGIL, `bicim == "uzun"` VE plan yeniden
    kurulabiliyor. 2026-08-20'den once yayinlanmis uzun kayitlarda
    `description`/`tags`/`ruh_hali` alanlari YOK (o gun eklendi), yani
    onlardan turetmek eksik bir plan kurar. Sessizce eksik plan kurmaktansa
    kaydi listeye HIC almamak dogru: cagiran "turetilebilir yayin yok" der
    ve sebep gorunur olur.
    """
    uygun = []
    for kayit in state.get("published", []) or []:
        if kayit.get("bicim") != KAYNAK_BICIMI:
            continue
        if kayit.get("status") != "published":
            continue
        if not plani_kurulabilir_mi(kayit):
            continue
        uygun.append(kayit)
    return list(reversed(uygun))


ZORUNLU_ALANLAR = (
    "topic",
    "visual_anchor",
    "script",
    "sahneler",
    "description",
    "tags",
)


def plani_kurulabilir_mi(kayit: dict[str, Any]) -> bool:
    """Kayit `ContentPlan`i SIFIR CIKARIMLA kurmaya yetiyor mu.

    `ruh_hali` ZORUNLU DEGIL: `ContentPlan`da varsayilani bos ve bos deger
    "muzigi havuzdan sec" demek — bugunku davranisin aynisi, kusur degil.
    """
    for alan in ZORUNLU_ALANLAR:
        if not kayit.get(alan):
            return False
    return bool(pencere_sayisi(len(kayit.get("sahneler") or [])))


def turetilmis_sahneler(
    kayit: dict[str, Any], sira: int, *, pencere: int = TURETME_SAHNE_SAYISI
) -> list[dict[str, str]]:
    """`sira`. pencerenin sahnelerini `ContentPlan.scenes` biciminde dondurur.

    `sira` SIFIR TABANLI: 0 -> uzun videonun 1-6. sahneleri.

    ⚠️ `kaynak_dosya_2` BOS birakiliyor. Uzun formatta sahne basina tek kare
    var (`kare_yuvasi=1`), yani kayitta ikinci dosya zaten yok. Shorts iki
    yuva istiyor ve eksik ikincil bir kusur DEGIL: `kare_yerlesimi` o sahnede
    birincili iki yuvada gosteriyor. Buraya komsu sahneden bir dosya
    doldurmak cazip ama YANLIS olurdu — anlatim o gorseli anlatmiyor, yani
    deponun imza kusurunu (kapi/tuketici ayrismasi) elle uretmek olurdu.
    """
    sahneler = kayit.get("sahneler") or []
    bas = int(sira) * pencere
    dilim = sahneler[bas : bas + pencere]
    if len(dilim) < pencere:
        raise ValueError(
            f"pencere {sira} icin yeterli sahne yok: {len(dilim)} < {pencere}"
        )
    return [
        {
            "narration": ilk_cumle(sahne.get("anlatim", "")),
            "search_term": str(sahne.get("terim", "")),
            "kaynak_dosya": str(sahne.get("kaynak_dosya", "")),
            "kaynak_dosya_2": "",
        }
        for sahne in dilim
    ]


def turetilmis_plan_alanlari(
    kayit: dict[str, Any], sira: int, *, pencere: int = TURETME_SAHNE_SAYISI
) -> dict[str, Any]:
    """`ContentPlan` alanlari — `title` HARIC.

    ⚠️ `title` neden yok: determinist bir baslik kurali denendi ve ÖLÇÜMLE
    CÜRÜDÜ. Kural "ilk cumleyi ilk yan cumle sinirinda kes" idi; dort
    pencerede sonuc:

        pencere  1- 6 : "Herculaneum's boat houses held 340 skeletons"  (44) ✓
        pencere  7-12 : 150 karakter — baslik degil, cumle              ✗
        pencere 13-18 : 122 karakter                                    ✗
        pencere 19-24 : 114 karakter                                    ✗

    1/4. Yani plan bedava kuruluyor ama baslik icin tek kucuk cikarim
    cagrisi gerekiyor; o cagri `youtube_automation.turetilmis_plani_kur`da.
    "Sifir cikarim" hedefi PLAN icin tutuyor, metadata icin tutmuyor.

    ⚠️ `script` sahne anlatimlarindan YENIDEN kuruluyor, kayittaki `script`
    alani kopyalanmiyor. Olculdu: uzun kayitta `script` (5.843 krkt) ile
    anlatimlarin birlesigi (7.242 krkt) AYNI DEGIL — model ikisini ayri
    yaziyor. Kaydi kopyalasaydik turetilen videonun sesi 28 sahneyi,
    goruntusu 6 sahneyi anlatirdi.
    """
    sahneler = turetilmis_sahneler(kayit, sira, pencere=pencere)
    return {
        "topic": str(kayit.get("topic", "")),
        "visual_anchor": str(kayit.get("visual_anchor", "")),
        "script": " ".join(sahne["narration"] for sahne in sahneler).strip(),
        "scenes": sahneler,
        "description": str(kayit.get("description", "")),
        "tags": list(kayit.get("tags") or []),
        "ruh_hali": str(kayit.get("ruh_hali", "")),
    }


def turetme_kimligi(kayit: dict[str, Any], sira: int) -> str:
    """Bu (uzun video, pencere) ciftinin kimligi — tekrar turetmeyi engeller."""
    return f"{kayit.get('slot', '')}#{int(sira)}"


def turetilmis_pencereler(state: dict[str, Any], kayit: dict[str, Any]) -> set[int]:
    """Bu uzun videodan DAHA ONCE turetilmis pencerelerin sira numaralari."""
    kimlikler = {
        str(y.get("turetildi", {}).get("kimlik", ""))
        for y in (state.get("published", []) or [])
        if isinstance(y.get("turetildi"), dict)
    }
    return {
        sira
        for sira in range(pencere_sayisi(len(kayit.get("sahneler") or [])))
        if turetme_kimligi(kayit, sira) in kimlikler
    }


def sonraki_pencere(state: dict[str, Any], kayit: dict[str, Any]) -> int | None:
    """Bu uzun videodan turetilecek SIRADAKI pencere; hepsi bittiyse None."""
    kullanilmis = turetilmis_pencereler(state, kayit)
    for sira in range(pencere_sayisi(len(kayit.get("sahneler") or []))):
        if sira not in kullanilmis:
            return sira
    return None
