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
symbol_cooldown = {}

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

def fetch_kline(symbol, interval, limit=40):
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

def analyze_future_scenarios(symbol):
    df_m5 = fetch_kline(symbol, "5m", 20)
    df_m1 = fetch_kline(symbol, "1m", 30)

    if df_m5 is None or len(df_m5) < 10 or df_m1 is None or len(df_m1) < 20:
        return "NONE", 0, "DATA_ERROR"

    # 1. วิเคราะห์เทรนด์หลักจาก M5 (แท่งที่ปิดแล้ว)
    df_m5['ema_20'] = df_m5['close'].ewm(span=20, adjust=False).mean()
    m5_close = float(df_m5['close'].iloc[-2])
    m5_ema = float(df_m5['ema_20'].iloc[-2])
    is_m5_uptrend = m5_close > m5_ema
    is_m5_downtrend = m5_close < m5_ema

    # 2. วิเคราะห์ M1 และจำลองอนาคต (Scenario Projection)
    df_m1['ema_20'] = df_m1['close'].ewm(span=20, adjust=False).mean()
    o = float(df_m1['open'].iloc[-2])
    c = float(df_m1['close'].iloc[-2])
    ema = float(df_m1['ema_20'].iloc[-2])
    vol = float(df_m1['volume'].iloc[-2])
    avg_vol = df_m1['volume'].iloc[-10:-2].mean()

    body_size = abs(c - o)
    score_base = int((abs(c - ema) / (ema + 1e-9)) * 10000)

    # จำลอง Scenario A: Momentum Continuation (ไปต่อตามเทรนด์)
    if is_m5_uptrend and c > ema and c > o:
        score = score_base + int((vol / (avg_vol + 1e-9)) * 50)
        return "CALL", score, f"SCENARIO: UPTREND CONTINUATION (Score: {score})"

    elif is_m5_downtrend and c < ema and c < o:
        score = score_base + int((vol / (avg_vol + 1e-9)) * 50)
        return "PUT", score, f"SCENARIO: DOWNTREND CONTINUATION (Score: {score})"

    # จำลอง Scenario B: Pullback / Trend Support (ย่อตัวรับเทรนด์)
    if is_m5_uptrend and c >= ema:
        score = score_base + 30
        return "CALL", score, f"SCENARIO: M5 BULLISH PULLBACK (Score: {score})"

    elif is_m5_downtrend and c <= ema:
        score = score_base + 30
        return "PUT", score, f"SCENARIO: M5 BEARISH PULLBACK (Score: {score})"

    return "NONE", 0, "SCENARIO: UNCERTAIN / NO MATCH"

def find_best_signal_scenarios():
    now_time = time.time()
    best_sym = None
    best_dir = "NONE"
    best_status = "NO_SIGNAL"
    highest_score = -999

    # เคลียร์คูลดาวน์เก่า (3 นาที)
    expired = [s for s, t in symbol_cooldown.items() if now_time - t > 180]
    for s in expired:
        del symbol_cooldown[s]

    for sym in SYMBOLS.keys():
        if sym in symbol_cooldown:
            continue

        direction, score, status = analyze_future_scenarios(sym)
        if direction != "NONE" and score > highest_score:
            highest_score = score
            best_sym = sym
            best_dir = direction
            best_status = status

    if not best_sym and SYMBOLS:
        best_sym = list(SYMBOLS.keys())[0]
        best_dir, highest_score, best_status = analyze_future_scenarios(best_sym)

    if best_sym:
        symbol_cooldown[best_sym] = now_time
        return best_sym, SYMBOLS.get(best_sym, best_sym), best_dir, best_status

    return None, None, "NONE", "NO_SIGNAL"

def send_signal(chat_id):
    try:
        sym, label, direction, status = find_best_signal_scenarios()
        if not sym or direction == "NONE":
            return

        step = user_martingale_step.get(chat_id, 1)
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "⬆️ BUY 🟢 (Trend-Following)" if is_buy else "⬇️ SELL 🔴 (Trend-Following)"
        btn_label = "CALL" if is_buy else "PUT"

        card_text = (
            f"👑 **TITAN SCENARIO MASTER 👑 M1**\n"
            f"⚡ **[ไม้ {step}]**\n\n"
            f"💎 **คู่ที่ดีที่สุดตามเทรนด์:** `{label}`\n"
            f"📈 **Timeframe:** `M1 + M5 Trend Filter`\n"
            f"⌚ **เข้าออเดอร์เวลา:** `{target_time_str}`\n"
            f"🚀 **ทิศทาง:** **{dir_emoji}**\n\n"
            f"🛡️ **การสแกนจำลอง:** `{status}`\n"
            f"⏱️ **Cooldown:** `เปิดใช้งาน (พักคู่เดิม 3 นาที)`"
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

def auto_broadcaster():
    last_sent_minute = -1
    while True:
        try:
            now = get_thai_time()
            if now.second == 30 and now.minute != last_sent_minute:
                last_sent_minute = now.minute
                for cid in list(active_chat_ids):
                    send_signal(cid)
            time.sleep(0.5)
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(2)

@bot.message_handler(commands=['start', 'scan'])
def handle_start_scan(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    if chat_id not in user_martingale_step:
        user_martingale_step[chat_id] = 1
    bot.reply_to(message, "⚡ **TITAN SCENARIO ENGINE ONLINE**\nเปิดระบบสแกนจำลองทิศทางอนาคตตามเทรนด์หลักเรียบร้อย!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Signal Locked")
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

threading.Thread(target=auto_broadcaster, daemon=True).start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
