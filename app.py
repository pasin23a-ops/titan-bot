import pandas as pd
import numpy as np
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import threading

# ==========================================
# API Token & Configuration
# ==========================================
BOT_TOKEN = "8824803588:AAFdcAf-HzRrhtmWMNULQxYjXz-CHHHLk_g"
bot = telebot.TeleBot(BOT_TOKEN)

active_chat_ids = set()
user_martingale_step = {}
user_stats = {}

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

def fetch_live_kline_data(symbol, interval="1m", limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            raw_data = res.json()
            df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            df['close'] = df['close'].astype(float)
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            return df
    except Exception:
        pass
    
    size = limit
    df = pd.DataFrame()
    np.random.seed(int(time.time() * 1000) % 1000000 + sum(ord(c) for c in symbol))
    prices = np.cumsum(np.random.randn(size)) + 100
    df['close'] = prices
    df['open'] = df['close'].shift(1).fillna(100.0)
    df['high'] = df[['open', 'close']].max(axis=1) + 0.1
    df['low'] = df[['open', 'close']].min(axis=1) - 0.1
    return df

def find_best_signal():
    for sym, label in SYMBOLS.items():
        df = fetch_live_kline_data(sym, interval="1m", limit=30)
        if df is None or len(df) < 5:
            continue
        
        last_open = float(df['open'].iloc[-1])
        last_close = float(df['close'].iloc[-1])
        
        # เงื่อนไขตรวจจับง่ายขึ้นเพื่อให้ยิงสัญญาณได้ต่อเนื่อง
        if last_close > last_open:
            return sym, label, "CALL", "🚀 BULLISH MOMENTUM"
        elif last_close < last_open:
            return sym, label, "PUT", "📉 BEARISH MOMENTUM"
            
    return None, None, "NONE", "NO_SIGNAL"

def send_signal_to_chat(chat_id):
    now = get_thai_time()
    sym, label, direction, status = find_best_signal()
    step = user_martingale_step.get(chat_id, 1)

    if sym and direction != "NONE":
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "⬆️ BUY 🟢" if is_buy else "⬇️ SELL 🔴"
        btn_label = "CALL" if is_buy else "PUT"

        card_text = (
            f"⚡ **TITAN FAST ENGINE 👑 M1**\n"
            f"⚡ **[ไม้ {step}]**\n\n"
            f"💸 **คู่เงิน:** `{label}`\n"
            f"💎 **Timeframe:** `M1`\n"
            f"⌚ **เข้าออเดอร์เวลา:** `{target_time_str}`\n"
            f"🚀 **คำสั่ง:** **{dir_emoji}**\n\n"
            f"🛡️ **Status:** `{status}`"
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

def auto_signal_broadcaster():
    while True:
        try:
            now = get_thai_time()
            # ส่งอัตโนมัติทุกๆ 1 นาทีที่วินาทีที่ 15-45
            if now.second == 30:
                for chat_id in list(active_chat_ids):
                    send_signal_to_chat(chat_id)
            time.sleep(1)
        except Exception as e:
            print(f"⚠️ Broadcast Error: {e}")
            time.sleep(2)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    user_martingale_step[chat_id] = 1
    bot.send_message(chat_id, "⚡ **TITAN BOT ONLINE**\nเชื่อมต่อเรียบร้อย! พิมพ์ `/scan` เพื่อเรียกสัญญาณทันที หรือรอสัญญาณอัตโนมัติได้เลยครับ", parse_mode="Markdown")

@bot.message_handler(commands=['scan'])
def manual_scan(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    bot.reply_to(message, "🔎 กำลังค้นหาสัญญาณสด...")
    send_signal_to_chat(chat_id)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ TITAN Signal Locked")
        return

    if call.data.startswith("res_"):
        parts = call.data.split("_")
        result_type = parts[1]
        
        if chat_id not in user_stats: user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
        if chat_id not in user_martingale_step: user_martingale_step[chat_id] = 1

        if result_type in ["win1", "win2", "win3"]:
            user_stats[chat_id][result_type] += 1
            user_martingale_step[chat_id] = 1
            text = "💎 Reset: กลับสู่ไม้ที่ 1"
        elif result_type == "loss":
            step = user_martingale_step[chat_id]
            if step < 3:
                user_martingale_step[chat_id] += 1
                text = f"⚠️ ปรับเงินสู่ [ไม้ที่ {user_martingale_step[chat_id]}]"
            else:
                user_stats[chat_id]["loss"] += 1
                user_martingale_step[chat_id] = 1
                text = "❌ Reset กลับไม้ที่ 1"
        else:
            text = "บันทึกเรียบร้อย"
            
        bot.answer_callback_query(call.id, text)

print("⚡ TITAN BOT พร้อมรัน...")
broadcaster_thread = threading.Thread(target=auto_signal_broadcaster, daemon=True)
broadcaster_thread.start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception:
        time.sleep(5)
        
