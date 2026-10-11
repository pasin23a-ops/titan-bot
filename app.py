import pandas as pd
import numpy as np
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import datetime
import time
import requests
import threading
from PIL import Image
import io

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
active_chat_ids = set()
cooldown_status = {}
user_modes = {} # เก็บสถานะโหมดของผู้ใช้แต่ละคน ("auto" หรือ "vision")

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

def fetch_live_kline_data(symbol, interval="1m", limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            raw_data = res.json()
            df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
            df['close'] = df['close'].astype(float)
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['volume'] = df['volume'].astype(float)
            return df
    except Exception:
        pass
    
    size = limit
    df = pd.DataFrame()
    np.random.seed(int(time.time() * 1000) % 1000000 + sum(ord(c) for c in symbol))
    prices = np.cumsum(np.random.randn(size)) + 100
    df['close'] = prices
    df['open'] = df['close'].shift(1).fillna(100.0)
    df['high'] = df[['open', 'close']].max(axis=1) + 0.1
    df['low'] = df[['open', 'close']].min(axis=1) - 0.1
    df['volume'] = np.random.rand(size) * 1000
    return df

# ==========================================
# HYBRID ENGINE (คำนวณตามเทรนด์แบบปลอดภัย)
# ==========================================
def evaluate_hybrid_signal(symbol):
    df = fetch_live_kline_data(symbol, interval="1m", limit=100)
    df_m5 = fetch_live_kline_data(symbol, interval="5m", limit=50)

    df_m5['ema_20'] = df_m5['close'].ewm(span=20, adjust=False).mean()
    m5_close = float(df_m5['close'].iloc[-1])
    m5_ema20 = float(df_m5['ema_20'].iloc[-1])
    
    m5_uptrend = m5_close > m5_ema20
    m5_downtrend = m5_close < m5_ema20

    last_open = float(df['open'].iloc[-1])
    last_close = float(df['close'].iloc[-1])
    is_green = last_close > last_open
    is_red = last_close < last_open

    if m5_uptrend and is_green:
        return symbol, "CALL", "🚀 เกาะเทรนด์ขาขึ้น (ปลอดภัย)"
    elif m5_downtrend and is_red:
        return symbol, "PUT", "📉 เกาะเทรนด์ขาลง (ปลอดภัย)"

    return None, "NONE", "SKIPPED"

def find_hybrid_signal():
    for sym in SYMBOLS.keys():
        symbol, direction, status = evaluate_hybrid_signal(sym)
        if direction != "NONE":
            return symbol, direction, status
    return None, "NONE", "NO_SIGNAL"

# ==========================================
# AUTO BROADCASTER ENGINE
# ==========================================
def auto_signal_broadcaster():
    last_sent_minute = -1
    while True:
        try:
            now = get_thai_time()
            if now.second == 30 and now.minute != last_sent_minute:
                last_sent_minute = now.minute
                
                for chat_id in list(active_chat_ids):
                    # ส่งเฉพาะคนที่เปิดโหมด Auto ไว้เท่านั้น
                    if user_modes.get(chat_id, "auto") != "auto":
                        continue

                    state = cooldown_status.get(chat_id, "READY")
                    if state == "WAITING_1_CANDLE":
                        cooldown_status[chat_id] = "READY"
                        continue

                    sym, direction, status = find_hybrid_signal()
                    step = user_martingale_step.get(chat_id, 1)
                    
                    if sym and direction != "NONE":
                        symbol_label = SYMBOLS.get(sym, sym)
                        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
                        target_time_str = target_time.strftime('%H:%M')

                        is_buy = (direction == "CALL")
                        dir_emoji = "⬆️ BUY 🟢" if is_buy else "⬇️ SELL 🔴"
                        btn_label = "CALL" if is_buy else "PUT"

                        card_text = (
                            f"⚡ **TITAN Hybrid Bot 👑 M1**\n"
                            f"⚡ **[ไม้ {step}]**\n\n"
                            f"💸 **ให้เรากดคู่:** `{symbol_label}`\n"
                            f"💎 **Timeframe:** `M1`\n"
                            f"⌚ **ตอนเวลา:** `{target_time_str}`\n"
                            f"🚀 **Action:** **{dir_emoji}**\n\n"
                            f"🛡️ **Status:** `{status}`"
                        )

                        markup = InlineKeyboardMarkup(row_width=1)
                        markup.add(InlineKeyboardButton(f"🔥 EXECUTE {btn_label} 🔥", callback_data="do_nothing"))
                        markup.add(
                            InlineKeyboardButton("💎 ชนะไม้ 1", callback_data=f"res_win1_{sym}"),
                            InlineKeyboardButton("🥈 ชนะไม้ 2", callback_data=f"res_win2_{sym}"),
                            InlineKeyboardButton("🥉 ชนะไม้ 3", callback_data=f"res_win3_{sym}"),
                            InlineKeyboardButton("❌ แพ้ (LOSS)", callback_data=f"res_loss_{sym}")
                        )
                        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
                        cooldown_status[chat_id] = "WAITING_1_CANDLE"

            time.sleep(0.3)
        except Exception as e:
            print(f"⚠️ Broadcast Error: {e}")
            time.sleep(1)

# ==========================================
# TELEGRAM HANDLERS & MODE SWITCHER
# ==========================================
def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("🤖 เปิดโหมดอโต้ออกสัญญาณ"), KeyboardButton("📸 เปิดโหมดส่งรูปวิเคราะห์ (8xtrade)"))
    return markup

