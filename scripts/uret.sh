#!/bin/bash
# Saat basi bir uretim kosumu — launchd bunu tetikler.
#
# ⚠️ NEDEN VAR: 2026-08-14'e kadar hicbir zamanlayici yoktu. Uretim yalnizca
# biri elle baslatinca calisiyordu ve kanal ~10 video/ay uretiyordu. Slot
# mekanizmasi (`publication_slot_key`) saatte bir yayina zaten izin
# veriyordu; kullanan yoktu. Yani cikti kapasitenin degil ILGININ siniriydi.
#
# ⚠️ ESZAMANLILIK ICIN YENI KOD YOK. Kilit
# (`storage/youtube_automation/automation.lock`) ve saatlik slot zaten var;
# bu betik yalnizca onlari dogru YORUMLUYOR.
#
# Cikis kodlari (`youtube_automation.main`):
#   0  yayinlandi
#   2  reddedildi  (kalite kapisi — normal, gunun cogu bu)
#   3  aday yok
#   1  digersi: kilit dolu (iyi huylu) YA DA yapisal hata (kotu)
#
# ⚠️ 1 KODU IKI SEYI BIRDEN ANLATIYOR ve ayirmak sart: kilit dolu demek
# "onceki kosum hala suruyor" (beklenen), yapisal hata demek "hat kirik"
# (bu oturumda uc kosum sessizce `NameError` ile oldu ve yalnizca video
# akmadigi icin fark edildi).

set -uo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_DOSYASI="${YTOTO_ENV:-/Users/mirzasaribiyik/Projects/Yt_Automation/.env}"
LOG_DIZINI="$KOK/storage/youtube_automation/logs"
OZET_LOG="$LOG_DIZINI/zamanlayici.log"
YETKI_BAYRAGI="$KOK/storage/youtube_automation/YETKI-GEREKIYOR"

mkdir -p "$LOG_DIZINI"
zaman() { date "+%Y-%m-%d %H:%M:%S"; }
yaz() { echo "$(zaman) | $*" >>"$OZET_LOG"; }

# ⚠️ PATH ACIKTAN KURULUYOR. launchd islerini `/usr/bin:/bin:/usr/sbin:/sbin`
# ile calistiriyor — kabuk profili OKUNMUYOR. Hat cikarimi `hermes` komutunu
# CIPLAK ADLA cagiriyor (`_json_completion` → `_run_hermes`) ve hermes
# `~/.local/bin` altinda, yani o dar PATH'te BULUNAMAZ.
#
# Elle calistirinca sorun gorunmuyor: oturumun kendi PATH'i devraliniyor ve
# her sey calisiyor. Kusur yalnizca zamanlayici ilk kez atesledigi anda
# ortaya cikardi — yani gozetimsizken.
#
# `ytoto` mutlak yolla yapilandirilmis (config.toml `ytoto_path`), ffmpeg
# `imageio_ffmpeg` ile paket icinden geliyor; PATH'e ihtiyac duyan tek sey
# hermes.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if ! command -v hermes >/dev/null 2>&1; then
  yaz "HATA | hermes bulunamadi (PATH=$PATH)"
  exit 1
fi

