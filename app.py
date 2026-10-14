import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import threading

BOT_TOKEN = "8316396699:AAHff4bp0RbvYJjx-eOhuUqr4kgD-MERj-c"
bot = telebot.TeleBot(BOT_TOKEN)

active_chat_ids = set()
user_martingale_step = {}
last_global_signal_time = 0 

# ระบบคูดาวแยกรายคู่เหรียญชั่วคราว (เมื่อเจอจุดอันตรายหรือพึ่งส่งสัญญาณ จะพักคู่รอนิ่งแล้วค่อยกลับมาคำนวณใหม่)
symbol_cooldowns = {}
PAIR_COOLDOWN_DURATION = 240  # พักคู่เหรียญที่มีปัญหาหรือพิ่งส่ง 4 นาที

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

# ตัวแปรเก็บผลลัพธ์ที่คำนวณล่วงหน้าสำหรับแท่งถัดไป (Look-ahead Cache)
next_candle_cache = {
    "symbol": "",
    "label": "",
    "direction": "NONE",
    "status": "CALCULATING_AHEAD",
    "score": 0
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval="1m", limit=50):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=2.5)
        if res.status_code == 200:
            raw = res.json()
            df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype(float)
            return df
    except Exception:
        pass

    try:
        url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=2.5)
        if res.status_code == 200:
            raw = res.json()
            df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype(float)
            return df
    except Exception:
        pass

    return None

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def analyze_autopilot_advanced(symbol):
    current_time = time.time()
    # เช็คว่าคู่ไหนติดคูดาวอันตรายชั่วคราวอยู่หรือไม่
    if symbol in symbol_cooldowns and current_time < symbol_cooldowns[symbol]:
        return "NONE", -99999, "PAIR_TEMPORARY_COOLDOWN"

    df = fetch_kline(symbol, "1m", 50)
    if df is None or len(df) < 40:
        return "NONE", 0, "DATA_ERROR"

    df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema_12'] - df['ema_26']
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal']
    df['rsi'] = calculate_rsi(df['close'], 14)

    c = float(df['close'].iloc[-2])
    o = float(df['open'].iloc[-2])
    h = float(df['high'].iloc[-2])
    l = float(df['low'].iloc[-2])
    
    ema10 = float(df['ema_10'].iloc[-2])
    ema20 = float(df['ema_20'].iloc[-2])
    rsi_val = float(df['rsi'].iloc[-2])
    macd_hist = float(df['hist'].iloc[-2])

    if pd.isna(rsi_val):
        rsi_val = 50.0

    # [ADVANCED SUPPORT & RESISTANCE CHECK] คำนวณแนวรับแนวต้านจาก High / Low ย้อนหลัง 20 แท่ง
    recent_high = df['high'].iloc[-22:-2].max()
    recent_low = df['low'].iloc[-22:-2].min()

    # ถ้า้าราคาอยู่ใกล้แนวต้านหรือแนวรับมากๆ (เสี่ยงชนกำแพง) ให้ตีตกเป็นอันตรายทันที
    range_span = recent_high - recent_low
    if range_span > 0:
        distance_to_high = (recent_high - c) / range_span
        distance_to_low = (c - recent_low) / range_span
        
        # หากใกล้แนวต้านเกินไป (< 3%) ห้ามกด CALL
        # หากใกล้แนวรับเกินไป (< 3%) ห้ามกด PUT
        near_resistance = distance_to_high < 0.03
        near_support = distance_to_low < 0.03
    else:
        near_resistance = False
        near_support = False

    raw_distance = int((abs(c - ema20) / (ema20 + 1e-9)) * 100000)

    # Smart Penalty & Danger Shield: ถ้าค่า PTS สูงเกิน 180 หรือเจอภาวะลากไส้ ให้หักคะแนนหนักและสั่งพักคู่เหรียญนี้ชั่วคราว
    quality_score = raw_distance
    if raw_distance > 180:
        # สั่งติดคูดาวพักคู่เหรียญนี้ทันที 4 นาที ป้องกันติดกับดักลากซ้ำ
        symbol_cooldowns[symbol] = current_time + PAIR_COOLDOWN_DURATION
        return "NONE", -99999, "DANGER_EXHAUSTION_PAUSED"

    direction = "NONE"
    status_msg = "SIDEWAY"

    # เงื่อนไขการออกออเดอร์พร้อมกรองแนวรับแนวต้าน
    if c < ema10 and c < ema20 and not near_support:
        if c <= o:
            direction = "PUT"
            status_msg = f"S&R SAFE DOWNTREND (RSI: {int(rsi_val)})"
            if macd_hist < 0:
                quality_score += 25

    elif c > ema10 and c > ema20 and not near_resistance:
        if c >= o:
            direction = "CALL"
            status_msg = f"S&R SAFE UPTREND (RSI: {int(rsi_val)})"
            if macd_hist > 0:
                quality_score += 25

    return direction, quality_score, status_msg

