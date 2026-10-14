import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import threading
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
    best_sym = None
    best_dir = "NONE"
    best_status = "ALPHA ULTIMATE FILTER"

    symbol_keys = list(SYMBOLS.keys())
    random.shuffle(symbol_keys)

    for sym in symbol_keys:
        df = fetch_kline(symbol=sym, interval="1m", limit=30)
        if df is None or len(df) < 25:
            continue

        c1 = float(df['close'].iloc[-2]) # แท่งล่าสุดที่ปิดแล้ว
        o1 = float(df['open'].iloc[-2])
        h1 = float(df['high'].iloc[-2])
        l1 = float(df['low'].iloc[-2])

        c2 = float(df['close'].iloc[-3]) # แท่งก่อนหน้า
        o2 = float(df['open'].iloc[-3])
        
        c3 = float(df['close'].iloc[-4]) # แท่งที่สาม
        o3 = float(df['open'].iloc[-4])

        body1 = abs(c1 - o1)
        range1 = h1 - l1
        
        # เงื่อนไขความคมชัดสูงสุด: เนื้อเทียนต้องหนา > 70% และ 3 แท่งต้องเรียงสีเดียวกันเป๊ะ (ห้ามสลับสี)
        if range1 > 0 and (body1 / range1) >= 0.7:
            if c1 > o1 and c2 > o2 and c3 > o3:
                best_sym = sym
                best_dir = "CALL"
                best_status = "ALPHA STRONG UPTREND (3-CANDLE LOCK)"
                break
            elif c1 < o1 and c2 < o2 and c3 < o3:
                best_sym = sym
                best_dir = "PUT"
                best_status = "ALPHA STRONG DOWNTREND (3-CANDLE LOCK)"
                break

    # หากรอบไหนไม่มีคู่ไหนผ่านเกณฑ์ 3 แท่งเข้มข้น บอทจะนิ่งไว้ก่อนเพื่อความปลอดภัยสูงสุด (ไม่ฝืนส่งมั่วซั่ว)
    if best_sym and best_dir != "NONE":
        label = SYMBOLS.get(best_sym, best_sym)
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')
        
        is_buy = (best_dir == "CALL")
        dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
        btn_label = "CALL" if is_buy else "PUT"
        step = user_martingale_step.get(chat_id, 1)

        card_text = (
            f"⚡ **TITAN ALPHA (v19.0 Ultimate Sniper)** ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🥊 **การเดินเงิน:** `ไม้ที่ {step}`\n"
            f"🎯 **คู่คำนวณสด:** `{label}` *(ผ่านเกณฑ์ความคมชัดสูงสุด)*\n"
            f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
            f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
            f"📊 **สถานะ:** `{best_status}`\n"
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
    else:
        # ถ้าไม่มีคู่ไหนผ่านเกณฑ์ 3 แท่งทองคำ แจ้งเตือนเพื่อให้รอก่อน ป้องกันการกดมั่ว
        try:
            bot.send_message(chat_id, "⚠️ **ตลาดกำลังผันผวนหรือไซด์เวย์!** ระบบ Alpha บล็อกสัญญาณไว้เพื่อความปลอดภัย กรุณากดขอสัญญาณใหม่อีกครั้งในรอบถัดไปครับ", parse_mode="Markdown")
        except Exception:
            pass

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    if chat_id not in user_martingale_step:
        user_martingale_step[chat_id] = 1
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อขอสัญญาณแรก (ALPHA SIGNAL)", callback_data="request_next_signal"))
    
    bot.reply_to(
        message, 
        "🚀 **TITAN ALPHA v19.0 ACTIVATED** 🚀\n"
        "เปิดระบบ Ultimate Sniper มั่นใจค่อยส่งสัญญาณ ไม่มั่นใจตัดทิ้ง ลุยกันใหม่เพื่อกู้พอร์ตคืนครับนาย!", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Alpha Sniper Active")
        return
        
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "🎯 กำลังสแกนหาจังหวะทองคำ...")
        generate_signal_on_demand(chat_id)
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

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
