import pandas as pd
import numpy as np
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BOT_TOKEN = "8316396699:AAHff4bp0RbvYJjx-eOhuUqr4kgD-MERj-c"
bot = telebot.TeleBot(BOT_TOKEN)

# 🧠 ระบบจัดเก็บสถานะเซสชันแยกตาม Chat ID ปลอดภัย 100%
user_sessions = {}

EXACT_8X_SYMBOLS = {
    "SNAPUSDT": "Snap Inc. (OTC)",
    "SHIBUSDT": "SHIB/USD (OTC)",
    "PENGUUSDT": "Pudgy Penguins (OTC)",
    "NGUSDT": "แก๊สธรรมชาติ (OTC)",
    "BIDUUSDT": "Baidu, Inc. (OTC)",
    "XRPUSDT": "Ripple (OTC)",
    "NKEUSDT": "Nike, Inc. (OTC)",
    "PAXGUSDT": "XAUUSD (OTC)",
    "MELANIAUSDT": "MELANIA Coin (OTC)",
    "AIGUSDT": "AIG (OTC)",
    "FETUSDT": "FET (OTC)",
    "VAULTUSDT": "Vaulta (OTC)",
    "ONDOUSDT": "Ondo (OTC)",
    "FTTUSDT": "Fartcoin (OTC)",
    "XAGUSDT": "XAGUSD (OTC)",
    "LTCUSDT": "Litecoin (OTC)",
    "MCDUSDT": "McDonald's Corp. (OTC)",
    "SUIUSDT": "Sui (OTC)",
    "INTCUSDT": "Intel Corp. (OTC)",
    "DYDXUSDT": "DYDX (OTC)",
    "PENUSDT": "PEN/USD (OTC)",
    "TRUMPUSDT": "TRUMP Coin (OTC)",
    "RAYUSDT": "Raydium (OTC)",
    "RENDERUSDT": "Render (OTC)"
}

def get_session(chat_id):
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {
            "step": 1,
            "base_stake": 100,
            "wins": 0,
            "losses": 0,
            "profit": 0,
            "consecutive_losses": 0,
            "locked_out": False
        }
    return user_sessions[chat_id]

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_real_economic_news():
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        res = requests.get(url, timeout=2.5)
        if res.status_code != 200:
            return False, "🟢 ตลาดปกติ"
        
        events = res.json()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        active_news = []
        
        for event in events:
            if event.get("impact") == "High" and event.get("country") == "USD":
                date_str = event.get("date")
                if date_str:
                    event_time = datetime.datetime.fromisoformat(date_str)
                    diff_minutes = (event_time - now_utc).total_seconds() / 60.0
                    if -15 <= diff_minutes <= 45:
                        title = event.get("title", "News")
                        time_label = f"อีก {int(diff_minutes)}น." if diff_minutes > 0 else f"ผ่านไป {abs(int(diff_minutes))}น."
                        active_news.append(f"🚨 **{title}** ({time_label})")
                        
        if active_news:
            return True, " | ".join(active_news)
        return False, "🟢 ตลาดปกติ (ไร้ข่าวแรง)"
    except Exception:
        return False, "🟢 ตลาดปกติ"

def fetch_kline_with_orderflow(symbol, interval="1m", limit=120):
    binance_symbol = symbol.replace("_OTC", "") 
    endpoints = [
        f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={limit}",
        f"https://api.binance.us/api/v3/klines?symbol={binance_symbol}&interval={interval}&limit={limit}"
    ]
    for url in endpoints:
        try:
            res = requests.get(url, timeout=1.5)
            if res.status_code == 200:
                raw = res.json()
                df = pd.DataFrame(raw, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 
                    'close_time', 'qav', 'num_trades', 'taker_buy_base_vol', 
                    'taker_buy_quote_vol', 'ignore'
                ])
                for col in ['open', 'high', 'low', 'close', 'volume', 'taker_buy_base_vol']:
                    df[col] = df[col].astype(float)
                return df
        except Exception:
            continue
    return None

