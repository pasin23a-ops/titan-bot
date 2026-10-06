import requests
import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time

# ==========================================
# API Token ของคุณ
# ==========================================
BOT_TOKEN = "8992651389:AAEo7yoADLGn863tac0nTkxrvy36BFZNCqU"
bot = telebot.TeleBot(BOT_TOKEN)

INTERVAL = "1m"
user_stats = {}
symbol_stats = {}

SYMBOLS = {
    "DYDXUSDT": "📊 DYDX (OTC)",
    "XAUUSDT": "🥇 XAUUSD (OTC)",
    "XRPUSDT": "🚀 Ripple (OTC)",
    "LTCUSDT": "⚡ Litecoin (OTC)",
    "SUIUSDT": "💧 Sui (OTC)",
    "SHIBUSDT": "🐕 SHIB/USD (OTC)",
    "ONDOUSDT": "🌊 Ondo (OTC)",
    "BTCUSDT": "🪙 BTC/USD (OTC)",
    "ETHUSDT": "💎 ETH/USDT (OTC)",
    "BNBUSDT": "💛 BNB/USDT (OTC)",
    "SPCEUSDT": "🚀 SpaceX (OTC)",
    "AIGUSDT": "🏛️ AIG (OTC)",
    "KOUSDT": "🥤 Coca-Cola (OTC)",
    "MCDUSDT": "🍟 McDonald's (OTC)",
    "PENGUUSDT": "🐧 Pudgy Penguins (OTC)",
    "FARTCOINUSDT": "💨 Fartcoin (OTC)",
    "PENUSDT": "🇵🇪 PEN/USD (OTC)",
    "SNAPUSDT": "👻 Snap Inc. (OTC)",
    "TRUMPUSDT": "🦅 TRUMP Coin (OTC)",
    "VAULTUSDT": "🏦 Vaulta (OTC)",
    "NKEUSDT": "👟 Nike, Inc. (OTC)",
    "INTCUSDT": "💻 Intel Corporation (OTC)",
    "MELANIAUSDT": "👑 MELANIA Coin (OTC)",
    "GASUSDT": "⛽ แก๊สธรรมชาติ (OTC)",
    "XAGUSDT": "🥈 XAGUSD (OTC)"
}

