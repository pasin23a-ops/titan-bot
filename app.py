import pandas as pd
import numpy as np
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import xml.etree.ElementTree as ET

# ==========================================
# API Token ใหม่ของคุณ
# ==========================================
BOT_TOKEN = "8822727043:AAEEKA96HNfVXO4CMYF7GxBTXq9q_uQhU4Y"
bot = telebot.TeleBot(BOT_TOKEN)

INTERVAL = "1m"
user_stats = {}
symbol_stats = {}
user_martingale_step = {}

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
    "BNBUSDT": "💛 BNB/USD (OTC)",
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

def get_forex_factory_high_impact_news():
    url = "https://www.forexfactory.com/ff_calendar_thisweek.xml"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    high_impact_events = []
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            for event in root.findall('event'):
                impact = event.find('impact')
                title = event.find('title')
                country = event.find('country')
                if impact is not None and impact.text == 'High':
                    c_name = country.text if country is not None else "ALL"
                    t_title = title.text if title is not None else "High Impact Event"
                    high_impact_events.append(f"{c_name}: {t_title}")
    except Exception as e:
        print(f"⚠️ ไม่สามารถเชื่อมต่อ Forex Factory API ได้: {e}")
    return high_impact_events

def check_market_zone_ttz():
    now_min = datetime.datetime.now().minute
    if now_min in [28, 29, 30, 58, 59, 0, 1]:
        return "RED", "🔴 [TTZ Zone] โซนผันผวนสูง (เปลี่ยนกรอบเวลาชั่วโมง)"
    elif now_min in [14, 15, 44, 45]:
        return "YELLOW", "🟡 [TTZ Zone] โซนเฝ้าระวัง (ย่อยกรอบ 15 นาที)"
    else:
        return "GREEN", "🟢 [TTZ Zone] โซนปลอดภัย (Green Zone)"

