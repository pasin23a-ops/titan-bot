import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import requests
import time
import logging
import traceback

# 📝 ระบบ Logging แจ้งเตือนข้อผิดพลาด
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 🔑 โทเคนใหม่ล่าสุดของนาย
BOT_TOKEN = "8842097514:AAGODOhJ-EbgZ2kGeFwqNFAPFkuqkwxb6J8"
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# 🎯 รายชื่อคู่เงิน/คริปโตในตลาดจริง
EXACT_SYMBOLS = {
    "DYDXUSDT": "DYDX / USDT",
    "SHIBUSDT": "SHIB / USDT",
    "SUIUSDT": "SUI / USDT",
    "ONDOUSDT": "ONDO / USDT",
    "XRPUSDT": "RIPPLE (XRP) / USDT",
    "LTCUSDT": "Litecoin (LTC) / USDT"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_real_kline_data(symbol):
    """ดึงข้อมูลแท่งเทียน M1 ล่าสุด 60 แท่งจาก Binance API จริง พร้อม Timestamp"""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=60"
        res = requests.get(url, timeout=2.5)
        if res.status_code == 200:
            data = res.json()
            closes = [float(candle[4]) for candle in data]
            volumes = [float(candle[5]) for candle in data]
            last_candle_open_time = data[-1][0]
            return closes, volumes, last_candle_open_time
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
    return None, None, None

def calculate_ema(closes, period):
    """คำนวณค่า EMA จริงแบบสะสมด้วย Multiplier"""
    if len(closes) < period:
        return sum(closes) / len(closes)
    
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    
    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_wilders_rsi(closes, period=14):
    """คำนวณ RSI ตามมาตรฐาน Wilder's Smoothing"""
    if len(closes) <= period:
        return 50.0

    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)

def analyze_symbol(symbol):
    closes, volumes, open_time = fetch_real_kline_data(symbol)
    if not closes or len(closes) < 30:
        return None
    
    current_price = closes[-1]
    rsi = calculate_wilders_rsi(closes, 14)
    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    
    # คำนวณคะแนนน้ำหนักทิศทาง
    score = 0
    if rsi < 50:
        score += 1
    else:
        score -= 1
        
    if current_price > ema9:
        score += 2
    else:
        score -= 2
        
    if closes[-1] > closes[-2]:
        score += 1
    else:
        score -= 1

    # บังคับตัดสินใจเด็ดขาด ห้ามเป็นกลาง (Force Direction)
    direction = "CALL" if score >= 0 else "PUT"
    strength = abs(score) + round(abs(rsi - 50) / 10, 1) # คำนวณความเด่นเพื่อเลือกตัวที่ดีที่สุด

    return {
        "symbol": symbol,
        "label": EXACT_SYMBOLS[symbol],
        "price": current_price,
        "rsi": rsi,
        "ema9": round(ema9, 6 if "SHIB" in symbol else 4),
        "ema21": round(ema21, 6 if "SHIB" in symbol else 4),
        "direction": direction,
        "strength": strength,
        "open_time": open_time
    }

def scan_best_market_signal():
    """สแกนทุกคู่แล้วเลือกตัวที่มีคะแนนความเด่นสูงสุดมาออกออเดอร์ทันทีทุกครั้ง"""
    candidates = []
    for symbol in EXACT_SYMBOLS.keys():
        res = analyze_symbol(symbol)
        if res:
            candidates.append(res)
            
    if not candidates:
        return None
        
    # เลือกตัวที่แรงส่ง (Strength) สูงที่สุดในรอบนั้นมาฟันธง
    best_candidate = max(candidates, key=lambda x: x['strength'])
    return best_candidate

def send_real_signal_card(chat_id):
    best_signal = scan_best_market_signal()
    
    if not best_signal:
        bot.send_message(chat_id, "⚠️ ไม่สามารถเชื่อมต่อข้อมูลตลาดจริงได้ในขณะนี้")
        return

    open_time_dt = datetime.datetime.fromtimestamp(best_signal['open_time'] / 1000.0, tz=datetime.timezone.utc)
    close_time_dt = open_time_dt + datetime.timedelta(minutes=1)
    close_time_thai = close_time_dt.astimezone(datetime.timezone(datetime.timedelta(hours=7)))
    target_time_str = close_time_thai.strftime('%H:%M:%S')

    now = get_thai_time()
    
    is_buy = (best_signal['direction'] == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"

    fmt = ".6f" if "SHIB" in best_signal['symbol'] else ".4f"

    card_text = (
        f"👑 **TITAN v107.0 FORCE-SIGNAL ENGINE** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **คู่เด่นทำกำไร (บังคับมีสัญญาณ):** `{best_signal['label']}`\n"
        f"💵 **ราคาปัจจุบัน:** `{best_signal['price']:{fmt}}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **Wilder's RSI (14):** `{best_signal['rsi']}`\n"
        f"📈 **True EMA (9 / 21):** `{best_signal['ema9']} / {best_signal['ema21']}`\n"
        f"⏱️ **หมดอายุแท่ง M1 จริง:** `{target_time_str}`\n"
        f"⚡ **ทิศทางฟันธง:** **{dir_emoji}**\n"
        f"🔥 **Momentum Score:** `{best_signal['strength']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ Update: `{now.strftime('%H:%M:%S')}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚔️ สแกนหาจุดเข้าถัดไป (การันตีมีสัญญาณ) ⚔️", callback_data="next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error sending message: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚔️ สแกนหาจุดเข้าถัดไป (การันตีมีสัญญาณ) ⚔️", callback_data="next_signal"))
    bot.reply_to(message, 
        "👑 **TITAN v107.0 Force-Signal พร้อมรบ!**\n"
        "กดปุ่มปุ๊บ บังคับคัดเลือกคู่ที่สัญญาณเด่นที่สุดมาพ่นการ์ดให้เทรดได้ทันทีทุกคลิก ลุยโลด:", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "next_signal")
def handle_next_signal(call):
    try:
        bot.answer_callback_query(call.id, text="⚡ กำลังคัดเลือกคู่ที่สัญญาณเด่นที่สุด...", show_alert=False)
    except Exception:
        pass
    
    send_real_signal_card(call.message.chat.id)

if __name__ == "__main__":
    logging.info("🚀 TITAN v107.0 Force-Signal Engine Running...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            logging.error(f"[POLLING ERROR CRASH]: {e}")
            logging.error(traceback.format_exc())
            time.sleep(2)
        
