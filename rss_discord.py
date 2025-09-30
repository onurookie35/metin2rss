import feedparser
import requests
import json
import os
from datetime import datetime

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

def send_to_discord(webhook_url, title, entry):
    """Discord'a mesaj gönder"""
    import re
    from html import unescape
    import time
    
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
            print(f"✅ Mesaj gönderildi: {entry_title}")
            # Discord rate limit için kısa bekleme
            time.sleep(1)
            return True
        else:
            print(f"❌ Hata: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ İstek hatası: {e}")
        return False

def check_rss_feeds():
    """RSS beslemelerini kontrol et ve yeni içerikleri gönder"""
    last_entries = load_last_entries()
    updated = False
    
    for feed_config in RSS_FEEDS:
        rss_url = feed_config["url"]
        webhook_url = feed_config["webhook"]
        feed_title = feed_config["title"]
        
        if not webhook_url:
            print(f"⚠️ {feed_title} için webhook bulunamadı, atlanıyor...")
            continue
        
        print(f"\n🔍 {feed_title} kontrol ediliyor...")
        print(f"RSS URL: {rss_url}")
        
        try:
            # RSS beslemesini parse et
            feed = feedparser.parse(rss_url)
            
            if not feed.entries:
                print(f"⚠️ {feed_title} için hiç entry bulunamadı")
                continue
            
            # Bu RSS kaynağı için daha önce gönderilen entry ID'lerini al
            sent_entry_ids = last_entries.get(rss_url, [])
            
            # Eğer liste değilse (eski format), listeye çevir
            if not isinstance(sent_entry_ids, list):
                sent_entry_ids = [sent_entry_ids] if sent_entry_ids else []
            
            # Yeni entry'leri bul
            new_entries = []
            for entry in feed.entries:
                entry_id = entry.get('id', entry.get('link', ''))
                if entry_id and entry_id not in sent_entry_ids:
                    new_entries.append(entry)
            
            if new_entries:
                print(f"🆕 {len(new_entries)} adet yeni içerik bulundu!")
                
                # Yeni entry'leri eski tarihten yeniye doğru sırala
                # (RSS feed'ler genelde yeni -> eski sıralıdır, biz tersini istiyoruz)
                new_entries.reverse()
                
                # Tüm yeni entry'leri gönder
                successfully_sent = []
                for entry in new_entries:
                    entry_id = entry.get('id', entry.get('link', ''))
                    entry_title = entry.get('title', 'Başlık yok')
                    
                    print(f"📤 Gönderiliyor: {entry_title}")
                    
                    if send_to_discord(webhook_url, feed_title, entry):
                        successfully_sent.append(entry_id)
                
                # Başarıyla gönderilen entry'leri kaydet
                if successfully_sent:
                    # Yeni gönderilen ID'leri mevcut listeye ekle
                    sent_entry_ids.extend(successfully_sent)
                    
                    # Son 50 entry ID'sini sakla (fazla büyümesini önlemek için)
                    if len(sent_entry_ids) > 50:
                        sent_entry_ids = sent_entry_ids[-50:]
                    
                    last_entries[rss_url] = sent_entry_ids
                    updated = True
                    
                    print(f"✅ {len(successfully_sent)} adet içerik başarıyla gönderildi")
            else:
                print(f"ℹ️ Yeni içerik yok")
                
        except Exception as e:
            print(f"❌ RSS işleme hatası ({feed_title}): {e}")
            continue
    
    # Eğer herhangi bir güncelleme olduysa kaydet
    if updated:
        save_last_entries(last_entries)
        print("\n💾 Son entry'ler kaydedildi")
    else:
        print("\n✨ Hiçbir yeni içerik bulunamadı")

if __name__ == "__main__":
    print("=" * 50)
    print("RSS to Discord Bot Başlatılıyor...")
    print(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    check_rss_feeds()
    print("\n" + "=" * 50)
    print("Bot çalışması tamamlandı")
    print("=" * 50)
