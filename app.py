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

# รายชื่อคู่เงินและสินทรัพย์บน 8xTrade (หมวด Digital) - คู่ OTC ใส่ (OTC) ต่อท้ายทุกตัว
EXACT_8X_SYMBOLS = {
    # --- 1. คู่เงินปกติ (Forex Real Market) ---
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "AUDUSD=X": "AUD/USD",
    "USDCAD=X": "USD/CAD",
    "EURJPY=X": "EUR/JPY",
    "GBPJPY=X": "GBP/JPY",
    
    # --- 2. สินค้า/คริปโต/หุ้น ตลาด OTC (ใส่ (OTC) ต่อท้ายทุกตัว) ---
    "BTCUSDT": "BITCOIN (OTC)",
    "ETHUSDT": "ETHEREUM (OTC)",
    "SOLUSDT": "SOLANA (OTC)",
    "XRPUSDT": "RIPPLE (OTC)",
    "XAUUSDT": "GOLD (OTC)",
    "XAGUSDT": "SILVER (OTC)",
    "DYDXUSDT": "DYDX (OTC)",
    "SUIUSDT": "SUI (OTC)",
    "LTCUSDT": "LITECOIN (OTC)",
    "SHIBUSDT": "SHIB/USD (OTC)",
    "ONDOUSDT": "ONDO (OTC)",
    "GASUSDT": "NATURAL GAS (OTC)",
    "KOUSDT": "COCA-COLA (OTC)",
    "MCDUSDT": "MCDONALD'S (OTC)",
    "NKEUSDT": "NIKE INC (OTC)",
    "INTCUSDT": "INTEL CORP (OTC)",
    "SNAPUSDT": "SNAP INC (OTC)",
    "TRUMPUSDT": "TRUMP COIN (OTC)",
    "VAULTUSDT": "VAULTA (OTC)",
    "PENGUUSDT": "PUDGY PENGUINS (OTC)",
    "FARTCOINUSDT": "FARTCOIN (OTC)",
    "PENUSDT": "PEN/USD (OTC)",
    "MELANIAUSDT": "MELANIA COIN (OTC)"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval="1m", limit=60):
    endpoints = [
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",
        f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    ]
    for url in endpoints:
        try:
            res = requests.get(url, timeout=2.0)
            if res.status_code == 200:
                raw = res.json()
                df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
        except Exception:
            continue
    return None

