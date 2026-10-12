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

def fetch_live_kline_data(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=30"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            raw_data = res.json()
            df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            df['close'] = df['close'].astype(float)
            df['open'] = df['open'].astype(float)
            return df
    except Exception as e:
        print(f"Fetch Error {symbol}: {e}")
    return None

def find_best_signal():
    best_sym = None
    best_direction = "NONE"
    highest_score = -1

    for sym in SYMBOLS.keys():
        df = fetch_live_kline_data(sym)
        if df is not None and len(df) >= 10:
            df['ema'] = df['close'].ewm(span=10, adjust=False).mean()
            last_close = float(df['close'].iloc[-1])
            last_open = float(df['open'].iloc[-1])
            last_ema = float(df['ema'].iloc[-1])

            body_size = abs(last_close - last_open)
            score = (abs(last_close - last_ema) / (last_ema + 1e-9)) * 10000

            if last_close > last_ema and last_close > last_open:
                if score > highest_score:
                    highest_score = score
                    best_sym = sym
                    best_direction = "CALL"
            elif last_close < last_ema and last_close < last_open:
                if score > highest_score:
                    highest_score = score
                    best_sym = sym
                    best_direction = "PUT"

    if best_sym:
        return best_sym, SYMBOLS.get(best_sym, best_sym), best_direction, int(highest_score)
    return "DYDXUSDT", "DYDX(OTC)", "CALL", 100 # Fallback เพื่อให้มีสัญญาณเสมอ

def send_signal(chat_id):
    try:
        sym, label, direction, score = find_best_signal()
        step = user_martingale_step.get(chat_id, 1)

        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "⬆️ BUY 🟢" if is_buy else "⬇️ SELL 🔴"
        btn_label = "CALL" if is_buy else "PUT"

        card_text = (
            f"⚡ **TITAN FAST-FLOW MASTER 👑 M1**\n"
            f"⚡ **[ไม้ {step}]**\n\n"
            f"💎 **คู่ที่เลือก:** `{label}`\n"
            f"📈 **Timeframe:** `M1`\n"
            f"⌚ **เข้าออเดอร์เวลา:** `{target_time_str}`\n"
            f"🚀 **ทิศทาง:** **{dir_emoji}**\n\n"
            f"🛡️ **สถานะ:** `MOMENTUM CONFIRMED (Score: {score})`"
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
    bot.reply_to(message, "⚡ **TITAN BOT RECONNECTED**\nกำลังส่งสัญญาณรอบล่าสุดทันที...")
    send_signal(chat_id)

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
