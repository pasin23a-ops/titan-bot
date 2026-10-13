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

resting_symbols = {}

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

best_autopilot_cache = {
    "symbol": "",
    "label": "",
    "direction": "NONE",
    "status": "SNIPER_SHIELD_ACTIVE",
    "score": 0,
    "is_risky": False
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def fetch_kline(symbol, interval="1m", limit=30):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=2.5)
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

    try:
        url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=2.5)
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

def analyze_autopilot(symbol):
    df = fetch_kline(symbol, "1m", 30)
    if df is None or len(df) < 20:
        return "NONE", 0, "DATA_ERROR", False

    df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()

    c = float(df['close'].iloc[-2])
    o = float(df['open'].iloc[-2])
    h = float(df['high'].iloc[-2])
    l = float(df['low'].iloc[-2])
    ema10 = float(df['ema_10'].iloc[-2])
    ema20 = float(df['ema_20'].iloc[-2])

    distance_score = int((abs(c - ema20) / (ema20 + 1e-9)) * 100000)

    # ตัดคะแนนกระชากเกิน 180 PTS ทิ้ง ป้องกันลากไส้แตก
    if distance_score > 180:
        return "NONE", distance_score, "EXHAUSTION_TRAP", False

    # [SNIPER SHIELD] กรองแท่งเทียนจิ๋ว (Sideway / Doji / ไร้แรงส่ง) ห้ามหลุดรอดมาเด็ดขาด
    body_size = abs(c - o)
    total_range = h - l
    if total_range > 0 and (body_size / total_range) < 0.35:
        return "NONE", distance_score, "WEAK_BODY_FILTERED", False

    recent_high = df['high'].iloc[-20:-2].max()
    recent_low = df['low'].iloc[-20:-2].min()
    
    is_risky = False
    status_msg = "SIDEWAY"
    direction = "NONE"

    # [STRICT COLOR MATCH] PUT: ต้องแดงเท่านั้น + อยู่ใต้ EMA 10/20
    if c < o and c < ema10 and c < ema20:
        direction = "PUT"
        status_msg = "STRICT DOWNTREND (RED)"
        if abs(c - recent_low) / (c + 1e-9) < 0.0008:
            is_risky = True

    # [STRICT COLOR MATCH] CALL: ต้องเขียวเท่านั้น + อยู่เหนือ EMA 10/20
    elif c > o and c > ema10 and c > ema20:
        direction = "CALL"
        status_msg = "STRICT UPTREND (GREEN)"
        if abs(recent_high - c) / (c + 1e-9) < 0.0008:
            is_risky = True

    return direction, distance_score, status_msg, is_risky

def background_scanner():
    global best_autopilot_cache
    while True:
        try:
            for cid in list(resting_symbols.keys()):
                for sym in list(resting_symbols[cid]):
                    _, _, _, is_risky = analyze_autopilot(sym)
                    if not is_risky:
                        resting_symbols[cid].remove(sym)

            candidates = []
            for sym in SYMBOLS.keys():
                direction, score, status, is_risky = analyze_autopilot(sym)
                if direction != "NONE":
                    candidates.append({
                        "symbol": sym,
                        "direction": direction,
                        "score": score,
                        "status": status,
                        "is_risky": is_risky
                    })

            active_resting = set()
            for r_set in resting_symbols.values():
                active_resting.update(r_set)

            available_candidates = [c for c in candidates if c["symbol"] not in active_resting]

            safe_candidates = [c for c in available_candidates if not c["is_risky"]]
            target_list = safe_candidates if safe_candidates else available_candidates

            if target_list:
                target_list.sort(key=lambda x: x['score'], reverse=True)
                top = target_list[0]
                best_autopilot_cache = {
                    "symbol": top["symbol"],
                    "label": SYMBOLS.get(top["symbol"], top["symbol"]),
                    "direction": top["direction"],
                    "status": top["status"],
                    "score": top["score"],
                    "is_risky": top["is_risky"]
                }
            else:
                best_autopilot_cache = {
                    "symbol": "",
                    "label": "",
                    "direction": "NONE",
                    "status": "SCANNING_MARKET",
                    "score": 0,
                    "is_risky": False
                }
            
            time.sleep(1)
        except Exception as e:
            print(f"Scanner Error: {e}")
            time.sleep(2)

