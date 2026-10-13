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

# Cache สำหรับเก็บคู่ที่แข็งแกร่งที่สุดจากการสแกนระดับ Quant
best_predator_cache = {
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

def fetch_kline(symbol, interval="1m", limit=35):
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

def quant_predator_analyze(symbol):
    """ระบบคัดกรองมหาโหด 3 ชั้น (EMA Alignment + Volume Surge + Candle Structure)"""
    df = fetch_kline(symbol, "1m", 35)
    if df is None or len(df) < 25:
        return "CALL", -9999, "DATA_ERROR"

    df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()

    o = float(df['open'].iloc[-2])
    c = float(df['close'].iloc[-2])
    h = float(df['high'].iloc[-2])
    l = float(df['low'].iloc[-2])
    
    ema10 = float(df['ema_10'].iloc[-2])
    ema20 = float(df['ema_20'].iloc[-2])
    ema50 = float(df['ema_50'].iloc[-2])
    
    vol = float(df['volume'].iloc[-2])
    avg_vol = df['volume'].iloc[-12:-2].mean()

    candle_range = h - l + 1e-9
    body_size = abs(c - o)
    body_ratio = body_size / candle_range

    # 1. กรองโดจิ / แท่งเทียนอ่อนแรง
    if body_ratio < 0.30:
        return "NONE", -5000, "FILTER: DOJI_WEAK_BODY"

    score = 0

    # 2. กรองเทรนด์ขาขึ้นเข้มงวด (Strict Bullish Alignment)
    if c > ema10 and ema10 > ema20 and c > o:
        score += 1000
        if ema20 > ema50:
            score += 500  # เทรนด์ใหญ่สนับสนุน
        if vol > avg_vol:
            score += 300  # วอลลุ่มซัพพอร์ต
        upper_wick = (h - c) / candle_range
        if upper_wick < 0.20:
            score += 200  # ไม่มีแรงต้านส่วนบน
        return "CALL", score, "PURE_BULLISH_MOMENTUM"

    # 3. กรองเทรนด์ขาลงเข้มงวด (Strict Bearish Alignment)
    elif c < ema10 and ema10 < ema20 and c < o:
        score += 1000
        if ema20 < ema50:
            score += 500  # เทรนด์ใหญ่สนับสนุน
        if vol > avg_vol:
            score += 300  # วอลลุ่มซัพพอร์ต
        lower_wick = (c - l) / candle_range
        if lower_wick < 0.20:
            score += 200  # ไม่มีแรงรับส่วนล่าง
        return "PUT", score, "PURE_BEARISH_MOMENTUM"

    # 4. Fallback ป้องกันสัญญาณขาดหาย (อิงตาม EMA หลัก)
    fallback_score = int((abs(c - ema20) / (ema20 + 1e-9)) * 5000)
    if c >= ema20:
        return "CALL", fallback_score, "FLOW_UPTREND"
    else:
        return "PUT", fallback_score, "FLOW_DOWNTREND"

def background_quant_scanner():
    """สแกนตลอดเวลาเพื่อเฟ้นหาคู่ที่ดีที่สุดแบบ Real-time"""
    global best_predator_cache
    while True:
        try:
            top_sym = None
            top_dir = "CALL"
            top_status = "QUANT_SCANNING"
            highest_score = -99999

            for sym in SYMBOLS.keys():
                direction, score, status = quant_predator_analyze(sym)
                if score > highest_score:
                    highest_score = score
                    top_sym = sym
                    top_dir = direction
                    top_status = status

            if not top_sym:
                top_sym = "DYDXUSDT"

            best_predator_cache = {
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

def send_quant_signal(chat_id):
    global last_global_signal_time
    try:
        now_time = time.time()
        
        # Cooldown ป้องกันการยิงเบิ้ลในแท่งเดียวกัน (60 วินาที)
        if now_time - last_global_signal_time < 60:
            return

        sym = best_predator_cache["symbol"]
        label = best_predator_cache["label"]
        direction = best_predator_cache["direction"]
        status = best_predator_cache["status"]
        score = best_predator_cache["score"]

        last_global_signal_time = now_time

        step = user_martingale_step.get(chat_id, 1)
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
        btn_label = "CALL" if is_buy else "PUT"

        # การ์ดสัญญาณสไตล์ Quant Predator
        card_text = (
            f"⚡ **TITAN QUANT-PREDATOR v4.0** ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🥊 **การจัดการเดินเงิน:** `ไม้ที่ {step}`\n"
            f"🎯 **สินทรัพย์ท็อปสุดรอบนี้:** `{label}`\n"
            f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
            f"🔥 **คำสั่งซื้อขาย:** **{dir_emoji}**\n\n"
            f"📊 **ระบบคัดกรอง:** `{status}`\n"
            f"🛡️ **Predator Score:** `{score} PTS`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *ระบบรันสแกนอัตโนมัติ ออกสัญญาณตรงเวลาทุกนาที*"
        )

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton(f"⚡ EXECUTE {btn_label} NOW ⚡", callback_data="do_nothing"))
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
    """ส่งสัญญาณอัตโนมัติตรงวินาทีที่ 30 ของทุกๆ นาที"""
    last_sent_minute = -1
    while True:
        try:
            now = get_thai_time()
            if now.second == 30 and now.minute != last_sent_minute:
                last_sent_minute = now.minute
                for cid in list(active_chat_ids):
                    send_quant_signal(cid)
            time.sleep(0.5)
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(2)

@bot.message_handler(commands=['start', 'scan', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    if chat_id not in user_martingale_step:
        user_martingale_step[chat_id] = 1
    
    bot.reply_to(
        message, 
        "🔥 **TITAN QUANT-PREDATOR ACTIVATED** 🔥\n"
        "เปิดระบบสแกนคัดกรองมหาโหด + ยิงสัญญาณตามเทรนด์อัตโนมัติเรียบร้อย!\n"
        "สัญญาณจะเด้งเข้าแชททุกๆ นาทีครับ", 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Signal Executed")
        return
    if call.data.startswith("res_"):
        parts = call.data.split("_")
        res_type = parts[1]
        if res_type in ["win1", "win2", "win3"]:
            user_martingale_step[chat_id] = 1
            bot.answer_callback_query(call.id, "💎 WIN! Reset เป็นไม้ 1 เรียบร้อย")
        elif res_type == "loss":
            step = user_martingale_step.get(chat_id, 1)
            user_martingale_step[chat_id] = 1 if step >= 3 else step + 1
            bot.answer_callback_query(call.id, f"⚠️ LOSS! ปรับเพิ่มเงินเป็นไม้ {user_martingale_step[chat_id]}")

threading.Thread(target=background_quant_scanner, daemon=True).start()
threading.Thread(target=auto_broadcaster, daemon=True).start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
