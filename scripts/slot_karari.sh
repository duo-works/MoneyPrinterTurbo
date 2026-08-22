# Slot penceresinde IKINCI bir uretim koşumu denensin mi.
#
# ⚠️ NEDEN AYRI DOSYA: karar `uret.sh`in govdesine gomulu olsaydi sinanamazdi
# ve bu depoda sinanmayan kapi, kapattigi kusura geri doner. Burasi SAF: ne
# dosya okuyor ne ag. `bugunku_yayin_sayisi` ayri tutuldu, o okuyor.
#
# ⚠️ NEDEN VAR — olculdu 2026-08-21, `zamanlayici.log`un 70 koşumu:
#
#     YAYIN 11 · red 44 · HATA 15   ->  koşum basina yayin p = 0,16
#     koşum medyan suresi           :  25 dk
#     3 saatlik pencerede kalan bos : 156 dk  (medyan)
#     denenen koşum                 :   1
#
# Yani hat %84 ihtimalle dusuyor ve sonra 2,5 saat HICBIR SEY yapmiyor.
# 15:05 koşumu 14 dakikada dustu, hat 18:05'e kadar bos bekledi.
#
# ⚠️ Bu bir KALITE gevsetmesi degil: esiklerin hicbiri degismiyor, yalnizca
# bos gecen pencerede ikinci bir konu deneniyor.
#
# Kanal sahibinin karari (21 Agu): slot basina EN FAZLA IKI koşum, ikincisi
# kanitlanmis capa havuzundan.

TETIK_SAATLERI="0 5 8 11 14 17 20"
# ⚠️ TEK KAYNAK. Zamanlayici (`com.shemz.uretim.plist`) ayni diziyi tasiyor
# ve `test_slot_karari.py` ikisini KARSILASTIRIYOR — ayrisirlarsa
# `sonraki_tetige_kalan_dk` gercekte olmayan bir tetigi bekler ve ikinci
# koşum penceresi yanlis hesaplanir.
#
# ⚠️ IZGARA ARTIK DUZENLI DEGIL (2026-08-22, kanal sahibinin karari):
# 00:05 UZUN · 05:05 · 08:05 · 11:05 · 14:05 · 17:05 · 20:05.
# Uzun slota ~5 saat veriliyor cunku olculen uzun koşum 100-210 dk surdu ve
# 3 saatlik pencereye SIGMIYORDU: tasan koşum sonraki Shorts slotunu
# "atlandi | onceki kosum suruyor" ile yakiyordu (20-21 Agu'da uc kez).

UZUN_SAAT=0
# ⚠️ Gunde TEK uzun video. Kalan alti tetik Shorts.

uzun_slot_mu() {
  # $1 saat (0-23) — verilmezse simdiki saat.
  # ⚠️ `10#` ONEKI ZORUNLU: `date +%H` saat 08'de "08" veriyor ve bash bunu
  # SEKIZLIK sanip hata veriyor. Ayni tuzak `uret.sh`te de yazili.
  [ "$((10#${1:-$(date +%H)}))" = "$UZUN_SAAT" ]
}

GUNLUK_YUKLEME_TAVANI=6
# ⚠️ YouTube kotasi: `videos.insert` 1600 birim, gunluk kota 10.000 ->
# gunde en fazla 6 yukleme. Bugune kadar hat bu tavana TEPKISEL carpiyordu
# (`quotaExceeded` yakalanip loglaniyor); ikinci koşum acilinca gunluk yayin
# sayisi artacagi icin tavan ONCEDEN sayiliyor.

ASGARI_PENCERE_DK=35
# ⚠️ Bir sonraki tetige bundan az kalmissa ikinci koşum BASLAMAZ: koşum
# medyani 25 dk ve tetik sirasinda kilit doluysa zamanlayici
# "atlandi | onceki kosum suruyor" yazip slotu bos gecer. Yani agresif
# davranmak bir sonraki slotu yakardi.

UZUN_ASGARI_PENCERE_DK=120
# ⚠️ Uzun koşum icin AYRI esik, ve sayi olculdu:
#
#     Herculaneum  slot 2026-08-20-14 -> yayin 15:42   ~100 dk
#     Alhambra     slot 2026-08-20-21 -> yayin 00:37   ~210 dk
#
# En KISA uzun koşum 100 dk. 35 dakikalik artikla uzun bir ikinci koşum
# baslatmak, kilidi bir sonraki tetige tasimak demekti — yani Shorts
# slotunu yakmak. Bu bir kalite esigi degil, SURE butcesi.