def background_lookahead_scanner():
    global next_candle_cache
    while True:
        try:
            top_sym = None
            top_dir = "NONE"
            top_status = "SCANNING"
            highest_score = -999999

            # คำนวณและประเมินล่วงหน้าทุกลมหายใจ เพื่อเลือกคู่ที่ดีที่สุดรอไว้สำหรับแท่งถัดไป
            for sym in SYMBOLS.keys():
                direction, score, status = analyze_autopilot_advanced(sym)
                if score > highest_score and direction != "NONE":
                    highest_score = score
                    top_sym = sym
                    top_dir = direction
                    top_status = status

            if top_sym and top_dir != "NONE":
                next_candle_cache = {
                    "symbol": top_sym,
                    "label": SYMBOLS.get(top_sym, top_sym),
                    "direction": top_dir,
                    "status": top_status,
                    "score": highest_score
                }
            else:
                next_candle_cache = {
                    "symbol": "",
                    "label": "",
                    "direction": "NONE",
                    "status": "WAITING_SAFE_SETUP",
                    "score": 0
                }
            
            time.sleep(1)
        except Exception as e:
            print(f"Scanner Error: {e}")
            time.sleep(2)

def send_auto_signal(chat_id):
    global last_global_signal_time
    try:
        now_time = time.time()
        
        # [STRICT 1-CANDLE INTERVAL] ล็อกเวลาส่งสัญญาณ 1 ครั้งต่อ 1 นาที (1 แท่ง M1) เป๊ะๆ
        if now_time - last_global_signal_time < 60:
            return

        direction = next_candle_cache["direction"]
        score = next_candle_cache["score"]

        if direction == "NONE":
            return

        sym = next_candle_cache["symbol"]
        label = next_candle_cache["label"]
        status = next_candle_cache["status"]

        # เมื่อส่งสัญญาณแล้ว ให้ติดคูดาวคู่เหรียญนี้ชั่วคราว เพื่อให้บอทรอบหน้าไปคำนวณหาคู่ใหม่ที่สดกว่า
        symbol_cooldowns[sym] = now_time + PAIR_COOLDOWN_DURATION
        last_global_signal_time = now_time

        step = user_martingale_step.get(chat_id, 1)
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
        btn_label = "CALL" if is_buy else "PUT"

        card_text = (
            f"🛡️ **TITAN AUTO-PILOT (Advanced S&R v11.0)** 🛡️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🥊 **การเดินเงิน:** `ไม้ที่ {step}`\n"
            f"🎯 **คู่คำนวณล่วงหน้า:** `{label}` *(พักคู่ชั่วคราวหลังส่ง)*\n"
            f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
            f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
            f"📊 **สถานะแนวรับแนวต้าน:** `{status}`\n"
            f"🛡️ **Quality Score:** `{score} PTS` *(คำนวณล่วงหน้าสมบูรณ์)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ *Cooldown: ล็อกสัญญาณ 1 แท่งเทียนเป๊ะ + กรอง S&R*"
        )

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton(f"🛡️ S&R PRECISE SIGNAL ({btn_label}) 🛡️", callback_data="do_nothing"))
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
                    send_auto_signal(cid)
            time.sleep(0.3)
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(1)

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    if chat_id not in user_martingale_step:
        user_martingale_step[chat_id] = 1
    
    bot.reply_to(
        message, 
        "🚀 **TITAN AUTO-PILOT ADVANCED S&R ACTIVATED** 🚀\n"
        "ระบบประมวลผลล่วงหน้า (Look-ahead) พร้อมระบบตรวจสอบแนวรับแนวต้าน + พักคู่เหรียญอันตรายชั่วคราว ล็อกสัญญาณเข้มงวด 1 แท่งเทียนเป๊ะ พร้อมลุยแล้วครับนาย!", 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "🛡️ S&R Shield Active")
        return
    if call.data.startswith("res_"):
        parts = call.data.split("_")
        res_type = parts[1]
        if res_type in ["win1", "win2", "win3"]:
            user_martingale_step[chat_id] = 1
            bot.answer_callback_query(call.id, "💎 WIN! Reset สู่ไม้ 1")
        elif res_type == "loss":
            step = user_martingale_step.get(chat_id, 1)
            user_martingale_step[chat_id] = 1 if step >= 3 else step + 1
            bot.answer_callback_query(call.id, f"⚠️ LOSS! ขยับเป็นไม้ {user_martingale_step[chat_id]}")

# รันเธรดเบื้องหลังสำหรับคำนวณล่วงหน้า
threading.Thread(target=background_lookahead_scanner, daemon=True).start()
threading.Thread(target=auto_broadcaster, daemon=True).start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
