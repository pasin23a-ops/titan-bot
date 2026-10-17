import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# 🚀 ใส่ Token จริงพร้อมใช้งานเรียบร้อย
BOT_TOKEN = "8316396699:AAHff4bp0RbvYJjx-eOhuUqr4kgD-MERj-c"
bot = telebot.TeleBot(BOT_TOKEN)

last_sent_symbol = {}

# 🌐 รายชื่อสินทรัพย์ที่ Binance API รองรับจริง
EXACT_8X_SYMBOLS = {
    "BTCUSDT": "BTC/USD (Proxy/Binance)",
    "ETHUSDT": "ETH/USD (Proxy/Binance)",
    "SOLUSDT": "SOL/USD (Proxy/Binance)",
    "XRPUSDT": "Ripple (Proxy/Binance)",
    "LTCUSDT": "Litecoin (Proxy/Binance)",
    "SHIBUSDT": "SHIB/USD (Proxy/Binance)",
    "SUIUSDT": "Sui (Proxy/Binance)",
    "XAUUSDT": "XAUUSD (Proxy/Binance)",
    "XAGUSDT": "XAGUSD (Proxy/Binance)",
    "GASUSDT": "แก๊สธรรมชาติ (Proxy/Binance)",
    "EURUSD_OTC": "EUR/USD (Proxy/Binance)",
    "NKEUSDT": "Nike, Inc. (Proxy/Binance)",
    "SNAPUSDT": "Snap Inc. (Proxy/Binance)",
    "MCDUSDT": "McDonald's Corp... (Proxy/Binance)",
    "INTCUSDT": "Intel Corporation... (Proxy/Binance)"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval="1m", limit=60):
    binance_symbol = symbol.replace("_OTC", "") 
    endpoints = [
        f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={limit}",
        f"https://api.binance.us/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={limit}"
    ]
    for url in endpoints:
        try:
            res = requests.get(url, timeout=1.2)
            if res.status_code == 200:
                raw = res.json()
                df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
        except Exception:
            continue
    print(f"[API Warning] ไม่สามารถดึงข้อมูลสำหรับ symbol: {symbol}")
    return None

def analyze_symbol_pro(sym):
    df1 = fetch_kline(symbol=sym, interval="1m", limit=60)
    if df1 is None or len(df1) < 50:
        return None

    # M5 ใช้แท่งปิดแล้ว (Closed Bar: iloc[-2]) เพื่อความเสถียร ไม่ Repainting
    df5 = fetch_kline(symbol=sym, interval="5m", limit=30)
    m5_trend = "NEUTRAL"
    if df5 is not None and len(df5) >= 20:
        m5_ema20 = df5['close'].ewm(span=20, adjust=False).mean()
        m5_close_closed = df5['close'].iloc[-2]
        m5_ema_closed = m5_ema20.iloc[-2]
        m5_trend = "UP" if m5_close_closed > m5_ema_closed else "DOWN"

    ema12 = df1['close'].ewm(span=12, adjust=False).mean()
    ema26 = df1['close'].ewm(span=26, adjust=False).mean()
    ppo_line = ((ema12 - ema26) / ema26) * 100
    current_ppo = float(ppo_line.iloc[-2])

    sma20 = df1['close'].rolling(window=20).mean()
    std20 = df1['close'].rolling(window=20).std()
    upper_band = sma20 + (std20 * 2)
    lower_band = sma20 - (std20 * 2)
    band_width = float((upper_band.iloc[-2] - lower_band.iloc[-2]) / sma20.iloc[-2])

    c1, o1, h1, l1 = float(df1['close'].iloc[-2]), float(df1['open'].iloc[-2]), float(df1['high'].iloc[-2]), float(df1['low'].iloc[-2])
    c2, o2 = float(df1['close'].iloc[-3]), float(df1['open'].iloc[-3])
    c3, o3 = float(df1['close'].iloc[-4]), float(df1['open'].iloc[-4])

    rng1 = h1 - l1
    if rng1 == 0:
        return None

    body1 = abs(c1 - o1)
    body_ratio = body1 / rng1
    ppo_distance = abs(current_ppo)

    direction = "CALL" if current_ppo > 0 else "PUT"

    # Heuristic Index Score (ไม่ใช่ความน่าจะเป็น %)
    base_score = (ppo_distance * 30) + (body_ratio * 40)

    if direction == "CALL" and (c1 > o1) and (c2 > o2) and (c3 > o3):
        base_score += 20
    elif direction == "PUT" and (c1 < o1) and (c2 < o2) and (c3 < o3):
        base_score += 20

    if (direction == "CALL" and m5_trend == "UP") or (direction == "PUT" and m5_trend == "DOWN"):
        base_score += 15
    elif (direction == "CALL" and m5_trend == "DOWN") or (direction == "PUT" and m5_trend == "UP"):
        base_score -= 15

    if band_width > 0.001:
        base_score += 10

    return {
        "symbol": sym,
        "direction": direction,
        "ppo": current_ppo,
        "m5_trend": m5_trend,
        "bandwidth": round(band_width, 5),
        "score": round(base_score, 2)
    }

