# Emekliye ayrılan müzik paketi (output000–029, 026 yok — 29 parça)

**Tarih:** 2026-08-12 · **İlgili:** DW-112 (yayın kapıları), DW-120 (müzik seçimi)

## Neden çıkarıldı

Bu 29 parça MoneyPrinterTurbo'nun kutudan çıkan paketiydi. İki sorunu vardı ve
ikincisi yayını fiilen bloke ediyordu:

1. **Sanatçısı ve kaynağı belirsiz.** Dosya adları `output000.mp3` … `output029.mp3`;
   ne besteci, ne kayıt, ne de nereden geldiği yazıyor.
2. **Lisansı doğrulanamıyor.** Kime ait olduğu bilinmeyen bir parçanın
   kullanım hakkı da bilinemez. DW-112'nin müzik lisansı kapısı bu yüzden
   açık kaldı: havuzda seçilme ihtimali olan tek bir belirsiz parça bile
   videoyu yayına kapatıyor.

Yerine `storage/bgm` altında **lisansı tek tek doğrulanmış 22 parçalık** yeni bir
havuz kuruldu (kamu malı / CC0 / CC BY; CC BY-SA bilerek dışarıda — pay-benzer
şartı videonun tamamını bağlar). Künye: `resource/muzik_kunye.json`.

## Neden silinmedi

Sessizce silmek, ileride "bu parçalar neden yok" sorusunu cevapsız bırakır ve
eski videolarda hangi müziğin çaldığını doğrulama imkânını yok eder. Dosyalar
duruyor, yalnızca **havuzun dışına** alındı.

## Havuzun dışında olduğunu ne garanti ediyor

`youtube_automation.py` içindeki `muzik_secenekleri()` dizinleri `iterdir()` ile
tarıyor — **özyinelemesiz**. Alt klasördeki dosyalar listeye girmiyor, dolayısıyla
`muzik_sec()` bunları seçemiyor. Geri almak için dosyaları bir üst dizine taşımak
yeterli.

## Havuzu yeniden kurmak

`storage/` git tarafından yok sayılıyor, yani yeni havuz repo'da **durmuyor**.
Temiz bir kopyada havuzu kurmak için:

    python3 muzik_havuzu_kur.py

Bu betik künyedeki kaynak adreslerinden parçaları yeniden indirir ve her birinin
lisansını yeniden doğrular.

> ⚠️ Havuz kurulmadan üretim yapılırsa `muzik_sec()` boş dize döner ve video
> **sessizce müziksiz** çıkar — hata vermez. Yeni bir makinede ilk iş bu betiği
> çalıştırmak.
