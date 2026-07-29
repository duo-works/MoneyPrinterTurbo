# YouTube Shorts Video Style and Production Standard

Bu belge, `MoneyPrinterTurbo` ile bu kanal için üretilecek videoların kalıcı üretim standardıdır.

## 1. Kanal hedefi

- Hedef kitle: Global ve İngilizce konuşan izleyiciler.
- İçerik türü: Şaşırtıcı gerçek olaylar, az bilinen tarih, sıra dışı insanlar ve hayvanlar, bilimsel veya tarihsel merak konuları.
- Anlatım biçimi: Hızlı, anlaşılır, duygusal veya şaşırtıcı; gereksiz giriş yapılmadan doğrudan güçlü kancayla başlanır.
- Her iddia mümkün olduğunca doğrulanabilir olmalı; kesin olmayan ayrıntılar kesin gerçek gibi anlatılmamalıdır.
- Başarı garanti edilemez; konu, kanca, izleyici tutma ve görsel uyum yüksek izlenme ihtimalini artıracak şekilde optimize edilir.

## 2. Korunacak video stili

- Dil: İngilizce (`en-US`).
- Format: Dikey 9:16, 1080x1920.
- Süre hedefi: 35-50 saniye.
- Senaryo: Yaklaşık 90-120 İngilizce kelime.
- Ses: `en-US-BrianMultilingualNeural-Male`.
- Ses hızı: Yaklaşık `1.05-1.10`; varsayılan tercih `1.08`.
- Klip süresi: En fazla 2-3 saniye.
- Kurgu: Hızlı ve sıralı; gereksiz geçiş efektleri kullanılmaz.
- Altyazı: Beyaz, siyah konturlu, yüksek kontrastlı ve dikey konumu yaklaşık %70-72.
- Altyazı ekranda güvenli alan içinde tutulur; Shorts düğmelerinin kapatabileceği en alt ve en sağ bölgelere taşmaz.
- Arka plan müziği: Telif riski belirsizse kullanılmaz. Yalnızca lisansı doğrulanmış müzik kullanılabilir.
- Görseller: Pexels/Pixabay/Coverr gibi yapılandırılmış stok kaynaklardan veya lisansı uygun yerel materyallerden seçilir.

## 3. Senaryo standardı

Senaryo şu akışla hazırlanmalıdır:

1. **0-2 saniye — Kanca:** Sonucu veya en şaşırtıcı ayrıntıyı hemen söyle.
2. **2-10 saniye — Kurulum:** Kim, nerede ve ne zaman sorularını kısa şekilde yanıtla.
3. **10-30 saniye — Gerilim/olay:** Olayı kronolojik, kısa cümlelerle anlat.
4. **30-42 saniye — Sonuç:** En güçlü sonucu veya sayısal bilgiyi ver.
5. **Son 3-5 saniye — Akılda kalan kapanış:** Tek cümlelik duygusal ya da şaşırtıcı final kullan.

Kurallar:

- İlk cümle `Did you know...` gibi zayıf ve fazla kullanılan girişlerle başlamamalıdır.
- Her cümle tek bir görsel fikri temsil etmelidir.
- Uzun ve çok parçalı cümlelerden kaçınılmalıdır.
- İlk 2 saniyede konu anlaşılmalıdır.
- Video sonunda tekrar veya uzun çağrı yapılmamalıdır.
- Yapay ve abartılı clickbait yerine merak uyandıran ama doğru bir başlık kullanılmalıdır.

## 4. Görsel-altyazı uyumu: zorunlu akıllı üretim yöntemi

Önceki videonun genel stili korunacak, fakat rastgele ve yalnızca anahtar kelime benzerliğine dayalı görsel seçimi yapılmayacaktır.

### 4.1 Önce sahne planı oluştur

Senaryo, üretimden önce 6-10 sahneye ayrılır. Her sahne için şu bilgiler hazırlanır:

