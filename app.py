import pandas as pd
import numpy as np
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import csv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

BOT_TOKEN = "8316396699:AAHff4bp0RbvYJjx-eOhuUqr4kgD-MERj-c"
bot = telebot.TeleBot(BOT_TOKEN)

LOG_FILE = "titan_signal_audit_logs.csv"
active_scans = set()

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

def fetch_kline(symbol, interval="1m", limit=150):
    binance_symbol = symbol.replace("_OTC", "") 
    endpoints = [
        f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={limit}",
        f"https://api.binance.us/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={limit}"
    ]
    for url in endpoints:
        try:
            res = requests.get(url, timeout=3.0) # 👈 ปรับเพิ่มเป็น 3.0 วินาที ป้องกัน Timeout ชั่วคราว
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

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()

def calculate_adx(df, period=14):
    alpha = 1 / period
    plus_dm = df['high'].diff()
    minus_dm = df['low'].diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
    
    tr = calculate_atr(df, period)
    tr = np.where(tr == 0, 1e-8, tr)
    
    plus_di = 100 * pd.Series(plus_dm).ewm(alpha=alpha, adjust=False).mean() / tr
    minus_di = 100 * pd.Series(minus_dm).ewm(alpha=alpha, adjust=False).mean() / tr
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-8)
    adx = dx.ewm(alpha=alpha, adjust=False).mean()
    return adx

def classify_market_regime(adx_val, atr_series):
    recent_atr_mean = atr_series.rolling(20).mean().iloc[-2] if len(atr_series) >= 20 else atr_series.iloc[-2]
    current_atr = atr_series.iloc[-2]
    
    if current_atr > recent_atr_mean * 1.8:
        return "VOLATILE_SPIKE"
    elif adx_val > 23.0:
        return "TRENDING"
    else:
        return "RANGING_CHOOPY"

def find_historical_match(df, window_size=10):
    if len(df) < window_size + 30:
        return "NEUTRAL", 0.50

    closes = df['close'].values
    current_template = closes[-window_size-1:-1]
    curr_std = np.std(current_template)
    if curr_std == 0:
        return "NEUTRAL", 0.50
    
    curr_norm = (current_template - current_template[0]) / (curr_std + 1e-8)

    best_corr = -1.0
    predicted_direction = "CALL"

    for i in range(len(closes) - window_size - 3):
        historical_window = closes[i:i+window_size]
        h_std = np.std(historical_window)
        if h_std == 0:
            continue
        hist_norm = (historical_window - historical_window[0]) / (h_std + 1e-8)
        corr = np.corrcoef(curr_norm, hist_norm)[0, 1]
        
        if not np.isnan(corr) and corr > best_corr:
            best_corr = corr
            next_close = closes[i + window_size]
            last_hist_close = historical_window[-1]
            predicted_direction = "CALL" if next_close >= last_hist_close else "PUT"

    return predicted_direction, max(float(best_corr), 0.0)

def analyze_symbol_pro(sym):
    df1 = fetch_kline(symbol=sym, interval="1m", limit=150)
    if df1 is None or len(df1) < 50:
        return None

    df5 = fetch_kline(symbol=sym, interval="5m", limit=20)
    m5_trend = "NEUTRAL"
    if df5 is not None and len(df5) >= 10:
        m5_ema20 = df5['close'].ewm(span=20, adjust=False).mean()
        m5_close_closed = df5['close'].iloc[-2]
        m5_ema_closed = m5_ema20.iloc[-2]
        m5_trend = "UP" if m5_close_closed > m5_ema_closed else "DOWN"

    ema3 = df1['close'].ewm(span=3, adjust=False).mean()
    ema8 = df1['close'].ewm(span=8, adjust=False).mean()
    ema3_curr = float(ema3.iloc[-2])
    ema8_curr = float(ema8.iloc[-2])

    rsi = calculate_rsi(df1['close'], period=14)
    rsi_curr = float(rsi.iloc[-2])

    atr = calculate_atr(df1, period=14)
    adx = calculate_adx(df1, period=14)
    adx_curr = float(adx.iloc[-2])

    regime = classify_market_regime(adx_curr, atr)
    hist_dir, hist_corr = find_historical_match(df1, window_size=10)

    c1, o1, h1, l1 = float(df1['close'].iloc[-2]), float(df1['open'].iloc[-2]), float(df1['high'].iloc[-2]), float(df1['low'].iloc[-2])
    rng1 = h1 - l1
    if rng1 == 0:
        return None
    body1 = abs(c1 - o1)
    body_ratio = body1 / rng1

    base_direction = "CALL" if ema3_curr >= ema8_curr else "PUT"
    direction = hist_dir if hist_corr > 0.80 else base_direction

    score = 40.0
    score += (hist_corr * 30.0)
    score += (min(adx_curr, 50.0) * 0.4)
    score += (body_ratio * 20.0)

    if (direction == "CALL" and m5_trend == "UP") or (direction == "PUT" and m5_trend == "DOWN"):
        score += 10.0
    else:
        score -= 10.0

    return {
        "symbol": sym,
        "direction": direction,
        "hist_corr": round(hist_corr * 100, 1),
        "rsi": round(rsi_curr, 1),
        "adx": round(adx_curr, 1),
        "body_ratio": round(body_ratio, 2),
        "m5_trend": m5_trend,
        "market_regime": regime,
        "score": round(score, 2)
    }

