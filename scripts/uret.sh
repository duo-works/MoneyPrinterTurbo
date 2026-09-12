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

# ⚠️ BOSTA UYKU KILIDI — olculdu (2026-09-12, `pmset -g log`). Bu makine bir
# MacBook; koşum surerken uyursa LLM/render denemesi zaman asimiyla oluyor ve
# ODENMIS token cope gidiyor (12 Eyl 05:13 koşumu 11:12'ye kadar dondu).
# `caffeinate -i` YALNIZCA bosta uykuyu tutar; kapak kapaninca makine yine
# uyur — o operasyon karari (fiste + kapak acik). `-w $$` ile kilit bu
# betikle birlikte olur; `command -v` yoksa (Linux) sessizce atlanir.
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -i -w $$ &
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

cd "$KOK" || exit 1

# ⚠️ Slot karari AYRI DOSYADA ve saf — gerekcesi `slot_karari.sh` icinde.
# Govdeye gomulu bir karar sinanamazdi. Kol secimi (`uzun_slot_mu`) ve
# deney kolu (`sahne_kolu`) de oradan geliyor, ayni sebeple.
#
# ⚠️ KAYNAK SIRASI: bu satir SAHNE hesabindan ONCE olmak ZORUNDA. Eskiden
# sonra geliyordu cunku hesap bir formuldu (`(SAAT/3)%2`) ve hicbir seye
# bagli degildi; `sahne_kolu` `TETIK_SAATLERI`yi geziyor.
# shellcheck source=slot_karari.sh
. "$KOK/scripts/slot_karari.sh"