def send_auto_signal(chat_id):
    global last_global_signal_time
    try:
        now_time = time.time()
        
        # [COOLDOWN] ล็อค 60 วินาทีไม่ให้ยิงเบิ้ลในนาทีเดิม
        if now_time - last_global_signal_time < 60:
            return

        direction = best_autopilot_cache["direction"]
        score = best_autopilot_cache["score"]
        is_risky = best_autopilot_cache["is_risky"]

        if direction == "NONE":
            return

        sym = best_autopilot_cache["symbol"]
        label = best_autopilot_cache["label"]
        status = best_autopilot_cache["status"]

        if chat_id in resting_symbols and sym in resting_symbols[chat_id]:
            return

        last_global_signal_time = now_time

        step = user_martingale_step.get(chat_id, 1)
        now = get_thai_time()
        target_time = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
        target_time_str = target_time.strftime('%H:%M')

        is_buy = (direction == "CALL")
        dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"
        btn_label = "CALL" if is_buy else "PUT"

        risk_warning_text = (
            "⚠️ **แจ้งเตือน: คู่นี้มีความเสี่ยงสูง (จ่อแนวรับ/แนวต้านสำคัญ)!**\n"
            "👉 *หลังจากชนะไม้นี้แล้ว ให้หยุดพักคู่นี้ชั่วคราวเพื่อรอคำนวณใหม่*\n"
        ) if is_risky else ""

        card_text = (
            f"⚡ **TITAN AUTO-PILOT (Sniper Shield)** ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{risk_warning_text}"
            f"🥊 **การเดินเงิน:** `ไม้ที่ {step}`\n"
            f"🎯 **คู่ตามเทรนด์:** `{label}`\n"
            f"⏱️ **เข้าออเดอร์แท่งถัดไป:** `{target_time_str}` (M1)\n\n"
            f"🔥 **ทิศทางคำสั่ง:** **{dir_emoji}**\n\n"
            f"📊 **สถานะเทรนด์:** `{status}`\n"
            f"🛡️ **Score Strength:** `{score} PTS`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ *Cooldown: บังคับพักระบบ 60 วินาทีเรียบร้อย*"
        )

        risk_flag = "risky" if is_risky else "safe"

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton(f"⚡ SNIPER SIGNAL ({btn_label}) ⚡", callback_data="do_nothing"))
        markup.add(
            InlineKeyboardButton("💎 ชนะไม้ 1", callback_data=f"res_win1_{sym}_{risk_flag}"),
            InlineKeyboardButton("🥈 ชนะไม้ 2", callback_data=f"res_win2_{sym}_{risk_flag}"),
            InlineKeyboardButton("🥉 ชนะไม้ 3", callback_data=f"res_win3_{sym}_{risk_flag}"),
            InlineKeyboardButton("❌ แพ้ (LOSS)", callback_data=f"res_loss_{sym}_{risk_flag}")
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
                    send_auto_signal(cid)
            time.sleep(0.3)
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(1)

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    active_chat_ids.add(chat_id)
    user_martingale_step[chat_id] = 1
    if chat_id in resting_symbols:
        resting_symbols[chat_id].clear()
    
    bot.reply_to(
        message, 
        "🚀 **TITAN AUTO-PILOT SNIPER ACTIVATED** 🚀\n"
        "ปลดเกณฑ์ขั้นต่ำออกแล้ว! พร้อมระบบกรองบอดี้แท่งเทียนจิ๋วและบล็อกไส้สะบัดหลอกตา ลุยกันยาวๆ ครับนาย!", 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "do_nothing":
        bot.answer_callback_query(call.id, "⚡ Sniper Shield Active")
        return
    
    if call.data.startswith("res_"):
        parts = call.data.split("_")
        res_type = parts[1]
        sym = parts[2] if len(parts) >= 4 else ""
        risk_flag = parts[-1] if len(parts) >= 5 else "safe"

        if res_type in ["win1", "win2", "win3"]:
            user_martingale_step[chat_id] = 1
            
            if risk_flag == "risky":
                if chat_id not in resting_symbols:
                    resting_symbols[chat_id] = set()
                resting_symbols[chat_id].add(sym)
                
                bot.answer_callback_query(call.id, "💎 WIN! สั่งพักคู่นี้ชั่วคราวตามเกณฑ์ความเสี่ยง")
                bot.send_message(
                    chat_id, 
                    f"⏸️ **RESTING PAIR:** ชนะในคู่ที่มีความเสี่ยงสูง (`{SYMBOLS.get(sym, sym)}`) เรียบร้อย!\n"
                    f"บอทพักคู่นี้ชั่วคราวและกำลังเฝ้าระวังเบื้องหลัง ทันทีที่กราฟหายเสี่ยง บอทจะดึงกลับมาคำนวณส่งสัญญาณต่อให้อัตโนมัติครับ!"
                )
            else:
                bot.answer_callback_query(call.id, "💎 WIN! Reset สู่ไม้ 1")
                
        elif res_type == "loss":
            step = user_martingale_step.get(chat_id, 1)
            user_martingale_step[chat_id] = 1 if step >= 3 else step + 1
            bot.answer_callback_query(call.id, f"⚠️ LOSS! ขยับเป็นไม้ {user_martingale_step[chat_id]}")

threading.Thread(target=background_scanner, daemon=True).start()
threading.Thread(target=auto_broadcaster, daemon=True).start()

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        time.sleep(3)
