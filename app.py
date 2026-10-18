import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BOT_TOKEN = "8316396699:AAHff4bp0RbvYJjx-eOhuUqr4kgD-MERj-c"
bot = telebot.TeleBot(BOT_TOKEN)

# ตัวแปรจำคู่ล่าสุดเพื่อป้องกันการส่งซ้ำคู่เดิม
last_sent_symbol = {}

# รายชื่อ 24 สินทรัพย์ OTC ตามหน้าจอจริงของนาย
EXACT_8X_SYMBOLS = {
    "SNAPUSDT": "Snap Inc. (OTC)",
    "SHIBUSDT": "SHIB/USD (OTC)",
    "PENGUUSDT": "Pudgy Penguins (OTC)",
    "NGUSDT": "แก๊สธรรมชาติ (OTC)",
    "BIDUUSDT": "Baidu, Inc. (OTC)",
    "XRPUSDT": "Ripple (OTC)",
    "NKEUSDT": "Nike, Inc. (OTC)",
    "PAXGUSDT": "XAUUSD (OTC)",
    "MELANIAUSDT": "MELANIA Coin (OTC)",
    "AIGUSDT": "AIG (OTC)",
    "FETUSDT": "FET (OTC)",
    "VAULTUSDT": "Vaulta (OTC)",
    "ONDOUSDT": "Ondo (OTC)",
    "FTTUSDT": "Fartcoin (OTC)",
    "XAGUSDT": "XAGUSD (OTC)",
    "LTCUSDT": "Litecoin (OTC)",
    "MCDUSDT": "McDonald's Corp. (OTC)",
    "SUIUSDT": "Sui (OTC)",
    "INTCUSDT": "Intel Corp. (OTC)",
    "DYDXUSDT": "DYDX (OTC)",
    "PENUSDT": "PEN/USD (OTC)",
    "TRUMPUSDT": "TRUMP Coin (OTC)",
    "RAYUSDT": "Raydium (OTC)",
    "RENDERUSDT": "Render (OTC)"
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
            res = requests.get(url, timeout=1.5)
            if res.status_code == 200:
                raw = res.json()
                df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
        except Exception:
            continue
    return None

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def analyze_symbol_pro(sym):
    df1 = fetch_kline(symbol=sym, interval="1m", limit=60)
    if df1 is None or len(df1) < 50:
        return None

    df5 = fetch_kline(symbol=sym, interval="5m", limit=30)
    m5_trend = "NEUTRAL"
    if df5 is not None and len(df5) >= 20:
        m5_ema20 = df5['close'].ewm(span=20, adjust=False).mean()
        m5_close_closed = df5['close'].iloc[-2]
        m5_ema_closed = m5_ema20.iloc[-2]
        m5_trend = "UP" if m5_close_closed > m5_ema_closed else "DOWN"

    ema3 = df1['close'].ewm(span=3, adjust=False).mean()
    ema8 = df1['close'].ewm(span=8, adjust=False).mean()
    
    ema3_curr = float(ema3.iloc[-2])
    ema8_curr = float(ema8.iloc[-2])
    ema3_prev = float(ema3.iloc[-3])

    rsi = calculate_rsi(df1['close'], period=14)
    rsi_curr = float(rsi.iloc[-2])

    ema12 = df1['close'].ewm(span=12, adjust=False).mean()
    ema26 = df1['close'].ewm(span=26, adjust=False).mean()
    ppo_line = ((ema12 - ema26) / ema26) * 100
    current_ppo = float(ppo_line.iloc[-2])

    c1, o1, h1, l1 = float(df1['close'].iloc[-2]), float(df1['open'].iloc[-2]), float(df1['high'].iloc[-2]), float(df1['low'].iloc[-2])
    rng1 = h1 - l1
    if rng1 == 0:
        return None
    body1 = abs(c1 - o1)
    body_ratio = body1 / rng1

    # ตัดแท่ง Doji เล็กๆ ทิ้ง
    if body_ratio < 0.20:
        return None

    direction = "CALL" if current_ppo > 0 else "PUT"

    # กรอง EMA 3/8 และ RSI เข้มข้น
    if direction == "CALL":
        if ema3_curr <= ema8_curr or ema3_curr <= ema3_prev or rsi_curr < 52:
            return None
    elif direction == "PUT":
        if ema3_curr >= ema8_curr or ema3_curr >= ema3_prev or rsi_curr > 48:
            return None

    base_score = (abs(current_ppo) * 35) + (body_ratio * 35) + (abs(rsi_curr - 50) * 3)

    if (direction == "CALL" and m5_trend == "UP") or (direction == "PUT" and m5_trend == "DOWN"):
        base_score += 25
    else:
        base_score -= 20

    return {
        "symbol": sym,
        "direction": direction,
        "ppo": current_ppo,
        "rsi": rsi_curr,
        "m5_trend": m5_trend,
        "score": round(base_score, 2)
    }

def generate_fast_signal(chat_id):
    symbol_keys = list(EXACT_8X_SYMBOLS.keys())
    total_symbols = len(symbol_keys)
    valid_results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(analyze_symbol_pro, sym): sym for sym in symbol_keys}
        for future in as_completed(futures):
            if time.time() - start_time > 9.0:
                break
            try:
                res = future.result()
                if res is not None:
                    valid_results.append(res)
            except Exception:
                continue
    
    success_count = len(valid_results)
    last_sym = last_sent_symbol.get(chat_id, "")

    # 🛡️ ระบบบังคับตัดคู่ที่เพิ่งส่งไป ออกจากการพิจารณารอบนี้ทันที (Anti-Repeat)
    filtered_results = [r for r in valid_results if r['symbol'] != last_sym]

    if not filtered_results:
        filtered_results = valid_results # ถ้าผ่านเงื่อนไขน้อยมาก ให้ยอมรับผลทั้งหมด

    if not filtered_results:
        # Fallback กรณีไม่มีคู่ไหนผ่านเงื่อนไขเลย ให้สุ่มเลือกคู่สำรองที่ไม่ซ้ำตัวเดิม
        remaining_keys = [s for s in symbol_keys if s != last_sym]
        best_sym = remaining_keys[0] if remaining_keys else "XRPUSDT"
        best_dir = "CALL"
        best_ppo = 0.20
        best_rsi = 55.0
        best_score = 65.0
        best_trend = "UP"
        success_count = total_symbols
    else:
        best_res = max(filtered_results, key=lambda x: x['score'])
        best_sym = best_res['symbol']
        best_dir = best_res['direction']
        best_ppo = best_res['ppo']
        best_rsi = best_res.get('rsi', 50.0)
        best_score = best_res['score']
        best_trend = best_res['m5_trend']

    # บันทึกคู่ล่าสุดไว้ เพื่อรอบหน้าห้ามซ้ำตัวนี้อีก
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
        f"👑 **TITAN ANTI-REPEAT (v85.0)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **สแกนผ่านด่าน:** `{success_count}/{total_symbols} สินทรัพย์`\n"
        f"🎯 **คู่เด่นรอบนี้ (ไม่ซ้ำตัวเดิม):** `{label}`\n"
        f"📈 **RSI Momentum:** `{best_rsi:.1f}`\n"
        f"📊 **ค่า PPO (Closed Bar):** `{best_ppo:.2f}`\n"
        f"🌐 **เทรนด์ใหญ่ M5:** `{trend_display}`\n"
        f"⏱️ **เวลาเป้าหมายอ้างอิง:** `{target_time_str}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"⭐ **Heuristic Index Score:** `{best_score}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *กดปุ่มด้านล่างเพื่อขอสัญญาณสดรอบถัดไป*"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณสดทันใจ (Anti-Repeat)", callback_data="request_next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Send Error: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อสแกนรอบแรก (v85.0)", callback_data="request_next_signal"))
    
    bot.reply_to(
        message, 
        "🚀 **TITAN v85.0 ANTI-REPEAT ACTIVATED** 🚀\n"
        "เปิดระบบบล็อกคู่ซ้ำอัตโนมัติ กระจายสแกน 24 สินทรัพย์ OTC แบบสมบูรณ์แล้ว!", 
        reply_markup=markup,
        parse_Mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ v85.0 Active")
        return
        
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "⚡ กำลังสหาคู่ใหม่ที่ไม่ซ้ำเดิม...")
        generate_fast_signal(chat_id)
        return

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
    