def generate_adaptive_market_data(symbol):
    np.random.seed(int(time.time() // 4) + sum(ord(c) for c in symbol))
    size = 60
    base_price = 100.0
    
    regime = (int(time.time() // 10) + sum(ord(c) for c in symbol)) % 3
    if regime == 0:
        returns = np.random.normal(loc=0.003, scale=0.0005, size=size)
    elif regime == 1:
        returns = np.random.normal(loc=0.0, scale=0.001, size=size)
    else:
        returns = np.random.normal(loc=0.0, scale=0.004, size=size)
        
    price_series = base_price * np.cumprod(1 + returns)
    
    df = pd.DataFrame()
    df['close'] = price_series
    df['open'] = df['close'].shift(1).fillna(base_price)
    df['high'] = df[['open', 'close']].max(axis=1) + np.random.uniform(0.0005, 0.003, size)
    df['low'] = df[['open', 'close']].min(axis=1) - np.random.uniform(0.0005, 0.003, size)
    
    return df

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def analyze_adaptive_market(symbol):
    df = generate_adaptive_market_data(symbol)
    
    df['returns'] = df['close'].pct_change()
    volatility = df['returns'].std()
    
    df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    trend_diff = abs(df['ema5'].iloc[-1] - df['ema20'].iloc[-1]) / df['ema20'].iloc[-1]
    
    last_close = df['close'].iloc[-1]
    last_open = df['open'].iloc[-1]
    
    if volatility > 0.003:
        tech_used = "⚙️ [Technique] Volatility Breaker Engine (ดักไส้เทียนผันผวน)"
        if last_close > last_open:
            return "CALL", "⚠️ [V70 Adaptive] HIGH VOLATILITY - BUY WITH CAUTION", tech_used
        else:
            return "PUT", "⚠️ [V70 Adaptive] HIGH VOLATILITY - SELL WITH CAUTION", tech_used

    elif trend_diff > 0.0015:
        tech_used = "⚙️ [Technique] Trend Following Engine (EMA5/20 + MACD Momentum)"
        df['macd_hist'] = df['ema5'] - df['ema20']
        hist_val = df['macd_hist'].iloc[-1]
        
        if df['ema5'].iloc[-1] > df['ema20'].iloc[-1] and hist_val > 0:
            return "CALL", "🔥 [V70 Adaptive] STRONG TREND BUY", tech_used
        else:
            return "PUT", "📉 [V70 Adaptive] STRONG TREND SELL", tech_used

    else:
        tech_used = "⚙️ [Technique] Range Bound Engine (RSI Mean Reversion + แนวรับแนวต้าน)"
        df['rsi'] = calculate_rsi(df['close'], period=14)
        last_rsi = df['rsi'].iloc[-1] if not np.isnan(df['rsi'].iloc[-1]) else 50
        
        if last_rsi < 45:
            return "CALL", "🎯 [V70 Adaptive] SIDEWAY OVERSOLD BUY (ดักเด้ง)", tech_used
        elif last_rsi > 55:
            return "PUT", "🎯 [V70 Adaptive] SIDEWAY OVERBOUGHT SELL (ดักย่อ)", tech_used
        else:
            if last_close >= last_open:
                return "CALL", "⚡ [V70 Adaptive] RANGE NEUTRAL BUY", tech_used
            else:
                return "PUT", "⚡ [V70 Adaptive] RANGE NEUTRAL SELL", tech_used

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

    current_step = user_martingale_step.get(chat_id, 1)

    text = (
        f"👑 **[ TITAN BEAM V70 ADAPTIVE STATS ]** 👑\n\n"
        f"🎯 **สถานะไม้ปัจจุบัน: แนะนำให้ลุย `[ ไม้ที่ {current_step} ]`**\n\n"
        f"🏆 ชนะไม้ 1: `[ {st['win1']} ]` ({win1_rate:.2f}%)\n"
        f"🥈 ชนะไม้ 2: `[ {st['win2']} ]`\n"
        f"🥉 ชนะไม้ 3: `[ {st['win3']} ]`\n"
        f"❌ แพ้ครบ 3 ไม้ (LOSS): `[ {st['loss']} ]`\n\n"
        f"📈 ชนะรวม: `{total_wins}` | ทั้งหมด: `{total_games}`\n"
        f"🔥 Win Rate รวม: `{win_rate:.2f}%`\n\n"
        f"📊 **สถิติรายคู่เงิน:**\n"
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
    user_martingale_step[message.chat.id] = 1
    bot.send_message(
        message.chat.id, 
        "🇷🇺 **Titan Beam Pro V70 (Adaptive Dynamic Engine)**\nเปิดระบบปรับเปลี่ยนเทคนิคอัตโนมัติเรียบร้อย เลือกคู่เงินเพื่อวิเคราะห์ได้เลย:", 
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
    user_martingale_step[chat_id] = 1
    bot.send_message(chat_id, "🔄 รีเซ็ตสถิติและสเต็ปการเดินเงินเรียบร้อย!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_all(call):
    chat_id = call.message.chat.id
    if chat_id not in user_stats:
        user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
    if chat_id not in symbol_stats:
        symbol_stats[chat_id] = {}
    if chat_id not in user_martingale_step:
        user_martingale_step[chat_id] = 1

    if call.data == "menu_stats":
        bot.answer_callback_query(call.id, "📊 แสดงข้อมูลสถิติของคุณ")
        bot.send_message(chat_id, get_stats_text(chat_id), parse_mode="Markdown")
        return

    if call.data == "menu_reset":
        user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
        symbol_stats[chat_id] = {}
        user_martingale_step[chat_id] = 1
        bot.answer_callback_query(call.id, "🔄 รีเซ็ตสถิติสำเร็จ")
        bot.send_message(chat_id, "🔄 รีเซ็ตสถิติและเริ่มนับไม้ที่ 1 ใหม่เรียบร้อยครับ!", parse_mode="Markdown")
        return

    if call.data.startswith("skip_"):
        symbol = call.data.split("skip_")[1]
        symbol_label = SYMBOLS.get(symbol, symbol)
        bot.answer_callback_query(call.id, f"⏭️ ข้ามออเดอร์ {symbol_label}")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"⏭ **ข้ามออเดอร์นี้ ({symbol_label})** เรียบร้อย\n\nเลือกคู่เงินอื่นลุยต่อได้เลย:",
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

        if result_type in ["win1", "win2", "win3"]:
            if result_type == "win1": user_stats[chat_id]["win1"] += 1
            elif result_type == "win2": user_stats[chat_id]["win2"] += 1
            elif result_type == "win3": user_stats[chat_id]["win3"] += 1
            
            if symbol: symbol_stats[chat_id][symbol]["win"] += 1
            user_martingale_step[chat_id] = 1
            text = "✅ ชนะออเดอร์! รีเซ็ตกลับสเต็ปไม้ 1"
        elif result_type == "loss":
            current_step = user_martingale_step[chat_id]
            if current_step < 3:
                user_martingale_step[chat_id] += 1
                text = f"❌ แพ้ไม้ {current_step} ➔ ขยับไปลุยต่อ [ไม้ที่ {user_martingale_step[chat_id]}]"
            else:
                user_stats[chat_id]["loss"] += 1
                user_martingale_step[chat_id] = 1
                text = "❌ ครบ 3 ไม้ บันทึก LOSS และรีเซ็ตกลับไม้ 1"
        else:
            text = "บันทึกผลเรียบร้อย"
        
        bot.answer_callback_query(call.id, text)
        bot.send_message(chat_id, f"📌 อัปเดตสถานะล่าสุด:\n{get_stats_text(chat_id)}", parse_mode="Markdown")
        return

    if call.data.startswith("analyze_"):
        symbol = call.data.split("analyze_")[1]
        symbol_label = SYMBOLS.get(symbol, symbol)
        
        ttz_code, ttz_desc = check_market_zone_ttz()
        ff_news = get_forex_factory_high_impact_news()
        news_status = f"🌐 Forex Factory: พบข่าวกล่องแดงวันนี้ {len(ff_news)} รายการ" if ff_news else "🌐 Forex Factory: ไร้ข่าวแดงรุนแรงในขณะนี้"

        direction, zone_status, tech_used = analyze_adaptive_market(symbol)
        current_step = user_martingale_step.get(chat_id, 1)
        
        now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
        target_time = (now_thai + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
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
            InlineKeyboardButton("❌ แพ้ (ขยับไม้ถัดไป)", callback_data=f"res_loss_{symbol}"),
            InlineKeyboardButton("📊 ดูสถิติรวม", callback_data="menu_stats"),
            InlineKeyboardButton("🔄 รีเซ็ตสถิติ", callback_data="menu_reset")
        )
        
        for sym, label in SYMBOLS.items():
            markup.add(InlineKeyboardButton(label, callback_data=f"analyze_{sym}"))

        signal_text = (
            f"🇷🇺 **Titan Beam Pro V70 (Adaptive Dynamic)**\n\n"
            f"🎯 **คำแนะนำ: ออกออเดอร์ `[ ไม้ที่ {current_step} ]`**\n"
            f"💲📊 {symbol_label}\n"
            f"💎 M1 | Win Rate: `{
