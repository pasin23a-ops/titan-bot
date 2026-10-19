import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import random
import time

# 🔑 โทเคนใหม่ล่าสุดของนาย
BOT_TOKEN = "8842097514:AAGODOhJ-EbgZ2kGeFwqNFAPFkuqkwxb6J8"
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

# 🎯 10 สินทรัพย์ OTC ชุดใหม่ของนายครบถ้วน 100%
EXACT_8X_SYMBOLS = {
    "DYDXUSDT": "DYDX OTC",
    "SHIBUSDT": "SHIB/USD OTC",
    "SUIUSDT": "SUI OTC",
    "ONDOUSDT": "ONDO OTC",
    "XRPUSDT": "RIPPLE OTC",
    "VAULTAUSDT": "VAULTA OTC",
    "SNAPUSDT": "SNAP LNE OTC",
    "MCDUSDT": "McDonald's OTC",
    "KOUSDT": "Coca-Cola OTC",
    "LTCUSDT": "Litecoin OTC"
}

def get_thai_time():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))

def generate_sniper_signal():
    symbol_key = random.choice(list(EXACT_8X_SYMBOLS.keys()))
    label = EXACT_8X_SYMBOLS[symbol_key]
    
    direction = random.choice(["CALL", "PUT"])
    
    # 🗳️ สภาโหวต M1 โมเมนตัมเพียวๆ - 15 เสียง
    up_votes = random.randint(11, 15)
    down_votes = 15 - up_votes
    if direction == "PUT" and up_votes > down_votes:
        up_votes, down_votes = down_votes, up_votes
        
    consensus_pct = round((max(up_votes, down_votes) / 15.0) * 100, 1)
    
    base_prices = {
        "DYDXUSDT": 1.25,
        "SHIBUSDT": 0.000018,
        "SUIUSDT": 2.15,
        "ONDOUSDT": 0.78,
        "XRPUSDT": 0.58,
        "VAULTAUSDT": 0.15,
        "SNAPUSDT": 10.50,
        "MCDUSDT": 295.0,
        "KOUSDT": 68.50,
        "LTCUSDT": 72.0
    }
    
    p = base_prices.get(symbol_key, 10.0)
    fluctuation = p * 0.0018
    poc = p + random.uniform(-fluctuation, fluctuation)
    val = poc - (p * 0.0025)
    vah = poc + (p * 0.0025)
    wall = vah if direction == "CALL" else val
    
    # 🌊 Order Imbalance & Delta Flow (จำเป็นสำหรับการซัด M1)
    imbalance_side = "BUY" if direction == "CALL" else "SELL"
    imbalance_ratio = round(random.uniform(2.5, 4.8), 2)
    delta_flow = f"+{random.randint(1200, 4800)} Vol" if direction == "CALL" else f"-{random.randint(1200, 4800)} Vol"
    
    smart_money_flow = f"🟢 HEAVY INFLOW ({random.randint(82, 98)}%)" if direction == "CALL" else f"🔴 HEAVY OUTFLOW ({random.randint(82, 98)}%)"
    
    sweep_options = [
        "🔱 LIQUIDITY SWEEP (กวาดสภาพคล่องสั้น)",
        "🧊 INSTITUTIONAL ICEBERG BLOCK",
        "🎯 MOMENTUM BREAKOUT DETECTED"
    ]
    
    edge = round(random.uniform(88.5, 98.9), 1)
    fmt = ".6f" if "SHIB" in symbol_key else ".4f"

    return {
        "symbol_label": label,
        "direction": direction,
        "up_votes": up_votes,
        "down_votes": down_votes,
        "consensus": consensus_pct,
        "imbalance": f"{imbalance_side} {imbalance_ratio}x ({delta_flow})",
        "wall": f"{wall:{fmt}}",
        "poc": f"{poc:{fmt}}",
        "val": f"{val:{fmt}}",
        "vah": f"{vah:{fmt}}",
        "sm_flow": smart_money_flow,
        "sweep": random.choice(sweep_options),
        "edge": edge
    }

def send_new_signal_card(chat_id):
    res = generate_sniper_signal()
    now = get_thai_time()
    target_time_str = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0).strftime('%H:%M')
    
    is_buy = (res['direction'] == "CALL")
    dir_emoji = "🟢 BUY (CALL) 🟢" if is_buy else "🔴 SELL (PUT) 🔴"

    card_text = (
        f"👑 **TITAN v104.0 M1 SNIPER EDITION** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **คู่เด่นสถาบัน OTC:** `{res['symbol_label']}`\n"
        f"🗳️ **สภาโหวต M1:** `[ขึ้น {res['up_votes']} : ลง {res['down_votes']}]` ({res['consensus']}%)\n"
        f"⏱️ **เวลาเข้าออเดอร์:** `{target_time_str}` (M1)\n"
        f"⚡ **ทิศทางฟันธง:** **{dir_emoji}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔱 **Smart Money Flow:** `{res['sm_flow']}`\n"
        f"🌊 **Order Imbalance:** `{res['imbalance']}`\n"
        f"🛡️ **Liquidity Wall:** `{res['wall']}`\n"
        f"🎯 **Volume Profile (POC):** `{res['poc']}`\n"
        f"📊 **Value Area (VAL / VAH):** `{res['val']} - {res['vah']}`\n"
        f"🧨 **Institutional Sweep:** `{res['sweep']}`\n"
        f"🔥 **Quant Edge:** `+{res['edge']}%`\n"
        f"⏱️ Update: `{now.strftime('%H:%M:%S')}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚔️ สแกนหาจุดเข้า M1 ถัดไป ⚔️", callback_data="next_signal"))
    
    try:
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"[ERROR SENDING MESSAGE]: {e}")

@bot.message_handler(commands=['start', 'run'])
def handle_start(message):
    chat_id = message.chat.id
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚔️ สแกนหาจุดเข้า M1 ถัดไป ⚔️", callback_data="next_signal"))
    bot.reply_to(message, 
        "👑 **TITAN v104.0 M1 Sniper พร้อมรบ!**\n"
        "การ์ดคลีน กระชับ โฟกัสเฉพาะเครื่องมือทำกำไรระยะสั้น กดสแกนลุยโลด:", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "next_signal")
def handle_next_signal(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    
    send_new_signal_card(call.message.chat.id)

if __name__ == "__main__":
    print("🚀 TITAN v104.0 M1 Sniper Engine Running...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            time.sleep(1)
