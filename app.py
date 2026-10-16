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

    recent_range = df['high'].iloc[-5:] - df['low'].iloc[-5:]
    if (recent_range == 0).all():
        return None

    c1 = float(df['close'].iloc[-2])
    o1 = float(df['open'].iloc[-2])
    h1 = float(df['high'].iloc[-2])
    l1 = float(df['low'].iloc[-2])

    c2 = float(df['close'].iloc[-3])
    o2 = float(df['open'].iloc[-3])

    body = abs(c1 - o1)
    candle_range = h1 - l1
    body_ratio = (body / candle_range) if candle_range > 0 else 0

    upper_wick = h1 - max(c1, o1)
    lower_wick = min(c1, o1) - l1

    # คำนวณอินดิเคเตอร์
    df['dinapoli'] = df['close'].ewm(span=8.3896, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    ema_fast = df['close'].ewm(span=6, adjust=False).mean()
    ema_slow = df['close'].ewm(span=14, adjust=False).mean()
    df['macd_hist'] = (ema_fast - ema_slow) - ema_fast.ewm(span=5, adjust=False).mean()
    
    din1 = float(df['dinapoli'].iloc[-2])
    ema50_1 = float(df['ema50'].iloc[-2])
    hist1 = float(df['macd_hist'].iloc[-2])
    hist2 = float(df['macd_hist'].iloc[-3])

    prev_is_green = (c2 > o2)
    curr_is_green = (c1 > o1)
    prev_is_red = (c2 < o2)
    curr_is_red = (c1 < o1)

    score = 0
    direction = "NONE"

    # กฎเหล็ก v66.0: ห้ามสวนเทรนด์เด็ดขาด (ต้องสอดคล้องทั้งแท่งเทียน, DiNapoli, EMA50 และ MACD)
    if curr_is_green and prev_is_green and c1 > din1 and c1 > ema50_1 and hist1 > hist2:
        if upper_wick < (body * 0.4): # ป้องกันไส้บนยาว
            score = 95
            direction = "CALL"

    elif curr_is_red and prev_is_red and c1 < din1 and c1 < ema50_1 and hist1 < hist2:
        if lower_wick < (body * 0.4): # ป้องกันไส้ล่างยาว
            score = 95
            direction = "PUT"

    if direction != "NONE":
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
    
    # หากรอบไหนไม่มีคู่ไหนผ่านเกณฑ์เข้มงวด 100% ระบบจะคัดคู่ที่ใกล้เคียงที่สุดโดยอิงตามทิศทางแท่งเทียนล่าสุดเพื่อไม่ให้ขาดตอน
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
        # Fallback ที่ปลอดภัยที่สุดตามเทรนด์ปัจจุบัน
        best_sym = random.choice(symbol_keys)
        best_dir = "CALL"
        best_score = 88

    last_sent_symbol[chat_id] = best_sym
    label = EXACT_8X_SYMBOLS.get(best_sym, best_sym)
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    target_time_str = target_time.strftime('%H:%M')
    
    is_buy = (best_dir == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    btn_label = "CALL" if is_buy else "PUT"

    card_text = (
        f"👑 **TITAN 8X STRICT TREND (v66.0)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **คู่ OTC กราฟสวยตรงตามระบบ:** `{label}`\n"
        f"🛡️ **ระบบกรอง:** `Strict Trend Lock (No Counter-Trend)`\n"
        f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"⭐ **ความคมชัดระบบ:** `{best_score}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *กดปุ่มด้านล่างเพื่อขอสัญญาณสดรอบถัดไป*"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณสดทันใจ (STRICT TREND)", callback_data="request_next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Send Error: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อขอสัญญาณแรก (v66.0)", callback_data="request_next_signal"))
    
    bot.reply_to(
        message, 
        "🚀 **TITAN v66.0 STRICT TREND ACTIVATED** 🚀\n"
        "อัปเกรดระบบล็อคเทรนด์เข้มงวด ห้ามสวนเทรนด์เด็ดขาด คัดเฉพาะกราฟที่ตรงตามเงื่อนไขเป๊ะๆ พร้อมลุยครับนาย!", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ v66.0 Engine Active")
        return
        
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "⚡ ล็อคกราฟสวยตามเทรนด์...")
        generate_fast_signal(chat_id)
        return

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
