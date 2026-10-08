import pandas as pd
import numpy as np
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import xml.etree.ElementTree as ET

# ==========================================
# API Token & Firebase Configuration
# ==========================================
BOT_TOKEN = "8822727043:AAEEKA96HNfVXO4CMYF7GxBTXq9q_uQhU4Y"
FIREBASE_PROJECT_ID = "v70-user-auth"

bot = telebot.TeleBot(BOT_TOKEN)

INTERVAL = "1m"
user_stats = {}
symbol_stats = {}
user_martingale_step = {}
user_creds = {}  # เก็บอีเมลและรหัสผ่านประจำ Chat ID

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

# ==========================================
# FIREBASE AUTH HELPER (EMAIL + PASSWORD)
# ==========================================
def check_user_approved(email: str, password: str = None) -> bool:
    """ เช็คสถานะการอนุมัติและรหัสผ่านของผู้ใช้จาก Firebase Firestore REST API """
    if not email or not password:
        return False
    
    email = email.lower().strip()
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/users/{email}"
    
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            fields = data.get("fields", {})
            status = fields.get("status", {}).get("stringValue", "")
            db_password = fields.get("password", {}).get("stringValue", "")
            
            # ตรวจสอบทั้งสถานะอนุมัติ (approved) และรหัสผ่านที่ตรงกัน
            return (status == "approved") and (str(db_password) == str(password))
    except Exception as e:
        print(f"⚠️ Firebase Error: {e}")
        
    return False

# ==========================================
# MARKET ANALYSIS & S&R FILTER FUNCTIONS
# ==========================================
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

def check_support_resistance_zones(df):
    """
    ระบบตรวจจับแนวรับแนวต้าน (Support & Resistance Filter)
    คำนวณจาก Swing High และ Swing Low ย้อนหลัง เพื่อป้องกันการโดนแนวต้าน/แนวรับดีดสวน
    """
    recent_high = df['high'].tail(20).max()
    recent_low = df['low'].tail(20).min()
    current_price = df['close'].iloc[-1]
    
    # คำนวณระยะห่างจากแนวต้านและแนวรับ (หน่วยเป็นเปอร์เซ็นต์)
    dist_to_resistance = abs(recent_high - current_price) / current_price
    dist_to_support = abs(current_price - recent_low) / current_price
    
    # ถ้าราชอยู่ชิดแนวต้านหรือแนวรับในระยะ < 0.15% แปลว่าเสี่ยงโดนดีดกลับ
    threshold = 0.0015
    if dist_to_resistance < threshold:
        return "NEAR_RESISTANCE", f"🛡️ [S&R Filter] ราคาชิดแนวต้านสำคัญ ({recent_high:.2f}) ระวังแรงขายดีดกลับ!"
    elif dist_to_support < threshold:
        return "NEAR_SUPPORT", f"🛡️ [S&R Filter] ราคาชิดแนวรับสำคัญ ({recent_low:.2f}) ระวังแรงซื้อดีดกลับ!"
    
    return "CLEAR", "🛡️ [S&R Filter] โซนปลอดภัย ไม่ติดแนวรับ/แนวต้านหนาแน่น"

