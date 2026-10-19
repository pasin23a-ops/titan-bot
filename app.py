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

def analyze_symbol_democratic(sym):
    # 1. ดึงข้อมูลจริง M1
    df1 = fetch_kline(symbol=sym, interval="1m", limit=60)
    if df1 is None or len(df1) < 50:
        return None

    # 2. ดึงข้อ 2 ของโค้ดปัจจุบัน: เทรนด์ระยะยาว M5 และ M15 จริง
    df5 = fetch_kline(symbol=sym, interval="5m", limit=30)
    df15 = fetch_kline(symbol=sym, interval="15m", limit=30)
    
    m5_trend = "NEUTRAL"
    if df5 is not None and len(df5) >= 20:
        m5_ema20 = df5['close'].ewm(span=20, adjust=False).mean()
        m5_trend = "UP" if df5['close'].iloc[-2] > m5_ema20.iloc[-2] else "DOWN"

    m15_trend = "NEUTRAL"
    if df15 is not None and len(df15) >= 20:
        m15_ema20 = df15['close'].ewm(span=20, adjust=False).mean()
        m15_trend = "UP" if df15['close'].iloc[-2] > m15_ema20.iloc[-2] else "DOWN"

    # 3. คำนวณอินดิเคเตอร์จริง (PPO, RSI, Bollinger Bands)
    ema12 = df1['close'].ewm(span=12, adjust=False).mean()
    ema26 = df1['close'].ewm(span=26, adjust=False).mean()
    ppo_line = ((ema12 - ema26) / ema26) * 100
    current_ppo = float(ppo_line.iloc[-2])

    delta = df1['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi_series = 100 - (100 / (1 + rs))
    current_rsi = float(rsi_series.iloc[-2])

    sma20 = df1['close'].rolling(window=20).mean()
    std20 = df1['close'].rolling(window=20).std()
    upper_band = sma20 + (std20 * 2)
    lower_band = sma20 - (std20 * 2)
    band_width = float((upper_band.iloc[-2] - lower_band.iloc[-2]) / sma20.iloc[-2])

    # 4. ระบบประชาธิปไตย (Democratic Voting System - นับคะแนนเสียงจริงจากทุกเครื่องมือ)
    call_votes = 0
    put_votes = 0

    # เสียงที่ 1: PPO Momentum
    if current_ppo > 0: call_votes += 1
    else: put_votes += 1

    # เสียงที่ 2: RSI Zone
    if current_rsi < 45: call_votes += 1
    elif current_rsi > 55: put_votes += 1

    # เสียงที่ 3: M5 Trend Confirmation
    if m5_trend == "UP": call_votes += 2
    elif m5_trend == "DOWN": put_votes += 2

    # เสียงที่ 4: M15 Trend Confirmation (กรอบใหญ่สุด)
    if m15_trend == "UP": call_votes += 2
    elif m15_trend == "DOWN": put_votes += 2

    # ตัดสินทิศทางจากเสียงข้างมาก (ประชาธิปไตยแท้จริง)
    if call_votes >= put_votes:
        direction = "CALL"
        majority_votes = call_votes
        total_votes = call_votes + put_votes
    else:
        direction = "PUT"
        majority_votes = put_votes
        total_votes = call_votes + put_votes

    consensus_pct = round((majority_votes / max(total_votes, 1)) * 100, 1)

    # คำนวณ Score จากผลโหวตและความกว้างของกรอบจริง
    base_score = (consensus_pct * 0.7) + (band_width * 300)

    return {
        "symbol": sym,
        "direction": direction,
        "ppo": current_ppo,
        "rsi": round(current_rsi, 2),
        "m5_trend": m5_trend,
        "m15_trend": m15_trend,
        "call_votes": call_votes,
        "put_votes": put_votes,
        "consensus": consensus_pct,
        "score": round(base_score, 2)
    }

def generate_fast_signal(chat_id):
    symbol_keys = list(EXACT_8X_SYMBOLS.keys())
    total_symbols = len(symbol_keys)
    valid_results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=total_symbols) as executor:
        futures = {executor.submit(analyze_symbol_democratic, sym): sym for sym in symbol_keys}
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
        # หากดึงข้อมูลไม่ได้จริงๆ จะแจ้งเตือนตรงๆ ไม่ออกเลขมโนมั่วซั่ว
        try:
            bot.send_message(chat_id, "⚠️ กำลังหน่วงกับเซิร์ฟเวอร์ตลาดจริง กรุณากดขอสัญญาณใหม่อีกครั้งทันที", parse_mode="Markdown")
        except:
            pass
        return

    last_sym = last_sent_symbol.get(chat_id, "")
    filtered_results = [r for r in valid_results if r['symbol'] != last_sym]
    if not filtered_results:
        filtered_results = valid_results

    best_res = max(filtered_results, key=lambda x: x['score'])
    
    last_sent_symbol[chat_id] = best_res['symbol']
    label = EXACT_8X_SYMBOLS.get(best_res['symbol'], best_res['symbol'])
    
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    target_time_str = target_time.strftime('%H:%M')
    
    is_buy = (best_res['direction'] == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    btn_label = "CALL" if is_buy else "PUT"
    
    trend_m5_disp = "📈 ขาขึ้น" if best_res['m5_trend'] == "UP" else ("📉 ขาลง" if best_res['m5_trend'] == "DOWN" else "⚖️ ไซด์เวย์")
    trend_m15_disp = "📈 ขาขึ้น" if best_res['m15_trend'] == "UP" else ("📉 ขาลง" if best_res['m15_trend'] == "DOWN" else "⚖️ ไซด์เวย์")

    card_text = (
        f"👑 **TITAN v82.0 DEMOCRATIC REAL-DATA** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **สถานะระบบ:** `ดึงข้อมูลจริง {success_count}/{total_symbols} สำเร็จ`\n"
        f"🎯 **คู่ที่ถูกเลือก:** `{label}`\n"
        f"🗳️ **ระบบประชาธิปไตย (โหวตขึ้น/ลง):** `[ขึ้น {best_res['call_votes']} : ลง {best_res['put_votes']}]` ({best_res['consensus']}%)\n"
        f"🌐 **เทรนด์ใหญ่ (M5 / M15):** `{trend_m5_disp} / {trend_m15_disp}`\n"
        f"📊 **ค่า PPO / RSI (14):** `{best_res['ppo']:.2f} / {best_res['rsi']}`\n"
        f"⏱️ **เวลาเป้าหมายอ้างอิง:** `{target_time_str}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"⭐ **Democratic Score:** `{best_res['score']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📰 *กรองสภาวะตลาดจริง ไร้ตัวเลขมโน*"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณสดทันใจ (DEMOCRATIC)", callback_data="request_next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Send Error: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อสแกนรอบแรก (v82.0)", callback_data="request_next_signal"))
    bot.reply_to(
        message, 
        "🚀 **TITAN v82.0 DEMOCRATIC ENGINE ACTIVATED** 🚀\n"
        "รวมร่างระบบวิเคราะห์ M5/M15, ระบบโหวตประชาธิปไตยจากอินดิเคเตอร์จริง และตัดตัวเลขมโนออก 100% ลุยโลด:", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ v82.0 Active")
        return
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "⚡ กำลังประมวลผลข้อมูลจริง...")
        generate_fast_signal(chat_id)
        return

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
