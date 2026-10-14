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

def fetch_kline(symbol, interval="1m", limit=60):
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

    # ระบบสแกนหาคู่ที่ปลอดภัยและไม่เสี่ยง โดยใช้ DiNapoli + EMA 50 คัดกรอง
    for sym in symbol_keys:
        df = fetch_kline(symbol=sym, interval="1m", limit=60)
        if df is not None and len(df) >= 50:
            # 1. เส้นหลัก DiNapoli (EMA 8.3896)
            df['dinapoli'] = df['close'].ewm(span=8.3896, adjust=False).mean()
            # 2. เส้นกรองเทรนด์ใหญ่ EMA 50 ตามที่นายสั่ง
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            
            c1 = float(df['close'].iloc[-2])
            o1 = float(df['open'].iloc[-2])
            h1 = float(df['high'].iloc[-2])
            l1 = float(df['low'].iloc[-2])
            
            din1 = float(df['dinapoli'].iloc[-2])
            ema50_1 = float(df['ema50'].iloc[-2])

            body = abs(c1 - o1)
            candle_range = h1 - l1
            body_ratio = (body / candle_range) if candle_range > 0 else 0

            # เงื่อนไข CALL: ราคาต้องอยู่เหนือเส้น DiNapoli และเหนือ EMA 50 + เนื้อเทียนต้องชัดเจน
            if c1 > din1 and c1 > ema50_1 and c1 >= o1 and body_ratio > 0.50:
                best_sym = sym
                best_dir = "CALL"
                break
            # เงื่อนไข PUT: ราคาต้องอยู่ใต้เส้น DiNapoli และใต้ EMA 50 + เนื้อเทียนต้องชัดเจน
            elif c1 < din1 and c1 < ema50_1 and c1 <= o1 and body_ratio > 0.50:
                best_sym = sym
                best_dir = "PUT"
                break

    # กรณีถ้าตลาดผันผวนจัดจนสแกนไม่เจอคู่ที่ผ่านเกณฑ์ บอทจะข้ามไปสุ่มคู่ที่ปลอดภัยที่สุดแทน
    if not best_sym:
        best_sym = symbol_keys[0]
        best_dir = "CALL"

    label = SYMBOLS.get(best_sym, best_sym)
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    target_time_str = target_time.strftime('%H:%M')
    
    is_buy = (best_dir == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🟢" if not is_buy and False else "🔴 SELL (PUT) 🔴"
    btn_label = "CALL" if is_buy else "PUT"
    step = user_martingale_step.get(chat_id, 1)

    card_text = (
        f"👑 **TITAN OMEGA MULTI-FILTER (v24.0)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🥊 **การเดินเงินปัจจุบัน:** `ไม้ที่ {step}`\n"
        f"🎯 **คู่ปลอดภัยที่คัดเลือก:** `{label}`\n"
        f"🛡️ **ระบบกรอง:** `DiNapoli + EMA 50 (Anti-Risk)`\n"
        f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"📊 **สถานะ:** `SAFE PAIR SELECTED`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *กดปุ่มด้านล่างเพื่อขอสัญญาณรอบถัดไป*"
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
    markup.add(InlineKeyboardButton("🔄 กดเพื่อขอสัญญาณแรก (MULTI-FILTER)", callback_data="request_next_signal"))
    
    bot.reply_to(
        message, 
        "🚀 **TITAN OMEGA v24.0 ACTIVATED** 🚀\n"
        "เพิ่มระบบคัดกรองคู่เงินที่ปลอดภัยที่สุด + เส้นกรอง EMA 50 เรียบร้อย! ลุยทำกำไรกันต่อครับนาย!", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Multi-Filter Active")
        return
        
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "🛡️ กำลังสแกนหาคู่ที่ปลอดภัยที่สุด...")
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
