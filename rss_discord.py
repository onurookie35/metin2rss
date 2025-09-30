import feedparser
import requests
import json
import os
from datetime import datetime, timedelta
import time

# RSS Kaynaklarınızı ve Webhook'larınızı buraya ekleyin
# BURAYA KENDİ RSS URL'LERİNİZİ VE BAŞLIKLARINIZI GİRİN:
RSS_FEEDS = [
    {
        "url": "https://board.tr.metin2.gameforge.com/index.php?board-feed/809/",
        "webhook": os.environ.get("WEBHOOK_1"),
        "title": "🏷️ Happy Hour"
    },
    {
        "url": "https://board.tr.metin2.gameforge.com/index.php?board-feed/764/",
        "webhook": os.environ.get("WEBHOOK_2"),
        "title": "💸 Nesne Market"
    },
    {
        "url": "https://board.tr.metin2.gameforge.com/index.php?board-feed/688/",
        "webhook": os.environ.get("WEBHOOK_3"),
        "title": "🎟️ Oyun Event"
    },
    {
        "url": "https://board.tr.metin2.gameforge.com/index.php?board-feed/910/",
        "webhook": os.environ.get("WEBHOOK_4"),
        "title": "🔧 Bakım ve Sunucu"
    }
]

LAST_ENTRIES_FILE = "last_entries.json"
MAX_ENTRIES_TO_SEND = 2  # Maksimum gönderilecek entry sayısı
HOURS_THRESHOLD = 24  # Entry kaç saat içinde yayınlanmış olmalı (24 saat = 1 gün)