| Alan | Açıklama |
|---|---|
| Zaman | Tahmini başlangıç ve bitiş |
| Anlatım | O anda duyulacak cümle |
| Ana görsel | Ekranda görünmesi gereken kişi, nesne veya olay |
| Arama terimi | Somut İngilizce stok video araması |
| Kaçınılacak görsel | Konuyla ilgisiz veya yanlış çağrışım yapan görüntü |

Örnek:

| Anlatım | Zayıf terim | Kullanılacak somut terim |
|---|---|---|
| Soldiers were trapped in World War One | `war history` | `World War One soldiers trench archival` |
| A carrier pigeon carried the final message | `hope` | `carrier pigeon taking flight close up` |
| The message reached headquarters | `military communication` | `soldier reading urgent field message` |

### 4.2 Arama terimi kuralları

- Soyut terimler (`hope`, `kindness`, `bravery`, `respect`) tek başına kullanılmaz.
- Terimler somut kişi + eylem + ortam biçiminde yazılır.
- Tarih videosunda mümkün olduğunda dönem belirtilir: `World War One`, `medieval castle`, `Roman soldier` gibi.
- Her önemli cümle için ayrı ve sıralı bir arama terimi kullanılır.
- Görsel olarak bulunması zor özel kişiler için sembolik fakat doğru bağlamlı görüntü seçilir; modern ve alakasız görüntü kullanılmaz.
- Aynı nesnenin çok benzer görüntüleri tüm videoyu kaplamamalıdır. Yakın plan, geniş plan, mekân ve olay görüntüleri dengelenir.

### 4.3 MoneyPrinterTurbo ayarları

- `--video-concat-mode sequential`
- `--match-materials-to-script`
- `--video-clip-duration 3`
- `--video-transition-mode none`
- `--video-aspect 9:16`
- `--video-language en-US`
- `--voice-rate 1.08`
- `--bgm-type none` (lisansı doğrulanmış müzik yoksa)

`--video-terms` değeri, sahne sırasına göre virgülle ayrılmış somut terimlerden oluşmalıdır. Terimlerin sırası senaryodaki cümle sırasını izlemelidir.

## 5. Üretim komutu şablonu

Aşağıdaki şablonda konu, senaryo ve arama terimleri her video için özel hazırlanır:

```bash
./venv/Scripts/python.exe cli.py \
  --video-subject "<ENGLISH SUBJECT>" \
  --video-script "<90-120 WORD ENGLISH SCRIPT>" \
  --video-terms "<SCENE 1 TERM>,<SCENE 2 TERM>,<SCENE 3 TERM>" \
  --video-language en-US \
  --video-source pexels \
  --video-count 1 \
  --video-aspect 9:16 \
  --video-concat-mode sequential \
  --video-transition-mode none \
  --video-clip-duration 3 \
  --match-materials-to-script \
  --voice-name "en-US-BrianMultilingualNeural-Male" \
  --voice-rate 1.08 \
  --bgm-type none \
  --subtitle-enabled \
  --subtitle-position custom \
  --custom-position 72 \
  --text-fore-color "#FFFFFF" \
  --font-size 60 \
  --stroke-color "#000000" \
  --stroke-width 2 \
  --subtitle-background-enabled \
  --subtitle-background-color "#000000" \
  --rounded-subtitle-background
```

## 6. Yayından önce zorunlu kalite kontrolü

Video üretildi diye doğrudan yüklenmez. Şu kontroller zorunludur:

1. FFmpeg ile çözünürlük, süre, video ve ses akışları doğrulanır.
2. Videodan başlangıç, orta ve son bölümleri kapsayan en az 6-8 kare çıkarılır.
3. Karelerde altyazı okunabilirliği, kırpma, bozulma ve sahne-anlatım uyumu incelenir.
4. `script.json` içindeki `material_sources` ve `search_term` alanları kontrol edilir.
5. Görsellerin en az %75'i o anda anlatılan cümleyle doğrudan ilişkili olmalıdır.
6. Kritik sahnelerde uyumsuzluk varsa video yüklenmez; arama terimleri değiştirilerek yeniden üretilir.
7. Özel isimler, tarihler, sayılar ve altyazı yazımı kontrol edilir.
8. Sesin anlaşılır olduğu ve altyazı zamanlamasının sesle uyumlu olduğu doğrulanır.
9. İlk 2 saniyedeki görüntü ve altyazı birlikte güçlü bir kanca oluşturmalıdır.
10. Son kare yarım cümlede veya ani bir kesilmeyle bitmemelidir.

