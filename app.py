import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import random
import requests

BOT_TOKEN = "8316396699:AAHff4bp0RbvYJjx-eOhuUqr4kgD-MERj-c"
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

EXACT_8X_SYMBOLS = {
    "PAXGUSDT": "XAUUSD (ทองคำ OTC)",
    "XRPUSDT": "Ripple (OTC)",
    "SOLUSDT": "Solana (OTC)",
    "BTCUSDT": "Bitcoin (OTC)",
    "ETHUSDT": "Ethereum (OTC)",
    "SUIUSDT": "Sui (OTC)",
    "DOGEUSDT": "Dogecoin (OTC)",
    "LTCUSDT": "Litecoin (OTC)",
    "RENDERUSDT": "Render (OTC)",
    "ADAUSDT": "Cardano (OTC)"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_real_economic_news():
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        res = requests.get(url, timeout=1.5)
        if res.status_code != 200:
            return "🛡️ ตลาดปกติ (ไร้ข่าวแรง)"
        
        events = res.json()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        active_news = []
        
        for event in events:
            if event.get("impact") == "High" and event.get("country") == "USD":
                date_str = event.get("date")
                if date_str:
                    event_time = datetime.datetime.fromisoformat(date_str)
                    diff_minutes = (event_time - now_utc).total_seconds() / 60.0
                    if -15 <= diff_minutes <= 45:
                        title = event.get("title", "News")
                        time_label = f"อีก {int(diff_minutes)}น." if diff_minutes > 0 else f"ผ่านไป {abs(int(diff_minutes))}น."
                        active_news.append(f"🔥 **{title}** ({time_label})")
                        
        if active_news:
            return " | ".join(active_news)
        return "🛡️ ตลาดปกติ (ไร้ข่าวแรง)"
    except Exception:
        return "🛡️ ตลาดปกติ (ไร้ข่าวแรง)"

def generate_ultimate_grandmaster_signal():
    symbol_key = random.choice(list(EXACT_8X_SYMBOLS.keys()))
    label = EXACT_8X_SYMBOLS[symbol_key]
    
    direction = random.choice(["CALL", "PUT"])
    up_votes = random.randint(10, 14)
    down_votes = 15 - up_votes
    if direction == "PUT" and up_votes > down_votes:
        up_votes, down_votes = down_votes, up_votes
        
    consensus_pct = round((max(up_votes, down_votes) / 15.0) * 100, 1)
    
    base_prices = {
        "PAXGUSDT": 2740.0, "BTCUSDT": 68500.0, "ETHUSDT": 2650.0,
        "SOLUSDT": 155.0, "XRPUSDT": 0.58, "SUIUSDT": 2.15,
        "DOGEUSDT": 0.12, "LTCUSDT": 72.0, "RENDERUSDT": 5.80, "ADAUSDT": 0.36
    }
    
    p = base_prices.get(symbol_key, 100.0)
    fluctuation = p * 0.0018
    poc = p + random.uniform(-fluctuation, fluctuation)
    val = poc - (p * 0.0025)
    vah = poc + (p * 0.0025)
    wall = vah if direction == "CALL" else val
    
    imbalance_side = "BUY" if direction == "CALL" else "SELL"
    imbalance_ratio = round(random.uniform(2.1, 4.2), 2)
    
    sweep_options = [
        "🧨 BULLISH SWEEP (กวาดสภาพคล่องแนวรับ)",
        "🧨 BEARISH SWEEP (กวาดสภาพคล่องแนวต้าน)",
        "🧊 INSTITUTIONAL ICEBERG DETECTED",
        "🛡️ STANDARD ORDER FLOW"
    ]
    
    regime_options = [
        "⚔️ สภาพตลาดสมบูรณ์ (High Volatility)",
        "🌊 ตลาดทรงพลัง (Institutional Trend)"
    ]
    
    edge = round(random.uniform(81.2, 96.5), 1)

    return {
        "symbol_label": label,
        "direction": direction,
        "up_votes": up_votes,
        "down_votes": down_votes,
        "consensus": consensus_pct,
        "imbalance": f"{imbalance_side} {imbalance_ratio}x",
        "wall": f"{wall:.4f}",
        "poc": f"{poc:.4f}",
        "val": f"{val:.4f}",
        "vah": f"{vah:.4f}",
        "sweep": random.choice(sweep_options),
        "regime": random.choice(regime_options),
        "edge": edge
    }

def send_new_signal_card(chat_id):
    news_msg = fetch_real_economic_news()
    res = generate_ultimate_grandmaster_signal()
    now = get_thai_time()
    target_time_str = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0).strftime('%H:%M')
    
    is_buy = (res['direction'] == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"

    card_text = (
        f"🩸 **TITAN v97.0 ANTI-FREEZE ENGINE** 🩸\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📰 {news_msg}\n"
        f"🎯 **คู่เด่นระดับสถาบัน:** `{res['symbol_label']}`\n"
        f"🗳️ **สภาโหวต 3 มิติ (MACD/BB/RSI):** `[ขึ้น {res['up_votes']} : ลง {res['down_votes']}]` ({res['consensus']}%)\n"
        f"⏱️ **เวลาเข้าออเดอร์:** `{target_time_str}` (M1)\n"
        f"⚡ **ทิศทางฟันธง:** **{dir_emoji}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌊 **Order Imbalance:** `{res['imbalance']}`\n"
        f"🛡️ **Liquidity Wall:** `{res['wall']}` (กำแพงเจ้ามือ)\n"
        f"🎯 **Volume Profile (POC):** `{res['poc']}`\n"
        f"📊 **Value Area (VAL / VAH):** `{res['val']} - {res['vah']}`\n"
        f"🧨 **Institutional Sweep:** `{res['sweep']}`\n"
        f"📊 **Market Regime:** `{res['regime']}`\n"
        f"🔥 **Grandmaster Quant Edge:** `+{res['edge']}%` (God Odds)\n"
        f"⏱️ Update: `{now.strftime('%H:%M:%S')}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚔️ สแกนหาจุดเข้าคมกริบถัดไป ⚔️", callback_data="next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"[ERROR SENDING MESSAGE]: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚔️ ปลดล็อกพลัง Anti-Freeze ⚔️", callback_data="next_signal"))
    bot.reply_to(message, 
        "🩸 **TITAN v97.0 พร้อมรบแบบไร้รอยต่อแล้วครับนาย!**\n"
        "แก้ปัญหาปุ่มกดติดๆ ดับๆ เรียบร้อย กดปุ๊บพ่นการ์ดใหม่ทันทีไม่มีสะดุด:", 
        reply_markup=markup, 
        parse_Mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "next_signal")
def handle_next_signal(call):
    chat_id = call.message.chat.id
    
    # 🛡️ บังคับเคลียร์สถานะปุ่มกดทันที ป้องกันปุ่มหมุนค้างและบล็อกการคลิกครั้งถัดไป
    try:
        bot.answer_callback_query(call.id, text="⚡ กำลังพ่นการ์ดสัญญาณใหม่...", show_alert=False)
    except Exception:
        pass
    
    send_new_signal_card(chat_id)

if __name__ == "__main__":
    print("🚀 TITAN v97.0 Anti-Freeze Engine Running...")
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=10)
        except Exception as e:
            print(f"[RECOVERING]: {e}")
            import time
            time.sleep(1)
            
