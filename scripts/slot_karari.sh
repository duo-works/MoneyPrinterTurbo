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

TETIK_SAATLERI="6 11 16 21"
# ⚠️ UZUN KOL KAPALI (2026-09-13, kanal sahibinin karari): uzun videolar artik
# OpenMontage autopilot'undan geliyor (gunde 2, zamanlanmis yayin —
# `~/Projects/OpenMontage-autopilot`, launchd `com.shemz.openmontage.autopilot`).
# 00:05 tetigi kaldirildi; bu hat yalnizca Shorts uretir. Geri acmak icin:
# "0 6 11 16 21" + `UZUN_SAAT=0` + plist'e 00:05 + testlerdeki tablo.
#
# ⚠️ TEK KAYNAK. Zamanlayici (`com.shemz.uretim.plist`) ayni diziyi tasiyor
# ve `test_slot_karari.py` ikisini KARSILASTIRIYOR — ayrisirlarsa
# `sonraki_tetige_kalan_dk` gercekte olmayan bir tetigi bekler ve ikinci
# koşum penceresi yanlis hesaplanir. `sahne_kolu` da bu diziyi geziyor.
#
# ⚠️ 10 TETIK -> 5 TETIK (2026-09-12, kanal sahibinin karari: "tasarruflu
# olmamiz lazim"): 00:05 UZUN · 06:05 11:05 16:05 21:05.
#
# ⚠️ VE BU BIR VERIM ARTISI DEGIL, SURE UZATMASIDIR — karistirilmasin.
# Olculdu: hesap $10,0315 harcamis, ayni donemde 88 zamanlanmis kosum
# bitmis -> ~$0,114/kosum; 16 YAYIN -> ~$0,63/yayinlanan video. Kredi KOSUM
# satin aliyor, GUN degil. Tetigi yariya indirmek ayni ~24 videoyu daha uzun
# zamana yayar; dolar basina video sayisini DEGISTIRMEZ. Onu degistirmenin
# tek yolu bosa giden kosumu azaltmak (redlerin %59'u kalite reddi).
#
#     10 tetik/gun -> ~$1,14/gun -> kalan $14,97 ~13 gun
#      5 tetik/gun -> ~$0,57/gun -> kalan $14,97 ~26 gun
#
# ⚠️ Eski 2 saatlik Shorts bandi (05/07/09/11/13/15/17/19/21) BUNUN yerine
# geldi. Bosluklar 5 saat, yani her slot tek kosumluk pencereden (olculen
# max 60 dk) kat kat genis; uzun slot 00:05 -> 06:05 = 360 dk ile ESKISINDEN
# de genis (onceki 300 dk).
#
# ⚠️ 120 DAKIKALIK PENCERE OLCULDU (`zamanlayici.log`, "kol |" satirinin
# eklendigi 22 Agu'dan beri, n=8 Shorts slotu — dusuk ama DURUST n):
#
#     tek koşumla biten slot  n=4  29 · 60 · 28 · 33 dk   max  60
#     iki koşumlu slot        n=4  21 · 35 · 98 · 144 dk  max 144
#
# Tek koşum her vakada sigiyor. Iki koşumlu slotlarin 1/4'u asiyor; bedeli
# bir sonraki tetigin "atlandi | onceki kosum suruyor" yazmasi.
#
# ⚠️ Gece bandina Shorts KONMADI, ve gerekcesi olcum: 23:05 koşumu 1/4
# ihtimalle kilidi 00:05'e tasiyip uzun slotu yakardi (tek koşum max 60 dk),
# 03:05 ise uzun slotun IKINCI koşumunu oldururdu — 120 dk esigi 3 saatlik
# pencereye sigmaz, yani "uzun israr et" karari devre disi kalirdi.

UZUN_SAAT=-1
# ⚠️ UZUN KOL KAPALI (2026-09-13): hicbir saat -1 olmadigi icin `uzun_slot_mu`
# her zaman yanlis doner; dort tetigin dordu de Shorts. Eskiden `0` idi
# (gunde TEK uzun video, 00:05).

uzun_slot_mu() {
  # $1 saat (0-23) — verilmezse simdiki saat.
  # ⚠️ `10#` ONEKI ZORUNLU: `date +%H` saat 08'de "08" veriyor ve bash bunu
  # SEKIZLIK sanip hata veriyor. Ayni tuzak `uret.sh`te de yazili.
  [ "$((10#${1:-$(date +%H)}))" = "$UZUN_SAAT" ]
}

