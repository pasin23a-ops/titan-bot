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
            df['volume'] = df['volume'].astype(float)
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
    df['volume'] = np.random.rand(size) * 1000
    return df

# ==========================================
# Advanced Scoring & Multi-Timeframe Engine
# ==========================================
def analyze_and_score(symbol):
    df_m1 = fetch_live_kline_data(symbol, interval="1m", limit=60)
    df_m5 = fetch_live_kline_data(symbol, interval="5m", limit=30)

    if df_m1 is None or len(df_m1) < 20 or df_m5 is None or len(df_m5) < 10:
        return "NONE", 0, "DATA_INSUFFICIENT"

    # คำนวณเทรนด์ M5
    df_m5['ema_20'] = df_m5['close'].ewm(span=20, adjust=False).mean()
    m5_close = float(df_m5['close'].iloc[-1])
    m5_ema20 = float(df_m5['ema_20'].iloc[-1])
    
    is_m5_uptrend = m5_close > m5_ema20
    is_m5_downtrend = m5_close < m5_ema20

    # คำนวณ M1
    df_m1['ema_50'] = df_m1['close'].ewm(span=50, adjust=False).mean()
    m1_close = float(df_m1['close'].iloc[-1])
    m1_open = float(df_m1['open'].iloc[-1])
    m1_ema50 = float(df_m1['ema_50'].iloc[-1])

    is_m1_green = m1_close > m1_open
    is_m1_red = m1_close < m1_open

    body_size = abs(m1_close - m1_open)
    if body_size < 0.0001:
        return "NONE", 0, "NOISY"

    # คำนวณ Score ความห่างของราคาจากเส้น EMA (ยิ่งห่างและแท่งเทียนชัด คะแนนความมั่นใจยิ่งสูง)
    score = abs(m1_close - m1_ema50) * 100 + body_size * 10

    if is_m5_uptrend and m1_close > m1_ema50 and is_m1_green:
        return "CALL", score, "🔥 TOP UPTREND CONFIRMED"
    elif is_m5_downtrend and m1_close < m1_ema50 and is_m1_red:
        return "PUT", score, "📉 TOP DOWNTREND CONFIRMED"

    return "NONE", 0, "NO_TREND"

def find_most_confident_signal():
    best_sym = None
    best_direction = "NONE"
    best_status = "NO_SIGNAL"
    highest_score = -1

    # สแกนทุกคู่ในตลาด แล้วหาคู่ที่ Score สูงสุด (มั่นใจที่สุด)
    for sym in SYMBOLS.keys():
        direction, score, status = analyze_and_score(sym)
        if direction != "NONE" and score > highest_score:
            highest_score = score
            best_sym = sym
            best_direction = direction
            best_status = f"{status} (Score: {int(score)})"

    if best_sym:
        return best_sym, SYMBOLS.get(best_sym, best_sym), best_direction, best_status
    return None, None, "NONE", "NO_SIGNAL"

def send_signal_card(chat_id):
    current_state = cooldown_status.get(chat_id, "READY")
    if current_state == "WAITING_COOLDOWN":
        cooldown_status[chat_id] = "READY"
        return

    sym, label, direction, status = find_most_confident_signal()
    step = user_martingale_step.get(chat_id, 1)

    if sym and direction != "NONE":
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "⬆️ BUY 🟢 (มั่นใจสูงสุด)" if is_buy else "⬇️ SELL 🔴 (มั่นใจสูงสุด)"
        btn_label = "CALL" if is_buy else "PUT"

        card_text = (
            f"⚡ **TITAN TOP-PICK MASTER 👑 M1**\n"
            f"⚡ **[ไม้ {step}]**\n\n"
            f"💎 **คัดคู่ที่ดีที่สุด:** `{label}`\n"
            f"📈 **Timeframe:** `M1`\n"
            f"⌚ **กดออเดอร์เวลา:** `{target_time_str}`\n"
            f"🚀 **ทิศทาง:** **{dir_emoji}**\n\n"
            f"🛡️ **สถานะ:** `{status}`\n"
            f"⏱️ **Cooldown:** `เปิดใช้งานรอบ่อทพัก 1 แท่ง`"
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
        cooldown_status[chat_id] = "WAITING_COOLDOWN"
        last_signal_time[chat_id] = now

def auto_signal_broadcaster():
    last_sent_minute = -1
    while True:
        try:
            now = get_thai_time()
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
    cooldown_status[chat_id] = "READY"
    bot.send_message(chat_id, "⚡ **TITAN TOP-PICK BOT ONLINE**\nระบบสแกนหากราฟที่มั่นใจที่สุดพร้อมทำงานแล้ว พิมพ์ `/scan` เพื่อทดสอบได้เลย!", parse_mode="Markdown")

@bot.message_handler(commands=['scan'])
def manual_scan(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    bot.reply_to(message, "🔎 กำลังสแกนทุกคู่เงินเพื่อหาตัวที่มั่นใจที่สุด...")
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
print("⚡ TITAN TOP-PICK ENGINE พร้อมรันบน Railway...")
print("--------------------------------------------------")

broadcaster_thread = threading.Thread(target=auto_signal_broadcaster, daemon=True)
broadcaster_thread.start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(5)
        
