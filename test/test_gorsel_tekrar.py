"""Gecici OpenAI hatasinda gorsel uretimini tekrar deneme (DW-115).

⚠️ Olculdu (2026-08-09): bes konuluk bir kosumda api.openai.com Cloudflare
uzerinden DORT kez 520 dondu. OpenAI'nin durum sayfasi ayni anda "All Systems
Operational" diyordu — kesinti araliktiydi ve hatanin govdesi
`"retryable": true, "retry_after": 60` tasiyordu.

Tekrar yokken bedeli agirdi: hata 8 sahnenin ortasinda gelince o ana kadar
uretilmis gorseller ve plan icin harcanan para cope gidiyordu; kosumun iki
konusu tam da boyle dustu.

Depo ayni gerekceyi `wikimedia_materials._get_with_retry` icin zaten yaziyor
("gecici bir ag hatasinin bedeli harcanan LLM/gorsel parasi oluyor"); eksik
olan, ayni korumanin gorsel ucunda olmamasiydi.
"""

import sys
from pathlib import Path

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, BadRequestError, InternalServerError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import youtube_automation as ya  # noqa: E402

_ISTEK = httpx.Request("POST", "https://api.openai.com/v1/images/generations")


def _sunucu_hatasi() -> InternalServerError:
    yanit = httpx.Response(520, request=_ISTEK, text="origin error")
    return InternalServerError("520", response=yanit, body=None)


class _Istemci:
    """Ilk `hata_sayisi` cagride patlar, sonra basarili doner."""

    def __init__(self, hata_sayisi: int, hata=None):
        self.cagri = 0
        self._hata_sayisi = hata_sayisi
        self._hata = hata or _sunucu_hatasi()
        self.images = self

    def generate(self, **_kwargs):
        self.cagri += 1
        if self.cagri <= self._hata_sayisi:
            raise self._hata
        return "GORSEL"


def test_ilk_denemede_basarili_olan_beklemiyor():
    uyunan = []
    istemci = _Istemci(0)

    sonuc = ya._gorsel_uret_tekrarli(istemci, {}, sahne=1, uyu=uyunan.append)

    assert sonuc == "GORSEL"
    assert istemci.cagri == 1
    assert uyunan == [], "gereksiz bekleme uretimi yavaslatir"


def test_gecici_hatadan_sonra_basariyor():
    """⚠️ Asil kazanc bu: 520 gelen sahne yeniden denenip gecince, o ana kadar
    uretilmis gorseller ve plan parasi kurtuluyor.
    """
    uyunan = []
    istemci = _Istemci(2)

    sonuc = ya._gorsel_uret_tekrarli(istemci, {}, sahne=3, uyu=uyunan.append)

    assert sonuc == "GORSEL"
    assert istemci.cagri == 3


def test_bekleme_katlanarak_artiyor():
    """Sabit bekleme, suren bir kesintide dort kez ust uste ayni anda vurur."""
    uyunan = []
    ya._gorsel_uret_tekrarli(_Istemci(3), {}, sahne=1, uyu=uyunan.append)

    assert uyunan == [
        ya.GORSEL_BEKLEME_SN,
        ya.GORSEL_BEKLEME_SN * 2,
        ya.GORSEL_BEKLEME_SN * 4,
    ]


def test_surekli_hata_sonunda_yukseliyor():
    """Sonsuza kadar denemek kosumu asili birakirdi; hata gorunur olmali."""
    uyunan = []
    istemci = _Istemci(99)

    with pytest.raises(InternalServerError):
        ya._gorsel_uret_tekrarli(istemci, {}, sahne=1, uyu=uyunan.append)

    assert istemci.cagri == ya.GORSEL_DENEME_SAYISI


@pytest.mark.parametrize(
    "hata",
    [
        APIConnectionError(request=_ISTEK),
        APITimeoutError(request=_ISTEK),
    ],
)
def test_ag_hatalari_da_tekrarlaniyor(hata):
    """Baglanti kopmasi ve zaman asimi da tanimi geregi gecici."""
    istemci = _Istemci(1, hata=hata)

    assert ya._gorsel_uret_tekrarli(istemci, {}, sahne=1, uyu=lambda _s: None) == "GORSEL"


def test_moderasyon_hatasi_TEKRARLANMIYOR():
    """⚠️ Kalici hata tekrarlanirsa yalnizca gecikme uretilir.

    Moderasyonun ayri bir kurtarma yolu var (guvenli istemle yeniden deneme);
    buradan gecmesi o yolu geciktirmekten baska ise yaramaz.
    """
    yanit = httpx.Response(400, request=_ISTEK, json={"error": {"code": "moderation_blocked"}})
    istemci = _Istemci(99, hata=BadRequestError("blocked", response=yanit, body=None))

    with pytest.raises(BadRequestError):
        ya._gorsel_uret_tekrarli(istemci, {}, sahne=1, uyu=lambda _s: None)

    assert istemci.cagri == 1, "moderasyon hatasi tekrarlanmamali"


def test_uretim_yolu_tekrarli_cagriyi_kullaniyor():
    """⚠️ Baglanti testi — yardimci dogru olsa bile cagrilmazsa koruma yok."""
    kaynak = Path(ya.__file__).read_text(encoding="utf-8")
    i = kaynak.index("def generate_ai_scene_materials(")
    govde = kaynak[i : kaynak.index("def ", i + 100)]

    assert "_gorsel_uret_tekrarli(" in govde
    assert "client.images.generate(" not in govde, "korumasiz cagri kalmis"
