# ============================================================
# SK Tools Shop — Ultimate Auto-Shop & Multi-API Licensing Bot
# ============================================================
# requirements.txt ফাইলে লিখবেন:
# pyTelegramBotAPI
# requests
# flask
# ============================================================

import telebot
import requests
import random
import string
import sqlite3
import threading
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============================================================
# আপনার দেওয়া নতুন কনফিগারেশন
# ============================================================
BOT_TOKEN = "8944774594:AAG2CtEfzZWN0dPC-0UhsijjApYpVAZS_qw"
ADMIN_ID  = 7865823978  # আপনার টেলিগ্রাম চ্যাট আইডি

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')

# অ্যাডমিনের সাময়িক স্টেট ট্র্যাকিং (প্রোডাক্ট এবং গেটওয়ে অ্যাড করার জন্য)
admin_state = {}

# ──────────────────────────────────────────────
# ডাটাবেজ সেটআপ (SQLite)
# ──────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect('shuvo_ultimate_shop.db')
    cursor = conn.cursor()
    
    # ১. প্রোডাক্ট টেবিল (আলাদা আলাদা লাইসেন্স API সহ)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            download_link TEXT,
            license_api_url TEXT,
            admin_secret TEXT,
            days INTEGER,
            price INTEGER
        )
    ''')
    
    # ২. অর্ডার ও সেলস টেবিল
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            chat_id INTEGER,
            user_name TEXT,
            product_id INTEGER,
            product_name TEXT,
            days INTEGER,
            price INTEGER,
            status TEXT,
            device_id TEXT,
            license_key TEXT,
            timestamp TEXT
        )
    ''')
    
    # ৩. গেটওয়ে সেটিংস টেবিল
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # ডিফল্ট SteadyPay ক্রেডেনশিয়াল সেট করা (পরবর্তীতে অ্যাডমিন প্যানেল থেকে চেঞ্জ করা যাবে)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('api_key', 'YOUR_STEADYPAY_API_KEY')")
    
    conn.commit()
    conn.close()

init_db()