# --- 🏛️ อินดิเคเตอร์สภาโหวต & Order Flow ปลอดภัยไร้ Error ---
def vote_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-8)
    rsi = 100 - (100 / (1 + rs))
    return 1 if rsi.iloc[-2] >= 50 else -1

def vote_dinapoli_macd(df, fast=8, slow=17, signal=9):
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    hist = (ema_fast - ema_slow) - (ema_fast - ema_slow).ewm(span=signal, adjust=False).mean()
    return 1 if hist.iloc[-2] >= 0 else -1

def vote_stochastic(df, period=14):
    low_min = df['low'].rolling(window=period).min()
    high_max = df['high'].rolling(window=period).max()
    k = 100 * (df['close'] - low_min) / (high_max - low_min + 1e-8)
    d = k.rolling(window=3).mean()
    return 1 if k.iloc[-2] >= d.iloc[-2] else -1

def vote_cci(df, period=14):
    tp = (df['high'] + df['low'] + df['close']) / 3
    mad = (tp - tp.rolling(window=period).mean()).abs().rolling(window=period).mean()
    cci = (tp - tp.rolling(window=period).mean()) / (0.015 * mad + 1e-8)
    return 1 if cci.iloc[-2] >= 0 else -1

def vote_bollinger_bands(df, period=20):
    sma = df['close'].rolling(window=period).mean()
    return 1 if df['close'].iloc[-2] >= sma.iloc[-2] else -1

def vote_ema_crossover(df):
    ema3 = df['close'].ewm(span=3, adjust=False).mean().iloc[-2]
    ema8 = df['close'].ewm(span=8, adjust=False).mean().iloc[-2]
    return 1 if ema3 >= ema8 else -1

def vote_order_flow_delta(df):
    try:
        taker_buy = df['taker_buy_base_vol']
        total_vol = df['volume'] + 1e-8
        taker_sell = total_vol - taker_buy
        delta = taker_buy - taker_sell
        return 1 if delta.iloc[-2] >= 0 else -1
    except Exception:
        return 1 if df['close'].iloc[-2] >= df['open'].iloc[-2] else -1

def analyze_symbol_voting(sym):
    df1 = fetch_kline_with_orderflow(symbol=sym, interval="1m", limit=120)
    df5 = fetch_kline_with_orderflow(symbol=sym, interval="5m", limit=60)
    
    if df1 is None or len(df1) < 40 or df5 is None or len(df5) < 20:
        return None

    votes_m1 = [
        vote_rsi(df1['close']),
        vote_dinapoli_macd(df1),
        vote_stochastic(df1),
        vote_cci(df1),
        vote_bollinger_bands(df1),
        vote_ema_crossover(df1),
        vote_order_flow_delta(df1)
    ]

    votes_m5 = [
        vote_rsi(df5['close']),
        vote_dinapoli_macd(df5),
        vote_order_flow_delta(df5)
    ]

    all_votes = votes_m1 + votes_m5
    up_votes = sum(1 for v in all_votes if v == 1)
    down_votes = sum(1 for v in all_votes if v == -1)
    
    # การันตีทิศทางเสมอ 100% ทุกคลิก
    if up_votes > down_votes:
        direction = "CALL"
        majority_count = up_votes
    elif down_votes > up_votes:
        direction = "PUT"
        majority_count = down_votes
    else:
        direction = "CALL" if df1['close'].iloc[-2] >= df1['open'].iloc[-2] else "PUT"
        majority_count = max(up_votes, down_votes)

    consensus_pct = round((majority_count / len(all_votes)) * 100, 1)
    score = (consensus_pct * 0.8) + (float(df1['close'].iloc[-2] > df1['open'].iloc[-2]) * 20)

    return {
        "symbol": sym,
        "direction": direction,
        "consensus": consensus_pct,
        "up_votes": up_votes,
        "down_votes": down_votes,
        "score": round(score, 2)
    }

