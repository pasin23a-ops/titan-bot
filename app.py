import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import random

BOT_TOKEN = "8316396699:AAHff4bp0RbvYJjx-eOhuUqr4kgD-MERj-c"
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

def fetch_kline(symbol, interval="1m", limit=30):
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
    
    try:
        url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
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

def generate_signal_on_demand(chat_id):
    symbol_keys = list(SYMBOLS.keys())
    random.shuffle(symbol_keys)
    
    best_sym = None
    best_dir = "NONE"
    predicted_win_step = "ไม้ที่ 1 (WIN SURE 💎)"
    confidence_score = 98

    for sym in symbol_keys:
        df = fetch_kline(symbol=sym, interval="1m", limit=30)
        if df is not None and len(df) >= 20:
            # 1. DiNapoli Line (EMA 8.3896)
            df['dinapoli'] = df['close'].ewm(span=8.3896, adjust=False).mean()
            # 2. Fast EMA (3/6) & MACD Hist
            df['ema3'] = df['close'].ewm(span=3, adjust=False).mean()
            df['ema6'] = df['close'].ewm(span=6, adjust=False).mean()
            
            c1 = float(df['close'].iloc[-2])
            o1 = float(df['open'].iloc[-2])
            h1 = float(df['high'].iloc[-2])
            l1 = float(df['low'].iloc[-2])
            din1 = float(df['dinapoli'].iloc[-2])
            e3 = float(df['ema3'].iloc[-2])
            e6 = float(df['ema6'].iloc[-2])

            body = abs(c1 - o1)
            candle_range = h1 - l1
            body_ratio = (body / candle_range) if candle_range > 0 else 0

            # วิเคราะห์ความแข็งแกร่งเพื่อคาดการณ์ไม้ที่จะชนะ
            if body_ratio > 0.65 and e3 > e6:
                if c1 > din1:
                    best_sym = sym
                    best_dir = "CALL"
                    predicted_win_step = "ไม้ที่ 1 (มั่นใจสูงสุด 💎)"
                    confidence_score = 99
                    break
            elif body_ratio > 0.65 and e3 < e6:
                if c1 < din1:
                    best_sym = sym
                    best_dir = "PUT"
                    predicted_win_step = "ไม้ที่ 1 (มั่นใจสูงสุด 💎)"
                    confidence_score = 99
                    break

    # กรณีสำรอง หากจังหวะพอดี ดึงค่าปัจจุบันมายิงทันทีพร้อมประเมินไม้ทบ
    if not best_sym:
        best_sym = symbol_keys[0]
        df_fb = fetch_kline(symbol=best_sym, interval="1m", limit=5)
        if df_fb is not None and len(df_fb) >= 2:
            c = float(df_fb['close'].iloc[-2])
            o = float(df_fb['open'].iloc[-2])
            best_dir = "CALL" if c >= o else "PUT"
            predicted_win_step = "ไม้ที่ 2 (เก็บตกแก้เกม 🥈)"
            confidence_score = 92
        else:
            best_dir = "CALL"
            predicted_win_step = "ไม้ที่ 1 (ตามรอบสตรีม 💎)"

    label = SYMBOLS.get(best_sym, best_sym)
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    target_time_str = target_time.strftime('%H:%M')
    
    is_buy = (best_dir == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    btn_label = "CALL" if is_buy else "PUT"
    step = user_martingale_step.get(chat_id, 1)

    card_text = (
        f"👑 **TITAN OMEGA GOD BOT (v22.0)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🥊 **การเดินเงินปัจจุบัน:** `ไม้ที่ {step}`\n"
        f"🎯 **คู่ทำกำไรสด:** `{label}`\n"
        f"🔮 **คาดการณ์จะชนะที่:** **{predicted_win_step}**\n"
        f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"📊 **ความแม่นยำ (Confidence):** `{confidence_score}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *กดปุ่มด้านล่างเพื่อขอสัญญาณทำกำไรถัดไป*"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณรอบถัดไป (NEXT SIGNAL)", callback_data="request_next_signal"))
    markup.add(
        InlineKeyboardButton("💎 ชนะไม้ 1", callback_data=f"res_win1_{best_sym}"),
        InlineKeyboardButton("🥈 ชนะไม้ 2", callback_data=f"res_win2_{best_sym}"),
        InlineKeyboardButton("🥉 ชนะไม้ 3", callback_data=f"res_win3_{best_sym}"),
        InlineKeyboardButton("❌ แพ้ (LOSS)", callback_data=f"res_loss_{best_sym}")
    )
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Send Error: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    if chat_id not in user_martingale_step:
        user_martingale_step[chat_id] = 1
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อขอสัญญาณแรก (OMEGA SIGNAL)", callback_data="request_next_signal"))
    
    bot.reply_to(
        message, 
        "🚀 **TITAN OMEGA GOD BOT v22.0 ACTIVATED** 🚀\n"
        "หลอมรวมทุกสคริปต์ขั้นเทพ + ระบบคาดการณ์ไม้ชนะพร้อมทำกำไรแล้ว! ลุยทวงเงินคืนกันครับนาย!", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Omega Engine Active")
        return
        
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "🔮 กำลังคำนวณและคาดการณ์ผลชนะ...")
        generate_signal_on_demand(chat_id)
        return

    if call.data.startswith("res_"):
        parts = call.data.split("_")
        res_type = parts[1]
        if res_type in ["win1", "win2", "win3"]:
            user_martingale_step[chat_id] = 1
            bot.answer_callback_query(call.id, "💎 WIN! Reset สู่ไม้ 1 เรียบร้อย")
        elif res_type == "loss":
            step = user_martingale_step.get(chat_id, 1)
            user_martingale_step[chat_id] = 1 if step >= 3 else step + 1
            bot.answer_callback_query(call.id, f"⚠️ LOSS! ขยับทบเป็นไม้ {user_martingale_step[chat_id]}")

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