# ──────────────────────────────────────────────
# Helper Functions (ডাটাবেজ ও এপিআই কল)
# ──────────────────────────────────────────────
def get_setting(key):
    conn = sqlite3.connect('shuvo_ultimate_shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else ""

def call_custom_license_api(api_url, secret, device_id, days):
    """প্রত্যেক প্রোডাক্টের নিজস্ব লাইসেন্স এপিআই কল করার ফাংশন"""
    chars = string.ascii_uppercase + string.digits
    key = f"SHUVO-{''.join(random.choices(chars, k=5))}-{''.join(random.choices(chars, k=5))}"
    expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    
    data = {
        'action': 'add',
        'admin_secret': secret,
        'key': key,
        'device': device_id,
        'expiry': expiry
    }
    try:
        r = requests.post(api_url, data=data, timeout=15)
        res = r.json()
        if res.get('status') == 'success':
            return res.get('key', key)
    except:
        return key  # এপিআই রেসপন্স না করলে ব্যাকআপ কী
    return key

# ──────────────────────────────────────────────
# ইউজার ভিউ (/start মেনু)
# ──────────────────────────────────────────────
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    chat_id = msg.chat.id
    markup = InlineKeyboardMarkup(row_width=1)
    
    # ডাটাবেজ থেকে সচল প্রোডাক্ট লিস্ট আনা
    conn = sqlite3.connect('shuvo_ultimate_shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, days FROM products")
    products = cursor.fetchall()
    conn.close()
    
    if products:
        for p in products:
            markup.add(InlineKeyboardButton(f"🖥️ {p[1]} ({p[2]} টাকা / {p[3]} দিন)", callback_data=f"usr_select_{p[0]}"))
    else:
        bot.send_message(chat_id, "🛒 আমাদের শপে বর্তমানে কোনো সফটওয়্যার উপলব্ধ নেই।")
        if chat_id == ADMIN_ID:
            markup.add(InlineKeyboardButton("⭐ ওপেন অ্যাডমিন প্যানেল ⭐", callback_data="adm_panel"))
            bot.send_message(chat_id, "🔧 অ্যাডমিন প্যানেল অ্যাক্সেস করুন:", reply_markup=markup)
        return

    if chat_id == ADMIN_ID:
        markup.add(InlineKeyboardButton("⭐ ওপেন অ্যাডমিন প্যানেল ⭐", callback_data="adm_panel"))
        
    bot.send_message(chat_id, 
        f"👋 *স্বাগতম {msg.from_user.first_name}!*\n\n"
        f"🚀 *SK Tools Shop*-এ আপনাকে স্বাগতম। আপনার পছন্দের অ্যাপটি কিনতে নিচে ক্লিক করুন:", 
        parse_mode='Markdown', reply_markup=markup)

# ──────────────────────────────────────────────
# অ্যাডমিন প্যানেল লজিক
# ──────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    chat_id = call.message.chat.id
    if chat_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ আপনি অ্যাডমিন নন!")
        return

    data = call.data

    if data == "adm_panel":
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("➕ নতুন সফটওয়্যার অ্যাড করুন", callback_data="adm_add_product"),
            InlineKeyboardButton("📊 সেলস রিপোর্ট ও ইউজার লিস্ট", callback_data="adm_sales_report"),
            InlineKeyboardButton("⚙️ SteadyPay API সেটিংস", callback_data="adm_gateway_settings"),
            InlineKeyboardButton("⬅️ ইউজার মেনু", callback_data="adm_back_to_user")
        )
        bot.edit_message_text("🛠️ *SK Tools Shop Admin Panel* — আপনার শপ নিয়ন্ত্রণ করুন:", 
                              chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data == "adm_back_to_user":
        bot.delete_message(chat_id, call.message.message_id)
        cmd_start(call.message)

    # ১. নতুন প্রোডাক্ট অ্যাড করার স্টেপ বাই স্টেপ প্রসেস
    elif data == "adm_add_product":
        bot.edit_message_text("📝 সফটওয়্যারের *নাম (Name)* লিখুন:", chat_id, call.message.message_id, parse_mode='Markdown')
        admin_state[chat_id] = {"step": "add_name"}

    # ২. গেটওয়ে সেটিংস প্রদর্শন
    elif data == "adm_gateway_settings":
        current_api = get_setting("api_key")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔧 API Key পরিবর্তন করুন", callback_data="adm_change_api"))
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text(f"⚙️ *SteadyPay Settings:*\n\n🔑 Current API Key:\n`{current_api}`", 
                              chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data == "adm_change_api":
        bot.edit_message_text("🔑 আপনার নতুন *SteadyPay API Key* টি পাঠান:", chat_id, call.message.message_id, parse_mode='Markdown')
        admin_state[chat_id] = {"step": "change_api_key"}

    # ৩. সেলস রিপোর্ট দেখা
    elif data == "adm_sales_report":
        conn = sqlite3.connect('shuvo_ultimate_shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(price) FROM orders WHERE status='COMPLETED' OR status='PAID'")
        total_sales, total_earnings = cursor.fetchone()
        total_earnings = total_earnings if total_earnings else 0
        
        cursor.execute("SELECT user_name, product_name, price, timestamp FROM orders WHERE status='COMPLETED' OR status='PAID' ORDER BY timestamp DESC LIMIT 5")
        recent_orders = cursor.fetchall()
        conn.close()

        report_text = f"📊 *বিক্রয় ও ইউজার রিপোর্ট:*\n\n" \
                      f"💰 মোট আয়: `{total_earnings}` টাকা\n" \
                      f"📦 মোট বিক্রি হয়েছে: `{total_sales}` টি লাইসেন্স\n\n" \
                      f"📋 *সর্বশেষ ৫টি ক্রয়:* \n"
        
        for o in recent_orders:
            report_text += f"👤 {o[0]} ➔ {o[1]} (`{o[2]} tk` - {o[3]})\n"
            
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text(report_text, chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    bot.answer_callback_query(call.id)

# ──────────────────────────────────────────────
# অ্যাডমিন টেক্সট ইনপুট হ্যান্ডলিং
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda msg: msg.chat.id == ADMIN_ID and msg.chat.id in admin_state)
def handle_admin_inputs(msg):
    chat_id = msg.chat.id
    state = admin_state[chat_id]
    step = state.get("step")

    if step == "add_name":
        state["name"] = msg.text.strip()
        bot.send_message(chat_id, "📥 সফটওয়্যারের ডিরেক্ট *Download Link* দিন:")
        state["step"] = "add_link"

    elif step == "add_link":
        state["link"] = msg.text.strip()
        bot.send_message(chat_id, "🔗 এই নির্দিষ্ট সফটওয়্যারের জন্য আলাদা *License API URL* দিন:")
        state["step"] = "add_api_url"

    elif step == "add_api_url":
        state["api_url"] = msg.text.strip()
        bot.send_message(chat_id, "🔑 এই লাইসেন্স এপিআই এর *Admin Secret Key* দিন:")
        state["step"] = "add_secret"

    elif step == "add_secret":
        state["secret"] = msg.text.strip()
        bot.send_message(chat_id, "📅 লাইসেন্সের মেয়াদ কতদিন হবে? *(শুধুমাত্র সংখ্যা লিখুন, যেমন: ৩০)*")
        state["step"] = "add_days"

    elif step == "add_days":
        if not msg.text.isdigit():
            bot.send_message(chat_id, "❌ দয়া করে শুধুমাত্র সংখ্যা লিখুন। মেয়াদ দিন:")
            return
        state["days"] = int(msg.text)
        bot.send_message(chat_id, "💰 এই প্যাকেজের জন্য কত *দাম (Price)* সেট করতে চান? *(যেমন: ৩০০)*")
        state["step"] = "add_price"

    elif step == "add_price":
        if not msg.text.isdigit():
            bot.send_message(chat_id, "❌ দয়া করে শুধুমাত্র সংখ্যা লিখুন। দাম দিন:")
            return
        price = int(msg.text)
        
        conn = sqlite3.connect('shuvo_ultimate_shop.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (name, download_link, license_api_url, admin_secret, days, price) VALUES (?, ?, ?, ?, ?, ?)",
                       (state["name"], state["link"], state["api_url"], state["secret"], state["days"], price))
        conn.commit()
        conn.close()
        
        bot.send_message(chat_id, f"✅ *সফলভাবে প্রোডাক্ট লিস্ট করা হয়েছে!*\n\n🖥️ নাম: {state['name']}\n💰 দাম: {price} টাকা", parse_mode='Markdown')
        del admin_state[chat_id]

    elif step == "change_api_key":
        new_key = msg.text.strip()
        conn = sqlite3.connect('shuvo_ultimate_shop.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value=? WHERE key='api_key'", (new_key,))
        conn.commit()
        conn.close()
        bot.send_message(chat_id, "✅ SteadyPay API Key সফলভাবে আপডেট করা হয়েছে।")
        del admin_state[chat_id]

# ──────────────────────────────────────────────
# ইউজার পারচেজ লজিক (SteadyPay Integration)
# ──────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("usr_") or call.data.startswith("dev_"))
def user_callbacks(call):
    chat_id = call.message.chat.id
    data = call.data

    if data.startswith("usr_select_"):
        p_id = data.replace("usr_select_", "")
        
        conn = sqlite3.connect('shuvo_ultimate_shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, price, days FROM products WHERE id=?", (p_id,))
        p = cursor.fetchone()
        conn.close()

        order_id = f"SK_{random.randint(100000, 999999)}"
        
        conn = sqlite3.connect('shuvo_ultimate_shop.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (order_id, chat_id, user_name, product_id, product_name, days, price, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)",
                       (order_id, chat_id, call.from_user.first_name, p[0], p[1], p[3], p[2], datetime.now().strftime('%Y-%m-%d %H:%M')))
        conn.commit()
        conn.close()

        api_key = get_setting("api_key")
        pay_url = f"https://api.steadypay.com.bd/v1/payment?api_key={api_key}&amount={p[2]}&order_id={order_id}"

        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("💳 SteadyPay পেমেন্ট করুন (বিকাশ/নগদ/রকেট)", url=pay_url))
        
        bot.edit_message_text(
            f"🛒 *অর্ডার কনফার্মেশন:*\n\n"
            f"🖥️ সফটওয়্যার: *{p[1]}*\n"
            f"📅 মেয়াদ: `{p[3]}` দিন\n"
            f"💰 পরিশোধযোগ্য মূল্য: `{p[2]}` টাকা\n\n"
            f"⚠️ নিচের বাটনে ক্লিক করে বিকাশ, নগদ বা রকেটের মাধ্যমে ইনস্ট্যান্ট পেমেন্ট সম্পন্ন করুন।",
            chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data.startswith("dev_"):
        order_id = data.replace("dev_", "")
        msg = bot.send_message(chat_id, "📱 এবার আপনার অ্যাপ থেকে kopi করা *Device ID* টি এখানে টেক্সট আকারে লিখে পাঠান:")
        bot.register_next_step_handler(msg, process_user_device_id, order_id)

    bot.answer_callback_query(call.id)

# ──────────────────────────────────────────────
# ইউজার ডিভাইস আইডি প্রসেস এবং আলাদা এপিআই-কী জেনারেট
# ──────────────────────────────────────────────
def process_user_device_id(msg, order_id):
    chat_id = msg.chat.id
    device_id = msg.text.strip().upper()

    conn = sqlite3.connect('shuvo_ultimate_shop.db')
    cursor = conn.cursor()
    cursor.execute("SELECT product_id, days, status FROM orders WHERE order_id=?", (order_id,))
    order = cursor.fetchone()

    if not order or order[2] != "PAID":
        bot.send_message(chat_id, "❌ আপনার পেমেন্ট ভেরিফাইড নয় অথবা অর্ডারটি পাওয়া যায়নি।")
        conn.close()
        return

    p_id, days, status = order
    
    cursor.execute("SELECT license_api_url, admin_secret FROM products WHERE id=?", (p_id,))
    api_info = cursor.fetchone()
    
    if api_info:
        api_url, secret = api_info
        license_key = call_custom_license_api(api_url, secret, device_id, days)
        
        cursor.execute("UPDATE orders SET status='COMPLETED', device_id=?, license_key=? WHERE order_id=?",
                       (device_id, license_key, order_id))
        conn.commit()

        bot.send_message(chat_id,
            f"🎉 *লাইসেন্স জেনারেশন সফল!*\n\n"
            f"🔑 *License Key:*\n`{license_key}`\n\n"
            f"💻 *Device ID:* `{device_id}`\n"
            f"📅 *মেয়াদ:* {days} দিন\n\n"
            f"✅ কী-টি কপি করে সফটওয়্যারে বসিয়ে নিন। ধন্যবাদ!",
            parse_mode='Markdown'
        )
        bot.send_message(ADMIN_ID, f"🔔 *সেলস সফল!* \n👤 কাস্টমার: {msg.from_user.first_name}\n🔑 কী: `{license_key}`")
    else:
        bot.send_message(chat_id, "❌ এই সফটওয়্যারের লাইসেন্স সার্ভার কনফিগারেশনে সমস্যা রয়েছে।")
        
    conn.close()

# ──────────────────────────────────────────────
# SteadyPay Webhook / Callback ইভেন্ট রিসিভার
# ──────────────────────────────────────────────
@app.route('/')
def home():
    return "SteadyPay Automation Core is Active!"

@app.route('/payment-callback', methods=['POST', 'GET'])
def steadypay_callback():
    data = request.args if request.method == 'GET' else request.json
    
    order_id = data.get('order_id')
    status = data.get('status')
    
    if order_id and (status == 'success' or status == 'paid'):
        conn = sqlite3.connect('shuvo_ultimate_shop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, product_id, product_name FROM orders WHERE order_id=? AND status='PENDING'", (order_id,))
        res = cursor.fetchone()
        
        if res:
            chat_id, p_id, p_name = res
            cursor.execute("UPDATE orders SET status='PAID' WHERE order_id=?", (order_id,))
            conn.commit()
            
            cursor.execute("SELECT download_link FROM products WHERE id=?", (p_id,))
            link_res = cursor.fetchone()
            download_link = link_res[0] if link_res else ""
            conn.close()

            markup = InlineKeyboardMarkup()
            if download_link:
                markup.add(InlineKeyboardButton("📥 Download Software", url=download_link))
            markup.add(InlineKeyboardButton("📱 Submit Device ID", callback_data=f"dev_{order_id}"))
            
            bot.send_message(chat_id,
                f"✅ *আপনার পেমেন্ট সফলভাবে সম্পন্ন হয়েছে!*\n\n"
                f"🚀 কেনা প্রোডাক্ট: *{p_name}*\n\n"
                f"📌 নিচে থাকা *Download Software* বাটনে ক্লিক করে অ্যাপটি ডাউনলোড করুন। এরপর অ্যাপটি ওপেন করে যে **Device ID** পাবেন, তা *Submit Device ID* বাটনে ক্লিক করে পাঠিয়ে দিন।",
                parse_mode='Markdown', reply_markup=markup
            )
            return jsonify({"status": "success"}), 200
        conn.close()

    return jsonify({"status": "ignored"}), 400

# ──────────────────────────────────────────────
# রান সার্ভার ও পোলিং
# ──────────────────────────────────────────────
def run_server():
    app.run(host='0.0.0.0', port=10000)

if __name__ == '__main__':
    threading.Thread(target=run_server, daemon=True).start()
    print("🤖 SK Tools Shop Bot Loaded perfectly. Infinity polling started...")
    bot.infinity_polling()
    