# ⚠️ DENEY KOLU SAATE GORE DONUSUMLU. Yoksa deney hic olusmaz: zamanlayici
# bayraksiz kosar, model her seferinde 6-10 arasindan kendi secer ve iki kol
# birbirine karisir.
#
# Olculdu (2026-08-14, `audienceWatchRatio`): izleyicinin ucte biri ILK SAHNE
# DEGISIMINDE gidiyor ve klip suresi `ses ÷ sahne`, yani sahne sayisi o
# kesmenin ne zaman geldigini belirliyor. Karsilastirilacak sey bu.
#
# ⚠️ SECIM ARTIK `slot_karari.sh`TE ve SAATTEN degil `TETIK_SAATLERI`
# icindeki SIRADAN turuyor. Eski `(SAAT / 3) % 2` formulu 3 saatlik izgarada
# dengeliydi ama 2 saatlik bantta 2:1 carpitiyordu (8 sahne 6 slot / 6 sahne
# 3 slot) — yani deneyi sessizce curutuyordu. Gerekcenin tamami ve olcum
# `sahne_kolu`nun yorumunda.
#
# ⚠️ `10#` ONEKI ZORUNLU. `date +%H` saat 06'da "06" veriyor ve bash bunu
# `(( ))` icinde SEKIZLIK sayi sanip hata veriyor; hata da sessizce yanlis
# kola yazardi.
SAAT=$((10#$(date +%H)))
SAHNE="$(sahne_kolu "$SAAT")"

# ⚠️ KOL SECIMI — kanal sahibinin karari (2026-08-22): 00:05 UZUN video,
# kalan alti tetik Shorts.
#
# ⚠️ Uzun kolda `--sahne-sayisi` GECILMIYOR ve bu zorunlu: CLI o ikiliyi
# yasakliyor (`--uzun ile --sahne-sayisi birlikte kullanilamaz`), cunku
# sahne sayisi deneyi Shorts koluna ait. Gecirilseydi uzun slot her gun
# arguman hatasiyla olurdu.
#
# ⚠️ IKINCI KOSUM DA AYNI KOLDA: dizi bir kez kuruluyor ve iki koşum da
# onu kullaniyor, yani uzun slotun ikinci denemesi de uzun ("uzun israr
# et"). Shorts'a dusus yok.
if uzun_slot_mu "$SAAT"; then
  KOL="uzun"
  KOL_BAYRAKLARI=(--uzun)
  UZUN_KOL=1
else
  KOL="shorts"
  KOL_BAYRAKLARI=(--sahne-sayisi "$SAHNE")
  UZUN_KOL=0
fi
yaz "kol | $KOL"

# ⚠️ GECIKMIS TETIK GORUNUR OLSUN — gerekce `tetikten_gecen_dk`. launchd
# uyuyan makinede tetigi uyaninca atesliyor; 15 dk'dan gec baslayan tetik
# "makine uyudu" demek. Slot ATLANMAZ, yalnizca loglanir: "koşum neden 6 saat
# surdu" sorusu artik `zamanlayici.log`dan cevaplanir.
GECIKME_DK="$(tetikten_gecen_dk)"
if [ "${GECIKME_DK:-0}" -gt 15 ]; then
  yaz "tetik gecikmesi | $GECIKME_DK dk (makine uyudu mu?)"
fi

kilit_var() {
  [ -e "$KOK/storage/youtube_automation/automation.lock" ] && echo 1 || echo 0
}

uretim_kosumu() {
  # $@ = konu KAYNAGI bayraklari; gerisi kola gore (`KOL_BAYRAKLARI`).
  .venv/bin/python youtube_automation.py \
    "$@" --privacy public "${KOL_BAYRAKLARI[@]}" \
    >>"$CIKTI_DOSYASI" 2>&1
}

# ⚠️ ISLENMIS SATIR SAYACI — cift yazimi kapatiyor (2026-08-23).
PLAN_RED_ISLENEN=0

plan_redlerini_yaz() {
  # ⚠️ HER koşumdan sonra calisiyor: ikinci koşumun denemeleri de bir butce
  # yakiyor ve #41'in olcmek istedigi sinyal tam olarak o.
  #
  # ⚠️ YALNIZCA YENI SATIRLAR — olculdu (2026-08-23). Eskiden `CIKTI_DOSYASI`nin
  # TAMAMI yeniden grep'leniyordu. Ikinci koşum ayni dosyaya `>>` ile ekliyor,
  # yani ilk koşumun red satirlari IKI KEZ yaziliyordu. Log'un tek kullanicisi
  # olcum oldugu icin sayi dogrudan yaniltiyordu:
  #
  #     147 ham satir -> 123 tekil   (%16 sisme)
  #
  # Ornegin 23 Agu 05:50 ve 06:43 bloklari ilk dort satirda BIREBIR ayni.
  local toplam
  toplam="$(wc -l <"$CIKTI_DOSYASI" 2>/dev/null | tr -d ' ')"
  toplam="${toplam:-0}"
  # ⚠️ ${VAR:-0} ZORUNLU: betik `set -u` ile kosuyor ve bu fonksiyon
  # testte GOVDESINDEN KESILIP tek basina calistiriliyor. Disaridaki
  # baslangic degerine yaslanan bir surum orada tanimsiz degiskene duser —
  # ve `bash -n` bunu yakalamaz.
  tail -n "+$(( ${PLAN_RED_ISLENEN:-0} + 1 ))" "$CIKTI_DOSYASI" 2>/dev/null \
    | grep "reddedildi" \
    | while IFS= read -r satir; do echo "$(zaman) | $satir"; done \
    >>"$LOG_DIZINI/plan-redleri.log" || true
  PLAN_RED_ISLENEN="$toplam"
}

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

# ⚠️ ILK KOSUM DA TAVANI GORUYOR. Bugune kadar tavan YALNIZCA ikinci koşumu
# kapatiyordu; her slotun ilk koşumu tavandan bagimsiz calisip ~30 dakikalik
# render'i yakiyor ve yuklemede `quotaExceeded` ile oluyordu. Izgara
# siklastikca (6 -> 9 Shorts slotu) bu israf da siklasir.
YAYIN_SAYISI="$(bugunku_yayin_sayisi .venv/bin/python "$KOK/storage/youtube_automation/state.json")"
if tetik_atlansin_mi "$YAYIN_SAYISI"; then
  yaz "tavan | bugun $YAYIN_SAYISI yayin, tetik atlandi"
  exit 0
fi

uretim_kosumu --from-notion --yedek-konu
KOD=$?
plan_redlerini_yaz

# ⚠️ IKINCI KOSUM — olculdu 2026-08-21. Koşum medyani 25 dk, 3 saatlik
# pencerede kalan bos sure 156 dk, denenen koşum 1. Hat %84 ihtimalle
# dusuyor ve sonra 2,5 saat hicbir sey yapmiyor.
#
# ⚠️ Ikinci koşum `--from-notion` GECMIYOR: kanal sahibinin karari, ikinci
# deneme kanitlanmis capa havuzundan gelsin. Bayrak davranisi kodda
# dogrulandi — `--from-notion` yokken `aday` None kalir, `--yedek-konu`
# `no-candidate` donusunu engeller ve akis `kaynak = "yedek"` daline duser
# (`youtube_automation.py:8486`). Olculmus gerekce: model-secimli anit/yer
# konulari 70-90 skor / 0-3 kusur, huniden gelen kisi konulari 68-84 / 9-11.
if ikinci_kosum_gerekli_mi \
    "$KOD" \
    "$(sonraki_tetige_kalan_dk)" \
    "$(bugunku_yayin_sayisi .venv/bin/python "$KOK/storage/youtube_automation/state.json")" \
    "$(kilit_var)" \
    "$UZUN_KOL"; then
  yaz "ikinci koşum | ilk koşum reddedildi, havuz çapasıyla yeniden deneniyor"
  uretim_kosumu --yedek-konu
  KOD=$?
  plan_redlerini_yaz
fi

# ⚠️ PLAN DENEMELERI KALICI HALE GETIRILIYOR — olculdu (2026-08-18, #41).
# Bu satirdan onceki tek kayit yolu suydu: `CIKTI_DOSYASI` bir `mktemp` ve
# `:68`deki trap onu CIKISTA SILIYOR. Kopya yalnizca BEKLENMEDIK cikis
# kodunda (`*)` dali) `hata-*.log`a aliniyor; 0 (yayin) ve 2 (red) — yani
# koşumlarin neredeyse tamami — stdout'u cope atiyor.
#
# Kalici `<slot>-rejected.json` bu bosluğu KAPATMIYOR: oraya yalnizca bes
# denemenin HEPSI tukenirse tek bir "son kusur" yaziliyor. Yani 1. deneme
# 184 kelimede dusup 2. deneme gecerse geriye HIC iz kalmiyor — ve #41'in
# olcmek istedigi sinyal tam olarak bu, cunku o deneme bir butce yakiyor.
#
# `youtube_automation.py:3841` ayni korlugu bir kez olcup ic dongude
# kapatmisti ("her deneme yaziliyor, yalnizca sonuncusu degil"); duzeltme
# elle koşumlara ulasti, zamanlayiciya ulasmadi. Burasi o eksik yarisi.
#
# ⚠️ `case`ten ONCE ve her cikis kodu icin calisiyor: yayinlanan bir koşum
# da deneme yakmis olabilir ve o da sinyaldir.
# ⚠️ `|| true` — betikte `set -e` yok (`set -uo pipefail`) ama eslesmeyen
# grep 1 donduruyor; bagimliligi yok etmek icin acikca yutuluyor.
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
      # ⚠️ Gunluk YouTube kotasi doldu, hat kirik degil.
      #
      # ⚠️ ESKI GEREKCE CURUDU (2026-08-23): burada "videos.insert 1600 birim,
      # gunluk kota 10.000 -> gunde en fazla 6 yukleme" yaziyordu. Google'in
      # belgesi `videos.insert`in AYRI bir kovasi oldugunu ve gunluk 100
      # cagri verildigini soyluyor (maliyet 1 birim). Bu dala DUSULURSE sebep
      # yukleme sayisi degil, buyuk olasilikla 10.000 birimlik ORTAK havuz
      # (arama/liste cagrilari) — o yuzden mesaj artik sayi soylemiyor.
      yaz "kota doldu | YouTube gunluk kotasi"
      exit 0
    fi
    if grep -q "KREDI_TABANI" "$CIKTI_DOSYASI"; then
      # ⚠️ Bakiye tabanin altinda; hat kirik DEGIL ve hata logu gerekmiyor.
      # Olculdu: 23 Agu 15:15 - 12 Eyl arasi 135 tetigin 135'i HTTP 402 ile
      # yigin iziyle oldu ve hepsi loga "HATA | cikis 1" yazdi. O satir
      # gercek bir kusurla ayni gorunuyordu; sebebi gormek icin her seferinde
      # hata logunu elle acmak gerekiyordu.
      yaz "kredi bitti | bakiye tabanin altinda"
      exit 0
    fi
    if grep -q "SAGLAYICI_REDDI" "$CIKTI_DOSYASI"; then
      # Kosum SIRASINDA bakiye/kota bitti (402/403/429). Kayit `state.json`a
      # `provider_error` olarak dustu, yani telemetri bunu kalite reddinden
      # ayirt edebiliyor.
      yaz "saglayici reddi | kosum sirasinda kesildi"
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
