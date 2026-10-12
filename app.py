import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import threading

BOT_TOKEN = "8824803588:AAFdcAf-HzRrhtmWMNULQxYjXz-CHHHLk_g"
bot = telebot.TeleBot(BOT_TOKEN)

active_chat_ids = set()
user_martingale_step = {}

SYMBOLS = {
    "DYDXUSDT": "DYDX(OTC)",
    "XAUUSDT": "XAUUSD(OTC)",
    "XRPUSDT": "RIPPLE(OTC)",
    "LTCUSDT": "LITECOIN(OTC)",
    "SUIUSDT": "SUI(OTC)",
    "SHIBUSDT": "SHIB/USD(OTC)",
    "ONDOUSDT": "ONDO(OTC)",
    "AIGUSDT": "AIG(OTC)",
    "KOUSDT": "COCA-COLA(OTC)",
    "MCDUSDT": "MCDONALD'S(OTC)",
    "PENGUUSDT": "PUDGY PENGUINS(OTC)",
    "FARTCOINUSDT": "FARTCOIN(OTC)",
    "PENUSDT": "PEN/USD(OTC)",
    "SNAPUSDT": "SNAP INC(OTC)",
    "TRUMPUSDT": "TRUMP COIN(OTC)",
    "VAULTUSDT": "VAULTA(OTC)",
    "NKEUSDT": "NIKE INC(OTC)",
    "INTCUSDT": "INTEL CORP(OTC)",
    "MELANIAUSDT": "MELANIA COIN(OTC)",
    "GASUSDT": "NATURAL GAS(OTC)",
    "XAGUSDT": "XAGUSD(OTC)"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval, limit=50):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            raw = res.json()
            df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            df['close'] = df['close'].astype(float)
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['volume'] = df['volume'].astype(float)
            return df
    except Exception:
        pass
    return None

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def strict_analyze(symbol):
    # ดึงข้อมูล M5 และ M1
    df_m5 = fetch_kline(symbol, "5m", 30)
    df_m1 = fetch_kline(symbol, "1m", 40)

    if df_m5 is None or len(df_m5) < 20 or df_m1 is None or len(df_m1) < 30:
        return "NONE", 0, "DATA_INSUFFICIENT"

    # 1. เช็กเทรนด์ M5 จากแท่งที่ปิดแล้ว (iloc[-2])
    df_m5['ema_20'] = df_m5['close'].ewm(span=20, adjust=False).mean()
    m5_close = float(df_m5['close'].iloc[-2])
    m5_ema = float(df_m5['ema_20'].iloc[-2])
    
    is_m5_up = m5_close > m5_ema
    is_m5_down = m5_close < m5_ema

    # 2. เช็กแท่งเทียน M1 ที่ "ปิดสมบูรณ์แล้ว" จริงๆ (iloc[-2]) เพื่อตัดสัญญาณหลอก
    df_m1['ema_50'] = df_m1['close'].ewm(span=50, adjust=False).mean()
    df_m1['rsi'] = calculate_rsi(df_m1['close'], 14)

    o = float(df_m1['open'].iloc[-2])
    c = float(df_m1['close'].iloc[-2])
    h = float(df_m1['high'].iloc[-2])
    l = float(df_m1['low'].iloc[-2])
    ema = float(df_m1['ema_50'].iloc[-2])
    rsi = float(df_m1['rsi'].iloc[-2])
    vol = float(df_m1['volume'].iloc[-2])
    avg_vol = df_m1['volume'].iloc[-15:-2].mean()

    is_green = c > o
    is_red = c < o
    body_size = abs(c - o)
    body_pct = (body_size / o) * 100

    # กฎเหล็กที่ 1: ขนาดเนื้อเทียนต้องมีความชัดเจน (ไม่เอาโดจิหรือแท่งแคบเกินไป)
    if body_pct < 0.04:
        return "NONE", 0, "FILTER: DOJI / LOW_BODY_SIZE"

    # กฎเหล็กที่ 2: วอลลุ่มต้องสูงกว่าค่าเฉลี่ย
    if vol < (avg_vol * 0.8):
        return "NONE", 0, "FILTER: LOW_VOLUME"

    # คำนวณ Score จากความห่างและเนื้อเทียน
    score = int((abs(c - ema) / ema) * 10000 + (body_pct * 200))

    # --- ตรวจสอบฝั่ง UPTREND (CALL) ---
    if is_m5_up and is_green and c > ema:
        # เช็กไส้เทียนบน (ห้ามมีแรงขายกดทับเยอะเกินไป)
        if (h - c) / (h - l + 1e-9) > 0.4:
            return "NONE", 0, "FILTER: UPPER_REJECTION"
        # เช็ก RSI (ห้ามเข้าถ้า Overbought เกินไป)
        if 50 <= rsi <= 72:
            return "CALL", score, f"TITAN ELITE UPTREND (Score: {score})"

    # --- ตรวจสอบฝั่ง DOWNTREND (PUT) ---
    elif is_m5_down and is_red and c < ema:
        # เช็กไส้เทียนล่าง (ห้ามมีแรงซื้อดันกลับเยอะเกินไป)
        if (c - l) / (h - l + 1e-9) > 0.4:
            return "NONE", 0, "FILTER: LOWER_REJECTION"
        # เช็ก RSI (ห้ามเข้าถ้า Oversold เกินไป)
        if 28 <= rsi <= 50:
            return "PUT", score, f"TITAN ELITE DOWNTREND (Score: {score})"

    return "NONE", 0, "NO_MATCH"

