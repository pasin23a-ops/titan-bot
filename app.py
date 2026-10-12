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
user_selected_symbol = {}  # เก็บค่าคู่เงินที่ผู้ใช้เลือกเอง (แยกตามแชท)

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

def fetch_kline(symbol, interval="1m", limit=30):
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
            return df
    except Exception:
        pass
    return None

def analyze_symbol(symbol):
    df = fetch_kline(symbol, "1m", 30)
    if df is None or len(df) < 20:
        return "CALL", 0, "NEUTRAL"

    df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()

    c = float(df['close'].iloc[-2])
    o = float(df['open'].iloc[-2])
    ema10 = float(df['ema_10'].iloc[-2])
    ema20 = float(df['ema_20'].iloc[-2])

    # เช็กความแรงและทิศทางเทรนด์
    if c > ema10 and ema10 > ema20 and c > o:
        return "CALL", 80, "STRONG UPTREND"
    elif c < ema10 and ema10 < ema20 and c < o:
        return "PUT", 80, "STRONG DOWNTREND"
    elif c >= ema20:
        return "CALL", 40, "WEAK UPTREND"
    else:
        return "PUT", 40, "WEAK DOWNTREND"

def send_signal_for_symbol(chat_id, sym):
    try:
        label = SYMBOLS.get(sym, sym)
        direction, score, status = analyze_symbol(sym)

        step = user_martingale_step.get(chat_id, 1)
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "⬆️ BUY 🟢" if is_buy else "⬇️ SELL 🔴"
        btn_label = "CALL" if is_buy else "PUT"

        card_text = (
            f"👑 **TITAN MANUAL SELECTOR 👑 M1**\n"
            f"⚡ **[ไม้ {step}]**\n\n"
            f"🎯 **คู่ที่คุณเลือก:** `{label}`\n"
            f"📈 **Timeframe:** `M1 (Manual Pick)`\n"
            f"⌚ **เข้าออเดอร์เวลา:** `{target_time_str}`\n"
            f"🚀 **ทิศทาง:** **{dir_emoji}**\n\n"
            f"🛡️ **สถานะ:** `{status} (Score: {score})`"
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

@bot.message_handler(commands=['start', 'pair', 'menu'])
def handle_menu(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    if chat_id not in user_martingale_step:
        user_martingale_step[chat_id] = 1

    # สร้างปุ่มช้อยส์คู่เงินทั้งหมด 21 คู่ พร้อมเช็กสีความมั่นใจ (เขียว = มั่นใจสูง, แดง = ยังไม่มั่นใจ)
    markup = InlineKeyboardMarkup(row_width=2)
    for sym, label in SYMBOLS.items():
        _, score, _ = analyze_symbol(sym)
        # ถ้าคะแนน >= 70 ให้เป็นสีเขียว (มั่นใจ) ถ้าต่ำกว่าให้เป็นสีแดง (ไม่มั่นใจ)
        dot = "🟢" if score >= 70 else "🔴"
        btn_text = f"{dot} {label}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"select_{sym}"))

    bot.reply_to(
        message, 
        "⚡ **TITAN MANUAL CHOOSE MODE** ⚡\n"
        "เลือกคู่เงินที่ต้องการเทรนด์ด้านล่างได้เลยครับ:\n"
        "🟢 = บอทมั่นใจ (โครงสร้างเทรนด์ชัด)\n"
        "🔴 = บอทมองว่ายังไม่ค่อยนิ่ง/ความมั่นใจต่ำ", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Signal Locked")
        return

    # เมื่อผู้ใช้กดเลือกคู่เงินจากช้อยส์
    if call.data.startswith("select_"):
        sym = call.data.replace("select_", "")
        user_selected_symbol[chat_id] = sym
        bot.answer_callback_query(call.id, f"✅ เลือก {SYMBOLS.get(sym, sym)} แล้ว!")
        send_signal_for_symbol(chat_id, sym)
        return

    # จัดการผลแพ้ชนะ (Martingale)
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

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
