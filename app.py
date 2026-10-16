import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

BOT_TOKEN = "8316396699:AAHff4bp0RbvYJjx-eOhuUqr4kgD-MERj-c"
bot = telebot.TeleBot(BOT_TOKEN)

active_chat_ids = set()
last_sent_symbol = {}

# 22 คู่ OTC เกรดพรีเมียม เปิดตลอด 24 ชม.
EXACT_8X_SYMBOLS = {
    "BTCUSDT": "BTC/USD (OTC)",
    "ETHUSDT": "ETH/USD (OTC)",
    "SOLUSDT": "SOL/USD (OTC)",
    "XRPUSDT": "Ripple (OTC)",
    "LTCUSDT": "Litecoin (OTC)",
    "SHIBUSDT": "SHIB/USD (OTC)",
    "SUIUSDT": "Sui (OTC)",
    "XAUUSDT": "XAUUSD (OTC)",
    "XAGUSDT": "XAGUSD (OTC)",
    "GASUSDT": "แก๊สธรรมชาติ (OTC)",
    "GBPJPY_OTC": "GBP/JPY (OTC)",
    "AUDJPY_OTC": "AUD/JPY (OTC)",
    "AUDUSD_OTC": "AUD/USD (OTC)",
    "EURUSD_OTC": "EUR/USD (OTC)",
    "EURJPY_OTC": "EUR/JPY (OTC)",
    "EURGBP_OTC": "EUR/GBP (OTC)",
    "GBPCAD_OTC": "GBP/CAD (OTC)",
    "USDCHF_OTC": "USD/CHF (OTC)",
    "NKEUSDT": "Nike, Inc. (OTC)",
    "SNAPUSDT": "Snap Inc. (OTC)",
    "MCDUSDT": "McDonald's Corp... (OTC)",
    "INTCUSDT": "Intel Corporation... (OTC)"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval="1m", limit=60):
    binance_symbol = symbol.replace("_OTC", "=X") if "_OTC" in symbol else symbol
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
    return None