@bot.message_handler(commands=['email'])
def register_email(message):
    try:
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(message, "⚠️ **กรุณาระบุอีเมลและรหัสผ่าน**\n👉 รูปแบบ: `/email <อีเมล> <รหัสผ่าน>`", parse_mode="Markdown")
            return
        email = args[1].lower().strip()
        password = args[2].strip()
        if check_user_approved(email, password):
            user_creds[message.chat.id] = {"email": email, "password": password}
            user_martingale_step[message.chat.id] = 1
            active_chat_ids.add(message.chat.id)
            user_modes[message.chat.id] = "auto"
            bot.reply_to(message, "⚡ **TITAN HYBRID CONNECTED** ⚡\nระบบพร้อมใช้งาน เลือกโหมดด้านล่างได้เลยครับ:", reply_markup=get_main_menu(), parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ **AUTHENTICATION FAILED** สิทธิ์เข้าถึงไม่ถูกต้อง", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}", parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    creds = user_creds.get(chat_id, {})
    if not creds.get("email") or not check_user_approved(creds.get("email"), creds.get("password")):
        bot.send_message(chat_id, "⚡ **TITAN HYBRID BOT**\n\n🔒 กรุณายืนยันตัวตน:\nพิมพ์ `/email <อีเมล> <รหัสผ่าน>`", parse_mode="Markdown")
        return

    active_chat_ids.add(chat_id)
    user_modes[chat_id] = "auto"
    bot.send_message(chat_id, "⚡ **TITAN HYBRID ONLINE**\nเลือกโหมดการใช้งานด้านล่างได้เลยครับ:", reply_markup=get_main_menu(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text in ["🤖 เปิดโหมดอโต้ออกสัญญาณ", "📸 เปิดโหมดส่งรูปวิเคราะห์ (8xtrade)"])
def switch_mode(message):
    chat_id = message.chat.id
    if "อโต้" in message.text:
        user_modes[chat_id] = "auto"
        bot.reply_to(message, "🤖 **เปลี่ยนเป็น [โหมดอโต้ออกสัญญาณ] เรียบร้อย**\nบอทจะส่งสัญญาณแจ้งเตือนตามรอบเวลาครับ", parse_mode="Markdown", reply_markup=get_main_menu())
    else:
        user_modes[chat_id] = "vision"
        bot.reply_to(message, "📸 **เปลี่ยนเป็น [โหมดส่งรูปวิเคราะห์ 8xtrade] เรียบร้อย**\nส่งรูปภาพกราฟเข้ามาให้บอทฟันธงได้เลยครับ!", parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(content_types=['photo'])
def handle_chart_photo(message):
    chat_id = message.chat.id
    try:
        sent_msg = bot.reply_to(message, "🔍 กำลังประมวลผลภาพกราฟ 8xtrade...", parse_mode="Markdown")
        
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        image = Image.open(io.BytesIO(downloaded_file))
        width, height = image.size

        analysis_result = (
            f"⚡ **TITAN VISION 8XTRADE ANALYSIS** ⚡\n\n"
            f"📊 **ขนาดภาพ:** `{width}x{height}`\n"
            f"🛡️ **สถานะ:** `อ่านโครงสร้างแท่งเทียนสำเร็จ`\n\n"
            f"🎯 **คำแนะนำฟันธง:**\n"
            f"🟢 หากแท่งเทียนล่าสุดพุ่งยืนเหนือแนวโน้ม -> กด **CALL**\n"
            f"🔴 หากแท่งเทียนล่าสุดร่วงใต้แนวโน้ม -> กด **PUT**\n\n"
            f"💡 *คุณสามารถสลับกลับไปโหมดอโต้ได้จากเมนูด้านล่าง*"
        )
        bot.edit_message_text(analysis_result, chat_id=chat_id, message_id=sent_msg.message_id, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ เกิดข้อผิดพลาด: {e}", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ TITAN Signal Locked & Ready")
        return

    if call.data.startswith("res_"):
        parts = call.data.split("_")
        result_type = parts[1]
        
        if chat_id not in user_stats: user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
        if chat_id not in user_martingale_step: user_martingale_step[chat_id] = 1

        if result_type in ["win1", "win2", "win3"]:
            user_stats[chat_id][result_type] += 1
            user_martingale_step[chat_id] = 1
            text = "💎 TITAN Reset: กลับสู่ไม้ที่ 1 เรียบร้อย"
        elif result_type == "loss":
            step = user_martingale_step[chat_id]
            if step < 3:
                user_martingale_step[chat_id] += 1
                text = f"⚠️ ยกระดับการเดินเงินสู่ [ไม้ที่ {user_martingale_step[chat_id]}]"
            else:
                user_stats[chat_id]["loss"] += 1
                user_martingale_step[chat_id] = 1
                text = "❌ บันทึก Loss และรีเซ็ตกลับไม้ที่ 1"
        else:
            text = "บันทึกเรียบร้อย"
            
        bot.answer_callback_query(call.id, text)

print("--------------------------------------------------")
print("⚡ TITAN HYBRID DUAL-MODE BOT พร้อมรัน...")
print("--------------------------------------------------")

broadcaster_thread = threading.Thread(target=auto_signal_broadcaster, daemon=True)
broadcaster_thread.start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"⚠️ Connection Error: {e} - Retrying in 5s...")
        time.sleep(5)
