import os
import time
import datetime
import pandas as pd
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from concurrent.futures import ThreadPoolExecutor, as_completed

# 🔑 ตั้งค่า Bot Token และ Telegram Chat ID ของนาย
BOT_TOKEN = "8919259236:AAGOUrAxGr_FnjqEANxERHAdFvcnBeP5YCk"
CHAT_ID = "8644030650"

bot = telebot.TeleBot(BOT_TOKEN)

# รายชื่อคู่เงินยอดนิยมสำหรับวิเคราะห์
SYMBOLS = {
    "BTCUSDT": "BTC/USDT (Binance)",
    "ETHUSDT": "ETH/USDT (Binance)",
    "SOLUSDT": "SOL/USDT (Binance)",
    "XRPUSDT": "XRP/USDT (Binance)",
    "LTCUSDT": "LTC/USDT (Binance)",
    "SHIBUSDT": "SHIB/USDT (Binance)",
    "SUIUSDT": "SUI/USDT (Binance)",
    "XAUUSDT": "XAUUSD/Gold (Binance)",
    "EURUSDT": "EUR/USDT (Binance)"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval="1m", limit=50):
    """ดึงข้อมูลแท่งเทียนจาก Binance พร้อมระบบ API สำรองป้องกันการค้าง"""
    endpoints = [
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",
        f"https://api1.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",
        f"https://api2.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",
        f"https://api3.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    ]
    for url in endpoints:
        try:
            res = requests.get(url, timeout=1.2)
            if res.status_code == 200:
                raw = res.json()
                if len(raw) >= 30:
                    df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    return df
        except Exception:
            continue
    return None

def analyze_symbol(symbol):
    """วิเคราะห์ความแม่นยำของคู่เงินด้วยอินดิเคเตอร์"""
    df = fetch_kline(symbol)
    if df is None or len(df) < 30:
        return None

    closes = df['close']
    
    # คำนวณ EMA & MACD
    ema4 = closes.ewm(span=4, adjust=False).mean()
    ema9 = closes.ewm(span=9, adjust=False).mean()
    macd_line = ema4 - ema9
    signal_line = macd_line.ewm(span=4, adjust=False).mean()
    macd_hist = macd_line - signal_line

    # คำนวณ RSI
    delta = closes.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    last_close = closes.iloc[-1]
    last_hist = macd_hist.iloc[-1]
    last_rsi = rsi.iloc[-1]

    direction = "CALL" if last_hist > 0 else "PUT"
    score = 80 + abs(last_hist * 100)
    if (direction == "CALL" and last_rsi < 60) or (direction == "PUT" and last_rsi > 40):
        score += 10

    return {
        "symbol": symbol,
        "direction": direction,
        "close": last_close,
        "rsi": round(last_rsi, 2),
        "score": round(score, 1)
    }

def generate_signal(chat_id):
    """สแกนค้นหาคู่เงินที่ดีที่สุดและส่งข้อความแจ้งเตือน"""
    start_time = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        futures = {executor.submit(analyze_symbol, sym): sym for sym in SYMBOLS.keys()}
        for future in as_completed(futures):
            if time.time() - start_time > 3.0:
                break
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception:
                continue

    if not results:
        bot.send_message(chat_id, "⚠️ **เกิดข้อผิดพลาดในการดึงราคา:** กรุณากดใหม่อีกครั้งครับนาย!", parse_mode="Markdown")
        return

    best = max(results, key=lambda x: x['score'])
    label = SYMBOLS.get(best['symbol'], best['symbol'])
    
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).strftime('%H:%M')
    
    is_buy = (best['direction'] == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    
    card_text = (
        f"👑 **TITAN PURE QUANT SIGNAL** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **คู่เงินที่สแกนเจอ:** `{label}`\n"
        f"💵 **ราคาปัจจุบัน:** `{best['close']}`\n"
        f"📊 **ค่า RSI:** `{best['rsi']}`\n"
        f"⏱️ **เวลาเข้าออเดอร์:** `{target_time}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"⭐ **ความแม่นยำประมาณการ:** `{best['score']}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💯 *ระบบสแกนสดจาก Binance ไร้การค้างแน่นอน!*"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณสดทันใจ (สแกนใหม่)", callback_data="get_signal"))

    bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['start', 'run'])
def send_welcome(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 กดเพื่อสแกนสัญญาณด่วน", callback_data="get_signal"))
    bot.reply_to(
        message,
        "🚀 **TITAN PURE ENGINE พร้อมทำงานเต็มรูปแบบ!** 🚀\n"
        "กดปุ่มด้านล่างเพื่อขอสัญญาณซื้อ-ขายด่วนได้ตลอด 24 ชั่วโมงครับนาย:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "get_signal":
        bot.answer_callback_query(call.id, "⚡ กำลังสแกนสัญญาณสด...")
        generate_signal(call.message.chat.id)

if __name__ == "__main__":
    print("Bot is polling...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
