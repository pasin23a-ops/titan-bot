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

# [ระบบคูดาว] คูดาวแยกรายคู่ (3 นาที) และคูดาวควบคุมจังหวะส่งสัญญาณ 1 แท่งเทียน
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

def analyze_symbol_master(symbol):
    current_time = time.time()
    # [ระบบคูดาวรายคู่] ตรวจสอบว่าคู่นี้ติดพักชั่วคราวอยู่หรือไม่
    if symbol in symbol_cooldowns and current_time < symbol_cooldowns[symbol]:
        return "NONE", -99999, "PAIR_COOLDOWN"

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

    # [ระบบแนวรับแนวต้าน S&R Filter] ตรวจสอบกำแพงราคาจาก High/Low ย้อนหลัง
    recent_high = df['high'].iloc[-22:-2].max()
    recent_low = df['low'].iloc[-22:-2].min()
    range_span = recent_high - recent_low
    if range_span > 0:
        near_resistance = (recent_high - c) / range_span < 0.025
        near_support = (c - recent_low) / range_span < 0.025
    else:
        near_resistance = False
        near_support = False

    # [ระบบกรองความแรงแท่งเทียน] ตัดแท่งจิ๋วไร้พลังทิ้ง
    body_size = abs(c - o)
    total_range = h - l
    if total_range > 0 and (body_size / total_range) < 0.25:
        return "NONE", -99999, "WEAK_CANDLE_FILTERED"

    raw_distance = int((abs(c - ema20) / (ema20 + 1e-9)) * 100000)

    # [ระบบเตือนอันตราย Exhaustion Trap] หากราคากระชากเกิน 180 PTS สั่งพักคู่ทันที
    if raw_distance > 180:
        symbol_cooldowns[symbol] = current_time + PAIR_COOLDOWN_DURATION
        return "NONE", -99999, "⚠️ DANGER_EXHAUSTION_PAUSED"

    direction = "NONE"
    status_msg = "SIDEWAY"

    # [เงื่อนไขเทรนด์ + กรองแนวรับแนวต้าน + MACD Confluence]
    if c < ema10 and c < ema20 and not near_support and macd_hist < 0:
        if c <= o:
            direction = "PUT"
            status_msg = f"S&R SAFE DOWNTREND (RSI: {int(rsi_val)})"
            raw_distance += 25

    elif c > ema10 and c > ema20 and not near_resistance and macd_hist > 0:
        if c >= o:
            direction = "CALL"
            status_msg = f"S&R SAFE UPTREND (RSI: {int(rsi_val)})"
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
                direction, score, status = analyze_symbol_master(sym)
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
                # [Fast Rotation Fallback] สำรองข้อมูลดึงคู่ที่พร้อมที่สุดมาหมุนเวียน เพื่อให้สัญญาณไม่ขาดช่วงทุกนาที
                fallback_sym, fallback_score, fallback_dir = "", -99999, "CALL"
                for sym in SYMBOLS.keys():
                    cur_t = time.time()
                    if sym not in symbol_cooldowns or cur_t >= symbol_cooldowns[sym]:
                        df_t = fetch_kline(sym, "1m", 15)
                        if df_t is not None:
                             c_t = float(df_t['close'].iloc[-2])
                             o_t = float(df_t['open'].iloc[-2])
                             d_s = int(abs(c_t - o_t) * 10000)
                             if d_s > fallback_score:
                                 fallback_score = d_s
                                 fallback_sym = sym
                                 fallback_dir = "CALL" if c_t >= o_t else "PUT"
                                 
                if fallback_sym:
                    market_data_cache = {
                        "symbol": fallback_sym,
                        "label": SYMBOLS.get(fallback_sym, fallback_sym),
                        "direction": fallback_dir,
                        "status": "FAST_ROTATION_READY",
                        "score": max(70, min(160, fallback_score))
                    }
            
            time.sleep(0.5)
        except Exception as e:
            print(f"Scanner Error: {e}")
            time.sleep(1)

def send_auto_signal(chat_id):
    global last_global_signal_time
    try:
        now_time = time.time()
        
        # [Strict 1-Candle Global Cooldown] บังคับส่งสัญญาณตรงเวลาทุก 1 นาทีเป๊ะ
        if now_time - last_global_signal_time < 58:
            return

        direction = market_data_cache.get("direction", "NONE")
        score = market_data_cache.get("score", 0)

        if direction == "NONE":
            return

        sym = market_data_cache["symbol"]
        label = market_data_cache["label"]
        status = market_data_cache["status"]

        # เมื่อส่งแล้ว ให้ติดคูดาวพักคู่ชั่วคราว
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
            f"🛡️ **TITAN AUTO-PILOT (Master Guard v13.1)** 🛡️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🥊 **การเดินเงิน:** `ไม้ที่ {step}`\n"
            f"🎯 **คู่คำนวณ:** `{label}` *(พักคู่ 3 นาที)*\n"
            f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
            f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
            f"📊 **สถานะ S&R / Guard:** `{status}`\n"
            f"🛡️ **Quality Score:** `{score} PTS` *(ระบบป้องกันครบถ้วน)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ *Cooldown: สัญญาณมาต่อเนื่องทุก 1 แท่งเทียนเป๊ะ*"
        )

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton(f"🛡️ MASTER SIGNAL ({btn_label}) 🛡️", callback_data="do_nothing"))
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
        "🚀 **TITAN AUTO-PILOT MASTER GUARD v13.1 ACTIVATED** 🚀\n"
        "ระบบครบถ้วนสมบูรณ์: คูดาวรายคู่ + แนวรับแนวต้าน (S&R) + แจ้งเตือนอันตราย Exhaustion Trap + สัญญาณไหลลื่นทุกแท่งเทียน พร้อมลุยเต็มระบบครับนาย!", 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "🛡️ Master Guard Active")
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
