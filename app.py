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
cooldown_status = {}
last_signal_time = {}

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

def fetch_live_kline_data(symbol, interval="1m", limit=50):
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
            df['volume'] = df['volume'].astype(float)
            return df
    except Exception:
        pass
    return None

# ==========================================
# Fast & Responsive Trend Engine (สัญญาณมาไว)
# ==========================================
def analyze_fast_momentum(symbol):
    df = fetch_live_kline_data(symbol, interval="1m", limit=30)
    if df is None or len(df) < 20:
        return "NONE", 0, "NO_DATA"

    # คำนวณ EMA ระยะสั้นเพื่อดูโมเมนตัมปัจจุบัน
    df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
    
    last_open = float(df['open'].iloc[-1])
    last_close = float(df['close'].iloc[-1])
    last_ema = float(df['ema_10'].iloc[-1])
    
    body_size = abs(last_close - last_open)
    if body_size < 0.00001:
        return "NONE", 0, "DOJI"

    # คำนวณ Score จากความห่างราคาปัจจุบันกับเส้น EMA
    score = (abs(last_close - last_ema) / last_ema) * 10000

    # เงื่อนไขยืดหยุ่นเพื่อให้ส่งสัญญาณได้ต่อเนื่องทุกรอบ
    if last_close > last_ema and last_close > last_open:
        return "CALL", score, f"🚀 BULLISH MOMENTUM (Score: {int(score)})"
    elif last_close < last_ema and last_close < last_open:
        return "PUT", score, f"📉 BEARISH MOMENTUM (Score: {int(score)})"

    return "NONE", 0, "NO_TREND"

def find_active_signal():
    best_sym = None
    best_direction = "NONE"
    best_status = "NO_SIGNAL"
    highest_score = -1

    # กวาดทุกคู่ แล้วเลือกตัวที่มีโมเมนตัมเด่นชัดที่สุดในรอบนั้นมาส่งทันที
    for sym in SYMBOLS.keys():
        direction, score, status = analyze_fast_momentum(sym)
        if direction != "NONE" and score > highest_score:
            highest_score = score
            best_sym = sym
            best_direction = direction
            best_status = status

    if best_sym:
        return best_sym, SYMBOLS.get(best_sym, best_sym), best_direction, best_status
    return None, None, "NONE", "WAITING"

def send_signal_card(chat_id):
    sym, label, direction, status = find_active_signal()
    step = user_martingale_step.get(chat_id, 1)

    if sym and direction != "NONE":
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

def auto_signal_broadcaster():
    last_sent_minute = -1
    while True:
        try:
            now = get_thai_time()
            # ส่งสัญญาณทุกๆ นาที ตรงวินาทีที่ 30 แบบเป๊ะๆ
            if now.second == 30 and now.minute != last_sent_minute:
                last_sent_minute = now.minute
                for chat_id in list(active_chat_ids):
                    send_signal_card(chat_id)
            time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Broadcast Error: {e}")
            time.sleep(2)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    user_martingale_step[chat_id] = 1
    bot.send_message(chat_id, "⚡ **TITAN FAST-FLOW BOT ONLINE**\nระบบสแกนไว สัญญาณมาต่อเนื่องทุกนาทีพร้อมทำงานแล้ว! พิมพ์ `/scan` เพื่อทดสอบได้ทันที", parse_mode="Markdown")

@bot.message_handler(commands=['scan'])
def manual_scan(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    bot.reply_to(message, "🔎 กำลังสแกนหาคู่ที่โมเมนตัมแรงที่สุด...")
    send_signal_card(chat_id)

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
            text = "💎 Win Reset: กลับสู่ไม้ที่ 1 เรียบร้อย"
        elif result_type == "loss":
            step = user_martingale_step[chat_id]
            if step < 3:
                user_martingale_step[chat_id] += 1
                text = f"⚠️ ปรับแผนเงินสู่ [ไม้ที่ {user_martingale_step[chat_id]}]"
            else:
                user_stats[chat_id]["loss"] += 1
                user_martingale_step[chat_id] = 1
                text = "❌ Loss Reset: กลับสู่ไม้ที่ 1"
        else:
            text = "บันทึกเรียบร้อย"
            
        bot.answer_callback_query(call.id, text)

print("--------------------------------------------------")
print("⚡ TITAN FAST-FLOW ENGINE พร้อมรันบน Railway...")
print("--------------------------------------------------")

broadcaster_thread = threading.Thread(target=auto_signal_broadcaster, daemon=True)
broadcaster_thread.start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(5)