# .env dosyasi degerleri: `ytoto` koprusu ve API anahtarlari oradan geliyor.
# ⚠️ Icerik LOGA BASILMAZ; yalnizca ortama alinir.
if [[ -f "$ENV_DOSYASI" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_DOSYASI"
  set +a
else
  yaz "HATA | .env bulunamadi: $ENV_DOSYASI"
  exit 1
fi

CIKTI_DOSYASI="$(mktemp)"
trap 'rm -f "$CIKTI_DOSYASI"' EXIT

# ⚠️ DENEY KOLU SAATE GORE DONUSUMLU. Yoksa deney hic olusmaz: zamanlayici
# bayraksiz kosar, model her seferinde 6-10 arasindan kendi secer ve iki kol
# birbirine karisir.
#
# Olculdu (2026-08-14, `audienceWatchRatio`): izleyicinin ucte biri ILK SAHNE
# DEGISIMINDE gidiyor ve klip suresi `ses ÷ sahne`, yani sahne sayisi o
# kesmenin ne zaman geldigini belirliyor. Karsilastirilacak sey bu.
#
# 0/6/12/18 → 6 sahne (uzun klip) · 3/9/15/21 → 8 sahne (mevcut davranis)
# Gunde 4'er deneme, yani kol basina haftada ~28 sans.
# ⚠️ `10#` ONEKI ZORUNLU. `date +%H` saat 06'da "06" veriyor ve bash bunu
# `(( ))` icinde SEKIZLIK sayi sanip hata veriyor; hata da sessizce `else`
# daline dusurup 06:05 koşumunu yanlis kola yazardi.
SAAT=$((10#$(date +%H)))
if (( (SAAT / 3) % 2 == 0 )); then
  SAHNE=6
else
  SAHNE=8
fi

cd "$KOK" || exit 1

# ⚠️ URETIMDEN ONCE KUYRUGU BESLE. Olculdu (2026-08-14): uretim iki kez
# durdu ve ikisinde de sebep hattin kendisi degil beslenmemesiydi —
# `Secildi` kuyrugu 1-2 adaya dusmustu, `Yeni`de 100+ aday bekliyordu ve
# yedek capa havuzu tukenmisti (kalan 0). Yedek havuz EMNIYET SUPABI
# olmali, ana kaynak degil.
#
# ⚠️ Cikis kodu BILEREK yok sayiliyor (`|| true`): besleme bir
# IYILESTIRME adimi, on kosul degil. Notion erisilemezse bile uretim
# denenmeli — kuyrukta aday varsa ya da yedek capa kaldiysa video cikar.
# Besleme hatasi uretimi oldururse, tek bir ag kesintisi butun gunu
# bosa gecirirdi.
# Ilk yazim `>`: ayni slotta yeniden denenirse eski gunluk uzerine
# eklenmesin, uretim ciktisi asagida `>>` ile bunun ardina gelsin.
.venv/bin/python huni_besle.py >"$CIKTI_DOSYASI" 2>&1 || true

.venv/bin/python youtube_automation.py \
  --from-notion --yedek-konu --privacy public --sahne-sayisi "$SAHNE" \
  >>"$CIKTI_DOSYASI" 2>&1
KOD=$?

case "$KOD" in
  0)
    URL="$(grep -o '"url": "[^"]*"' "$CIKTI_DOSYASI" | head -1 | cut -d'"' -f4)"
    yaz "YAYIN | $URL"
    rm -f "$YETKI_BAYRAGI"
    ;;
  2)
    SKOR="$(grep -o '"visual_alignment_score": [0-9]*' "$CIKTI_DOSYASI" | tail -1 | tr -d ' ' | cut -d: -f2)"
    yaz "red | en son skor ${SKOR:-?}"
    rm -f "$YETKI_BAYRAGI"
    ;;
  3)
    yaz "aday yok"
    ;;
  *)
    if grep -q "already running" "$CIKTI_DOSYASI"; then
      # Onceki kosum hala suruyor. Bir kosum ~20 dk; saatlik tetikte bu
      # normaldir ve BEKLENMEZ — siradaki saat zaten gelecek.
      yaz "atlandi | onceki kosum suruyor"
      exit 0
    fi
    if grep -q "quotaExceeded" "$CIKTI_DOSYASI"; then
      # ⚠️ Gunluk YouTube kotasi doldu, hat kirik degil. `videos.insert`
      # 1600 birim ve gunluk kota 10.000 — yani GUNDE EN FAZLA 6 YUKLEME.
      # Tetikleme araligi (3 saat = 8 deneme) bu tavana gore secildi; yine de
      # yayin orani yukselirse gun icinde tavana vurulabilir.
      yaz "kota doldu | gunluk 6 yukleme tavani"
      exit 0
    fi
    HATA_DOSYASI="$LOG_DIZINI/hata-$(date +%Y%m%d-%H%M%S).log"
    cp "$CIKTI_DOSYASI" "$HATA_DOSYASI"
    # ⚠️ OAuth ayrı isaretleniyor. Olculmus not (`youtube_upload`): onay
    # ekrani Google Cloud'da "Testing" durumundayken refresh token 7 GUNDE
    # BIR geciyor. Gozetimsiz bir zamanlayici o gun sessizce olur; bayrak
    # dosyasi sebebi goz onune koyuyor.
    if grep -qE "RefreshError|invalid_grant" "$CIKTI_DOSYASI"; then
      echo "$(zaman) — YouTube yetkisi dustu. Cozum: onay ekranini Cloud Console'da Production'a al, sonra token'i yenile." >"$YETKI_BAYRAGI"
      yaz "HATA | YouTube yetkisi dustu -> $YETKI_BAYRAGI"
    else
      yaz "HATA | cikis $KOD -> $HATA_DOSYASI"
    fi
    exit "$KOD"
    ;;
esac
