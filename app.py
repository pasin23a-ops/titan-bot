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

best_autopilot_cache = {
    "symbol": "",
    "label": "",
    "direction": "NONE",
    "status": "STRICT_TREND_MODE",
    "score": 0
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval="1m", limit=30):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=2.5)
        if res.status_code == 200:
            raw = res.json()
            df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            df['close'] = df['close'].astype(float)
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            return df
    except Exception:
        pass

    try:
        url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=2.5)
        if res.status_code == 200:
            raw = res.json()
            df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            df['close'] = df['close'].astype(float)
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            return df
    except Exception:
        pass

    return None

def analyze_autopilot(symbol):
    df = fetch_kline(symbol, "1m", 30)
    if df is None or len(df) < 20:
        return "NONE", 0, "DATA_ERROR"

    df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()

    c = float(df['close'].iloc[-2])
    o = float(df['open'].iloc[-2])
    ema10 = float(df['ema_10'].iloc[-2])
    ema20 = float(df['ema_20'].iloc[-2])

    distance_score = int((abs(c - ema20) / (ema20 + 1e-9)) * 100000)

    # คงระบบกรองแท่นเทียนและเส้น EMA เข้มงวดตามเทรนด์ 100% ห้ามสวน
    if c < o and c < ema10 and c < ema20:
        return "PUT", distance_score, "STRICT DOWNTREND"
    elif c > o and c > ema10 and c > ema20:
        return "CALL", distance_score, "STRICT UPTREND"
    
    return "NONE", distance_score, "WEAK OR SIDEWAY"

def background_scanner():
    global best_autopilot_cache
    while True:
        try:
            top_sym = None
            top_dir = "NONE"
            top_status = "SCANNING"
            highest_score = -999999

            # ไม่จำกัด PTS ขั้นต่ำ เอาเฉพาะที่ผ่านเงื่อนไขเทรนด์หลัก
            for sym in SYMBOLS.keys():
                direction, score, status = analyze_autopilot(sym)
                if score > highest_score and direction != "NONE":
                    highest_score = score
                    top_sym = sym
                    top_dir = direction
                    top_status = status

            if top_sym and top_dir != "NONE":
                best_autopilot_cache = {
                    "symbol": top_sym,
                    "label": SYMBOLS.get(top_sym, top_sym),
                    "direction": top_dir,
                    "status": top_status,
                    "score": highest_score
                }
            
            time.sleep(1)
        except Exception as e:
            print(f"Scanner Error: {e}")
            time.sleep(2)

def send_auto_signal(chat_id):
    global last_global_signal_time
    try:
        now_time = time.time()
        
        if now_time - last_global_signal_time < 60:
            return

        direction = best_autopilot_cache["direction"]
        score = best_autopilot_cache["score"]

        if direction == "NONE":
            return

        sym = best_autopilot_cache["symbol"]
        label = best_autopilot_cache["label"]
        status = best_autopilot_cache["status"]

        last_global_signal_time = now_time

        step = user_martingale_step.get(chat_id, 1)
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
        btn_label = "CALL" if is_buy else "PUT"

        card_text = (
            f"⚡ **TITAN AUTO-PILOT v6.6** ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🥊 **การเดินเงิน:** `ไม้ที่ {step}`\n"
            f"🎯 **คู่ตามเทรนด์:** `{label}`\n"
            f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
            f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
            f"📊 **สถานะเทรนด์:** `{status}`\n"
            f"🛡️ **Score Strength:** `{score} PTS`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ *Cooldown: พักระบบ 1 แท่งเทียนอัตโนมัติ*"
        )

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton(f"⚡ AUTO SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
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
        "🚀 **TITAN AUTO-PILOT v6.6 ACTIVATED** 🚀\n"
        "คงระบบกรองแท่นเทียนและ EMA ตามเทรนด์ครบถ้วน ปลดล็อคเกณฑ์ PTS แล้ว สัญญาณมาต่อเนื่องแน่นอน!", 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Trend Filter Active")
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

threading.Thread(target=background_scanner, daemon=True).start()
threading.Thread(target=auto_broadcaster, daemon=True).start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