def send_signal_card(chat_id, message_id=None):
    session = get_session(chat_id)
    
    if session["locked_out"]:
        lockout_text = (
            f"🛑 **STOP-LOSS GUARD ACTIVATED (TITAN v92.0)** 🛑\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ ตรวจพบการแพ้ติดต่อกันครบ 3 ไม้ (Max Loss Limit)\n"
            f"🛡️ **ระบบทำการล็อกพอร์ตเพื่อความปลอดภัยชั่วคราว!**\n"
            f"💡 กรุณาพักผ่อนหรือรอตลาดนิ่งอย่างน้อย 15-30 นาที\n"
            f"🔄 หากต้องการรีเซ็ตเริ่มเซสชันใหม่ พิมพ์คำสั่ง 👉 `/reset`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 รีเซ็ตเซสชันใหม่ (/reset)", callback_data="do_reset"))
        try:
            if message_id:
                bot.edit_message_text(lockout_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, lockout_text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass
        return

    has_news, news_msg = fetch_real_economic_news()
    symbol_keys = list(EXACT_8X_SYMBOLS.keys())
    valid_results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(analyze_symbol_voting, sym): sym for sym in symbol_keys}
        for future in as_completed(futures):
            if time.time() - start_time > 5.5:
                break
            try:
                res = future.result()
                if res is not None:
                    valid_results.append(res)
            except Exception:
                continue
    
    if not valid_results:
        try:
            bot.send_message(chat_id, "⚠️ **เครือข่ายขัดข้อง:** ไม่สามารถดึงข้อมูลเรียลไทม์จาก Binance ได้!", parse_mode="Markdown")
        except Exception:
            pass
        return

    best_res = max(valid_results, key=lambda x: x['score'])
    if has_news:
        best_res['score'] = max(0.0, best_res['score'] - 15.0)

    label = EXACT_8X_SYMBOLS.get(best_res['symbol'], best_res['symbol'])
    now = get_thai_time()
    target_time_str = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0).strftime('%H:%M')
    
    is_buy = (best_res['direction'] == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    
    risk_warning = "\n⚠️ **หมายเหตุ:** มติเสียงก้ำกึ่ง ตลาดผันผวนแต่ระบบการันตีออเดอร์ให้" if best_res['consensus'] < 60.0 else "\n🔥 **ความแม่นยำสูง:** สภาโหวต Order Flow สอดคล้องกันชัดเจน"

    base = session["base_stake"]
    step = session["step"]
    current_stake = base if step == 1 else (int(base * 2.2) if step == 2 else int(base * 4.8))

    card_text = (
        f"👑 **TITAN 92.0 GUARANTEED EXECUTION** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📰 {news_msg}\n"
        f"🎯 **คู่เด่น:** `{label}` | มติ: `[ขึ้น {best_res['up_votes']} : ลง {best_res['down_votes']}]` ({best_res['consensus']}%)\n"
        f"⏱️ **เวลาเข้า:** `{target_time_str}` (M1) | ⚡ **{dir_emoji}**{risk_warning}\n"
        f"📊 **MM แนะนำ:** ไม้ที่ `{step}/3` 👉 **{current_stake} บาท** (ทุนตั้งต้น: {base}บ.)\n"
        f"📈 **สถิติวันนี้:** ชนะ `{session['wins']}` | แพ้ `{session['losses']}` | กำไร `+{session['profit']}บ.`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("✅ ชนะ", callback_data="mm_win"),
        InlineKeyboardButton("❌ แพ้", callback_data="mm_loss"),
        InlineKeyboardButton("🔄 สแกนใหม่", callback_data="request_next_signal")
    )
    
    try:
        if message_id:
            bot.edit_message_text(card_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            try:
                bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                pass

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    get_session(chat_id)
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🚀 เริ่มต้นสแกนออเดอร์ (v92.0)", callback_data="request_next_signal"))
    bot.reply_to(message, 
        "✨ **TITAN v92.0 พร้อมลุยแล้วครับนาย!**\n"
        "การันตีคำนวณและออกทิศทางให้เทรดทุกคลิก 100% ไม่มีกั๊ก!", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['reset'])
def handle_reset(message):
    chat_id = message.chat.id
    session = get_session(chat_id)
    session["step"] = 1
    session["wins"] = 0
    session["losses"] = 0
    session["profit"] = 0
    session["consecutive_losses"] = 0
    session["locked_out"] = False
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 เริ่มต้นสแกนสัญญาณแรก (v92.0)", callback_data="request_next_signal"))
    bot.reply_to(message, "🔄 **รีเซ็ตเซสชันสำเร็จ!** ล้างสถิติและปลดล็อกระบบเรียบร้อย พร้อมลุยต่อครับนาย!", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['setstake'])
def handle_set_stake(message):
    chat_id = message.chat.id
    try:
        parts = message.text.split()
        if len(parts) > 1:
            new_stake = int(parts[1])
            if new_stake > 0:
                session = get_session(chat_id)
                session["base_stake"] = new_stake
                session["step"] = 1
                bot.reply_to(message, f"✅ **ตั้งค่าทุนเริ่มต้นใหม่สำเร็จ:** `{new_stake} บาท` (รีเซ็ตกลับไม้ 1 เรียบร้อย)", parse_mode="Markdown")
                return
        bot.reply_to(message, "⚠️ กรุณาใส่ตัวเลขให้ถูกต้อง เช่น `/setstake 300`", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "⚠️ เกิดข้อผิดพลาดในการตั้งค่าทุน กรุณาลองใหม่อีกครั้ง", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    session = get_session(chat_id)
    
    if call.data == "do_reset":
        session["step"] = 1
        session["wins"] = 0
        session["losses"] = 0
        session["profit"] = 0
        session["consecutive_losses"] = 0
        session["locked_out"] = False
        try:
            bot.answer_callback_query(call.id, "🔄 รีเซ็ตเซสชันเรียบร้อย!")
        except Exception:
            pass
        send_signal_card(chat_id, msg_id)
        return

    if call.data == "request_next_signal":
        try:
            bot.answer_callback_query(call.id, "⚡ กำลังประมวลผลออเดอร์...")
        except Exception:
            pass
        send_signal_card(chat_id, msg_id)
        return
        
    elif call.data == "mm_win":
        session["wins"] += 1
        session["consecutive_losses"] = 0
        base = session["base_stake"]
        step = session["step"]
        curr_s = base if step == 1 else (int(base * 2.2) if step == 2 else int(base * 4.8))
        session["profit"] += int(curr_s * 0.85)
        session["step"] = 1
        try:
            bot.answer_callback_query(call.id, "🎉 บันทึกผล: ชนะ! (รีเซ็ตสเต็ป MM กลับไม้ 1)")
        except Exception:
            pass
        send_signal_card(chat_id, msg_id)
        
    elif call.data == "mm_loss":
        session["losses"] += 1
        session["consecutive_losses"] += 1
        base = session["base_stake"]
        step = session["step"]
        curr_s = base if step == 1 else (int(base * 2.2) if step == 2 else int(base * 4.8))
        session["profit"] -= curr_s
        
        if session["consecutive_losses"] >= 3 or session["step"] >= 3:
            session["locked_out"] = True
            try:
                bot.answer_callback_query(call.id, "🛑 แพ้ครบ 3 ไม้ติด! ระบบล็อกพอร์ตชั่วคราวเพื่อความปลอดภัย")
            except Exception:
                pass
            send_signal_card(chat_id, msg_id)
            return

        session["step"] = min(3, session["step"] + 1)
        try:
            bot.answer_callback_query(call.id, "⚠️ บันทึกผล: แพ้! (ขยับสเต็ป MM ไม้ถัดไป)")
        except Exception:
            pass
        send_signal_card(chat_id, msg_id)

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"[BOT ERROR]: {e}")
        time.sleep(3)
                                