def generate_fast_signal(chat_id):
    symbol_keys = list(EXACT_8X_SYMBOLS.keys())
    total_symbols = len(symbol_keys)
    valid_results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=total_symbols) as executor:
        futures = {executor.submit(analyze_symbol_pro, sym): sym for sym in symbol_keys}
        for future in as_completed(futures):
            if time.time() - start_time > 8.5:
                break
            try:
                res = future.result()
                if res is not None:
                    valid_results.append(res)
            except Exception:
                continue
    
    success_count = len(valid_results)

    if not valid_results:
        no_signal_text = (
            f"🛡️ **TITAN 8X PRO (v80.0)** 🛡️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 **สถานะข้อมูล:** `สำเร็จ 0/{total_symbols} สินทรัพย์`\n"
            f"⚠️ **คำแนะนำ:** `ไม่พบผลวิเคราะห์ที่พร้อมใช้งานในรอบนี้`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👇 *กดปุ่มด้านล่างเพื่อลองสแกนใหม่อีกครั้ง*"
        )
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("🔄 ลองสแกนใหม่อีกครั้ง (PRO ENGINE)", callback_data="request_next_signal"))
        try:
            bot.send_message(chat_id, no_signal_text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass
        return

    last_sym = last_sent_symbol.get(chat_id, "")
    filtered_results = [r for r in valid_results if r['symbol'] != last_sym]
    if not filtered_results:
        filtered_results = valid_results

    best_res = max(filtered_results, key=lambda x: x['score'])
    best_sym = best_res['symbol']
    best_dir = best_res['direction']
    best_ppo = best_res['ppo']
    best_score = best_res['score']
    best_trend = best_res['m5_trend']

    last_sent_symbol[chat_id] = best_sym
    label = EXACT_8X_SYMBOLS.get(best_sym, best_sym)
    
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    target_time_str = target_time.strftime('%H:%M')
    
    is_buy = (best_dir == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    btn_label = "CALL" if is_buy else "PUT"
    trend_display = "📈 ขาขึ้น (Bullish)" if best_trend == "UP" else ("📉 ขาลง (Bearish)" if best_trend == "DOWN" else "⚖️ ไซด์เวย์")

    card_text = (
        f"👑 **TITAN 8X PRO FILTER (v80.0)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **ความสำเร็จข้อมูล:** `ดึงสำเร็จ {success_count}/{total_symbols} สินทรัพย์`\n"
        f"🎯 **คู่ผ่านการคัดกรองสูงสุด:** `{label}`\n"
        f"📊 **ค่า PPO (Closed Bar):** `{best_ppo:.2f}`\n"
        f"🌐 **เทรนด์ใหญ่ M5 (Closed Bar):** `{trend_display}`\n"
        f"⏱️ **เวลาเป้าหมายอ้างอิง:** `{target_time_str}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"⭐ **Heuristic Index Score:** `{best_score}` (ไม่ใช่เปอร์เซ็นต์ความแม่นยำ)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *กดปุ่มด้านล่างเพื่อขอสัญญาณสดรอบถัดไป*"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณสดทันใจ (PRO ENGINE)", callback_data="request_next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Send Error: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อสแกนรอบแรก (v80.0)", callback_data="request_next_signal"))
    
    bot.reply_to(
        message, 
        "🚀 **TITAN v80.0 PRODUCTION ARCHITECTURE ACTIVATED** 🚀\n"
        "สถาปัตยกรรมสมบูรณ์แบบ: แยกสถิติความสำเร็จการดึงข้อมูล (Success/Total) และพร้อมลุยแล้ว!", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ v80.0 Active")
        return
        
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "⚡ กำลังประมวลผลข้อมูลตลาดจริง...")
        generate_fast_signal(chat_id)
        return

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