def find_best_signal():
    best_sym = None
    best_dir = "NONE"
    best_status = "NO_SIGNAL"
    highest_score = -1

    for sym in SYMBOLS.keys():
        direction, score, status = strict_analyze(sym)
        if direction != "NONE" and score > highest_score:
            highest_score = score
            best_sym = sym
            best_dir = direction
            best_status = status

    if best_sym:
        return best_sym, SYMBOLS.get(best_sym, best_sym), best_dir, best_status
    return None, None, "NONE", "MARKET_UNCERTAIN_WAITING"

def send_signal(chat_id):
    try:
        sym, label, direction, status = find_best_signal()
        
        # ถ้าไม่มีคู่ไหนผ่านเกณฑ์เลย บอทจะไม่ส่งสัญญาณขยะออกไป (ยอมเงียบเพื่อความปลอดภัย)
        if not sym or direction == "NONE":
            print(f"[{get_thai_time().strftime('%H:%M:%S')}] ตลาดไม่สวย ผ่านการกรอง 0 คู่ (งดส่งสัญญาณ)")
            return

        step = user_martingale_step.get(chat_id, 1)
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "⬆️ BUY 🟢 (กรองเข้มข้นพิเศษ)" if is_buy else "⬇️ SELL 🔴 (กรองเข้มข้นพิเศษ)"
        btn_label = "CALL" if is_buy else "PUT"

        card_text = (
            f"👑 **TITAN ELITE MASTER 👑 M1**\n"
            f"⚡ **[ไม้ {step}]**\n\n"
            f"💎 **คู่ที่ผ่านเกณฑ์:** `{label}`\n"
            f"📈 **Timeframe:** `M1 (Closed Candle)`\n"
            f"⌚ **เข้าออเดอร์เวลา:** `{target_time_str}`\n"
            f"🚀 **ทิศทาง:** **{dir_emoji}**\n\n"
            f"🛡️ **สถานะ:** `{status}`"
        )

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton(f"🔥 EXECUTE {btn_label} 🔥", callback_data="do_nothing"))
        markup.add(
            InlineKeyboardButton("💎 ชนะไม้ 1", callback_data=f"res_win1_{sym}"),
            InlineKeyboardButton("🥈 ชนะไม้ 2", callback_data=f"res_win2_{sym}"),
            InlineKeyboardButton("🥉 ชนะไม้ 3", callback_data=f"res_win3_{sym}"),
            InlineKeyboardButton("❌ แพ้ (LOSS)", callback_data=f"res_loss_{sym}")
        )
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Send Error: {e}")

def auto_broadcaster():
    last_sent_minute = -1
    while True:
        try:
            now = get_thai_time()
            if now.second == 30 and now.minute != last_sent_minute:
                last_sent_minute = now.minute
                for cid in list(active_chat_ids):
                    send_signal(cid)
            time.sleep(0.5)
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(2)

@bot.message_handler(commands=['start', 'scan'])
def handle_start_scan(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    if chat_id not in user_martingale_step:
        user_martingale_step[chat_id] = 1
    bot.reply_to(message, "👑 **TITAN ELITE FILTER ONLINE**\nเปิดโหมดกรองเข้มข้นสูงสุด (ไม่ผ่านเกณฑ์จะไม่ส่งสัญญาณรบกวน) ระบบพร้อมทำงานแล้ว!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Signal Locked")
        return
    if call.data.startswith("res_"):
        parts = call.data.split("_")
        res_type = parts[1]
        if res_type in ["win1", "win2", "win3"]:
            user_martingale_step[chat_id] = 1
            bot.answer_callback_query(call.id, "💎 Reset สู่ไม้ 1")
        elif res_type == "loss":
            step = user_martingale_step.get(chat_id, 1)
            user_martingale_step[chat_id] = 1 if step >= 3 else step + 1
            bot.answer_callback_query(call.id, f"⚠️ ปรับสู่ไม้ {user_martingale_step[chat_id]}")

threading.Thread(target=auto_broadcaster, daemon=True).start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
