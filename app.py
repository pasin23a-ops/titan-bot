import pandas as pd
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from flask import Flask, request

# 🔑 ตั้งค่า Bot Token และ Telegram Chat ID
BOT_TOKEN = "8919259236:AAGOUrAxGr_FnjqEANxERHAdFvcnBeP5YCk"
CHAT_ID = "8644030650"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

last_sent_symbol = {}

EXACT_8X_SYMBOLS = {
    "BTCUSDT": "BTC/USD (Proxy/Binance)",
    "ETHUSDT": "ETH/USD (Proxy/Binance)",
    "SOLUSDT": "SOL/USD (Proxy/Binance)",
    "XRPUSDT": "Ripple (Proxy/Binance)",
    "LTCUSDT": "Litecoin (Proxy/Binance)",
    "SHIBUSDT": "SHIB/USD (Proxy/Binance)",
    "SUIUSDT": "Sui (Proxy/Binance)",
    "XAUUSDT": "XAUUSD (Proxy/Binance)",
    "XAGUSDT": "XAGUSD (Proxy/Binance)",
    "GASUSDT": "แก๊สธรรมชาติ (Proxy/Binance)",
    "EURUSD_OTC": "EUR/USD (Proxy/Binance)",
    "NKEUSDT": "Nike, Inc. (Proxy/Binance)",
    "SNAPUSDT": "Snap Inc. (Proxy/Binance)",
    "MCDUSDT": "McDonald's Corp... (Proxy/Binance)",
    "INTCUSDT": "Intel Corporation... (Proxy/Binance)"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval="1m", limit=60):
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
                if len(raw) < 30:
                    continue
                df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                return df
        except Exception:
            continue
    return None

def calculate_sar(df, af_start=0.12, af_max=0.2):
    highs = df['high'].values
    lows = df['low'].values
    length = len(df)
    sar = list(highs)
    is_uptrend = True
    ep = lows[0]
    af = af_start

    for i in range(1, length):
        prev_sar = sar[i-1]
        if is_uptrend:
            cur_sar = prev_sar + af * (ep - prev_sar)
            cur_sar = min(cur_sar, lows[i-1], lows[i-2] if i > 1 else lows[i-1])
            if lows[i] < cur_sar:
                is_uptrend = False
                cur_sar = ep
                ep = lows[i]
                af = af_start
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_start, af_max)
        else:
            cur_sar = prev_sar + af * (ep - prev_sar)
            cur_sar = max(cur_sar, highs[i-1], highs[i-2] if i > 1 else highs[i-1])
            if highs[i] > cur_sar:
                is_uptrend = True
                cur_sar = ep
                ep = highs[i]
                af = af_start
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_start, af_max)
        sar[i] = cur_sar
    return sar

def analyze_symbol_master(sym):
    df1 = fetch_kline(symbol=sym, interval="1m", limit=60)
    if df1 is None or len(df1) < 40:
        return None

    df5 = fetch_kline(symbol=sym, interval="5m", limit=30)
    m5_trend = "NEUTRAL"
    if df5 is not None and len(df5) >= 20:
        m5_ema20 = df5['close'].ewm(span=20, adjust=False).mean()
        m5_trend = "UP" if df5['close'].iloc[-2] > m5_ema20.iloc[-2] else "DOWN"

    closes = df1['close']
    highs = df1['high']
    lows = df1['low']
    volumes = df1['volume']

    ema4 = closes.ewm(span=4, adjust=False).mean()
    ema9 = closes.ewm(span=9, adjust=False).mean()
    macd_line = ema4 - ema9
    signal_line = macd_line.ewm(span=4, adjust=False).mean()
    macd_hist = macd_line - signal_line

    ema20 = closes.ewm(span=20, adjust=False).mean()
    tr = pd.concat([highs - lows, (highs - closes.shift()).abs(), (lows - closes.shift()).abs()], axis=1).max(axis=1)
    atr20 = tr.rolling(20).mean()
    kc_upper = ema20 + (2 * atr20)
    kc_lower = ema20 - (2 * atr20)

    sar_values = calculate_sar(df1, af_start=0.12, af_max=0.2)
    last_close = closes.iloc[-2]
    last_sar = sar_values[-2]
    sar_trend = "UP" if last_close > last_sar else "DOWN"

    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    ppo_line = ((ema12 - ema26) / ema26) * 100
    current_ppo = float(ppo_line.iloc[-2])

    delta = closes.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = float(rsi.iloc[-2])

    vol_mean = volumes.iloc[-20:-2].mean()
    cur_vol = volumes.iloc[-2]
    news_impact = "NORMAL"
    if cur_vol > (vol_mean * 2.2):
        news_impact = "HIGH VOLATILITY (NEWS)"

    call_votes = 0
    put_votes = 0

    if sar_trend == "UP": call_votes += 2
    else: put_votes += 2

    if macd_hist.iloc[-2] > 0: call_votes += 1.5
    else: put_votes += 1.5

    if last_close > kc_upper.iloc[-2]: call_votes += 1.5
    elif last_close < kc_lower.iloc[-2]: put_votes += 1.5

    if current_ppo > 0: call_votes += 1
    else: put_votes += 1
    if current_rsi < 45: call_votes += 1
    elif current_rsi > 55: put_votes += 1

    if m5_trend == "UP": call_votes += 2
    elif m5_trend == "DOWN": put_votes += 2

    if call_votes >= put_votes:
        direction = "CALL"
        majority_votes = call_votes
    else:
        direction = "PUT"
        majority_votes = put_votes

    total_votes = call_votes + put_votes
    consensus_pct = round((majority_votes / max(total_votes, 1)) * 100, 1)
    base_score = (consensus_pct * 0.8) + (10 if news_impact != "NORMAL" else 0)

    return {
        "symbol": sym,
        "direction": direction,
        "ppo": current_ppo,
        "rsi": round(current_rsi, 2),
        "m5_trend": m5_trend,
        "sar_trend": sar_trend,
        "news_impact": news_impact,
        "call_votes": round(call_votes, 1),
        "put_votes": round(put_votes, 1),
        "consensus": consensus_pct,
        "score": round(base_score, 2)
    }

