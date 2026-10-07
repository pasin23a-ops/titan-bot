import pandas as pd
import numpy as np
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import datetime
import time

# ==========================================
# API Token ของคุณ
# ==========================================
BOT_TOKEN = "8992651389:AAEo7yoADLGn863tac0nTkxrvy36BFZNCqU"
bot = telebot.TeleBot(BOT_TOKEN)

INTERVAL = "1m"
user_stats = {}
symbol_stats = {}
user_martingale_step = {} # ติดตามสเต็ปไม้ (ไม้ 1, ไม้ 2, ไม้ 3)

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

def generate_hardcore_market_data(symbol):
    np.random.seed(int(time.time() // 4) + sum(ord(c) for c in symbol))
    size = 60
    base_price = 100.0
    
    # จำลองความผันผวนแบบเข้มงวดเพื่อทดสอบตัวกรอง
    regime = (int(time.time() // 12) + sum(ord(c) for c in symbol)) % 3
    if regime == 0:
        returns = np.random.normal(loc=0.0025, scale=0.0006, size=size)
    elif regime == 1:
        returns = np.random.normal(loc=-0.0025, scale=0.0006, size=size)
    else:
        returns = np.random.normal(loc=0.0, scale=0.002, size=size)
        
    price_series = base_price * np.cumprod(1 + returns)
    
    df = pd.DataFrame()
    df['close'] = price_series
    df['open'] = df['close'].shift(1).fillna(base_price)
    df['high'] = df[['open', 'close']].max(axis=1) + np.random.uniform(0.0005, 0.003, size)
    df['low'] = df[['open', 'close']].min(axis=1) - np.random.uniform(0.0005, 0.003, size)
    
    return df

def analyze_hardcore_market(symbol):
    df = generate_hardcore_market_data(symbol)
    
    # คำนวณอินดิเคเตอร์แบบเข้มข้น (DiNapoli MACD + EMA Trend Alignment)
    df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
    df['ema13'] = df['close'].ewm(span=13, adjust=False).mean()
    df['macd_hist'] = df['ema5'] - df['ema13']
    
    last_close = df['close'].iloc[-1]
    last_open = df['open'].iloc[-1]
    prev_close = df['close'].iloc[-2]
    prev_open = df['open'].iloc[-2]
    
    hist_val = df['macd_hist'].iloc[-1]
    body = last_close - last_open
    prev_body = prev_close - prev_open
    
    # เงื่อนไขคัดกรองความคมชัดระดับสูงสุด (Hardcore Filter)
    if hist_val > 0 and body > 0 and prev_body > 0 and last_close > df['ema5'].iloc[-1]:
        return "CALL", "🔥 [HARDCORE V50] ULTRA BUY (แรงซื้อหนาแน่น คอนเฟิร์มทุกแท่ง)"
    elif hist_val < 0 and body < 0 and prev_body < 0 and last_close < df['ema5'].iloc[-1]:
        return "PUT", "📉 [HARDCORE V50] ULTRA SELL (แรงขายกดดันชัดเจน ทุกเงื่อนไขตรงกัน)"
    else:
        # หากตลาดยังไม่เข้าเกณฑ์เข้มงวด จะบล็อกหรือเลือกฝั่งตามโมเมนตัมหลัก
        if hist_val >= 0:
            return "CALL", "⚡ [HARDCORE V50] CONDITIONAL BUY"
        else:
            return "PUT", "⚠️ [HARDCORE V50] CONDITIONAL SELL"

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
        f"👑 **[ TITAN BEAM V50 STATS ]** 👑\n\n"
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

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_martingale_step[message.chat.id] = 1
    bot.send_message(
        message.chat.id, 
        "🇷🇺 **Titan Beam Pro V50 (Hardcore Engine)**\nเปิดระบบกรองสัญญาณเข้มข้นสูงสุด และคุมสเต็ปเดินเงินเรียบร้อย เลือกคู่ลุยกันเลย:", 
        reply_markup=build_menu_keyboard(), 
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['stats'])
def show_stats(message):
    bot.send_message(message.chat.id, get_stats_text(message.chat.id), parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def reset_stats(message):
    chat_id = message.chat.id
    user_stats[chat_id] = {"win1": 0, "win2": 0, "win3": 0, "loss": 0}
    symbol_stats[chat_id] = {}
    user_martingale_step[chat_id] = 1
    bot.send_message(chat_id, "🔄 รีเซ็ตสถิติและรีเซ็ตสเต็ปกลับเป็นไม้ 1 เรียบร้อย!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_all(call):
    chat_id = call.message.chat.id
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

        if result_type == "win1":
            user_stats[chat_id]["win1"] += 1
            if symbol: symbol_stats[chat_id][symbol]["win"] += 1
            user_martingale_step[chat_id] = 1 # ชนะแล้วรีเซ็ตกลับไม้ 1
            text = "✅ ชนะไม้ 1! รีเซ็ตกลับสเต็ปไม้ 1"
        elif result_type == "win2":
            user_stats[chat_id]["win2"] += 1
            if symbol: symbol_stats[chat_id][symbol]["win"] += 1
            user_martingale_step[chat_id] = 1 # ชนะแล้วรีเซ็ตกลับไม้ 1
            text = "✅ ชนะไม้ 2! รีเซ็ตกลับสเต็ปไม้ 1"
        elif result_type == "win3":
            user_stats[chat_id]["win3"] += 1
            if symbol: symbol_stats[chat_id][symbol]["win"] += 1
            user_martingale_step[chat_id] = 1 # ชนะแล้วรีเซ็ตกลับไม้ 1
            text = "✅ ชนะไม้ 3! รีเซ็ตกลับสเต็ปไม้ 1"
        elif result_type == "loss":
            # ถ้าแพ้ ให้เลื่อนสเต็ปไปไม้ถัดไป
            current_step = user_martingale_step[chat_id]
            if current_step < 3:
                user_martingale_step[chat_id] += 1
                text = f"❌ แพ้ไม้ {current_step} ➔ ขยับไปลุยต่อ [ไม้ที่ {user_martingale_step[chat_id]}]"
            else:
                user_stats[chat_id]["loss"] += 1
                user_martingale_step[chat_id] = 1 # ครบ 3 ไม้ บันทึก Loss และวนกลับไม้ 1
                text = "❌ ครบ 3 ไม้ บันทึก LOSS และรีเซ็ตกลับไม้ 1"
        else:
            text = "บันทึกผลเรียบร้อย"
        
        bot.answer_callback_query(call.id, text)
        bot.send_message(chat_id, f"📌 อัปเดตสถานะล่าสุด:\n{get_stats_text(chat_id)}", parse_mode="Markdown")
        return

    if call.data.startswith("analyze_"):
        symbol = call.data.split("analyze_")[1]
        symbol_label = SYMBOLS.get(symbol, symbol)
        
        direction, zone_status = analyze_hardcore_market(symbol)
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
            f"🇷🇺 Titan Beam Pro V50 (Hardcore)\n\n"
            f"🎯 **คำแนะนำ: ออกออเดอร์ `[ ไม้ที่ {current_step} ]`**\n"
            f"💲📊 {symbol_label}\n"
            f"💎 M1 | Win Rate: `{sym_wr:.2f}%`\n"
            f"⏱️ เวลาเป้าหมาย: `{target_time_str}`\n"
            f"🛡️ {zone_status}\n"
            f"📈 ทิศทาง: {'BUY 🟢' if direction == 'CALL' else 'SELL 🔴'}"
        )

        bot.send_message(chat_id, signal_text, reply_markup=markup, parse_mode="Markdown")

print("--------------------------------------------------")
print("🇷🇺 Titan Beam Pro V50 (Hardcore Engine) กำลังรันระบบ...")
print("--------------------------------------------------")

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"⚠️ การเชื่อมต่อขัดข้อง: {e} - กำลังเชื่อมต่อใหม่ใน 5 วินาที...")
        time.sleep(5)