asgari_pencere_dk() {
  # $1 uzun kol mu (1/0)
  [ "${1:-0}" = "1" ] && echo "$UZUN_ASGARI_PENCERE_DK" || echo "$ASGARI_PENCERE_DK"
}

ikinci_kosum_gerekli_mi() {
  # $1 ilk koşumun cikis kodu · $2 sonraki tetige kalan dakika
  # $3 bugun yayinlanan video · $4 kilit var mi (1/0) · $5 uzun kol mu (1/0)
  #
  # ⚠️ UZUN SLOTTA IKINCI KOSUM DA UZUN — Shorts'a DUSULMUYOR (kanal
  # sahibinin karari: "uzun israr et"). Kol secimi `uret.sh`te bir kez
  # yapiliyor ve iki koşum da ayni bayraklarla kosuyor; burasi yalnizca
  # PENCERE esigini kola gore seciyor.
  local kod="$1" kalan="$2" yayin="$3" kilit="$4" uzun="${5:-0}"

  # ⚠️ YALNIZCA KALITE REDDINDE (cikis 2) yeniden deneniyor.
  #   0 yayinlandi   -> slot dolu, is bitti
  #   3 aday yok     -> hemen yeniden denemek ayni bos kuyruga bakar
  #   1 yapisal hata -> olculdu 21 Agu: uc koşum da DISK DOLU ile dustu,
  #                     yeniden denemek uc kez bosa render ederdi
  [ "$kod" = "2" ] || return 1

  [ "$kilit" = "0" ] || return 1
  [ "$kalan" -ge "$(asgari_pencere_dk "$uzun")" ] || return 1
  [ "$yayin" -lt "$GUNLUK_YUKLEME_TAVANI" ] || return 1
  return 0
}

sonraki_tetige_kalan_dk() {
  # $1 saat (0-23) · $2 dakika — verilmezse simdiki zaman.
  #
  # ⚠️ ARTIK FORMUL DEGIL LISTE GEZILIYOR (2026-08-22). Eski hali
  # `(saat / 3 + 1) * 3 * 60 + 5` idi ve 3 SAATLIK DUZENLI IZGARA
  # varsayiyordu. Yeni dizilim duzensiz (0,5,8,11,14,17,20): formul saat
  # 05:30'da bir sonraki tetigi 06:05 sanardi, gercekte 08:05 — yani
  # ikinci koşum penceresini 35 dk gorup 155 dk'yi kaciririrdi.
  #
  # ⚠️ `10#` ONEKI HEM VARSAYILANA HEM GECILEN DEGERE — `date +%H` saat 08'de
  # "08" veriyor ve bash bunu SEKIZLIK sanip hata veriyor.
  #
  # ⚠️ Ilk yazimda onek yalnizca VARSAYILANDAYDI ve uretimde gorunmezdi
  # (`uret.sh` bu fonksiyonu argumansiz cagiriyor); testi yazarken "08 09"
  # gecince patladi. Sinanmayan dal, sinanan daldan farkli davraniyordu.
  local saat=$((10#${1:-$(date +%H)}))
  local dakika=$((10#${2:-$(date +%M)}))
  local simdi=$((saat * 60 + dakika))
  local tetik
  for tetik in $TETIK_SAATLERI; do
    local an=$((tetik * 60 + 5))
    if [ "$an" -gt "$simdi" ]; then
      echo $((an - simdi))
      return 0
    fi
  done
  # ⚠️ GECE YARISI SARMASI: bugunku tetiklerin hepsi gecmisse sonraki tetik
  # YARININ ilkidir. Sarma olmadan fonksiyon 20:30'da NEGATIF doner ve
  # `[ "$kalan" -ge ... ]` sessizce yanlis tarafa duserdi.
  local ilk
  ilk=$(echo "$TETIK_SAATLERI" | awk '{print $1}')
  echo $((24 * 60 + ilk * 60 + 5 - simdi))
}

bugunku_yayin_sayisi() {
  # $1 python yolu · $2 state.json yolu
  local py="$1" durum="$2"
  "$py" -c "
import json, sys
from datetime import date
try:
    d = json.load(open(sys.argv[1], encoding='utf-8'))
except Exception:
    print(0); raise SystemExit
bugun = date.today().isoformat()
print(sum(1 for r in d.get('published', [])
          if str(r.get('published_at', '')).startswith(bugun)))
" "$durum" 2>/dev/null || echo 0
  # ⚠️ HATADA 0 DONER, tavani KAPATMAZ. Okunamayan bir durum dosyasi yuzunden
  # uretimi durdurmak, tavani bir kez asmaktan kotu — kota hatasi zaten
  # `uret.sh` tarafinda yakalaniyor.
}
