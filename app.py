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
last_global_signal_time = 0 

# คูดาวเฉพาะคู่ที่เสี่ยง/อันตราย
symbol_cooldowns = {}
DANGER_PAIR_COOLDOWN = 180  

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

def fetch_kline(symbol, interval="1m", limit=40):
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
    rsi = 100 - (100 / (1 + rs))
    return rsi

def scan_and_broadcast():
    global last_global_signal_time
    last_sent_minute = -1
    
    while True:
        try:
            now = get_thai_time()
            # ทำงานทุกๆ วินาทีที่ 30 ของนาที
            if now.second >= 30 and now.minute != last_sent_minute:
                last_sent_minute = now.minute
                
                # วนหาคู่ที่ดีที่สุดในรอบนี้
                best_sym = None
                best_dir = "NONE"
                best_score = 100
                best_status = "FLOW READY"
                current_time = time.time()

                for sym, label in SYMBOLS.items():
                    # เช็คคูดาวเฉพาะคู่ที่เสี่ยง
                    if sym in symbol_cooldowns and current_time < symbol_cooldowns[sym]:
                        continue
                        
                    df = fetch_kline(sym, "1m", 40)
                    if df is None or len(df) < 30:
                        continue
                        
                    df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
                    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
                    df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
                    df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
                    df['macd'] = df['ema_12'] - df['ema_26']
                    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
                    df['hist'] = df['macd'] - df['signal']
                    df['rsi'] = calculate_rsi(df['close'], 14)

                    c = float(df['close'].iloc[-2])
                    o = float(df['open'].iloc[-2])
                    ema10 = float(df['ema_10'].iloc[-2])
                    ema20 = float(df['ema_20'].iloc[-2])
                    rsi_val = float(df['rsi'].iloc[-2])
                    
                    if pd.isna(rsi_val):
                        rsi_val = 50.0

                    raw_distance = int((abs(c - ema20) / (ema20 + 1e-9)) * 100000)

                    # ถ้าเสี่ยง/ห่างเกินไป ให้ติดคูดาวเฉพาะคู่นี้แล้วข้าม
                    if raw_distance > 180:
                        symbol_cooldowns[sym] = current_time + DANGER_PAIR_COOLDOWN
                        continue

                    direction = "NONE"
                    if c < ema10 and c < ema20 and c <= o:
                        direction = "PUT"
                        best_status = f"DOWNTREND (RSI: {int(rsi_val)})"
                    elif c > ema10 and c > ema20 and c >= o:
                        direction = "CALL"
                        best_status = f"UPTREND (RSI: {int(rsi_val)})"

                    if direction != "NONE":
                        best_sym = sym
                        best_dir = direction
                        best_score = max(80, min(160, raw_distance))
                        break # เจอแล้วหยิบส่งทันที

                # ถ้าหาคู่ตามเทรนด์ไม่ได้ บังคับหยิบตัวแรกที่ไม่ติดคูดาวมาส่งทันทีเพื่อให้สัญญาณไม่ขาด
                if not best_sym:
                    for sym in SYMBOLS.keys():
                        if sym not in symbol_cooldowns or current_time >= symbol_cooldowns[sym]:
                            df_t = fetch_kline(sym, "1m", 15)
                            if df_t is not None and len(df_t) > 2:
                                c_t = float(df_t['close'].iloc[-2])
                                o_t = float(df_t['open'].iloc[-2])
                                best_sym = sym
                                best_dir = "CALL" if c_t >= o_t else "PUT"
                                best_status = "FORCE FLOW SYNC"
                                best_score = 100
                                break

                # ส่งข้อความเข้า Telegram ทุกห้องแชทที่กด /start ไว้
                if best_sym and best_dir != "NONE":
                    label = SYMBOLS.get(best_sym, best_sym)
                    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
                    target_time_str = target_time.strftime('%H:%M')
                    
                    is_buy = (best_dir == "CALL")
                    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
                    btn_label = "CALL" if is_buy else "PUT"

                    for chat_id in list(active_chat_ids):
                        step = user_martingale_step.get(chat_id, 1)
                        card_text = (
                            f"⚡ **TITAN AUTO-PILOT (v14.1 Direct Flow)** ⚡\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🥊 **การเดินเงิน:** `ไม้ที่ {step}`\n"
                            f"🎯 **คู่คำนวณสด:** `{label}` *(วนซ้ำได้อิสระ)*\n"
                            f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
                            f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
                            f"📊 **สถานะ:** `{best_status}`\n"
                            f"🛡️ **Quality Score:** `{best_score} PTS`\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"⏱️ *Cooldown: สัญญาณไหลลื่นตรงเวลาทุกนาที*"
                        )

                        markup = InlineKeyboardMarkup(row_width=1)
                        markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
                        markup.add(
                            InlineKeyboardButton("💎 ชนะไม้ 1", callback_data=f"res_win1_{best_sym}"),
                            InlineKeyboardButton("🥈 ชนะไม้ 2", callback_data=f"res_win2_{best_sym}"),
                            InlineKeyboardButton("🥉 ชนะไม้ 3", callback_data=f"res_win3_{best_sym}"),
                            InlineKeyboardButton("❌ แพ้ (LOSS)", callback_data=f"res_loss_{best_sym}")
                        )
                        try:
                            bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
                        except Exception as e:
                            print(f"Telegram Send Error: {e}")

            time.sleep(0.5)
        except Exception as e:
            print(f"Broadcast Loop Error: {e}")
            time.sleep(1)

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    if chat_id not in user_martingale_step:
        user_martingale_step[chat_id] = 1
    
    bot.reply_to(
        message, 
        "🚀 **TITAN AUTO-PILOT v14.1 ACTIVATED** 🚀\n"
        "อัปเกรดระบบ Direct Flow ยิงตรงเข้า Telegram แบบเรียลไทม์ สัญญาณเด้งมาแน่นอนทุกแท่งเทียนครับ!", 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Direct Flow Active")
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

# เริ่มต้นเธรดสแกนและส่งสัญญาณตรง
threading.Thread(target=scan_and_broadcast, daemon=True).start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
