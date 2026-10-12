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
last_global_signal_time = 0 
symbol_cooldown = {}

best_candidate_cache = {
    "symbol": "DYDXUSDT",
    "label": "DYDX(OTC)",
    "direction": "CALL",
    "status": "INITIALIZING",
    "score": 0
}

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

def fetch_kline(symbol, interval="1m", limit=40):
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

def smart_balanced_analyze(symbol):
    df = fetch_kline(symbol, "1m", 40)
    if df is None or len(df) < 30:
        return "CALL", 50, "DEFAULT_SAFE"

    df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()

    o = float(df['open'].iloc[-2])
    c = float(df['close'].iloc[-2])
    h = float(df['high'].iloc[-2])
    l = float(df['low'].iloc[-2])
    
    ema10 = float(df['ema_10'].iloc[-2])
    ema20 = float(df['ema_20'].iloc[-2])

    # ตรวจสอบแนวรับ-แนวต้านแบบยืดหยุ่น (เตือนเฉยๆ แต่ไม่บล็อกจนขาดสัญญาณ)
    recent_high = df['high'].iloc[-20:-2].max()
    recent_low = df['low'].iloc[-20:-2].min()
    
    score = int((abs(c - ema20) / (ema20 + 1e-9)) * 10000)

    # เช็กทิศทางตาม EMA และราคาปิด
    if c >= ema10 and c >= ema20:
        # ถ้าใกล้แนวต้าน ให้ลดคะแนนลงนิดหน่อยแต่ยังให้ไปต่อได้ถ้าแรงส่งดี
        penalty = 200 if abs(c - recent_high) / (recent_high + 1e-9) < 0.01 else 0
        final_score = score + 500 - penalty
        return "CALL", final_score, f"TREND UP (Score: {final_score})"
    else:
        penalty = 200 if abs(c - recent_low) / (recent_low + 1e-9) < 0.01 else 0
        final_score = score + 500 - penalty
        return "PUT", final_score, f"TREND DOWN (Score: {final_score})"

def background_deep_scanner():
    global best_candidate_cache
    while True:
        try:
            now_t = time.time()
            expired_syms = [s for s, t in symbol_cooldown.items() if now_t - t > 120]
            for s in expired_syms:
                del symbol_cooldown[s]

            top_sym = None
            top_dir = "NONE"
            top_status = "SCANNING"
            highest_score = -99999

            for sym in SYMBOLS.keys():
                if sym in symbol_cooldown:
                    continue

                direction, score, status = smart_balanced_analyze(sym)
                if score > highest_score:
                    highest_score = score
                    top_sym = sym
                    top_dir = direction
                    top_status = status

            # บังคับเลือกคู่ที่ดีที่สุดเสมอ ไม่ให้เป็นค่าว่าง
            if not top_sym:
                top_sym = list(SYMBOLS.keys())[0]
                top_dir, highest_score, top_status = smart_balanced_analyze(top_sym)

            if top_sym:
                best_candidate_cache = {
                    "symbol": top_sym,
                    "label": SYMBOLS.get(top_sym, top_sym),
                    "direction": top_dir,
                    "status": top_status,
                    "score": highest_score
                }
            time.sleep(2)
        except Exception as e:
            print(f"Scanner Error: {e}")
            time.sleep(3)

def send_signal(chat_id):
    global last_global_signal_time
    try:
        now_time = time.time()
        if now_time - last_global_signal_time < 65:
            return

        sym = best_candidate_cache["symbol"]
        label = best_candidate_cache["label"]
        direction = best_candidate_cache["direction"]
        status = best_candidate_cache["status"]

        symbol_cooldown[sym] = now_time
        last_global_signal_time = now_time

        step = user_martingale_step.get(chat_id, 1)
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "⬆️ BUY 🟢 (Optimized Trend)" if is_buy else "⬇️ SELL 🔴 (Optimized Trend)"
        btn_label = "CALL" if is_buy else "PUT"

        card_text = (
            f"👑 **TITAN CONTINUOUS MASTER 👑 M1**\n"
            f"⚡ **[ไม้ {step}]**\n\n"
            f"🔥 **คู่ที่ดีที่สุดรอบนี้:** `{label}`\n"
            f"📈 **Timeframe:** `M1 (Balanced Filter + Force Emit)`\n"
            f"⌚ **เข้าออเดอร์เวลา:** `{target_time_str}`\n"
            f"🚀 **ทิศทาง:** **{dir_emoji}**\n\n"
            f"🛡️ **สถานะ:** `{status}`\n"
            f"⏱️ **Cooldown:** `พักคู่เดิม 2 นาที / ส่งต่อเนื่องทุกนาที`"
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
    bot.reply_to(message, "⚡ **TITAN CONTINUOUS MODE ONLINE**\nเปิดระบบส่งสัญญาณต่อเนื่องทุกรอบนาที พร้อมกรองความเสี่ยงเรียบร้อย!", parse_mode="Markdown")

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

threading.Thread(target=background_deep_scanner, daemon=True).start()
threading.Thread(target=auto_broadcaster, daemon=True).start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