### Otomatik reddetme koşulları

Aşağıdakilerden biri varsa video yeniden üretilir:

- Tarih anlatılırken belirgin biçimde modern ve ilgisiz görüntüler kullanılması.
- Aynı tür stok görüntünün videonun büyük bölümünde tekrarlanması.
- Anlatılan kişi/nesne yerine alakasız insan, hayvan veya mekân gösterilmesi.
- Altyazının Shorts arayüzü tarafından kapatılabilecek konumda olması.
- Bir altyazı bloğunun ekranda okunamayacak kadar uzun olması.
- İlk 2 saniyede konuya ait güçlü bir görsel bulunmaması.
- Önemli bir sayının, adın veya tarihsel iddianın doğrulanmamış olması.

## 7. Başlık ve açıklama standardı

Başlık:

- Tercihen 45-65 karakter.
- En güçlü kişi, olay veya sayı başlığın başında yer alır.
- İngilizce ve doğal olmalıdır.
- En fazla bir uygun emoji kullanılabilir.
- `#Shorts` başlıkta veya açıklamada bulunabilir.

Örnek biçim:

```text
The WWI Pigeon That Saved 194 Soldiers 🕊️ #Shorts
```

Açıklama:

- İlk cümlede olayın kısa özeti.
- İkinci cümlede merak veya duygusal sonuç.
- 3-5 alakalı hashtag; gereksiz etiket yığını kullanılmaz.

Etiket örneği:

```text
Shorts, History, Amazing Facts, Historical Facts, WWI
```

## 8. Yükleme standardı

- Video kalite kontrolünü geçmeden `public` olarak yüklenmez.
- Yükleme için proje kökündeki `youtube_upload.py`, `client_secret.json` ve `youtube_token.json` kullanılır.
- Kimlik bilgileri veya token içerikleri hiçbir rapora, komuta, belgeye ya da çıktıya yazılmaz.
- Yükleme sonrasında Shorts URL'si ve YouTube oEmbed başlığı doğrulanır.
- Başlık, açıklama ve etiketler yüklemeden önce son kez kontrol edilir.

Örnek:

```bash
./venv/Scripts/python.exe youtube_upload.py "<VIDEO_PATH>" \
  --title "<TITLE>" \
  --description "<DESCRIPTION>" \
  --tags "<COMMA-SEPARATED TAGS>" \
  --privacy public
```

## 9. Bu stile ait referans video

- Konu: Cher Ami — I. Dünya Savaşı'nda 194 askerin kurtarılmasına yardım eden taşıyıcı güvercin.
- Süre: Yaklaşık 39 saniye.
- Referans özellikler: İngilizce anlatım, hızlı kurgu, 9:16, yüksek kontrastlı altyazı, duygusal tarih hikâyesi.
- Korunacak yönler: Süre, anlatım temposu, ses, altyazı görünümü ve merak odaklı tarih formatı.
- İyileştirilecek yön: Her anlatım cümlesine daha doğrudan karşılık veren dönem ve olay görüntüleri kullanılacak; videonun tamamı yalnızca genel güvercin görüntülerine dayandırılmayacak.

## 10. Nihai kural

Her yeni videoda öncelik sırası şöyledir:

1. Doğru ve ilgi çekici konu.
2. İlk 2 saniyede güçlü kanca.
3. Anlatım ile birebir uyumlu görseller.
4. Akıcı İngilizce ses ve okunabilir altyazı.
5. Telif güvenliği.
6. Teknik kalite ve yayın sonrası doğrulama.

Bu kontroller tamamlanmadan video bitmiş kabul edilmez.