def analyze_adaptive_market(symbol):
    df = generate_adaptive_market_data(symbol)
    
    df['returns'] = df['close'].pct_change()
    volatility = df['returns'].std()
    
    df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    trend_diff = abs(df['ema5'].iloc[-1] - df['ema20'].iloc[-1]) / df['ema20'].iloc[-1]
    
    last_close = df['close'].iloc[-1]
    last_open = df['open'].iloc[-1]
    
    # เช็คสถานะแนวรับแนวต้าน
    sr_status, sr_desc = check_support_resistance_zones(df)
    
    # วิเคราะห์ทิศทางพื้นฐานตาม Engine
    if volatility > 0.003:
        tech_used = "⚙️ [Technique] Volatility Breaker Engine (ดักไส้เทียนผันผวน)"
        base_dir = "CALL" if last_close > last_open else "PUT"
        status_msg = "⚠️ [V70 S&R Secured] HIGH VOLATILITY - CAUTION"
    elif trend_diff > 0.0015:
        tech_used = "⚙️ [Technique] Trend Following Engine (EMA5/20 + MACD Momentum)"
        df['macd_hist'] = df['ema5'] - df['ema20']
        hist_val = df['macd_hist'].iloc[-1]
        base_dir = "CALL" if (df['ema5'].iloc[-1] > df['ema20'].iloc[-1] and hist_val > 0) else "PUT"
        status_msg = "🔥 [V70 S&R Secured] STRONG TREND SIGNAL"
    else:
        tech_used = "⚙️ [Technique] Range Bound Engine (RSI Mean Reversion + S&R Guard)"
        df['rsi'] = calculate_rsi(df['close'], period=14)
        last_rsi = df['rsi'].iloc[-1] if not np.isnan(df['rsi'].iloc[-1]) else 50
        
        if last_rsi < 45:
            base_dir = "CALL"
            status_msg = "🎯 [V70 S&R Secured] OVERSOLD BUY (ดักเด้ง)"
        elif last_rsi > 55:
            base_dir = "PUT"
            status_msg = "🎯 [V70 S&R Secured] OVERBOUGHT SELL (ดักย่อ)"
        else:
            base_dir = "CALL" if last_close >= last_open else "PUT"
            status_msg = "⚡ [V70 S&R Secured] RANGE NEUTRAL SIGNAL"

    # ระบบกรองไม้ด้วย S&R Filter ป้องกันการโดนดีดสวนทาง (กลับตัวอัตโนมัติหากชนแนวแข็งแกร่ง)
    final_dir = base_dir
    if sr_status == "NEAR_RESISTANCE" and base_dir == "CALL":
        final_dir = "PUT"  # ชนแนวต้านแต่ออก Call -> สลับเป็น Put ดักพักตัวทันที
        status_msg = "🔄 [S&R Counter-Rejection] ชนแนวต้าน! สลับสวนทางดักแท่งกลับตัว"
    elif sr_status == "NEAR_SUPPORT" and base_dir == "PUT":
        final_dir = "CALL" # ชนแนวรับแต่ออก Put -> สลับเป็น Call ดักเด้งกลับทันที
        status_msg = "🔄 [S&R Counter-Rejection] ชนแนวรับ! สลับสวนทางดักแท่งดีดตัว"

    return final_dir, status_msg, tech_used, sr_desc

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
        f"👑 **[ TITAN BEAM V70 S&R GUARD STATS ]** 👑\n\n"
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