def load_last_entries():
    """Son gönderilen RSS entry ID'lerini yükle"""
    if os.path.exists(LAST_ENTRIES_FILE):
        with open(LAST_ENTRIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_last_entries(entries):
    """Son gönderilen RSS entry ID'lerini kaydet"""
    with open(LAST_ENTRIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

def is_entry_recent(entry, hours=HOURS_THRESHOLD):
    """Entry'nin yayın tarihini kontrol et - belirtilen saat içinde mi?"""
    try:
        # Entry'den tarih bilgisini al
        published_parsed = entry.get('published_parsed')
        if not published_parsed:
            # Eğer published_parsed yoksa, string halini parse etmeyi dene
            return True  # Tarih bulunamazsa güvenli tarafta kalıp gönder
        
        # Tuple'ı datetime'a çevir
        published_date = datetime(*published_parsed[:6])
        
        # Şu anki zamanı al
        now = datetime.now()
        
        # Farkı hesapla
        time_diff = now - published_date
        
        # Belirtilen saat içinde mi kontrol et
        is_recent = time_diff.total_seconds() <= (hours * 3600)
        
        if not is_recent:
            print(f"  ⏰ Eski entry (>{hours} saat önce yayınlanmış): {entry.get('title', 'Başlık yok')}")
        
        return is_recent
        
    except Exception as e:
        print(f"  ⚠️ Tarih kontrolü hatası: {e}")
        return True  # Hata durumunda güvenli tarafta kalıp gönder

def send_to_discord(webhook_url, title, entry):
    """Discord'a mesaj gönder"""
    import re
    from html import unescape
    
    # Entry bilgilerini al
    entry_title = entry.get('title', 'Başlık yok')
    entry_link = entry.get('link', '')
    entry_summary = entry.get('summary', entry.get('description', ''))
    
    # HTML etiketlerini temizle
    entry_summary = re.sub('<.*?>', '', entry_summary)
    # HTML özel karakterlerini çevir (&nbsp; vb.)
    entry_summary = unescape(entry_summary)
    # Fazla boşlukları temizle
    entry_summary = re.sub(r'\s+', ' ', entry_summary).strip()
    
    # Özeti kısalt (Discord 4096 karakter limiti var, ama 500'de keselim)
    if len(entry_summary) > 500:
        entry_summary = entry_summary[:500] + "..."
    
    # Eğer özet boşsa, kısa bir mesaj ekle
    if not entry_summary or len(entry_summary.strip()) == 0:
        entry_summary = "İçerik detayları için linke tıklayın."
    
    # Yayın tarihini al
    published = entry.get('published', 'Tarih belirtilmemiş')
    
    # Discord embed mesajı oluştur
    embed = {
        "title": entry_title[:256],  # Discord embed title limiti 256 karakter
        "description": entry_summary,
        "url": entry_link,
        "color": 5814783,  # Mavi renk
        "footer": {
            "text": f"Yayın Tarihi: {published}"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # @everyone mention ile mesaj gönder
    payload = {
        "content": f"@everyone\n\n**{title}**",
        "embeds": [embed]
    }
    
    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 204:
            print(f"  ✅ Mesaj gönderildi: {entry_title}")
            # Discord rate limit için kısa bekleme
            time.sleep(1)
            return True
        else:
            print(f"  ❌ Hata: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"  ❌ İstek hatası: {e}")
        return False

def check_rss_feeds():
    """RSS beslemelerini kontrol et ve yeni içerikleri gönder"""
    last_entries = load_last_entries()
    updated = False
    
    # Tüm aktif RSS URL'lerini topla
    active_rss_urls = [feed["url"] for feed in RSS_FEEDS]
    
    # Artık kullanılmayan RSS feed'lerini sil
    removed_feeds = []
    for saved_url in list(last_entries.keys()):
        if saved_url not in active_rss_urls:
            removed_feeds.append(saved_url)
            del last_entries[saved_url]
            updated = True
    
    if removed_feeds:
        print(f"\n🗑️ Kaldırılan RSS feed'leri: {len(removed_feeds)}")
        for removed in removed_feeds:
            print(f"  - {removed}")
    
    for feed_config in RSS_FEEDS:
        rss_url = feed_config["url"]
        webhook_url = feed_config["webhook"]
        feed_title = feed_config["title"]
        
        if not webhook_url:
            print(f"\n⚠️ {feed_title} için webhook bulunamadı, atlanıyor...")
            continue
        
        print(f"\n🔍 {feed_title} kontrol ediliyor...")
        print(f"  RSS URL: {rss_url}")
        
        try:
            # RSS beslemesini parse et
            feed = feedparser.parse(rss_url)
            
            if not feed.entries:
                print(f"  ⚠️ Hiç entry bulunamadı")
                continue
            
            # Bu RSS kaynağı için son kontrol edilen entry ID'sini al
            last_entry_id = last_entries.get(rss_url)
            
            # Yeni entry'leri bul (son kaydedilen entry'ye kadar)
            new_entries = []
            for entry in feed.entries:
                entry_id = entry.get('id', entry.get('link', ''))
                
                # Eğer son kaydedilen entry'ye ulaştıysak dur
                if entry_id == last_entry_id:
                    break
                
                # Entry'nin tarihini kontrol et - güncel mi?
                if is_entry_recent(entry):
                    new_entries.append(entry)
                else:
                    # Eski entry'lere ulaştık, aramayı durdur
                    break
            
            if new_entries:
                # Maksimum 2 entry gönder (en yeniden başlayarak)
                entries_to_send = new_entries[:MAX_ENTRIES_TO_SEND]
                
                print(f"  🆕 {len(new_entries)} adet yeni içerik bulundu (en fazla {MAX_ENTRIES_TO_SEND} tanesi gönderilecek)")
                
                # new_entries zaten yeni->eski sıralı, aynen kullan (en yeni önce gönderilecek)
                
                # Tüm yeni entry'leri gönder
                successfully_sent = []
                for entry in entries_to_send:
                    entry_id = entry.get('id', entry.get('link', ''))
                    entry_title = entry.get('title', 'Başlık yok')
                    
                    print(f"  📤 Gönderiliyor: {entry_title}")
                    
                    if send_to_discord(webhook_url, feed_title, entry):
                        successfully_sent.append(entry_id)
                
                # Başarıyla gönderilen entry'leri kaydet
                if successfully_sent:
                    # En son (en yeni) entry'nin ID'sini kaydet
                    latest_entry_id = feed.entries[0].get('id', feed.entries[0].get('link', ''))
                    last_entries[rss_url] = latest_entry_id
                    updated = True
                    
                    print(f"  ✅ {len(successfully_sent)} adet içerik başarıyla gönderildi")
            else:
                print(f"  ℹ️ Yeni içerik yok")
                
        except Exception as e:
            print(f"  ❌ RSS işleme hatası: {e}")
            continue
    
    # Eğer herhangi bir güncelleme olduysa kaydet
    if updated:
        save_last_entries(last_entries)
        print("\n💾 Veriler kaydedildi")
    else:
        print("\n✨ Hiçbir yeni içerik bulunamadı")

if __name__ == "__main__":
    print("=" * 50)
    print("RSS to Discord Bot Başlatılıyor...")
    print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Ayarlar: Maks {MAX_ENTRIES_TO_SEND} entry, Son {HOURS_THRESHOLD} saat içindekiler")
    print("=" * 50)
    check_rss_feeds()
    print("\n" + "=" * 50)
    print("Bot çalışması tamamlandı")
    print("=" * 50)
