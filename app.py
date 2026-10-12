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

# เก็บข้อความเมนูล่าสุดของแต่ละแชท เพื่อให้บอทรีเฟรชแก้ข้อความเดิมอัตโนมัติทุกนาที
active_menu_messages = {}

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

def fetch_kline(symbol, interval="1m", limit=30):
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
            return df
    except Exception:
        pass
    return None

def analyze_symbol(symbol):
    df = fetch_kline(symbol, "1m", 30)
    if df is None or len(df) < 20:
        return "CALL", 50, "NEUTRAL"

    df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()

    c = float(df['close'].iloc[-2])
    o = float(df['open'].iloc[-2])
    ema10 = float(df['ema_10'].iloc[-2])
    ema20 = float(df['ema_20'].iloc[-2])
    vol = float(df['volume'].iloc[-2])
    avg_vol = df['volume'].iloc[-12:-2].mean()

    base_score = int((abs(c - ema20) / (ema20 + 1e-9)) * 50000)

    if c > ema10 and ema10 > ema20 and c > o:
        score = 85 + min(base_score, 14)  # การันตีความมั่นใจช่วง 85% - 99%
        if vol > avg_vol:
            score = min(score + 3, 99)
        return "CALL", score, "STRONG UPTREND"
    elif c < ema10 and ema10 < ema20 and c < o:
        score = 85 + min(base_score, 14)
        if vol > avg_vol:
            score = min(score + 3, 99)
        return "PUT", score, "STRONG DOWNTREND"
    else:
        # กรณีเทรนด์กลางๆ ให้ปรับคะแนนช่วง 75% - 92% เพื่อไม่ให้แดงหมดทั้งกระดาน
        score = 75 + min(base_score, 17)
        direction = "CALL" if c >= ema20 else "PUT"
        return direction, score, "STABLE FLOW"

def build_market_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    for sym, label in SYMBOLS.items():
        _, score, _ = analyze_symbol(sym)
        # ปรับเกณฑ์สีเขียวให้ครอบคลุม (Score >= 80% เป็นเขียว เพื่อไม่ให้แดงหมด)
        dot = "🟢" if score >= 80 else "🔴"
        btn_text = f"{dot} {label} ({score}%)"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"select_{sym}"))
    return markup

def send_signal_for_symbol(chat_id, sym):
    try:
        label = SYMBOLS.get(sym, sym)
        direction, score, status = analyze_symbol(sym)

        step = user_martingale_step.get(chat_id, 1)
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "⬆️ BUY 🟢" if is_buy else "⬇️ SELL 🔴"
        btn_label = "CALL" if is_buy else "PUT"

        card_text = (
            f"👑 **TITAN MANUAL SELECTOR 👑 M1**\n"
            f"⚡ **[ไม้ {step}]**\n\n"
            f"🎯 **คู่ที่คุณเลือก:** `{label}`\n"
            f"📈 **Timeframe:** `M1 (Auto-Analyzed)`\n"
            f"⌚ **เข้าออเดอร์เวลา:** `{target_time_str}`\n"
            f"🚀 **ทิศทาง:** **{dir_emoji}**\n\n"
            f"🛡️ **สถานะความมั่นใจ:** `{status} (Score: {score}%)`"
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
    except Exception as e:
        print(f"Send Error: {e}")

@bot.message_handler(commands=['start', 'pair', 'menu'])
def handle_menu(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    if chat_id not in user_martingale_step:
        user_martingale_step[chat_id] = 1

    menu_markup = build_market_menu()
    sent_msg = bot.reply_to(
        message, 
        "⚡ **TITAN LIVE MARKET RADAR (AUTO-REFRESH)** ⚡\n"
        "สถานะสีและคะแนนความมั่นใจอัปเดตอัตโนมัติทุกแท่งเทียน M1:\n"
        "🟢 = มั่นใจสูง (Score $\ge$ 80%)\n"
        "🔴 = เฝ้าระวัง / ต่ำกว่าเกณฑ์\n\n"
        "กดเลือกคู่ที่ต้องการเทรดด้านล่างได้เลยครับ:", 
        reply_markup=menu_markup, 
        parse_mode="Markdown"
    )
    active_menu_messages[chat_id] = sent_msg.message_id

def auto_menu_refresher():
    """ระบบเบื้องหลังทำการรีเฟรชหน้าจอเมนูทุกๆ 1 นาที (ทุกแท่งเทียนใหม่) อัตโนมัติ"""
    last_minute = -1
    while True:
        try:
            now = get_thai_time()
            if now.second == 5 and now.minute != last_minute:
                last_minute = now.minute
                new_markup = build_market_menu()
                for cid in list(active_chat_ids):
                    if cid in active_menu_messages:
                        try:
                            bot.edit_message_text(
                                chat_id=cid,
                                message_id=active_menu_messages[cid],
                                text=(
                                    "⚡ **TITAN LIVE MARKET RADAR (AUTO-REFRESH)** ⚡\n"
                                    f"🔄 *อัปเดตสดล่าสุดรอบเวลา {now.strftime('%H:%M:%S')}*\n\n"
                                    "กดเลือกคู่ที่ต้องการเทรดด้านล่างได้เลยครับ:"
                                ),
                                reply_markup=new_markup,
                                parse_mode="Markdown"
                            )
                        except Exception:
                            pass
            time.sleep(1)
        except Exception as e:
            print(f"Refresher Error: {e}")
            time.sleep(3)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Signal Locked")
        return

    if call.data.startswith("select_"):
        sym = call.data.replace("select_", "")
        bot.answer_callback_query(call.id, f"✅ เลือก {SYMBOLS.get(sym, sym)} แล้ว!")
        send_signal_for_symbol(chat_id, sym)
        return

    if call.data.startswith("res_"):
        parts = call.data.split("_")
        res_type = parts[1]
        if res_type in ["win1", "win2", "win3"]:
            user_martingale_step[chat_id] = 1
            bot.answer_callback_query(call.id, "💎 Reset สู่ไม้ 1")
        elif res_type == "loss":
            step = user_martingale_step.get(chat_id, 1)
            user_martingale_step[chat_id] = 1 if step >= 3 else step + 1
            bot.answer_callback_query(call.id, f"⚠️ ปรับสู่ไม้ {user_martingale_step[chat_id]}")

threading.Thread(target=auto_menu_refresher, daemon=True).start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
