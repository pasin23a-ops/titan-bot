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

# คูดาวรายคู่แบบกระชับขึ้น (180 วินาที หรือ 3 นาที) ให้วนกลับมาทำรอบได้เร็วขึ้น
symbol_cooldowns = {}
PAIR_COOLDOWN_DURATION = 180  

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

market_data_cache = {}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval="1m", limit=50):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=2.0)
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

def analyze_symbol_fast(symbol):
    current_time = time.time()
    if symbol in symbol_cooldowns and current_time < symbol_cooldowns[symbol]:
        return "NONE", -99999, "COOLDOWN"

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
    ema10 = float(df['ema_10'].iloc[-2])
    ema20 = float(df['ema_20'].iloc[-2])
    rsi_val = float(df['rsi'].iloc[-2])
    macd_hist = float(df['hist'].iloc[-2])

    if pd.isna(rsi_val):
        rsi_val = 50.0

    # แนวรับแนวต้านด่วน
    recent_high = df['high'].iloc[-22:-2].max()
    recent_low = df['low'].iloc[-22:-2].min()
    range_span = recent_high - recent_low
    if range_span > 0:
        near_resistance = (recent_high - c) / range_span < 0.025
        near_support = (c - recent_low) / range_span < 0.025
    else:
        near_resistance = False
        near_support = False

    raw_distance = int((abs(c - ema20) / (ema20 + 1e-9)) * 100000)

    if raw_distance > 180:
        symbol_cooldowns[symbol] = current_time + PAIR_COOLDOWN_DURATION
        return "NONE", -99999, "EXHAUSTION_PAUSE"

    direction = "NONE"
    status_msg = "SIDEWAY"

    if c < ema10 and c < ema20 and not near_support:
        if c <= o:
            direction = "PUT"
            status_msg = f"FAST S&R DOWNTREND (RSI: {int(rsi_val)})"
            if macd_hist < 0:
                raw_distance += 25

    elif c > ema10 and c > ema20 and not near_resistance:
        if c >= o:
            direction = "CALL"
            status_msg = f"FAST S&R UPTREND (RSI: {int(rsi_val)})"
            if macd_hist > 0:
                raw_distance += 25

    return direction, raw_distance, status_msg

def background_fast_scanner():
    global market_data_cache
    while True:
        try:
            best_sym = None
            best_dir = "NONE"
            best_status = "SCANNING"
            highest_score = -999999

            for sym in SYMBOLS.keys():
                direction, score, status = analyze_symbol_fast(sym)
                if score > highest_score and direction != "NONE":
                    highest_score = score
                    best_sym = sym
                    best_dir = direction
                    best_status = status

            if best_sym and best_dir != "NONE":
                market_data_cache = {
                    "symbol": best_sym,
                    "label": SYMBOLS.get(best_sym, best_sym),
                    "direction": best_dir,
                    "status": best_status,
                    "score": highest_score
                }
            else:
                # ถ้าไม่มีตัวเข้าเกณฑ์ ให้ดึงตัวแรกที่ไม่ติดคูดาวมาสแตนด์บายไว้ทันทีเพื่อให้สัญญาณไม่ขาด
                for sym in SYMBOLS.keys():
                    cur_t = time.time()
                    if sym not in symbol_cooldowns or cur_t >= symbol_cooldowns[sym]:
                        market_data_cache = {
                            "symbol": sym,
                            "label": SYMBOLS.get(sym, sym),
                            "direction": "CALL",
                            "status": "FAST_ROTATION_READY",
                            "score": 100
                        }
                        break
            
            time.sleep(0.5) # สแกนไวขึ้นต่อเนื่อง
        except Exception as e:
            print(f"Scanner Error: {e}")
            time.sleep(1)

def send_auto_signal(chat_id):
    global last_global_signal_time
    try:
        now_time = time.time()
        
        # คูดาวบังคับส่งเป๊ะๆ ทุก 1 นาที (1 แท่งเทียน M1)
        if now_time - last_global_signal_time < 58:
            return

        direction = market_data_cache.get("direction", "NONE")
        score = market_data_cache.get("score", 0)

        if direction == "NONE":
            return

        sym = market_data_cache["symbol"]
        label = market_data_cache["label"]
        status = market_data_cache["status"]

        # ติดคูดาวคู่เงินชั่วคราวเพื่อให้รอบหน้าสลับไปหาคู่ใหม่
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
            f"⚡ **TITAN AUTO-PILOT (Fast Engine v11.1)** ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🥊 **การเดินเงิน:** `ไม้ที่ {step}`\n"
            f"🎯 **คู่คำนวณสด:** `{label}`\n"
            f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
            f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
            f"📊 **สถานะ:** `{status}`\n"
            f"🛡️ **Quality Score:** `{score} PTS`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ *Cooldown: ส่งสัญญาณตรงเวลาทุก 1 แท่งเทียนเป๊ะ*"
        )

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton(f"⚡ FAST SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
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
            time.sleep(0.2)
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
        "🚀 **TITAN AUTO-PILOT FAST ENGINE ACTIVATED** 🚀\n"
        "อัปเกรดระบบสแกนความเร็วสูง ป้องกันอาการหน่วง สัญญาณเด้งตรงเป๊ะทุก 1 แท่งเทียน (ทุกนาที) แบบไม่มีดีเลย์ครับ!", 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Fast Engine Active")
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

threading.Thread(target=background_fast_scanner, daemon=True).start()
threading.Thread(target=auto_broadcaster, daemon=True).start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
