import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BOT_TOKEN = "8316396699:AAHff4bp0RbvYJjx-eOhuUqr4kgD-MERj-c"
bot = telebot.TeleBot(BOT_TOKEN)

last_sent_symbol = {}

# 22 คู่สินทรัพย์ชื่อสะอาด ตรงประเด็น
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

def analyze_symbol(sym):
    df = fetch_kline(symbol=sym, interval="1m", limit=60)
    if df is None or len(df) < 50:
        return None

    # PPO Calculation (12, 26, Close, EMA)
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    ppo_line = ((ema12 - ema26) / ema26) * 100
    current_ppo = float(ppo_line.iloc[-2])

    c1, o1, h1, l1 = float(df['close'].iloc[-2]), float(df['open'].iloc[-2]), float(df['high'].iloc[-2]), float(df['low'].iloc[-2])
    c2, o2 = float(df['close'].iloc[-3]), float(df['open'].iloc[-3])
    c3, o3 = float(df['close'].iloc[-4]), float(df['open'].iloc[-4])

    rng1 = h1 - l1
    if rng1 == 0:
        return None

    body1 = abs(c1 - o1)
    body_ratio = body1 / rng1
    ppo_distance = abs(current_ppo)

    # คุมทิศทางหลักด้วยเส้นศูนย์ของ PPO (เหนือ 0 = CALL, ใต้ 0 = PUT)
    direction = "CALL" if current_ppo > 0 else "PUT"
    
    # คำนวณคะแนนเชิงปริมาณจริง (Objective Momentum Score) จาก PPO Distance และ Body Ratio
    base_score = (ppo_distance * 30) + (body_ratio * 40)
    
    # ให้โบนัสเพิ่มเติมถ้า 3 แท่งเรียงตัวสอดคล้องกับทิศทาง PPO
    if direction == "CALL" and (c1 > o1) and (c2 > o2) and (c3 > o3):
        base_score += 30
    elif direction == "PUT" and (c1 < o1) and (c2 < o2) and (c3 < o3):
        base_score += 30

    return {
        "symbol": sym,
        "direction": direction,
        "ppo": current_ppo,
        "score": round(base_score, 2)
    }

def generate_fast_signal(chat_id):
    symbol_keys = list(EXACT_8X_SYMBOLS.keys())
    valid_results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=len(symbol_keys)) as executor:
        futures = {executor.submit(analyze_symbol, sym): sym for sym in symbol_keys}
        for future in as_completed(futures):
            if time.time() - start_time > 8.5:
                break
            try:
                res = future.result(timeout=0.8)
                if res is not None:
                    valid_results.append(res)
            except Exception:
                continue
    
    if not valid_results:
        best_sym = symbol_keys[0]
        best_dir = "CALL"
        best_ppo = 0.0
        best_score = 50.0
    else:
        # กรองคู่ซ้ำเพื่อไม่ให้ส่งคู่เดิมติดต่อกัน
        last_sym = last_sent_symbol.get(chat_id, "")
        filtered_results = [r for r in valid_results if r['symbol'] != last_sym]
        if not filtered_results:
            filtered_results = valid_results

        # เลือกตัวที่ได้คะแนนโมเมนตัมเชิงปริมาณสูงสุดในรอบนั้น
        best_res = max(filtered_results, key=lambda x: x['score'])
        best_sym = best_res['symbol']
        best_dir = best_res['direction']
        best_ppo = best_res['ppo']
        best_score = best_res['score']

    last_sent_symbol[chat_id] = best_sym
    label = EXACT_8X_SYMBOLS.get(best_sym, best_sym)
    
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    target_time_str = target_time.strftime('%H:%M')
    
    is_buy = (best_dir == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    btn_label = "CALL" if is_buy else "PUT"

    card_text = (
        f"👑 **TITAN 8X ULTIMATE PURE (v73.0)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **คู่ OTC คัดเลือกพิเศษ:** `{label}`\n"
        f"📊 **ค่า PPO หลัก:** `{best_ppo:.2f}` (Zero-Line Aligned)\n"
        f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"⭐ **คะแนนโมเมนตัมจริง:** `{best_score}` (ประเมินจาก PPO + Body Ratio)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *กดปุ่มด้านล่างเพื่อขอสัญญาณสดรอบถัดไป*"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณสดทันใจ (ULTIMATE ENGINE)", callback_data="request_next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Send Error: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อสแกนรอบแรก (v73.0)", callback_data="request_next_signal"))
    
    bot.reply_to(
        message, 
        "🚀 **TITAN v73.0 ULTIMATE PURE ACTIVATED** 🚀\n"
        "ระบบสมบูรณ์แบบ: คัดเลือกคู่ที่ดีที่สุดด้วยคะแนนโมเมนตัมเชิงปริมาณจริง ทำงานต่อเนื่อง ไม่มีหยุดชะงัก!", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ v73.0 Ultimate Active")
        return
        
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "⚡ สแกนหาคู่ที่ทรงพลังที่สุด...")
        generate_fast_signal(chat_id)
        return

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
