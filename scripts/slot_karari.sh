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

ikinci_kosum_gerekli_mi() {
  # $1 ilk koşumun cikis kodu · $2 sonraki tetige kalan dakika
  # $3 bugun yayinlanan video · $4 kilit var mi (1/0)
  local kod="$1" kalan="$2" yayin="$3" kilit="$4"

  # ⚠️ YALNIZCA KALITE REDDINDE (cikis 2) yeniden deneniyor.
  #   0 yayinlandi   -> slot dolu, is bitti
  #   3 aday yok     -> hemen yeniden denemek ayni bos kuyruga bakar
  #   1 yapisal hata -> olculdu 21 Agu: uc koşum da DISK DOLU ile dustu,
  #                     yeniden denemek uc kez bosa render ederdi
  [ "$kod" = "2" ] || return 1

  [ "$kilit" = "0" ] || return 1
  [ "$kalan" -ge "$ASGARI_PENCERE_DK" ] || return 1
  [ "$yayin" -lt "$GUNLUK_YUKLEME_TAVANI" ] || return 1
  return 0
}

sonraki_tetige_kalan_dk() {
  # $1 saat (0-23) · $2 dakika — verilmezse simdiki zaman.
  # Zamanlayici 3 saatte bir :05'te atesliyor (com.shemz.uretim.plist).
  # ⚠️ `10#` ONEKI HEM VARSAYILANA HEM GECILEN DEGERE — `date +%H` saat 08'de
  # "08" veriyor ve bash bunu SEKIZLIK sanip hata veriyor. Ayni tuzak
  # `uret.sh:83`te de yazili.
  #
  # ⚠️ Ilk yazimda onek yalnizca VARSAYILANDAYDI ve uretimde gorunmezdi
  # (`uret.sh` bu fonksiyonu argumansiz cagiriyor); testi yazarken "08 09"
  # gecince patladi. Sinanmayan dal, sinanan daldan farkli davraniyordu.
  local saat=$((10#${1:-$(date +%H)}))
  local dakika=$((10#${2:-$(date +%M)}))
  local simdi=$((saat * 60 + dakika))
  local sonraki=$(((saat / 3 + 1) * 3 * 60 + 5))
  echo $((sonraki - simdi))
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