def generate_fast_signal(chat_id):
    symbol_keys = list(EXACT_8X_SYMBOLS.keys())
    total_symbols = len(symbol_keys)
    valid_results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=total_symbols) as executor:
        futures = {executor.submit(analyze_symbol_master, sym): sym for sym in symbol_keys}
        for future in as_completed(futures):
            if time.time() - start_time > 8.0:
                break
            try:
                res = future.result()
                if res is not None:
                    valid_results.append(res)
            except Exception:
                continue
    
    success_count = len(valid_results)

    if not valid_results:
        try:
            bot.send_message(chat_id, "⚠️ ไม่สามารถดึงราคาจริงได้ กรุณากดขอสัญญาณใหม่อีกครั้งครับ", parse_mode="Markdown")
        except Exception:
            pass
        return

    last_sym = last_sent_symbol.get(chat_id, "")
    filtered_results = [r for r in valid_results if r['symbol'] != last_sym]
    if not filtered_results:
        filtered_results = valid_results

    best_res = max(filtered_results, key=lambda x: x['score'])
    last_sent_symbol[chat_id] = best_res['symbol']
    label = EXACT_8X_SYMBOLS.get(best_res['symbol'], best_res['symbol'])
    
    now = get_thai_time()
    target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    target_time_str = target_time.strftime('%H:%M')
    
    is_buy = (best_res['direction'] == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
    btn_label = "CALL" if is_buy else "PUT"
    
    trend_m5_disp = "📈 ขาขึ้น" if best_res['m5_trend'] == "UP" else ("📉 ขาลง" if best_res['m5_trend'] == "DOWN" else "⚖️ ไซด์เวย์")
    sar_disp = "🟢 ไข่ปลาหนุนขึ้น" if best_res['sar_trend'] == "UP" else "🔴 ไข่ปลากดลง"

    card_text = (
        f"👑 **TITAN v85.0 MASTER QUANT** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **สถานะระบบ:** `ดึงข้อมูลจริง {success_count}/{total_symbols} สำเร็จ`\n"
        f"🎯 **คู่ที่ถูกเลือก:** `{label}`\n"
        f"🗳️ **ประชาธิปไตยโหวต:** `[ขึ้น {best_res['call_votes']} : ลง {best_res['put_votes']}]` ({best_res['consensus']}%)\n"
        f"🌐 **เทรนด์ M5:** `{trend_m5_disp}` | **SAR:** `{sar_disp}`\n"
        f"📊 **PPO / RSI:** `{best_res['ppo']:.2f} / {best_res['rsi']}`\n"
        f"📰 **สภาวะข่าวจริง:** `{best_res['news_impact']}`\n"
        f"⏱️ **เวลาเป้าหมายอ้างอิง:** `{target_time_str}` (M1)\n\n"
        f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
        f"⭐ **Master Score:** `{best_res['score']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💯 *ข้อมูลจริงจาก Binance 100% ไร้ตัวเลขมโน*"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"⚡ SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
    markup.add(InlineKeyboardButton("🔄 ขอสัญญาณสดทันใจ (MASTER V85)", callback_data="request_next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Send Error: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 กดเพื่อสแกนสัญญาณด่วน", callback_data="request_next_signal"))
    bot.reply_text = bot.reply_to(
        message, 
        "🚀 **TITAN v85.0 MASTER QUANT ACTIVATED** 🚀\n"
        "พร้อมรับสัญญาณสแกนด่วน และสแตนด์บายรับ Alert จาก TradingView แล้วครับนาย:", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Active")
        return
    if call.data == "request_next_signal":
        bot.answer_callback_query(call.id, "⚡ กำลังสแกนข้อมูลจริง...")
        generate_fast_signal(chat_id)
        return

@app.route('/', methods=['GET'])
def health_check():
    return "TITAN v85.0 Webhook Server is Live!", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json or request.data.decode('utf-8')
        text_message = f"🚨 **TRADINGVIEW SCREEN ALERT** 🚨\n\n{data}" if isinstance(data, str) else f"🚨 **TRADINGVIEW SCREEN ALERT** 🚨\n\n`{data}`"
        
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
            "chat_id": CHAT_ID,
            "text": text_message,
            "parse_mode": "Markdown"
        })
        return "OK", 200
    except Exception as e:
        return str(e), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