def analyze_single_symbol(sym):
    df = fetch_kline(symbol=sym, interval="1m", limit=60)
    if df is None or len(df) < 50:
        return None

    # เกราะที่ 1: กรองกราฟนิ่ง / สเปรดกระชาก
    recent_range = df['high'].iloc[-5:] - df['low'].iloc[-5:]
    if (recent_range == 0).all():
        return None

    c1 = float(df['close'].iloc[-2])
    o1 = float(df['open'].iloc[-2])
    h1 = float(df['high'].iloc[-2])
    l1 = float(df['low'].iloc[-2])

    c2 = float(df['close'].iloc[-3])
    o2 = float(df['open'].iloc[-3])

    # เกราะที่ 2: บังคับความหนาเนื้อเทียนต้อง ≥ 70% (Wick Guard ป้องกันไส้เทียนยาวหลอกตา)
    body = abs(c1 - o1)
    candle_range = h1 - l1
    body_ratio = (body / candle_range) if candle_range > 0 else 0
    if body_ratio < 0.70:
        return None

    # เกราะที่ 3: บังคับต่อเนื่อง 2 แท่งล่าสุดต้องไปในทิศทางเดียวกัน (ห้ามสลับฟันปลา)
    prev_is_green = (c2 > o2)
    curr_is_green = (c1 > o1)
    prev_is_red = (c2 < o2)
    curr_is_red = (c1 < o1)

    # คำนวณอินดิเคเตอร์เชิงลึก
    df['dinapoli'] = df['close'].ewm(span=8.3896, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    ema_fast = df['close'].ewm(span=6, adjust=False).mean()
    ema_slow = df['close'].ewm(span=14, adjust=False).mean()
    df['macd_hist'] = (ema_fast - ema_slow) - ema_fast.ewm(span=5, adjust=False).mean()
    
    df['resistance'] = df['high'].rolling(window=12).max()
    df['support'] = df['low'].rolling(window=12).min()
    
    din1 = float(df['dinapoli'].iloc[-2])
    ema50_1 = float(df['ema50'].iloc[-2])
    hist1 = float(df['macd_hist'].iloc[-2])
    hist2 = float(df['macd_hist'].iloc[-3])
    res1 = float(df['resistance'].iloc[-2])
    sup1 = float(df['support'].iloc[-2])

    score = 0
    direction = "NONE"

    # เกราะที่ 4: เงื่อนไข CALL ขั้นสูงสุด (ต้องเขียวติดต่อกัน + เหนือเส้นหลักทุกเส้น + MACD พุ่งแรง)
    if curr_is_green and prev_is_green and c1 > din1 and c1 > ema50_1 and c1 < (res1 * 0.9995):
        score += 40
        if hist1 > hist2 and hist1 > 0: score += 35
        if body_ratio > 0.80: score += 15
        if (c1 - din1) > (din1 * 0.0003): score += 10
        direction = "CALL"

    # เกราะที่ 5: เงื่อนไข PUT ขั้นสูงสุด (ต้องแดงติดต่อกัน + ใต้เส้นหลักทุกเส้น + MACD ดิ่งแรง)
    elif curr_is_red and prev_is_red and c1 < din1 and c1 < ema50_1 and c1 > (sup1 * 1.0005):
        score += 40
        if hist1 < hist2 and hist1 < 0: score += 35
        if body_ratio > 0.80: score += 15
        if (din1 - c1) > (din1 * 0.0003): score += 10
        direction = "PUT"

    # เกราะที่ 6: ตั้งกำแพงคะแนนความมั่นใจต้อง ≥ 90% เท่านั้นถึงจะปล่อยผ่าน
    if direction != "NONE" and score >= 90:
        return {
            "symbol": sym,
            "direction": direction,
            "score": score
        }
    return None

def generate_fast_signal(chat_id):
    symbol_keys = list(EXACT_8X_SYMBOLS.keys())
    valid_results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=len(symbol_keys)) as executor:
        futures = {executor.submit(analyze_single_symbol, sym): sym for sym in symbol_keys}
        for future in as_completed(futures):
            if time.time() - start_time > 8.5:
                break
            try:
                res = future.result(timeout=0.8)
                if res is not None:
                    valid_results.append(res)
            except Exception:
                continue
    
    if valid_results:
        last_sym = last_sent_symbol.get(chat_id, "")
        filtered_results = [r for r in valid_results if r['symbol'] != last_sym]
        
        if not filtered_results:
            filtered_results = valid_results
            
        best_res = max(filtered_results, key=lambda x: x['score'])
        best_sym = best_res['symbol']
        best_dir = best_res['direction']
        best_score = best_res['score']
    else:
        # เกราะที่ 7: ถ้ารอบไหนไม่มีคู่ไหนผ่านมาตรฐาน 90% บอทจะปฏิเสธการส่งสัญญาณเพื่อปกป้องเงินทุนทันที
        try:
            bot.send_message(
                chat_id, 
                "🛡️ **TITAN 8X FORTRESS (v62.0)** 🛡️\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ *ตรวจพบตลาดมีความผันผวนสูง หรือไม่มีคู่ไหนผ่านเกณฑ์ความปลอดภัยขั้นสูงสุด (Score < 90%)*\n\n"
                "🛑 **ระบบสั่งระงับการส่งสัญญาณรอบนี้เพื่อความปลอดภัยของทุนครับนาย!**\n"
                "━━━━━━━━━━━━━━━━━━━━━━", 
                parse_mode="Markdown"
            )
        except Exception:
            pass
        return

    last_sent_symbol[chat_id] = best_sym
    label = EXACT_8X_SYMBOLS.get(best_sym, best_sym)
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    target_time_str = target_time.strftime('%H:%M')
    
    is_buy = (best_dir == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    btn_label = "CALL" if is_buy else "PUT"

    card_text = (
        f"👑 **TITAN 8X ULTIMATE FORTRESS (v62.0)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **คู่เกรด S ที่ผ่านป้อมปราการ:** `{label}`\n"
        f"🛡️ **ระบบกรอง 7 ชั้น:** `Maximum Defense (Score ≥90%)`\n"
        f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"⭐ **ความคมชัดระบบ:** `{best_score}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *กดปุ่มด้านล่างเพื่อขอสัญญาณสดรอบถัดไป*"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณสดทันใจ (FORTRESS)", callback_data="request_next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Send Error: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อขอสัญญาณแรก (v62.0)", callback_data="request_next_signal"))
    
    bot.reply_to(
        message, 
        "🚀 **TITAN v62.0 ULTIMATE FORTRESS ACTIVATED** 🚀\n"
        "เปิดระบบป้อมปราการป้องกันความเสี่ยง 7 ชั้น บังคับเนื้อเทียน 70%+, ต่อเนื่อง 2 แท่ง, คะแนน 90%+ และมีระบบตัดใจไม่ส่งสัญญาณหากตลาดไม่ปลอดภัย พร้อมลุยครับนาย!", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ v62.0 Fortress Active")
        return
        
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "🛡️ ตรวจสอบป้อมปราการ 7 ชั้น...")
        generate_fast_signal(chat_id)
        return

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