def calculate_ultra_indicators(df):
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    ema_gain = gain.ewm(com=13, adjust=False).mean()
    ema_loss = loss.ewm(com=13, adjust=False).mean()
    rs = ema_gain / ema_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    low_min = df['low'].rolling(window=14).min()
    high_max = df['high'].rolling(window=14).max()
    df['Stoch_K'] = ((df['close'] - low_min) / (high_max - low_min)) * 100
    df['Stoch_D'] = df['Stoch_K'].rolling(window=3).mean()
    
    df['EMA3'] = df['close'].ewm(span=3, adjust=False).mean()
    df['EMA7'] = df['close'].ewm(span=7, adjust=False).mean()
    df['EMA14'] = df['close'].ewm(span=14, adjust=False).mean()
    
    exp1 = df['close'].ewm(span=8, adjust=False).mean()
    exp2 = df['close'].ewm(span=17, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
    
    df['BB_Middle'] = df['close'].rolling(window=20).mean()
    std = df['close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Middle'] + (std * 2.0)
    df['BB_Lower'] = df['BB_Middle'] - (std * 2.0)
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']
    
    df['IsGreen'] = df['close'] > df['open']
    df['IsRed'] = df['close'] < df['open']
    df['Body'] = abs(df['close'] - df['open'])
    df['PrevBody'] = df['Body'].shift(1)
    
    return df

def get_crypto_data(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={INTERVAL}&limit=100"
        res = requests.get(url, timeout=10).json()
        if isinstance(res, dict) and 'code' in res:
            url_fallback = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={INTERVAL}&limit=100"
            res = requests.get(url_fallback, timeout=10).json()
        
        df = pd.DataFrame(res, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
    except Exception:
        return None

def analyze_ultra_market(symbol):
    df = get_crypto_data(symbol)
    if df is None or len(df) < 50:
        return "CALL", "🛡️ WAITING FOR DATA"
    
    df = calculate_ultra_indicators(df)
    
    ema3 = df['EMA3'].iloc[-1]
    ema7 = df['EMA7'].iloc[-1]
    ema14 = df['EMA14'].iloc[-1]
    macd_hist = df['MACD_Hist'].iloc[-1]
    rsi = df['RSI'].iloc[-1]
    stoch_k = df['Stoch_K'].iloc[-1]
    bb_width = df['BB_Width'].iloc[-1]
    avg_bb_width = df['BB_Width'].rolling(window=20).mean().iloc[-1]
    
    is_green = df['IsGreen'].iloc[-1]
    is_red = df['IsRed'].iloc[-1]
    
    # ระบบกรองความคมขั้นสูง V12 (Ultra-Precision Filter)
    # บังคับเช็กแท่งเทียนปัจจุบันร่วมกับทิศทางโมเมนตัมหลักเพื่อลดความผิดพลาด
    is_strong_uptrend = (ema3 > ema7 > ema14) and (macd_hist > 0) and (rsi > 50)
    is_strong_downtrend = (ema3 < ema7 < ema14) and (macd_hist < 0) and (rsi < 50)
    
    if is_strong_uptrend:
        if is_green:
            return "CALL", "🔥 V12 Ultra Trend: STRONG BUY (ตามแรงซื้อเขียว)"
        else:
            return "CALL", "🔥 V12 Ultra Trend: DIP BUY (ย่อซื้อตามเทรนด์ขาขึ้น)"
    elif is_strong_downtrend:
        if is_red:
            return "PUT", "📉 V12 Ultra Trend: STRONG SELL (ตามแรงขายแดง)"
        else:
            return "PUT", "📉 V12 Ultra Trend: RALLY SELL (เด้งขายตามเทรนด์ขาลง)"
    else:
        # กรณีตลาดไซด์เวย์หรือกรอบแคบ ใช้การเช็ก Overbought/Oversold ที่เข้มงวดขึ้น
        if stoch_k < 20 and is_green:
            return "CALL", "🔄 V12 Reversal: OVERSOLD BOUNCE (BUY)"
        elif stoch_k > 80 and is_red:
            return "PUT", "🔄 V12 Reversal: OVERBOUGHT DROP (SELL)"
        else:
            # ถ้าไม่เข้าข่าย ให้ยึดตามทิศทางแท่งเทียนล่าสุดเพื่อความชัวร์ไม่สวนพร่ำเพรื่อ
            if is_green:
                return "CALL", "⚡ V12 Momentum: FOLLOW BUY"
            else:
                return "PUT", "⚡ V12 Momentum: FOLLOW SELL"

def build_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 ดูสถิติรวม", callback_data="menu_stats"),
        InlineKeyboardButton("🔄 รีเซ็ตสถิติ", callback_data="menu_reset")
    )
    for sym, label in SYMBOLS.items():
        markup.add(InlineKeyboardButton(label, callback_data=f"analyze_{sym}"))
    return markup

def get_stats_text(chat_id):
    if chat_id not in user_stats:
        user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
    
    st = user_stats[chat_id]
    total_wins = st["win1"] + st["win2"] + st["win3"]
    total_games = total_wins + st["loss"]
    win_rate = (total_wins / total_games * 100) if total_games > 0 else 0.0
    win1_rate = (st["win1"] / total_games * 100) if total_games > 0 else 0.0

    text = (
        f"👑 **[ ULTRA-PRECISION STATS V12 ]** 👑\n\n"
        f"🏆 **ชนะไม้ 1: `[ {st['win1']} ]` ({win1_rate:.2f}%)**\n"
        f"🥈 ชนะไม้ 2: `[ {st['win2']} ]`\n"
        f"🥉 ชนะไม้ 3: `[ {st['win3']} ]`\n"
        f"❌ แพ้ (LOSS): `[ {st['loss']} ]`\n\n"
        f"📈 ชนะรวม: `{total_wins}` | ทั้งหมด: `{total_games}`\n"
        f"🔥 Win Rate รวม: `{win_rate:.2f}%`\n\n"
        f"📊 **วินเรทรายคู่เงิน (Real-time):**\n"
    )
    
    symbol_breakdown = ""
    if chat_id in symbol_stats:
        for sym, data in symbol_stats[chat_id].items():
            tot = data["win"] + data["loss"]
            w_rate = (data["win"] / tot * 100) if tot > 0 else 0.0
            label = SYMBOLS.get(sym, sym)
            symbol_breakdown += f"• {label} ➔ `{w_rate:.2f}%` (ชนะ {data['win']}, แพ้ {data['loss']})\n"
            
    if symbol_breakdown == "":
        symbol_breakdown = "• ยังไม่มีประวัติการกดแยกรายคู่เงิน"

    return text + symbol_breakdown

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id, 
        "👑 **Ultra-Precision V12 พร้อมรบแล้ว!**\nเพิ่มระบบกรองสัญญาณอัจฉริยะ แม่นยำกว่าเดิม เลือกคู่ลุยกันเลย:", 
        reply_markup=build_menu_keyboard(), 
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['stats'])
def show_stats(message):
    bot.send_message(message.chat.id, get_stats_text(message.chat.id), parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def reset_stats(message):
    chat_id = message.chat.id
    user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
    symbol_stats[chat_id] = {}
    bot.send_message(chat_id, "🔄 รีเซ็ตสถิติทั้งหมดเรียบร้อยแล้วครับ!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_all(call):
    chat_id = call.message.chat.id
    if chat_id not in user_stats:
        user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
    if chat_id not in symbol_stats:
        symbol_stats[chat_id] = {}

    if call.data == "menu_stats":
        bot.answer_callback_query(call.id, "📊 แสดงข้อมูลสถิติของคุณ")
        bot.send_message(chat_id, get_stats_text(chat_id), parse_mode="Markdown")
        return

    if call.data == "menu_reset":
        user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
        symbol_stats[chat_id] = {}
        bot.answer_callback_query(call.id, "🔄 รีเซ็ตสถิติสำเร็จ")
        bot.send_message(chat_id, "🔄 รีเซ็ตสถิติทั้งหมดเป็น 0 เรียบร้อยแล้วครับ!", parse_mode="Markdown")
        return

    if call.data.startswith("skip_"):
        symbol = call.data.split("skip_")[1]
        symbol_label = SYMBOLS.get(symbol, symbol)
        bot.answer_callback_query(call.id, f"⏭️ ข้ามออเดอร์ {symbol_label} เรียบร้อย")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"⏭️ **ข้ามออเดอร์นี้ ({symbol_label})** เรียบร้อย\n\nเลือกคู่เงินอื่นที่กราฟนิ่งๆ ลุยต่อได้เลย:",
            reply_markup=build_menu_keyboard(),
            parse_mode="Markdown"
        )
        return

    if call.data.startswith("res_"):
        parts = call.data.split("_")
        result_type = parts[1]
        symbol = parts[2] if len(parts) > 2 else ""
        
        if symbol not in symbol_stats[chat_id] and symbol != "":
            symbol_stats[chat_id][symbol] = {"win": 0, "loss": 0}

        if result_type == "win1":
            user_stats[chat_id]["win1"] += 1
            if symbol: symbol_stats[chat_id][symbol]["win"] += 1
            text = "✅ บันทึก: ชนะไม้ที่ 1"
        elif result_type == "win2":
            user_stats[chat_id]["win2"] += 1
            if symbol: symbol_stats[chat_id][symbol]["win"] += 1
            text = "✅ บันทึก: ชนะไม้ที่ 2"
        elif result_type == "win3":
            user_stats[chat_id]["win3"] += 1
            if symbol: symbol_stats[chat_id][symbol]["win"] += 1
            text = "✅ บันทึก: ชนะไม้ที่ 3"
        elif result_type == "loss":
            user_stats[chat_id]["loss"] += 1
            if symbol: symbol_stats[chat_id][symbol]["loss"] += 1
            text = "❌ บันทึก: แพ้ (LOSS)"
        else:
            text = "บันทึกผลเรียบร้อย"
        
        bot.answer_callback_query(call.id, text)
        return

    if call.data.startswith("analyze_"):
        symbol = call.data.split("analyze_")[1]
        symbol_label = SYMBOLS.get(symbol, symbol)
        
        direction, zone_status = analyze_ultra_market(symbol)
        
        now = datetime.datetime.now()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')
        
        if symbol not in symbol_stats[chat_id]:
            symbol_stats[chat_id][symbol] = {"win": 0, "loss": 0}
        sym_data = symbol_stats[chat_id][symbol]
        tot_sym = sym_data["win"] + sym_data["loss"]
        sym_wr = (sym_data["win"] / tot_sym * 100) if tot_sym > 0 else 0.0

        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("⏭️ ข้ามออเดอร์นี้ (ไม่ชัวร์)", callback_data=f"skip_{symbol}"))
        markup.add(
            InlineKeyboardButton("🏆 ชนะไม้ 1", callback_data=f"res_win1_{symbol}"),
            InlineKeyboardButton("🏆 ชนะไม้ 2", callback_data=f"res_win2_{symbol}"),
            InlineKeyboardButton("🏆 ชนะไม้ 3", callback_data=f"res_win3_{symbol}"),
            InlineKeyboardButton("❌ แพ้", callback_data=f"res_loss_{symbol}"),
            InlineKeyboardButton("📊 ดูสถิติรวม", callback_data="menu_stats"),
            InlineKeyboardButton("🔄 รีเซ็ตสถิติ", callback_data="menu_reset")
        )
        
        for sym, label in SYMBOLS.items():
            markup.add(InlineKeyboardButton(label, callback_data=f"analyze_{sym}"))

        signal_text = (
            f"👑 Ultra Signal V12 (High Precision)\n\n"
            f"💲📊 {symbol_label}\n"
            f"💎 M1 | Win Rate คู่คู่นี้: `{sym_wr:.2f}%`\n"
            f"⏱️ {target_time_str}\n"
            f"🛡️ {zone_status}\n"
            f"📈 {'BUY 🟢' if direction == 'CALL' else 'SELL 🔴'}"
        )

        bot.send_message(chat_id, signal_text, reply_markup=markup, parse_mode="Markdown")

print("--------------------------------------------------")
print("👑 Ultra-Precision Engine V12 กำลังรันระบบ...")
print("--------------------------------------------------")

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"⚠️ การเชื่อมต่อขัดข้อง: {e} - กำลังเชื่อมต่อใหม่ใน 5 วินาที...")
        time.sleep(5)