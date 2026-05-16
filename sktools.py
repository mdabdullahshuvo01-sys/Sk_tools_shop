# ============================================================
# SK Tools Shop — Manual TxID Payment & Multi-Package Bot
# ============================================================
import telebot
import requests
import random
import string
import sqlite3
import threading
from flask import Flask
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8944774594:AAG2CtEfzZWN0dPC-0UhsijjApYpVAZS_qw"
ADMIN_ID  = 7865823978

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask('')

admin_state = {}

# ──────────────────────────────────────────────
# ডাটাবেজ সেটআপ (SQLite)
# ──────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect('sk_tools_v2.db')
    cursor = conn.cursor()
    
    # ১. মূল প্রোডাক্ট টেবিল
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            download_link TEXT,
            license_api_url TEXT,
            admin_secret TEXT
        )
    ''')
    
    # ২. প্রোডাক্টের প্যাকেজ টেবিল (একটি প্রোডাক্টের একাধিক দাম/মেয়াদ)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            label TEXT,
            days INTEGER,
            price INTEGER,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    ''')
    
    # ৩. অর্ডার টেবিল (TxID এবং ম্যানুয়াল ভেরিফিকেশন ট্র্যাকিং)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            chat_id INTEGER,
            user_name TEXT,
            product_id INTEGER,
            product_name TEXT,
            package_label TEXT,
            days INTEGER,
            price INTEGER,
            txid TEXT,
            status TEXT,
            device_id TEXT,
            license_key TEXT,
            timestamp TEXT
        )
    ''')
    
    # ৪. বিকাশ/নগদ নাম্বার সেটিংস টেবিল
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('payment_info', 'বিকাশ পার্সোনাল: ০১৭XXXXXXXX\nনগদ পার্সোনাল: ০১৮XXXXXXXX\n\nটাকা পাঠানোর পর ট্রানজেকশন আইডি (TxID) নিচে দিন।')")
    conn.commit()
    conn.close()

init_db()

# ──────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────
def get_setting(key):
    conn = sqlite3.connect('sk_tools_v2.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else ""

def call_custom_license_api(api_url, secret, device_id, days):
    chars = string.ascii_uppercase + string.digits
    key = f"SK-{''.join(random.choices(chars, k=5))}-{''.join(random.choices(chars, k=5))}"
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
        return key
    return key

# ──────────────────────────────────────────────
# ইউজার ভিউ (/start মেনু)
# ──────────────────────────────────────────────
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    chat_id = msg.chat.id
    markup = InlineKeyboardMarkup(row_width=1)
    
    conn = sqlite3.connect('sk_tools_v2.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM products")
    products = cursor.fetchall()
    conn.close()
    
    if products:
        for p in products:
            markup.add(InlineKeyboardButton(f"🖥️ {p[1]}", callback_data=f"usr_view_{p[0]}"))
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
# অ্যাডমিন প্যানেল কোর লজিক
# ──────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    chat_id = call.message.chat.id
    if chat_id != ADMIN_ID: return

    data = call.data

    if data == "adm_panel":
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("➕ নতুন সফটওয়্যার অ্যাড করুন", callback_data="adm_add_product"),
            InlineKeyboardButton("📦 প্রোডাক্ট লিস্ট ও ডিলিট", callback_data="adm_list_products"),
            InlineKeyboardButton("📊 সেলস রিপোর্ট ও ইউজার", callback_data="adm_sales_report"),
            InlineKeyboardButton("⚙️ বিকাশ/নগদ নাম্বার সেটিংস", callback_data="adm_wallet_settings"),
            InlineKeyboardButton("⬅️ ইউজার মেনু", callback_data="adm_back_to_user")
        )
        bot.edit_message_text("🛠️ *SK Tools Shop Admin Panel*:", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data == "adm_back_to_user":
        bot.delete_message(chat_id, call.message.message_id)
        cmd_start(call.message)

    elif data == "adm_add_product":
        bot.edit_message_text("📝 সফটওয়্যারের *নাম (Name)* লিখুন:", chat_id, call.message.message_id, parse_mode='Markdown')
        admin_state[chat_id] = {"step": "add_name", "packages": []}

    elif data == "adm_wallet_settings":
        current_info = get_setting("payment_info")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📝 নাম্বার ও নিয়ম আপডেট করুন", callback_data="adm_change_wallet"))
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text(f"⚙️ *বর্তমান পেমেন্ট তথ্য:*\n\n{current_info}", chat_id, call.message.message_id, reply_markup=markup)

    elif data == "adm_change_wallet":
        bot.edit_message_text("✍️ আপনার নতুন বিকাশ/নগদ নাম্বার এবং কাস্টমারদের জন্য নিয়মটি লিখে পাঠান:", chat_id, call.message.message_id)
        admin_state[chat_id] = {"step": "change_wallet"}

    elif data == "adm_list_products":
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM products")
        prods = cursor.fetchall()
        conn.close()
        
        markup = InlineKeyboardMarkup(row_width=1)
        for p in prods:
            markup.add(InlineKeyboardButton(f"❌ ডিলিট: {p[1]}", callback_data=f"adm_del_{p[0]}"))
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text("📦 বর্তমানে লিস্টেড প্রোডাক্টসমূহ (ডিলিট করতে বাটনে চাপুন):", chat_id, call.message.message_id, reply_markup=markup)

    elif data.startswith("adm_del_"):
        p_id = data.replace("adm_del_", "")
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id=?", (p_id,))
        cursor.execute("DELETE FROM packages WHERE product_id=?", (p_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ প্রোডাক্টটি ডিলিট করা হয়েছে!")
        admin_callbacks(call) # রিলোড লিস্ট

    elif data == "adm_sales_report":
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(price) FROM orders WHERE status='COMPLETED'")
        total_sales, total_earnings = cursor.fetchone()
        total_earnings = total_earnings if total_earnings else 0
        
        cursor.execute("SELECT user_name, product_name, price, timestamp FROM orders WHERE status='COMPLETED' ORDER BY timestamp DESC LIMIT 5")
        recent_orders = cursor.fetchall()
        conn.close()

        report_text = f"📊 *বিক্রয় রিপোর্ট:*\n\n💰 মোট আয়: `{total_earnings}` টাকা\n📦 মোট বিক্রি: `{total_sales}` টি লাইসেন্স\n\n📋 *সর্বশেষ ৫টি ক্রয়:* \n"
        for o in recent_orders:
            report_text += f"👤 {o[0]} ➔ {o[1]} (`{o[2]} tk`)\n"
            
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text(report_text, chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data.startswith("adm_approve_") or data.startswith("adm_reject_"):
        action, order_id = data.split("_")[1], data.split("_")[2]
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, product_id, product_name, package_label, status FROM orders WHERE order_id=?", (order_id,))
        order = cursor.fetchone()
        
        if not order or order[4] != "PENDING_APPROVAL":
            bot.answer_callback_query(call.id, "⚠️ এই অর্ডারটি ইতিমধ্যে প্রসেস করা হয়েছে।")
            conn.close()
            return
            
        usr_chat_id, p_id, p_name, pkg_label, _ = order
        
        if action == "approve":
            cursor.execute("UPDATE orders SET status='PAID' WHERE order_id=?", (order_id,))
            cursor.execute("SELECT download_link FROM products WHERE id=?", (p_id,))
            link_res = cursor.fetchone()
            download_link = link_res[0] if link_res else ""
            conn.commit()
            
            markup_usr = InlineKeyboardMarkup()
            if download_link:
                markup_usr.add(InlineKeyboardButton("📥 Download Software", url=download_link))
            markup_usr.add(InlineKeyboardButton("📱 Submit Device ID", callback_data=f"dev_{order_id}"))
            
            bot.send_message(usr_chat_id, f"✅ *আপনার পেমেন্ট ভেরিফাইড হয়েছে!*\n\n🚀 প্রোডাক্ট: *{p_name} ({pkg_label})*\n\n📌 নিচে থেকে সফটওয়্যারটি ডাউনলোড করে ওপেন করুন এবং প্রাপ্ত **Device ID** টি সাবমিট করুন।", parse_mode='Markdown', reply_markup=markup_usr)
            bot.edit_message_text(f"✅ অর্ডার `{order_id}` অ্যাপ্রুভ করা হয়েছে!", chat_id, call.message.message_id)
        else:
            cursor.execute("UPDATE orders SET status='REJECTED' WHERE order_id=?", (order_id,))
            conn.commit()
            bot.send_message(usr_chat_id, f"❌ দুঃখিত, আপনার দেওয়া ট্রানজেকশন আইডিটি ম্যাচ করেনি। পেমেন্ট বাতিল করা হয়েছে।")
            bot.edit_message_text(f"❌ অর্ডার `{order_id}` রিজেক্ট করা হয়েছে!", chat_id, call.message.message_id)
            
        conn.close()

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
        bot.send_message(chat_id, "🎯 এবার এই সফটওয়্যারের জন্য প্যাকেজ যোগ করুন।\n\nপ্রথমে ১ম প্যাকেজের নাম ও মেয়াদ লিখুন।\n*ফরম্যাট:* `মেয়াদের নাম,দিনের সংখ্যা` (যেমন: `৩০ দিন মেয়াদী,30` বা `১৫ দিন মেয়াদী,15`)")
        state["step"] = "add_pkg_label"

    elif step == "add_pkg_label":
        try:
            label, days = msg.text.split(",")
            state["current_pkg_label"] = label.strip()
            state["current_pkg_days"] = int(days.strip())
            bot.send_message(chat_id, f"💰 *'{label.strip()}'* প্যাকেজটির জন্য কত দাম সেট করতে চান? (শুধুমাত্র সংখ্যা লিখুন)")
            state["step"] = "add_pkg_price"
        except:
            bot.send_message(chat_id, "❌ ফরম্যাট ভুল হয়েছে! আবার সঠিকভাবে লিখুন। উদাহরণ: `৩০ দিন মেয়াদী,30`")

    elif step == "add_pkg_price":
        if not msg.text.isdigit():
            bot.send_message(chat_id, "❌ শুধুমাত্র সংখ্যা লিখুন। দাম:")
            return
        price = int(msg.text)
        state["packages"].append({
            "label": state["current_pkg_label"],
            "days": state["current_pkg_days"],
            "price": price
        })
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ আরও প্যাকেজ যোগ করুন", callback_data="adm_add_more_pkg"))
        markup.add(InlineKeyboardButton("✅ আর লাগবে না, প্রোডাক্ট সেভ করুন", callback_data="adm_save_product_final"))
        bot.send_message(chat_id, f"প্যাকেজ যুক্ত হয়েছে: {state['current_pkg_label']} = {price} টাকা।\n\nআপনি কি আরও প্যাকেজ যোগ করতে চান নাকি এটিই ফাইনাল?", reply_markup=markup)

    elif step == "change_wallet":
        new_info = msg.text.strip()
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value=? WHERE key='payment_info'", (new_info,))
        conn.commit()
        conn.close()
        bot.send_message(chat_id, "✅ পেমেন্ট নাম্বার ও নিয়ম সফলভাবে আপডেট করা হয়েছে।")
        del admin_state[chat_id]

# প্যাকেজ এন্ডিং বাটন হ্যান্ডলার (অ্যাডমিন)
@bot.callback_query_handler(func=lambda call: call.data in ["adm_add_more_pkg", "adm_save_product_final"])
def handle_pkg_buttons(call):
    chat_id = call.message.chat.id
    if chat_id != ADMIN_ID or chat_id not in admin_state: return

    state = admin_state[chat_id]

    if call.data == "adm_add_more_pkg":
        bot.edit_message_text("🎯 পরবর্তী প্যাকেজের নাম ও মেয়াদ লিখুন।\n*ফরম্যাট:* `মেয়াদের নাম,দিনের সংখ্যা` (যেমন: `৩ মাস মেয়াদী,90`)", chat_id, call.message.message_id)
        state["step"] = "add_pkg_label"
    elif call.data == "adm_save_product_final":
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (name, download_link, license_api_url, admin_secret) VALUES (?, ?, ?, ?)",
                       (state["name"], state["link"], state["api_url"], state["secret"]))
        p_id = cursor.lastrowid
        
        for pkg in state["packages"]:
            cursor.execute("INSERT INTO packages (product_id, label, days, price) VALUES (?, ?, ?, ?)",
                           (p_id, pkg["label"], pkg["days"], pkg["price"]))
        conn.commit()
        conn.close()
        
        bot.edit_message_text(f"🎉 *সফলভাবে '{state['name']}' সফটওয়্যারটি মোট {len(state['packages'])}টি প্যাকেজসহ লিস্ট করা হয়েছে!*", chat_id, call.message.message_id, parse_mode='Markdown')
        del admin_state[chat_id]

# ──────────────────────────────────────────────
# ইউজার পারচেজ ও ম্যানুয়াল পেমেন্ট লজিক
# ──────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("usr_") or call.data.startswith("dev_"))
def user_callbacks(call):
    chat_id = call.message.chat.id
    data = call.data

    if data.startswith("usr_view_"):
        p_id = data.replace("usr_view_", "")
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM products WHERE id=?", (p_id,))
        p_name = cursor.fetchone()[0]
        cursor.execute("SELECT id, label, price FROM packages WHERE product_id=?", (p_id,))
        pkgs = cursor.fetchall()
        conn.close()
        
        markup = InlineKeyboardMarkup(row_width=1)
        for pkg in pkgs:
            markup.add(InlineKeyboardButton(f"💳 {pkg[1]} — {pkg[2]} টাকা", callback_data=f"usr_buy_{pkg[0]}"))
        markup.add(InlineKeyboardButton("⬅️ মেইন মেনু", callback_data="adm_back_to_user"))
        
        bot.edit_message_text(f"📦 *{p_name}* এর জন্য আপনার পছন্দের প্যাকেজটি সিলেক্ট করুন:", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data.startswith("usr_buy_"):
        pkg_id = data.replace("usr_buy_", "")
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("SELECT product_id, label, days, price FROM packages WHERE id=?", (pkg_id,))
        p_id, label, days, price = cursor.fetchone()
        cursor.execute("SELECT name FROM products WHERE id=?", (p_id,))
        p_name = cursor.fetchone()[0]
        conn.close()
        
        order_id = f"SK{random.randint(10000, 99999)}"
        
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (order_id, chat_id, user_name, product_id, product_name, package_label, days, price, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_TXID', ?)",
                       (order_id, chat_id, call.from_user.first_name, p_id, p_name, label, days, price, datetime.now().strftime('%Y-%m-%d %H:%M')))
        conn.commit()
        conn.close()

        pmnt_info = get_setting("payment_info")
        msg = bot.edit_message_text(f"🛒 *অर्डर সামারি:*\n🖥️ সফটওয়্যার: {p_name}\n🎯 প্যাকেজ: {label}\n💰 মূল্য: {price} টাকা\n\n💵 *পেমেন্ট করার নিয়ম:*\n{pmnt_info}", chat_id, call.message.message_id)
        admin_state[chat_id] = {"step": "submit_txid", "order_id": order_id}

    elif data.startswith("dev_"):
        order_id = data.replace("dev_", "")
        msg = bot.send_message(chat_id, "📱 এবার আপনার অ্যাপ থেকে কপি করা *Device ID* টি এখানে টেক্সট আকারে লিখে পাঠান:")
        bot.register_next_step_handler(msg, process_user_device_id, order_id)

# ইউজার টেক্সট ইনপুট (TxID সাবমিট)
@bot.message_handler(func=lambda msg: msg.chat.id in admin_state and admin_state[msg.chat.id].get("step") == "submit_txid")
def handle_user_txid(msg):
    chat_id = msg.chat.id
    txid = msg.text.strip().upper()
    order_id = admin_state[chat_id]["order_id"]
    
    conn = sqlite3.connect('sk_tools_v2.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET txid=?, status='PENDING_APPROVAL' WHERE order_id=?", (txid, order_id))
    cursor.execute("SELECT product_name, package_label, price FROM orders WHERE order_id=?", (order_id,))
    p_name, label, price = cursor.fetchone()
    conn.commit()
    conn.close()
    
    del admin_state[chat_id]
    bot.send_message(chat_id, "⏳ আপনার ট্রানজেকশন আইডিটি অ্যাডমিনের কাছে পাঠানো হয়েছে। অনুগ্রহ করে ভেরিফিকেশন সম্পন্ন হওয়া পর্যন্ত অপেক্ষা করুন।")
    
    # অ্যাডমিনকে নোটিফিকেশন পাঠানো
    markup_adm = InlineKeyboardMarkup()
    markup_adm.add(InlineKeyboardButton("✅ Approve", callback_data=f"adm_approve_{order_id}"),
                   InlineKeyboardButton("❌ Reject", callback_data=f"adm_reject_{order_id}"))
    
    bot.send_message(ADMIN_ID, f"🔔 *নতুন পেমেন্ট রিকোয়েস্ট এসেছে!*\n\n👤 কাস্টমার: {msg.from_user.first_name}\n🖥️ সফটওয়্যার: {p_name}\n🎯 প্যাকেজ: {label}\n💰 মূল্য: {price} টাকা\n🔑 TxID: `{txid}`", parse_mode='Markdown', reply_markup=markup_adm)

# dispositivo ID id process
def process_user_device_id(msg, order_id):
    chat_id = msg.chat.id
    device_id = msg.text.strip().upper()

    conn = sqlite3.connect('sk_tools_v2.db')
    cursor = conn.cursor()
    cursor.execute("SELE    else:
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
# অ্যাডমিন প্যানেল কোর লজিক
# ──────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    chat_id = call.message.chat.id
    if chat_id != ADMIN_ID: return

    data = call.data

    if data == "adm_panel":
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("➕ নতুন সফটওয়্যার অ্যাড করুন", callback_data="adm_add_product"),
            InlineKeyboardButton("📦 প্রোডাক্ট লিস্ট ও ডিলিট", callback_data="adm_list_products"),
            InlineKeyboardButton("📊 সেলস রিপোর্ট ও ইউজার", callback_data="adm_sales_report"),
            InlineKeyboardButton("⚙️ বিকাশ/নগদ নাম্বার সেটিংস", callback_data="adm_wallet_settings"),
            InlineKeyboardButton("⬅️ ইউজার মেনু", callback_data="adm_back_to_user")
        )
        bot.edit_message_text("🛠️ *SK Tools Shop Admin Panel*:", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data == "adm_back_to_user":
        bot.delete_message(chat_id, call.message.message_id)
        cmd_start(call.message)

    elif data == "adm_add_product":
        bot.edit_message_text("📝 সফটওয়্যারের *নাম (Name)* লিখুন:", chat_id, call.message.message_id, parse_mode='Markdown')
        admin_state[chat_id] = {"step": "add_name", "packages": []}

    elif data == "adm_wallet_settings":
        current_info = get_setting("payment_info")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📝 নাম্বার ও নিয়ম আপডেট করুন", callback_data="adm_change_wallet"))
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text(f"⚙️ *বর্তমান পেমেন্ট তথ্য:*\n\n{current_info}", chat_id, call.message.message_id, reply_markup=markup)

    elif data == "adm_change_wallet":
        bot.edit_message_text("✍️ আপনার নতুন বিকাশ/নগদ নাম্বার এবং কাস্টমারদের জন্য নিয়মটি লিখে পাঠান:", chat_id, call.message.message_id)
        admin_state[chat_id] = {"step": "change_wallet"}

    elif data == "adm_list_products":
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM products")
        prods = cursor.fetchall()
        conn.close()
        
        markup = InlineKeyboardMarkup(row_width=1)
        for p in prods:
            markup.add(InlineKeyboardButton(f"❌ ডিলিট: {p[1]}", callback_data=f"adm_del_{p[0]}"))
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text("📦 বর্তমানে লিস্টেড প্রোডাক্টসমূহ (ডিলিট করতে বাটনে চাপুন):", chat_id, call.message.message_id, reply_markup=markup)

    elif data.startswith("adm_del_"):
        p_id = data.replace("adm_del_", "")
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id=?", (p_id,))
        cursor.execute("DELETE FROM packages WHERE product_id=?", (p_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ প্রোডাক্টটি ডিলিট করা হয়েছে!")
        admin_callbacks(call) # রিলোড লিস্ট

    elif data == "adm_sales_report":
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(price) FROM orders WHERE status='COMPLETED'")
        total_sales, total_earnings = cursor.fetchone()
        total_earnings = total_earnings if total_earnings else 0
        
        cursor.execute("SELECT user_name, product_name, price, timestamp FROM orders WHERE status='COMPLETED' ORDER BY timestamp DESC LIMIT 5")
        recent_orders = cursor.fetchall()
        conn.close()

        report_text = f"📊 *বিক্রয় রিপোর্ট:*\n\n💰 মোট আয়: `{total_earnings}` টাকা\n📦 মোট বিক্রি: `{total_sales}` টি লাইসেন্স\n\n📋 *সর্বশেষ ৫টি ক্রয়:* \n"
        for o in recent_orders:
            report_text += f"👤 {o[0]} ➔ {o[1]} (`{o[2]} tk`)\n"
            
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text(report_text, chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data.startswith("adm_approve_") or data.startswith("adm_reject_"):
        action, order_id = data.split("_")[1], data.split("_")[2]
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, product_id, product_name, package_label, status FROM orders WHERE order_id=?", (order_id,))
        order = cursor.fetchone()
        
        if not order or order[4] != "PENDING_APPROVAL":
            bot.answer_callback_query(call.id, "⚠️ এই অর্ডারটি ইতিমধ্যে প্রসেস করা হয়েছে।")
            conn.close()
            return
            
        usr_chat_id, p_id, p_name, pkg_label, _ = order
        
        if action == "approve":
            cursor.execute("UPDATE orders SET status='PAID' WHERE order_id=?", (order_id,))
            cursor.execute("SELECT download_link FROM products WHERE id=?", (p_id,))
            link_res = cursor.fetchone()
            download_link = link_res[0] if link_res else ""
            conn.commit()
            
            markup_usr = InlineKeyboardMarkup()
            if download_link:
                markup_usr.add(InlineKeyboardButton("📥 Download Software", url=download_link))
            markup_usr.add(InlineKeyboardButton("📱 Submit Device ID", callback_data=f"dev_{order_id}"))
            
            bot.send_message(usr_chat_id, f"✅ *আপনার পেমেন্ট ভেরিফাইড হয়েছে!*\n\n🚀 প্রোডাক্ট: *{p_name} ({pkg_label})*\n\n📌 নিচে থেকে সফটওয়্যারটি ডাউনলোড করে ওপেন করুন এবং প্রাপ্ত **Device ID** টি সাবমিট করুন।", parse_mode='Markdown', reply_markup=markup_usr)
            bot.edit_message_text(f"✅ অর্ডার `{order_id}` অ্যাপ্রুভ করা হয়েছে!", chat_id, call.message.message_id)
        else:
            cursor.execute("UPDATE orders SET status='REJECTED' WHERE order_id=?", (order_id,))
            conn.commit()
            bot.send_message(usr_chat_id, f"❌ দুঃখিত, আপনার দেওয়া ট্রানজেকশন আইডিটি ম্যাচ করেনি। পেমেন্ট বাতিল করা হয়েছে।")
            bot.edit_message_text(f"❌ অর্ডার `{order_id}` রিজেক্ট করা হয়েছে!", chat_id, call.message.message_id)
            
        conn.close()

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
        bot.send_message(chat_id, "🎯 এবার এই সফটওয়্যারের জন্য প্যাকেজ যোগ করুন।\n\nপ্রথমে ১ম প্যাকেজের নাম ও মেয়াদ লিখুন।\n*ফরম্যাট:* `মেয়াদের নাম,দিনের সংখ্যা` (যেমন: `৩০ দিন মেয়াদী,30` বা `১৫ দিন মেয়াদী,15`)")
        state["step"] = "add_pkg_label"

    elif step == "add_pkg_label":
        try:
            label, days = msg.text.split(",")
            state["current_pkg_label"] = label.strip()
            state["current_pkg_days"] = int(days.strip())
            bot.send_message(chat_id, f"💰 *'{label.strip()}'* প্যাকেজটির জন্য কত দাম সেট করতে চান? (শুধুমাত্র সংখ্যা লিখুন)")
            state["step"] = "add_pkg_price"
        except:
            bot.send_message(chat_id, "❌ ফরম্যাট ভুল হয়েছে! আবার সঠিকভাবে লিখুন। উদাহরণ: `৩০ দিন মেয়াদী,30`")

    elif step == "add_pkg_price":
        if not msg.text.isdigit():
            bot.send_message(chat_id, "❌ শুধুমাত্র সংখ্যা লিখুন। দাম:")
            return
        price = int(msg.text)
        state["packages"].append({
            "label": state["current_pkg_label"],
            "days": state["current_pkg_days"],
            "price": price
        })
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ আরও প্যাকেজ যোগ করুন", callback_data="adm_add_more_pkg"))
        markup.add(InlineKeyboardButton("✅ আর লাগবে না, প্রোডাক্ট সেভ করুন", callback_data="adm_save_product_final"))
        bot.send_message(chat_id, f"প্যাকেজ যুক্ত হয়েছে: {state['current_pkg_label']} = {price} টাকা।\n\nআপনি কি আরও প্যাকেজ যোগ করতে চান নাকি এটিই ফাইনাল?", reply_markup=markup)

    elif step == "change_wallet":
        new_info = msg.text.strip()
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value=? WHERE key='payment_info'", (new_info,))
        conn.commit()
        conn.close()
        bot.send_message(chat_id, "✅ পেমেন্ট নাম্বার ও নিয়ম সফলভাবে আপডেট করা হয়েছে।")
        del admin_state[chat_id]

# প্যাকেজ এন্ডিং বাটন হ্যান্ডলার (অ্যাডমিন)
@bot.callback_query_handler(func=lambda call: call.data in ["adm_add_more_pkg", "adm_save_product_final"])
def handle_pkg_buttons(call):
    chat_id = call.message.chat.id
    if chat_id != ADMIN_ID or chat_id prejudge not in admin_state: return

    state = admin_state[chat_id]

    if call.data == "adm_add_more_pkg":
        bot.edit_message_text("🎯 পরবর্তী প্যাকেজের নাম ও মেয়াদ লিখুন।\n*ফরম্যাট:* `মেয়াদের নাম,দিনের সংখ্যা` (যেমন: `৩ মাস মেয়াদী,90`)", chat_id, call.message.message_id)
        state["step"] = "add_pkg_label"
    elif call.data == "adm_save_product_final":
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (name, download_link, license_api_url, admin_secret) VALUES (?, ?, ?, ?)",
                       (state["name"], state["link"], state["api_url"], state["secret"]))
        p_id = cursor.lastrowid
        
        for pkg in state["packages"]:
            cursor.execute("INSERT INTO packages (product_id, label, days, price) VALUES (?, ?, ?, ?)",
                           (p_id, pkg["label"], pkg["days"], pkg["price"]))
        conn.commit()
        conn.close()
        
        bot.edit_message_text(f"🎉 *সফলভাবে '{state['name']}' সফটওয়্যারটি মোট {len(state['packages'])}টি প্যাকেজসহ লিস্ট করা হয়েছে!*", chat_id, call.message.message_id, parse_mode='Markdown')
        del admin_state[chat_id]

# ──────────────────────────────────────────────
# ইউজার পারচেজ ও ম্যানুয়াল পেমেন্ট লজিক
# ──────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("usr_") or call.data.startswith("dev_"))
def user_callbacks(call):
    chat_id = call.message.chat.id
    data = call.data

    if data.startswith("usr_view_"):
        p_id = data.replace("usr_view_", "")
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM products WHERE id=?", (p_id,))
        p_name = cursor.fetchone()[0]
        cursor.execute("SELECT id, label, price FROM packages WHERE product_id=?", (p_id,))
        pkgs = cursor.fetchall()
        conn.close()
        
        markup = InlineKeyboardMarkup(row_width=1)
        for pkg in pkgs:
            markup.add(InlineKeyboardButton(f"💳 {pkg[1]} — {pkg[2]} টাকা", callback_data=f"usr_buy_{pkg[0]}"))
        markup.add(InlineKeyboardButton("⬅️ মেইন মেনু", callback_data="adm_back_to_user"))
        
        bot.edit_message_text(f"📦 *{p_name}* এর জন্য আপনার পছন্দের প্যাকেজটি সিলেক্ট করুন:", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data.startswith("usr_buy_"):
        pkg_id = data.replace("usr_buy_", "")
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("SELECT product_id, label, days, price FROM packages WHERE id=?", (pkg_id,))
        p_id, label, days, price = cursor.fetchone()
        cursor.execute("SELECT name FROM products WHERE id=?", (p_id,))
        p_name = cursor.fetchone()[0]
        conn.close()
        
        order_id = f"SK{random.randint(10000, 99999)}"
        
        conn = sqlite3.connect('sk_tools_v2.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (order_id, chat_id, user_name, product_id, product_name, package_label, days, price, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_TXID', ?)",
                       (order_id, chat_id, call.from_user.first_name, p_id, p_name, label, days, price, datetime.now().strftime('%Y-%m-%d %H:%M')))
        conn.commit()
        conn.close()

        pmnt_info = get_setting("payment_info")
        msg = bot.edit_message_text(f"🛒 *অর্ডার সামারি:*\n🖥️ সফটওয়্যার: {p_name}\n🎯 প্যাকেজ: {label}\n💰 মূল্য: {price} টাকা\n\n💵 *পেমেন্ট করার নিয়ম:*\n{pmnt_info}", chat_id, call.message.message_id)
        admin_state[chat_id] = {"step": "submit_txid", "order_id": order_id}

    elif data.startswith("dev_"):
        order_id = data.replace("dev_", "")
        msg = bot.send_message(chat_id, "📱 এবার আপনার অ্যাপ থেকে কপি করা *Device ID* টি এখানে টেক্সট আকারে লিখে পাঠান:")
        bot.register_next_step_handler(msg, process_user_device_id, order_id)

# ইউজার টেক্সট ইনপুট (TxID সাবমিট)
@bot.message_handler(func=lambda msg: msg.chat.id in admin_state and admin_state[msg.chat.id].get("step") == "submit_txid")
def handle_user_txid(msg):
    chat_id = msg.chat.id
    txid = msg.text.strip().upper()
    order_id = admin_state[chat_id]["order_id"]
    
    conn = sqlite3.connect('sk_tools_v2.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET txid=?, status='PENDING_APPROVAL' WHERE order_id=?", (txid, order_id))
    cursor.execute("SELECT product_name, package_label, price FROM orders WHERE order_id=?", (order_id,))
    p_name, label, price = cursor.fetchone()
    conn.commit()
    conn.close()
    
    del admin_state[chat_id]
    bot.send_message(chat_id, "⏳ আপনার ট্রানজেকশন আইডিটি অ্যাডমিনের কাছে পাঠানো হয়েছে। অনুগ্রহ করে ভেরিফিকেশন সম্পন্ন হওয়া পর্যন্ত অপেক্ষা করুন।")
    
    # অ্যাডমিনকে নোটিফিকেশন পাঠানো
    markup_adm = InlineKeyboardMarkup()
    markup_adm.add(InlineKeyboardButton("✅ Approve", callback_data=f"adm_approve_{order_id}"),
                   InlineKeyboardButton("❌ Reject", callback_data=f"adm_reject_{order_id}"))
    
    bot.send_message(ADMIN_ID, f"🔔 *নতুন পেমেন্ট রিকোয়েস্ট এসেছে!*\n\n👤 কাস্টমার: {msg.from_user.first_name}\n🖥️ সফটওয়্যার: {p_name}\n🎯 প্যাকেজ: {label}\n💰 মূল্য: {price} টাকা\n🔑 TxID: `{txid}`", parse_mode='Markdown', reply_markup=markup_adm)

# ডিভাইস আইডি প্রসেস
def process_user_device_id(msg, order_id):
    chat_id = msg.chat.id
    device_id = msg.text.strip().upper()

    conn = sqlite3.connect('sk_tools_v2.db')
    cursor = conn.cursor()
    cursor.execute("S        'device': device_id,
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
    