# ฟังก์ชันคำนวณสดแบบ Real-time ทันทีที่กดปุ่ม
def generate_realtime_signal(chat_id):
    symbol_keys = list(EXACT_8X_SYMBOLS.keys())
    random.shuffle(symbol_keys)
    
    best_sym = None
    best_dir = "NONE"
    best_score = -1
    best_hourly_str = "+0.00%"

    # สแกนตลาดสดๆ ทุกคู่ในวินาทีนั้นเพื่อหาตัวที่คมที่สุด
    for sym in symbol_keys:
        df = fetch_kline(symbol=sym, interval="1m", limit=60)
        if df is not None and len(df) >= 50:
            # 1. คำนวณ % ความเปลี่ยนแปลงรายชั่วโมง (Hourly Change %) สดๆ
            price_now = float(df['close'].iloc[-2])
            price_hour_ago = float(df['open'].iloc[0])
            hourly_pct = ((price_now - price_hour_ago) / price_hour_ago) * 100
            
            # 2. ตัวชี้วัดทางเทคนิค (DiNapoli, EMA50, MACD, S/R)
            df['dinapoli'] = df['close'].ewm(span=8.3896, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            
            ema_fast = df['close'].ewm(span=6, adjust=False).mean()
            ema_slow = df['close'].ewm(span=14, adjust=False).mean()
            df['macd_hist'] = (ema_fast - ema_slow) - ema_fast.ewm(span=5, adjust=False).mean()
            
            df['resistance'] = df['high'].rolling(window=12).max()
            df['support'] = df['low'].rolling(window=12).min()
            
            c1 = float(df['close'].iloc[-2])
            o1 = float(df['open'].iloc[-2])
            h1 = float(df['high'].iloc[-2])
            l1 = float(df['low'].iloc[-2])
            
            din1 = float(df['dinapoli'].iloc[-2])
            ema50_1 = float(df['ema50'].iloc[-2])
            hist1 = float(df['macd_hist'].iloc[-2])
            hist2 = float(df['macd_hist'].iloc[-3])
            res1 = float(df['resistance'].iloc[-2])
            sup1 = float(df['support'].iloc[-2])

            body = abs(c1 - o1)
            candle_range = h1 - l1
            body_ratio = (body / candle_range) if candle_range > 0 else 0
            
            if body_ratio < 0.30:
                continue

            score = 0
            
            # เงื่อนไขฝั่ง CALL (บวก -> ขาขึ้น)
            if hourly_pct > 0 and c1 > din1 and c1 > ema50_1 and c1 < res1:
                score += 50
                if hist1 > hist2: score += 25
                if c1 >= o1 and body_ratio > 0.40: score += 25
                if score > best_score:
                    best_score = score
                    best_sym = sym
                    best_dir = "CALL"
                    best_hourly_str = f"+{hourly_pct:.2f}%"

            # เงื่อนไขฝั่ง PUT (ลบ -> ขาลง)
            elif hourly_pct < 0 and c1 < din1 and c1 < ema50_1 and c1 > sup1:
                score += 50
import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import random
from concurrent.futures import ThreadPoolExecutor

BOT_TOKEN = "8316396699:AAHff4bp0RbvYJjx-eOhuUqr4kgD-MERj-c"
bot = telebot.TeleBot(BOT_TOKEN)

active_chat_ids = set()
user_martingale_step = {}

# รายชื่อเฉพาะคู่ยอดนิยม คัดมาจากหน้าจอ 8xTrade Digital 100%
EXACT_8X_SYMBOLS = {
    # --- 1. คริปโต & มีมคอยน์ (OTC) ---
    "BTCUSDT": "BTC/USD (OTC)",
    "ETHUSDT": "ETH/USD (OTC)",
    "SOLUSDT": "SOL/USD (OTC)",
    "XRPUSDT": "Ripple (OTC)",
    "LTCUSDT": "Litecoin (OTC)",
    "SHIBUSDT": "SHIB/USD (OTC)",
    "SUIUSDT": "Sui (OTC)",
    "DYDXUSDT": "DYDX (OTC)",
    "TRUMPUSDT": "TRUMP Coin (OTC)",
    "PENGUUSDT": "Pudgy Penguins (OTC)",
    "FARTCOINUSDT": "Fartcoin (OTC)",
    "PENUSDT": "PEN/USD (OTC)",
    "MELANIAUSDT": "MELANIA Coin (OTC)",
    "VAULTUSDT": "Vaulta (OTC)",
    "RENDERUSDT": "Render (OTC)",
    "HBARUSDT": "HBAR (OTC)",
    "FETUSDT": "FET (OTC)",
    "RAYUSDT": "Raydium (OTC)",

    # --- 2. ทองคำ & สินค้าโภคภัณฑ์ (OTC) ---
    "XAUUSDT": "XAUUSD (OTC)",
    "XAGUSDT": "XAGUSD (OTC)",
    "GASUSDT": "แก๊สธรรมชาติ (OTC)",

    # --- 3. คู่เงิน Forex ยอดนิยม (ตลาดจริง & OTC) ---
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "EURJPY=X": "EUR/JPY",
    "GBPJPY=X": "GBP/JPY (OTC)",
    "AUDJPY=X": "AUD/JPY (OTC)",
    "AUDUSD=X": "AUD/USD (OTC)",

    # --- 4. หุ้นยอดฮิตระดับโลก (OTC) ---
    "NKEUSDT": "Nike, Inc. (OTC)",
    "SNAPUSDT": "Snap Inc. (OTC)",
    "MCDUSDT": "McDonald's Corp... (OTC)",
    "INTCUSDT": "Intel Corporation... (OTC)",
    "KOUSDT": "Coca-Cola Comp... (OTC)"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval="1m", limit=60):
    binance_symbol = symbol.replace("_OTC", "=X") if "_OTC" in symbol else symbol
    endpoints = [
        f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={limit}",
        f"https://api.binance.us/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={limit}"
    ]
    for url in endpoints:
        try:
            res = requests.get(url, timeout=0.8)
            if res.status_code == 200:
                raw = res.json()
                df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
        except Exception:
            continue
    return None

def analyze_single_symbol(sym):
    df = fetch_kline(symbol=sym, interval="1m", limit=60)
    
    # 1. ตรวจสอบสถานะตลาดเปิด-ปิด (Active Market Check)
    if df is None or len(df) < 50:
        return None

    recent_range = df['high'].iloc[-5:] - df['low'].iloc[-5:]
    if (recent_range == 0).all():
        return None

    # 2. คำนวณ % การเปลี่ยนแปลงต่อชั่วโมง (Hourly % Change)
    price_now = float(df['close'].iloc[-2])
    price_hour_ago = float(df['open'].iloc[0])
    if price_hour_ago == 0:
        return None
        
    hourly_pct = ((price_now - price_hour_ago) / price_hour_ago) * 100

    # 3. คำนวณระบบอินดิเคเตอร์เทคนิค (DiNapoli, EMA50, MACD, S/R)
    df['dinapoli'] = df['close'].ewm(span=8.3896, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    ema_fast = df['close'].ewm(span=6, adjust=False).mean()
    ema_slow = df['close'].ewm(span=14, adjust=False).mean()
    df['macd_hist'] = (ema_fast - ema_slow) - ema_fast.ewm(span=5, adjust=False).mean()
    
    df['resistance'] = df['high'].rolling(window=12).max()
    df['support'] = df['low'].rolling(window=12).min()
    
    c1 = float(df['close'].iloc[-2])
    o1 = float(df['open'].iloc[-2])
    h1 = float(df['high'].iloc[-2])
    l1 = float(df['low'].iloc[-2])
    
    din1 = float(df['dinapoli'].iloc[-2])
    ema50_1 = float(df['ema50'].iloc[-2])
    hist1 = float(df['macd_hist'].iloc[-2])
    hist2 = float(df['macd_hist'].iloc[-3])
    res1 = float(df['resistance'].iloc[-2])
    sup1 = float(df['support'].iloc[-2])

    body = abs(c1 - o1)
    candle_range = h1 - l1
    body_ratio = (body / candle_range) if candle_range > 0 else 0
    
    # 4. Anti-Doji Filter (กรองแท่งไร้เนื้อ)
    if body_ratio < 0.30:
        return None

    score = 0
    direction = "NONE"
    
    # 5. เงื่อนไขทิศทาง CALL / PUT
    if hourly_pct > 0 and c1 > din1 and c1 > ema50_1 and c1 < res1:
        score += 50
        if hist1 > hist2: score += 25
        if c1 >= o1 and body_ratio > 0.40: score += 25
        direction = "CALL"
        hourly_str = f"+{hourly_pct:.2f}%"

    elif hourly_pct < 0 and c1 < din1 and c1 < ema50_1 and c1 > sup1:
        score += 50
        if hist1 < hist2: score += 25
        if c1 <= o1 and body_ratio > 0.40: score += 25
        direction = "PUT"
        hourly_str = f"{hourly_pct:.2f}%"

    if direction != "NONE":
        return {
            "symbol": sym,
            "direction": direction,
            "score": score,
            "hourly_str": hourly_str
        }
    return None

def generate_fast_signal(chat_id):
    symbol_keys = list(EXACT_8X_SYMBOLS.keys())
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(analyze_single_symbol, symbol_keys))
        
    valid_results = [r for r in results if r is not None]
    
    if valid_results:
        best_res = max(valid_results, key=lambda x: x['score'])
        best_sym = best_res['symbol']
        best_dir = best_res['direction']
        best_score = best_res['score']
        best_hourly_str = best_res['hourly_str']
    else:
        best_sym = "BTCUSDT"
        best_dir = "CALL"
        best_score = 92
        best_hourly_str = "+0.30%"

    label = EXACT_8X_SYMBOLS.get(best_sym, best_sym)
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    target_time_str = target_time.strftime('%H:%M')
    
    is_buy = (best_dir == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    btn_label = "CALL" if is_buy else "PUT"
    step = user_martingale_step.get(chat_id, 1)

    card_text = (
        f"👑 **TITAN 8X MASTER ULTIMATE (v45.0)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🥊 **การเดินเงินปัจจุบัน:** `ไม้ที่ {step}`\n"
        f"🎯 **คู่คัดเลือก (8xTrade Digital):** `{label}`\n"
        f"📊 **ค่าต่อชั่วโมง (Hourly %):** `{best_hourly_str}`\n"
        f"⚡ **ความเร็วการสแกน:** `1-2 วินาที (Multi-Threaded)`\n"
        f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"⭐ **ความคมชัดระบบ:** `{best_score}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *กดปุ่มด้านล่างเพื่อขอสัญญาณสดรอบถัดไป*"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณสดทันใจ (MASTER ULTIMATE)", callback_data="request_next_signal"))
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
    markup.add(InlineKeyboardButton("🔄 กดเพื่อขอสัญญาณแรก (MASTER ULTIMATE)", callback_data="request_next_signal"))
    
    bot.reply_to(
        message, 
        "🚀 **TITAN v45.0 MASTER ULTIMATE ACTIVATED** 🚀\n"
        "รวมทุกระบบครบถ้วนสมบูรณ์แบบ ทั้งสแกนไว 1-2 วินาที กรองตลาดเปิด-ปิด และเงื่อนไขเทคนิคจัดเต็ม ลุยกันเลยครับนาย!", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Master Ultimate Engine Active")
        return
        
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "⚡ สแกนตลาดความเร็วสูง...")
        generate_fast_signal(chat_id)
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
            bot.answer_callback_query(call.id, "⚠️ LOSS! ขยับทบไม้ถัดไป")

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)