sahne_kolu() {
  # Tutunma deneyinin kolu: 6 sahne (uzun klip) mi 8 sahne mi.
  # $1 saat (0-23) — verilmezse simdiki saat.
  #
  # ⚠️ ESKIDEN `uret.sh` GOVDESINDE ve SAATTEN turetiliyordu: `(SAAT/3)%2`.
  # Kendi yorumu "duzensiz izgarada da bozulmuyor" diyordu ve 0/5/8/11/14/
  # 17/20 icin dogruydu (gunde 3'er). 2 SAATLIK BANTTA BOZULUYOR — olculdu:
  #
  #     saat      5  7  9 11 13 15 17 19 21
  #     (S/3)%2   1  0  1  1  0  1  1  0  1
  #     kol       8  6  8  8  6  8  8  6  8   -> 8 sahne 6 slot · 6 sahne 3
  #
  # 2:1 carpiklik. Bu kol `tutunma-ilk-sahne-degisiminde-dusuyor` olcumunun
  # deneyi; carpik kol deneyi SESSIZCE curutur.
  #
  # ⚠️ Kol artik `TETIK_SAATLERI` icindeki SIRADAN turuyor, saatten degil:
  #
  #     indeks    1  2  3  4  5  6  7  8  9   (0 = uzun slot)
  #     kol       8  6  8  6  8  6  8  6  8   -> 8 sahne 5 slot · 6 sahne 4
  #
  # Tam alternasyon; tek sayida slot oldugu icin 5/4 en dengeli bolunme.
  # Izgara yeniden dizilirse kol kendiliginde dengeli kalir.
  #
  # ⚠️ NEDEN BURADA: `uret.sh` govdesine gomulu oldugu surece SINANAMIYORDU
  # ve gercekten de HIC testi yoktu — bozuldugunu ancak elle hesaplayarak
  # gorduk. Bu dosyanin kurali: govdeye gomulu karar sinanamaz.
  #
  # ⚠️ `10#` ONEKI ZORUNLU (bkz. `uzun_slot_mu`): `date +%H` saat 08'de "08"
  # veriyor ve bash bunu SEKIZLIK sanip hata veriyor.
  local saat=$((10#${1:-$(date +%H)})) sira=0 tetik
  for tetik in $TETIK_SAATLERI; do
    if [ "$tetik" = "$saat" ]; then
      [ $((sira % 2)) = 1 ] && echo 8 || echo 6
      return 0
    fi
    sira=$((sira + 1))
  done
  # ⚠️ IZGARA DISI (elle koşum): bugunku varsayilan kol. Zamanlayici burayi
  # hic gormez; yine de sessiz bos deger dondurmek `--sahne-sayisi ""` ile
  # CLI hatasi uretirdi.
  echo 8
}

GUNLUK_YUKLEME_TAVANI=$(echo "$TETIK_SAATLERI" | wc -w | tr -d ' ')
# ⚠️ GEREKCESI DEGISTI — eski gerekce OLCULEREK CURUDU (2026-08-23).
#
# Burada `6` yaziyordu ve depoda dort yerde su gerekce vardi: "`videos.insert`
# 1600 birim, gunluk kota 10.000 -> gunde en fazla 6 yukleme." Google'in kendi
# belgesi bunu curutuyor (iki ayri sayfa okundu):
#
#   determine_quota_cost : "The search.list and videos.insert methods have
#                           their own quota buckets. Each of these methods has
#                           a default daily limit of 100 per day."
#                          videos.insert maliyeti 1 birim — 1600 DEGIL.
#   getting-started      : "100 search.list calls, 100 videos.insert calls,
#                           and 10,000 units per day combined for all other
#                           endpoints"
#
# Yani gercek tavan gunde ~100 yukleme. Dolayli kanit da tutuyor:
# `zamanlayici.log`da bugune dek TEK BIR `quotaExceeded` yok.
#
# ⚠️ Ve bu, izgarayi siklastirinca ILK KEZ ISIRIRDI: 22 Agu olculdu, 6 Shorts
# slotu -> 4 yayin. Ayni oranla 9 slot ~6 yayin, yani YANLIS tavan gercek
# yayinlari bloklamaya baslardi. Deponun imza kusuru yeni bir yerde — kapi,
# tuketicinin gercekte sahip oldugundan baska bir sayiyi olcuyor.
#
# ⚠️ SAYI ICAT EDILMIYOR, TURETILIYOR: bir slot yayinladiktan sonra ikinci
# koşum yapmiyor (`ikinci_kosum_gerekli_mi` yalnizca cikis 2'de donuyor),
# yani gun icinde MUMKUN olan en fazla yayin = tetik sayisi. Tavan boylece
# yapisi geregi baglamiyor ama patolojik bir donguye karsi EMNIYET SUPABI
# olarak duruyor.

tetik_atlansin_mi() {
  # $1 bugun yayinlanan video sayisi.
  #
  # ⚠️ ILK KOSUMUN kapisi. Bugune kadar tavan YALNIZCA ikinci koşumu
  # kapatiyordu (`ikinci_kosum_gerekli_mi`); her slotun ILK koşumu tavandan
  # bagimsiz calisip ~30 dakikalik render'i yakiyor ve ancak yuklemede
  # `quotaExceeded` ile oluyordu. Izgara siklastikca (6 -> 9 Shorts slotu)
  # o israf da siklasir.
  #
  # ⚠️ NEDEN BURADA, `uret.sh` govdesinde DEGIL: govdeye gomulu karar
  # sinanamaz — bu dosyanin varlik sebebi.
  [ "${1:-0}" -ge "$GUNLUK_YUKLEME_TAVANI" ]
}

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
  # varsayiyordu. Bugunku dizilim duzensiz (0,5,7,9,11,13,15,17,19,21) ve
  # formul TERS yone de yaniliyor: saat 06:30'da bir sonraki tetigi 09:05
  # sanip 155 dk gorurdu, gercekte 07:05 yani 35 dk. Yani ikinci koşumu
  # kalmayan pencerede baslatip BIR SONRAKI slotu yakardi.
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

tetikten_gecen_dk() {
  # $1 saat (0-23) · $2 dakika — verilmezse simdiki zaman.
  # En son tetikten (HH:05) bu yana gecen dakika.
  #
  # ⚠️ NEDEN VAR — olculdu (2026-09-12, `pmset -g log` + `hata-*.log`).
  # Bu makine bir MacBook ve kapak kapaninca UYUYOR. launchd tetigi uyku
  # sirasinda atesleyemiyor, makine uyaninca atesliyor: 12 Eyl'de 00:05 tetigi
  # 00:13'te, 05:05 tetigi 05:13'te basladi; 05:13 koşumu ~09:30'dan 11:12'ye
  # (kapak acilana) kadar dondu ve uc tetik atlandi. 9-11 Eyl'de 4-8 saatlik
  # ayni desen var. Uyku sirasinda zaman asimi yiyen bir LLM/render denemesi
  # ODENMIS tokeni yakar.
  #
  # Kod uykuyu ENGELLEYEMEZ (kapak uykusunu `caffeinate` bile tutmaz); bu
  # fonksiyon onu GORUNUR yapar: `uret.sh` gecikmeyi `zamanlayici.log`a
  # yazar ki "koşum neden 6 saat surdu" sorusu hata loglarini elle acmadan
  # cevaplansin. Slot ATLANMAZ — gecikmis bir tetik hala bir tetiktir.
  #
  # `10#` oneki `sonraki_tetige_kalan_dk` ile ayni sebepten.
  local saat=$((10#${1:-$(date +%H)}))
  local dakika=$((10#${2:-$(date +%M)}))
  local simdi=$((saat * 60 + dakika))
  local son=""
  local tetik
  for tetik in $TETIK_SAATLERI; do
    local an=$((tetik * 60 + 5))
    if [ "$an" -le "$simdi" ]; then
      son="$an"
    fi
  done
  if [ -n "$son" ]; then
    echo $((simdi - son))
    return 0
  fi
  # Gunun ilk tetiginden once: son tetik DUNUN sonuncusu.
  local sonuncu
  sonuncu=$(echo "$TETIK_SAATLERI" | awk '{print $NF}')
  echo $((simdi + 24 * 60 - (sonuncu * 60 + 5)))
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
