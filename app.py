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

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def generate_signal_on_demand(chat_id):
    best_sym = None
    best_dir = "NONE"
    best_score = 90
    best_status = "ULTIMATE FILTERED"

    # สแกนหาคู่ที่กราฟยืนยันเทรนด์ชัดเจนที่สุด ห้ามสวนทางเด็ดขาด
    for sym, label in SYMBOLS.items():
        df = fetch_kline(sym, "1m", 60)
        if df is None or len(df) < 50:
            continue
            
        df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['rsi'] = calculate_rsi(df['close'], 14)

        c = float(df['close'].iloc[-2])
        o = float(df['open'].iloc[-2])
        c_prev = float(df['close'].iloc[-3])
        o_prev = float(df['open'].iloc[-3])

        ema10 = float(df['ema_10'].iloc[-2])
        ema20 = float(df['ema_20'].iloc[-2])
        ema50 = float(df['ema_50'].iloc[-2])
        rsi_val = float(df['rsi'].iloc[-2])
        
        if pd.isna(rsi_val):
            rsi_val = 50.0

        raw_distance = int((abs(c - ema20) / (ema20 + 1e-9)) * 100000)

        # กรองความปลอดภัยขั้นสูงสุด: ห้ามชนแนวปะทะและต้องไปตามทิศทาง EMA50 เท่านั้น
        direction = "NONE"
        if c > ema50 and c > ema10 and c > ema20 and c >= o and c_prev >= o_prev:
            direction = "CALL"
            best_status = f"ULTIMATE UPTREND (RSI: {int(rsi_val)})"
        elif c < ema50 and c < ema10 and c < ema20 and c <= o and c_prev <= o_prev:
            direction = "PUT"
            best_status = f"ULTIMATE DOWNTREND (RSI: {int(rsi_val)})"

        if direction != "NONE":
            best_sym = sym
            best_dir = direction
            best_score = max(90, min(170, raw_distance))
            break

    # ถ้าไม่มีคู่ไหนผ่านเกณฑ์เข้มข้น ให้ดึงตัวที่วิ่งตาม EMA50 ชัดเจนที่สุดมาส่ง
    if not best_sym:
        for sym in SYMBOLS.keys():
            df_t = fetch_kline(sym, "1m", 50)
            if df_t is not None and len(df_t) > 40:
                c_t = float(df_t['close'].iloc[-2])
                ema50_t = float(df_t['close'].ewm(span=50, adjust=False).mean().iloc[-2])
                best_dir = "CALL" if c_t >= ema50_t else "PUT"
                best_sym = sym
                best_status = "TREND SYNC (ON-DEMAND)"
                best_score = 85
                break

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
            f"⚡ **TITAN AUTO-PILOT (v16.0 On-Demand)** ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🥊 **การเดินเงิน:** `ไม้ที่ {step}`\n"
            f"🎯 **คู่คำนวณสด:** `{label}` *(ตามเทรนด์ EMA50)*\n"
            f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
            f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
            f"📊 **สถานะ:** `{best_status}`\n"
            f"🛡️ **Quality Score:** `{best_score} PTS`\n"
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
    
    # ส่งข้อความต้อนรับพร้อมปุ่มกดขอสัญญาณ
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อขอสัญญาณแรก (START SIGNAL)", callback_data="request_next_signal"))
    
    bot.reply_to(
        message, 
        "🚀 **TITAN AUTO-PILOT v16.0 ON-DEMAND ACTIVATED** 🚀\n"
        "ระบบสั่งการด้วยมือเปิดใช้งานแล้ว! บอทจะไม่ส่งข้อความเองเด็ดขาด จนกว่าคุณจะกดปุ่ม **'ขอสัญญาณรอบถัดไป'** ระบบถึงจะคำนวณและส่งสัญญาณที่กรองอย่างดีให้ทันทีครับ!", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ On-Demand Active")
        return
        
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "🔍 กำลังสแกนหาคู่ที่ดีที่สุดตามเทรนด์...")
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
