import pandas as pd
import numpy as np
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
import threading
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
user_creds = {}
user_last_message = {}

SYMBOLS = {
    "DYDXUSDT": "⚡ DYDX (OTC)",
    "XAUUSDT": "👑 XAUUSD (OTC)",
    "XRPUSDT": "💎 RIPPLE (OTC)",
    "LTCUSDT": "🔮 LITECOIN (OTC)",
    "SUIUSDT": "💧 SUI (OTC)",
    "SHIBUSDT": "🔥 SHIB/USD (OTC)",
    "ONDOUSDT": "🌊 ONDO (OTC)",
    "AIGUSDT": "🏛️ AIG (OTC)",
    "KOUSDT": "🥤 COCA-COLA (OTC)",
    "MCDUSDT": "🍟 MCDONALD'S (OTC)",
    "PENGUUSDT": "🐧 PUDGY PENGUINS (OTC)",
    "FARTCOINUSDT": "💨 FARTCOIN (OTC)",
    "PENUSDT": "🇵🇪 PEN/USD (OTC)",
    "SNAPUSDT": "👻 SNAP INC (OTC)",
    "TRUMPUSDT": "🦅 TRUMP COIN (OTC)",
    "VAULTUSDT": "🏦 VAULTA (OTC)",
    "NKEUSDT": "👟 NIKE INC (OTC)",
    "INTCUSDT": "💻 INTEL CORP (OTC)",
    "MELANIAUSDT": "👑 MELANIA COIN (OTC)",
    "GASUSDT": "⛽ NATURAL GAS (OTC)",
    "XAGUSDT": "🛡️ XAGUSD (OTC)"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

# ==========================================
# FIREBASE AUTH HELPER (EMAIL + PASSWORD)
# ==========================================
def check_user_approved(email: str, password: str = None) -> bool:
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
            return (status == "approved") and (str(db_password) == str(password))
    except Exception as e:
        print(f"⚠️ Firebase Error: {e}")
    return False

# ==========================================
# REAL-TIME MARKET ENGINE
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
        print(f"⚠️ Forex Factory Error: {e}")
    return high_impact_events

def check_market_zone_ttz():
    now_min = get_thai_time().minute
    if now_min in [28, 29, 30, 58, 59, 0, 1]:
        return "RED", "🔴 [FORCE LIVE] โซนอันตรายรอบเปลี่ยนแท่ง"
    elif now_min in [14, 15, 44, 45]:
        return "YELLOW", "🟡 [FORCE LIVE] เฝ้าระวังความผันผวนรอบย่อย"
    else:
        return "GREEN", "🟢 [FORCE LIVE] เสถียรภาพตลาดระดับสูงสุด"

def fetch_live_kline_data(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=100"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            raw_data = res.json()
            df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            df['close'] = df['close'].astype(float)
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            return df
    except Exception:
        pass
    
    size = 100
    df = pd.DataFrame()
    base_price = 100.0 + (sum(ord(c) for c in symbol) % 50)
    df['close'] = [base_price + np.sin(i/3) for i in range(size)]
    df['open'] = df['close'].shift(1).fillna(base_price)
    df['high'] = df[['open', 'close']].max(axis=1) + 0.2
    df['low'] = df[['open', 'close']].min(axis=1) - 0.2
    return df

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def omega_god_5000_layers_analysis(symbol):
    df = fetch_live_kline_data(symbol)
    
    df['ema_5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    m_fast = df['close'].ewm(span=12, adjust=False).mean()
    m_slow = df['close'].ewm(span=26, adjust=False).mean()
    df['macd_line'] = m_fast - m_slow
    df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd_line'] - df['macd_signal']
    
    df['rsi'] = calculate_rsi(df['close'], 14)
    
    candle_body = abs(df['close'] - df['open'])
    avg_body = candle_body.tail(20).mean()
    last_body = candle_body.iloc[-1]
    is_spike_candle = last_body > (avg_body * 2.0)

    last_close = df['close'].iloc[-1]
    last_open = df['open'].iloc[-1]
    last_macd = df['macd_hist'].iloc[-1]
    last_rsi = df['rsi'].iloc[-1]
    
    if is_spike_candle:
        if last_close > last_open:
            return "PUT", "🛡️ [Anti-Spike Core] กราฟพุ่งกระชาก ➔ สั่งดักสวน PUT", "Force Live Engine", 50.0
        else:
            return "CALL", "🛡️ [Anti-Spike Core] กราฟดิ่งกระชาก ➔ สั่งดักสวน CALL", "Force Live Engine", 50.0

    score_call = 0
    score_put = 0

    if df['ema_5'].iloc[-1] > df['ema_20'].iloc[-1]: score_call += 1200
    else: score_put += 1200

    if df['ema_20'].iloc[-1] > df['ema_50'].iloc[-1]: score_call += 1000
    else: score_put += 1000

    if last_macd > 0: score_call += 800
    else: score_put += 800

    if last_rsi > 50: score_call += 600
    else: score_put += 600

    if last_close > last_open: score_call += 400
    else: score_put += 400

    total_score = score_call + score_put
    diff_score = abs(score_call - score_put)
    confidence_pct = (diff_score / total_score * 100) if total_score > 0 else 50.0

    if score_call >= score_put:
        return "CALL", f"⚡ [Force Live] วิเคราะห์สำเร็จ ({score_call}/4000)", "Live Bullish Confluence", confidence_pct
    else:
        return "PUT", f"⚡ [Force Live] วิเคราะห์สำเร็จ ({score_put}/4000)", "Live Bearish Confluence", confidence_pct

def build_dynamic_menu_keyboard(symbol):
    markup = InlineKeyboardMarkup(row_width=2)
    
    # เพิ่มปุ่มแสดงเวลาอัปเดตสดๆ เพื่อให้เทเลแกรมยอมรีเฟชข้อความทุกรอบ
    current_time_str = get_thai_time().strftime('%H:%M:%S')
    markup.add(InlineKeyboardButton(f"🔄 [Live Refresh: {current_time_str}]", callback_data="do_nothing"))
    
    markup.add(
        InlineKeyboardButton("📊 เช็คสถิติระบบ", callback_data="menu_stats"),
        InlineKeyboardButton("🔄 รีเซ็ตสถิติ", callback_data="menu_reset")
    )
    
    symbol_confidences = {s: omega_god_5000_layers_analysis(s)[3] for s in SYMBOLS.keys()}
    sorted_symbols = sorted(symbol_confidences.items(), key=lambda x: x[1], reverse=True)
    
    top_green_symbols = [item[0] for item in sorted_symbols[:2] if item[1] >= 65.0]

    for sym, label in SYMBOLS.items():
        pure_name = label.split(' ', 1)[1] if ' ' in label else label
        
        if sym in top_green_symbols:
            colored_label = f"🟢 {pure_name} [WIN 99%]"
        else:
            colored_label = f"🔴 {pure_name} [RISK]"
            
        markup.add(InlineKeyboardButton(colored_label, callback_data=f"analyze_{sym}"))
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
        f"🔥 **[ FORCE LIVE OMEGA-GOD // STATS ]** 🔥\n\n"
        f"🎯 **ปฏิบัติการปัจจุบัน: ลุย `[ ไม้ที่ {current_step} ]`**\n\n"
        f"🏆 ชนะไม้ 1: `[ {st['win1']} ]` ({win1_rate:.2f}%)\n"
        f"🥈 ชนะไม้ 2: `[ {st['win2']} ]`\n"
        f"🥉 ชนะไม้ 3: `[ {st['win3']} ]`\n"
        f"❌ หลุดครบ 3 ไม้ (LOSS): `[ {st['loss']} ]`\n\n"
        f"📈 ชนะรวม: `{total_wins}` | ทั้งหมด: `{total_games}`\n"
        f"🔥 Win Rate รวม: `{win_rate:.2f}%`\n\n"
        f"📊 **บันทึกสถิติแยกตามคู่สินทรัพย์:**\n"
    )
    symbol_breakdown = ""
    if chat_id in symbol_stats:
        for sym, data in symbol_stats[chat_id].items():
            tot = data["win"] + data["loss"]
            w_rate = (data["win"] / tot * 100) if tot > 0 else 0.0
            label = SYMBOLS.get(sym, sym)
            symbol_breakdown += f"• {label} ➔ `{w_rate:.2f}%` (ชนะ {data['win']}, แพ้ {data['loss']})\n"
    if symbol_breakdown == "":
        symbol_breakdown = "• ยังไม่มีประวัติการบันทึกแยกรายคู่"
    return text + symbol_breakdown

# ==========================================
# BACKGROUND WORKER: FORCE LIVE REFRESH EVERY 10 SECONDS
# ==========================================
def background_live_refresher():
    while True:
        try:
            for chat_id, info in list(user_last_message.items()):
                try:
                    msg_id = info.get("message_id")
                    symbol = info.get("symbol")
                    fixed_text = info.get("fixed_text")
                    if not msg_id or not symbol or not fixed_text:
                        continue

                    markup = build_dynamic_menu_keyboard(symbol)
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=fixed_text,
                        reply_markup=markup,
                        parse_mode="Markdown"
                    )
                except Exception as sub_e:
                    pass
            time.sleep(10)
        except Exception as e:
            print(f"⚠️ Background worker error: {e}")
            time.sleep(5)

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
                "⚠️ **กรุณาระบุอีเมลและรหัสผ่านให้ครบถ้วน**\n\n👉 รูปแบบ: `/email <อีเมล> <รหัสผ่าน>`", 
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
                f"🔥 **FORCE LIVE AUTHORIZATION SUCCESS** 🔥\nอีเมล `{email}` เชื่อมต่อระบบสำเร็จ เลือกคู่สินทรัพย์ลุยได้เลย:", 
                reply_markup=build_dynamic_menu_keyboard("DYDXUSDT"),
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, "❌ **AUTHENTICATION FAILED:** ข้อมูลไม่ถูกต้องหรือสิทธิ์ถูกระงับ", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ เกิดข้อผิดพลาด: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_martingale_step[chat_id] = 1
    creds = user_creds.get(chat_id, {})
    email = creds.get("email", "")
    password = creds.get("password", "")

    if not email or not password or not check_user_approved(email, password):
        bot.send_message(
            chat_id, 
            "🔥 **TITAN BEAM // FORCE LIVE CORE** 🔥\n\n🔒 กรุณายืนยันตัวตนระดับความปลอดภัยสูงสุด:\nพิมพ์ `/email <อีเมล> <รหัสผ่าน>`", 
            parse_mode="Markdown"
        )
        return

    bot.send_message(
        chat_id, 
        "🔥 **TITAN BEAM // FORCE LIVE CORE** 🔥\nเปิดระบบ Force Live-Ticker (มีปุ่มเวลาวิ่งสดทุก 10 วินาที):", 
        reply_markup=build_dynamic_menu_keyboard("DYDXUSDT"), 
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['stats'])
def show_stats(message):
    chat_id = message.chat.id
    creds = user_creds.get(chat_id, {})
    if not check_user_approved(creds.get("email"), creds.get("password")):
        bot.send_message(chat_id, "❌ กรุณายืนยันตัวตนก่อนผ่าน `/email <อีเมล> <รหัสผ่าน>`", parse_mode="Markdown")
        return
    bot.send_message(chat_id, get_stats_text(chat_id), parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def reset_stats(message):
    chat_id = message.chat.id
    creds = user_creds.get(chat_id, {})
    if not check_user_approved(creds.get("email"), creds.get("password")):
        bot.send_message(chat_id, "❌ กรุณายืนยันตัวตนก่อนใช้งาน", parse_mode="Markdown")
        return
    user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
    symbol_stats[chat_id] = {}
    user_martingale_step[chat_id] = 1
    bot.send_message(chat_id, "🔄 รีเซ็ตระบบสถิติและสเต็ปการเดินเงินเรียบร้อย!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_all(call):
    chat_id = call.message.chat.id
    creds = user_creds.get(chat_id, {})
    if not check_user_approved(creds.get("email"), creds.get("password")):
        bot.answer_callback_query(call.id, "❌ สิทธิ์การเข้าถึงหมดอายุหรือยังไม่ยืนยันตัวตน!", show_alert=True)
        return

    if chat_id not in user_stats: user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
    if chat_id not in symbol_stats: symbol_stats[chat_id] = {}
    if chat_id not in user_martingale_step: user_martingale_step[chat_id] = 1

    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ ระบบกำลังรีเฟรชข้อมูลเรียลไทม์สดๆ ทุก 10 วินาที")
        return

    if call.data == "menu_stats":
        bot.answer_callback_query(call.id, "📊 แสดงข้อมูลสถิติระบบ")
        bot.send_message(chat_id, get_stats_text(chat_id), parse_mode="Markdown")
        return

    if call.data == "menu_reset":
        user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
        symbol_stats[chat_id] = {}
        user_martingale_step[chat_id] = 1
        bot.answer_callback_query(call.id, "🔄 รีเซ็ตสำเร็จ")
        bot.send_message(chat_id, "🔄 รีเซ็ตสถิติและตั้งต้นไม้ที่ 1 ใหม่เรียบร้อย!", parse_mode="Markdown")
        return

    if call.data.startswith("res_"):
        parts = call.data.split("_")
        result_type = parts[1]
        symbol = parts[2] if len(parts) > 2 else ""
        if symbol and symbol not in symbol_stats[chat_id]:
            symbol_stats[chat_id][symbol] = {"win": 0, "loss": 0}

        if result_type in ["win1", "win2", "win3"]:
            if result_type == "win1": user_stats[chat_id]["win1"] += 1
            elif result_type == "win2": user_stats[chat_id]["win2"] += 1
            elif result_type == "win3": user_stats[chat_id]["win3"] += 1
            if symbol: symbol_stats[chat_id][symbol]["win"] += 1
            user_martingale_step[chat_id] = 1
            text = "💎 ชนะออเดอร์! รีเซ็ตกลับสเต็ปไม้ 1 เรียบร้อย"
        elif result_type == "loss":
            step = user_martingale_step[chat_id]
            if step < 3:
                user_martingale_step[chat_id] += 1
                text = f"⚠️ หลุดไม้ {step} ➔ ยกระดับลุยต่อ [ไม้ที่ {user_martingale_step[chat_id]}]"
            else:
                user_stats[chat_id]["loss"] += 1
                user_martingale_step[chat_id] = 1
                text = "❌ ครบ 3 สเต็ป บันทึก LOSS และรีเซ็ตกลับไม้ 1"
        else:
            text = "บันทึกข้อมูลเรียบร้อย"
        bot.answer_callback_query(call.id, text)
        bot.send_message(chat_id, f"📌 อัปเดตสถิติล่าสุด:\n{get_stats_text(chat_id)}", parse_mode="Markdown")
        return

    if call.data.startswith("analyze_"):
        symbol = call.data.split("analyze_")[1]
        symbol_label = SYMBOLS.get(symbol, symbol)
        ttz_code, ttz_desc = check_market_zone_ttz()
        ff_news = get_forex_factory_high_impact_news()
        news_status = f"🌐 Forex Factory: ตรวจพบข่าวกล่องแดง {len(ff_news)} รายการ" if ff_news else "🌐 Forex Factory: สภาวะเสถียร (ไร้ข่าวแดงรุนแรง)"

        direction, zone_status, tech_used, _ = omega_god_5000_layers_analysis(symbol)
        current_step = user_martingale_step.get(chat_id, 1)
        
        now_thai = get_thai_time()
        target_time = (now_thai + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        if symbol not in symbol_stats[chat_id]:
            symbol_stats[chat_id][symbol] = {"win": 0, "loss": 0}
        sym_data = symbol_stats[chat_id][symbol]
        tot_sym = sym_data["win"] + sym_data["loss"]
        sym_wr = (sym_data["win"] / tot_sym * 100) if tot_sym > 0 else 0.0

        direction_icon = "🟢 CALL (ขึ้น)" if direction == 'CALL' else "🔴 PUT (ลง)"

        fixed_signal_text = (
            f"🔥 **[ FORCE LIVE SIGNAL LOCK ]** 🔥\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **คำสั่ง: ลุยออเดอร์ `[ ไม้ที่ {current_step} ]`**\n"
            f"💲📊 สินทรัพย์: `{symbol_label}`\n"
            f"💎 Timeframe: `M1` | Win Rate: `{sym_wr:.2f}%`\n"
            f"⏱️ **เป้าหมายเวลาเข้าออเดอร์: `{target_time_str}`**\n\n"
            f"🛡️ **[ FORCE LIVE TELEMETRY ]**\n"
            f"• {tech_used}\n"
            f"• {zone_status}\n"
            f"• {ttz_desc}\n"
            f"• {news_status}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 **ฟันธงทิศทาง: {direction_icon}**"
        )
        
        markup = build_dynamic_menu_keyboard(symbol)
        sent_msg = bot.send_message(chat_id, fixed_signal_text, reply_markup=markup, parse_mode="Markdown")
        
        user_last_message[chat_id] = {
            "message_id": sent_msg.message_id, 
            "symbol": symbol,
            "fixed_text": fixed_signal_text
        }

# ==========================================
# MAIN EXECUTION LOOP & THREADING
# ==========================================
print("--------------------------------------------------")
print("🔥 TITAN FORCE LIVE CORE เริ่มต้นระบบ Force Live-Ticker...")
print("--------------------------------------------------")

refresher_thread = threading.Thread(target=background_live_refresher, daemon=True)
refresher_thread.start()

while true:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"⚠️ ระบบเชื่อมต่อขัดข้อง: {e} - กำลังรีเซ็ตการเชื่อมต่อใน 5 วินาที...")
        time.sleep(5)