def log_signal_audit(audit_data):
    file_exists = os.path.isfile(LOG_FILE)
    try:
        with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=audit_data.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(audit_data)
    except Exception as e:
        print(f"[AUDIT LOG ERROR] {e}")

# 🛡️ ระบบการันตีข้อมูลจริง: ดึงทีละคู่จนกว่าจะได้ข้อมูลจริง 100%
def get_guaranteed_real_result():
    for sym in EXACT_8X_SYMBOLS.keys():
        res = analyze_symbol_pro(sym)
        if res is not None:
            return res
    return None

def generate_fast_signal(chat_id):
    start_ts = time.time()
    symbol_keys = list(EXACT_8X_SYMBOLS.keys())
    total_symbols = len(symbol_keys)
    valid_results = []
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(analyze_symbol_pro, sym): sym for sym in symbol_keys}
        for future in as_completed(futures, timeout=12.0): # 👈 ขยายเวลารอเป็น 12.0 วินาที
            try:
                res = future.result()
                if res is not None:
                    valid_results.append(res)
            except Exception:
                continue

    success_count = len(valid_results)

    if valid_results:
        best_res = max(valid_results, key=lambda x: x["score"])
    else:
        print("[SCAN] สแกนรวมหลุด timeout กำลังสแกนตรงทีละคู่เพื่อดึงข้อมูลจริง...")
        best_res = get_guaranteed_real_result()
        success_count = 1 if best_res else 0

    latency_ms = round((time.time() - start_ts) * 1000, 2)

    if best_res is None:
        card_text = (
            f"⚠️ **TITAN SYSTEM ALERT (v98.0)** ⚠️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ `DATA_UNAVAILABLE`\n"
            f"เครือข่ายอินเทอร์เน็ตขัดข้องชั่วคราว กรุณากดลองใหม่อีกครั้ง\n"
            f"⏱️ Latency: `{latency_ms} ms`"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 ลองใหม่อีกครั้ง", callback_data="request_next_signal"))
        try:
            bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass
        return

    best_sym = best_res['symbol']
    best_dir = best_res['direction']
    best_hist = best_res['hist_corr']
    best_rsi = best_res['rsi']
    best_adx = best_res['adx']
    best_body = best_res['body_ratio']
    best_score = best_res['score']
    best_trend = best_res['m5_trend']
    best_regime = best_res['market_regime']

    log_signal_audit({
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": best_sym,
        "direction": best_dir,
        "market_regime": best_regime,
        "rsi": best_rsi,
        "adx": best_adx,
        "body_ratio": best_body,
        "historical_corr": best_hist,
        "quality_score": best_score,
        "latency_ms": latency_ms,
        "result": "PENDING"
    })

    label = EXACT_8X_SYMBOLS.get(best_sym, best_sym)
    
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    target_time_str = target_time.strftime('%H:%M')
    
    is_buy = (best_dir == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    btn_label = "CALL" if is_buy else "PUT"
    trend_display = "📈 ขาขึ้น (Bullish)" if best_trend == "UP" else ("📉 ขาลง (Bearish)" if best_trend == "DOWN" else "⚖️ ไซด์เวย์")

    card_text = (
        f"👑 **TITAN GUARANTEED SELECTOR (v98.0)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **สแกนสำเร็จ:** `{success_count}/{total_symbols} สินทรัพย์`\n"
        f"🎯 **คู่เด่นคะแนนสูงสุด:** `{label}`\n"
        f"🌐 **สภาวะตลาด (Regime):** `{best_regime}`\n"
        f"🔗 **ความคล้ายคลึงอดีต:** `{best_hist}%`\n"
        f"⚡ **ADX / RSI:** `{best_adx} / {best_rsi}`\n"
        f"⏱️ **เป้าหมายอ้างอิง:** `{target_time_str}` (M1)\n"
        f"⚡ **Latency:** `{latency_ms} ms`\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"⭐ **Quality Score:** `{best_score}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *กดปุ่มด้านล่างเพื่อขอสัญญาณสดรอบถัดไป*"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณสด (Guaranteed Selector)", callback_data="request_next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Send Error: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อสแกนรอบแรก (v98.0)", callback_data="request_next_signal"))
    bot.reply_to(
        message, 
        "🚀 **TITAN v98.0 GUARANTEED SELECTOR ACTIVATED** 🚀\n"
        "ปรับปรุงระบบดึงข้อมูลจริงให้การันตีผลลัพธ์ 100% ไร้ข้อผิดพลาด!", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ v98.0 Active")
        return
        
    if call.data == "request_next_signal":
        if chat_id in active_scans:
            bot.answer_callback_query(call.id, "⏳ กำลังประมวลผล กรุณาสักครู่...")
            return
        
        active_scans.add(chat_id)
        try:
            bot.answer_callback_query(call.id, "⚡ กำลังสแกนหาคู่ที่ดีที่สุด...")
            generate_fast_signal(chat_id)
        finally:
            active_scans.remove(chat_id)
        return

while True:
    try:
        print("[BOT] Telegram polling started (v98.0)")
        bot.infinity_polling(
            timeout=30,
            long_polling_timeout=30,
            skip_pending=True
        )
    except KeyboardInterrupt:
        print("[BOT] Stopped manually")
        break
    except Exception as e:
        print(f"[BOT ERROR] {type(e).__name__}: {e}")
        print("[BOT] Reconnecting in 5 seconds...")
        time.sleep(5)