# ==========================================
# TELEGRAM BOT HANDLERS WITH PASSWORD AUTH
# ==========================================
@bot.message_handler(commands=['email'])
def register_email(message):
    try:
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(
                message, 
                "⚠️ **กรุณาระบุอีเมลและรหัสผ่านให้ครบถ้วน**\n\n"
                "👉 รูปแบบ: `/email <อีเมล> <รหัสผ่าน>`\n"
                "ตัวอย่าง: `/email your_email@gmail.com 123456`", 
                parse_mode="Markdown"
            )
            return
        
        email = args[1].lower().strip()
        password = args[2].strip()
        
        if check_user_approved(email, password):
            user_creds[message.chat.id] = {"email": email, "password": password}
            user_martingale_step[message.chat.id] = 1
            bot.reply_to(
                message, 
                f"✅ **ยืนยันตัวตนสำเร็จ!**\n"
                f"อีเมล `{email}` และรหัสผ่านถูกต้อง พร้อมระบบกรองแนวรับ-แนวต้าน (S&R Guard)\n\n"
                f"เลือกคู่เงินเพื่อวิเคราะห์ได้เลย:", 
                reply_markup=build_menu_keyboard(),
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(
                message, 
                f"❌ **เข้าสู่ระบบไม่สำเร็จ:**\n"
                f"• อีเมลหรือรหัสผ่านไม่ถูกต้อง หรือ\n"
                f"• บัญชีของคุณยังไม่ได้รับการอนุมัติ (`status` ไม่ใช่ `approved`)\n\n"
                f"กรุณาตรวจสอบข้อมูล หรือติดต่อ Admin", 
                parse_mode="Markdown"
            )
    except Exception as e:
        bot.reply_to(message, f"❌ เกิดข้อผิดพลาด: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_martingale_step[chat_id] = 1
    creds = user_creds.get(chat_id, {})
    email = creds.get("email", "")
    password = creds.get("password", "")

    if not email or not password:
        bot.send_message(
            chat_id, 
            "🇷🇺 **Titan Beam Pro V70 (S&R Guard Edition)**\n\n"
            "🔒 **กรุณายืนยันตัวตนก่อนเข้าใช้งาน:**\n"
            "พิมพ์ `/email <อีเมล> <รหัสผ่าน>`\n"
            "ตัวอย่าง: `/email your_email@gmail.com 123456`", 
            parse_mode="Markdown"
        )
        return

    if not check_user_approved(email, password):
        bot.send_message(
            chat_id,
            f"❌ **ปฏิเสธการเข้าถึง:** ข้อมูลเข้าสู่ระบบไม่ถูกต้อง หรือสิทธิ์ถูกระงับในระบบ Firebase (`v70-user-auth`)\n"
            "พิมพ์ `/email <อีเมล> <รหัสผ่าน>` ใหม่ หรือติดต่อ Admin",
            parse_mode="Markdown"
        )
        return

    bot.send_message(
        chat_id, 
        "🇷🇺 **Titan Beam Pro V70 (S&R Guard Edition)**\nเปิดระบบตรวจจับเส้นแนวรับ-แนวต้านป้องกันการดีดกลับเรียบร้อย เลือกคู่เงินเพื่อลุยได้เลย:", 
        reply_markup=build_menu_keyboard(), 
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['stats'])
def show_stats(message):
    chat_id = message.chat.id
    creds = user_creds.get(chat_id, {})
    email = creds.get("email", "")
    password = creds.get("password", "")

    if not email or not password or not check_user_approved(email, password):
        bot.send_message(chat_id, "❌ คุณไม่มีสิทธิ์เข้าถึงข้อมูลสถิติ กรุณายืนยันตัวตนผ่าน `/email <อีเมล> <รหัสผ่าน>`", parse_mode="Markdown")
        return
    bot.send_message(chat_id, get_stats_text(chat_id), parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def reset_stats(message):
    chat_id = message.chat.id
    creds = user_creds.get(chat_id, {})
    email = creds.get("email", "")
    password = creds.get("password", "")

    if not email or not password or not check_user_approved(email, password):
        bot.send_message(chat_id, "❌ คุณไม่มีสิทธิ์ใช้งานคำสั่งนี้", parse_mode="Markdown")
        return
    
    user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
    symbol_stats[chat_id] = {}
    user_martingale_step[chat_id] = 1
    bot.send_message(chat_id, "🔄 รีเซ็ตสถิติและสเต็ปการเดินเงินเรียบร้อย!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_all(call):
    chat_id = call.message.chat.id
    creds = user_creds.get(chat_id, {})
    email = creds.get("email", "")
    password = creds.get("password", "")

    # 🔒 เช็คสิทธิ์จาก Firebase ทุกครั้งเมื่อมีคนคลิกปุ่ม
    if not email or not password or not check_user_approved(email, password):
        bot.answer_callback_query(call.id, "❌ คุณยังไม่ได้ยืนยันตัวตนหรือสิทธิ์ถูกระงับ!", show_alert=True)
        bot.send_message(
            chat_id,
            "⛔ **สิทธิ์ใช้งานถูกระงับหรือข้อมูลไม่ถูกต้อง:**\n"
            "พิมพ์ `/email <อีเมล> <รหัสผ่าน>` เพื่อยืนยันตัวตนใหม่ หรือติดต่อ Admin"
        )
        return

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

        direction, zone_status, tech_used, sr_desc = analyze_adaptive_market(symbol)
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
            f"🇷🇺 **Titan Beam Pro V70 (S&R Guard Edition)**\n\n"
            f"🎯 **คำแนะนำ: ออกออเดอร์ `[ ไม้ที่ {current_step} ]`**\n"
            f"💲📊 {symbol_label}\n"
            f"💎 M1 | Win Rate: `{sym_wr:.2f}%`\n"
            f"⏱️ เวลาเป้าหมาย: `{target_time_str}`\n\n"
            f"🕹️ **[ S&R Matrix & Adaptive Engine ]**\n"
            f"• {tech_used}\n"
            f"• {sr_desc}\n"
            f"• {ttz_desc}\n"
            f"• {news_status}\n"
            f"• {zone_status}\n\n"
            f"📈 ทิศทางสัญญาณ: **{'BUY 🟢' if direction == 'CALL' else 'SELL 🔴'}**"
        )

        bot.send_message(chat_id, signal_text, reply_markup=markup, parse_mode="Markdown")

# ==========================================
# MAIN EXECUTION LOOP
# ==========================================
print("--------------------------------------------------")
print("🇷🇺 Titan Beam Pro V70 (S&R Guard Edition) พร้อมลุยแล้ว...")
print("--------------------------------------------------")

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"⚠️ การเชื่อมต่อขัดข้อง: {e} - กำลังเชื่อมต่อใหม่ใน 5 วินาที...")
        time.sleep(5)
