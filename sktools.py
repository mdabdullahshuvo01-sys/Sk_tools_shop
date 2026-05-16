# ============================================================
# SK Tools Shop — Fixed for Render Deployment
# ============================================================
import telebot
import requests
import random
import string
import sqlite3
import threading
import os
import time
import logging
from flask import Flask
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = "8944774594:AAG2CtEfzZWN0dPC-0UhsijjApYpVAZS_qw"
ADMIN_ID  = 7865823978

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask('')

admin_state = {}

# ──────────────────────────────────────────────
# ডাটাবেজ
# ──────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect('sk_tools.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, download_link TEXT, license_api_url TEXT, admin_secret TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER, label TEXT, days INTEGER, price INTEGER,
        FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY, chat_id INTEGER, user_name TEXT,
        product_id INTEGER, product_name TEXT, package_label TEXT,
        days INTEGER, price INTEGER, txid TEXT, status TEXT,
        device_id TEXT, license_key TEXT, timestamp TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('payment_info', 'বিকাশ পার্সোনাল: ০১৭XXXXXXXX\nনগদ পার্সোনাল: ০১৮XXXXXXXX\n\nটাকা পাঠানোর পর TxID নিচে দিন।')")
    conn.commit()
    conn.close()
    logger.info("Database ready.")

init_db()

def get_setting(key):
    conn = sqlite3.connect('sk_tools.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else ""

def call_custom_license_api(api_url, secret, device_id, days):
    chars = string.ascii_uppercase + string.digits
    key = f"SK-{''.join(random.choices(chars, k=5))}-{''.join(random.choices(chars, k=5))}"
    expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    try:
        r = requests.post(api_url, data={'action':'add','admin_secret':secret,'key':key,'device':device_id,'expiry':expiry}, timeout=15)
        res = r.json()
        if res.get('status') == 'success':
            return res.get('key', key)
    except Exception as e:
        logger.error(f"License API: {e}")
    return key

# ──────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    chat_id = msg.chat.id
    markup = InlineKeyboardMarkup(row_width=1)
    conn = sqlite3.connect('sk_tools.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM products")
    products = cursor.fetchall()
    conn.close()

    if products:
        for p in products:
            markup.add(InlineKeyboardButton(f"🖥️ {p[1]}", callback_data=f"usr_view_{p[0]}"))
    if chat_id == ADMIN_ID:
        markup.add(InlineKeyboardButton("⭐ অ্যাডমিন প্যানেল ⭐", callback_data="adm_panel"))

    if not products and chat_id != ADMIN_ID:
        bot.send_message(chat_id, "🛒 বর্তমানে কোনো সফটওয়্যার নেই।")
        return

    bot.send_message(chat_id,
        f"👋 *স্বাগতম {msg.from_user.first_name}!*\n\n🚀 *SK Tools Shop* — পছন্দের অ্যাপ কিনতে ক্লিক করুন:",
        parse_mode='Markdown', reply_markup=markup)

# ──────────────────────────────────────────────
# অ্যাডমিন callbacks
# ──────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    chat_id = call.message.chat.id
    if chat_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ অ্যাক্সেস নেই!")
        return

    data = call.data

    if data == "adm_panel":
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("➕ নতুন সফটওয়্যার অ্যাড", callback_data="adm_add_product"),
            InlineKeyboardButton("📦 প্রোডাক্ট লিস্ট ও ডিলিট", callback_data="adm_list_products"),
            InlineKeyboardButton("📊 সেলস রিপোর্ট", callback_data="adm_sales_report"),
            InlineKeyboardButton("⚙️ বিকাশ/নগদ সেটিংস", callback_data="adm_wallet_settings"),
            InlineKeyboardButton("⬅️ ইউজার মেনু", callback_data="adm_back_to_user"))
        try:
            bot.edit_message_text("🛠️ *Admin Panel — SK Tools Shop*", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
        except:
            bot.send_message(chat_id, "🛠️ *Admin Panel*", parse_mode='Markdown', reply_markup=markup)

    elif data == "adm_back_to_user":
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        cmd_start(call.message)

    elif data == "adm_add_product":
        bot.edit_message_text("📝 সফটওয়্যারের *নাম* লিখুন:", chat_id, call.message.message_id, parse_mode='Markdown')
        admin_state[chat_id] = {"step": "add_name", "packages": []}

    elif data == "adm_wallet_settings":
        info = get_setting("payment_info")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📝 আপডেট করুন", callback_data="adm_change_wallet"))
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text(f"⚙️ *পেমেন্ট তথ্য:*\n\n{info}", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data == "adm_change_wallet":
        bot.edit_message_text("✍️ নতুন পেমেন্ট তথ্য লিখুন:", chat_id, call.message.message_id)
        admin_state[chat_id] = {"step": "change_wallet"}

    elif data == "adm_list_products":
        conn = sqlite3.connect('sk_tools.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM products")
        prods = cursor.fetchall()
        conn.close()
        markup = InlineKeyboardMarkup(row_width=1)
        for p in prods:
            markup.add(InlineKeyboardButton(f"❌ ডিলিট: {p[1]}", callback_data=f"adm_del_{p[0]}"))
        if not prods:
            markup.add(InlineKeyboardButton("(কোনো প্রোডাক্ট নেই)", callback_data="adm_panel"))
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text("📦 প্রোডাক্ট লিস্ট:", chat_id, call.message.message_id, reply_markup=markup)

    elif data.startswith("adm_del_"):
        p_id = data.replace("adm_del_", "")
        conn = sqlite3.connect('sk_tools.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id=?", (p_id,))
        cursor.execute("DELETE FROM packages WHERE product_id=?", (p_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ ডিলিট হয়েছে!")
        conn = sqlite3.connect('sk_tools.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM products")
        prods = cursor.fetchall()
        conn.close()
        markup = InlineKeyboardMarkup(row_width=1)
        for p in prods:
            markup.add(InlineKeyboardButton(f"❌ ডিলিট: {p[1]}", callback_data=f"adm_del_{p[0]}"))
        if not prods:
            markup.add(InlineKeyboardButton("(কোনো প্রোডাক্ট নেই)", callback_data="adm_panel"))
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text("📦 প্রোডাক্ট লিস্ট:", chat_id, call.message.message_id, reply_markup=markup)
        return

    elif data == "adm_sales_report":
        conn = sqlite3.connect('sk_tools.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(price) FROM orders WHERE status='COMPLETED'")
        total_sales, total_earnings = cursor.fetchone()
        total_earnings = total_earnings or 0
        cursor.execute("SELECT user_name, product_name, price, timestamp FROM orders WHERE status='COMPLETED' ORDER BY timestamp DESC LIMIT 5")
        recent = cursor.fetchall()
        conn.close()
        text = f"📊 *সেলস রিপোর্ট:*\n\n💰 আয়: `{total_earnings}` টাকা\n📦 বিক্রি: `{total_sales}` টি\n\n📋 *সর্বশেষ ৫টি:*\n"
        for o in recent:
            text += f"👤 {o[0]} ➔ {o[1]} (`{o[2]}tk`) {o[3]}\n"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ ব্যাক", callback_data="adm_panel"))
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data.startswith("adm_approve_") or data.startswith("adm_reject_"):
        parts = data.split("_")
        action = parts[1]
        order_id = parts[2]
        conn = sqlite3.connect('sk_tools.db')
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, product_id, product_name, package_label, status FROM orders WHERE order_id=?", (order_id,))
        order = cursor.fetchone()
        if not order or order[4] != "PENDING_APPROVAL":
            bot.answer_callback_query(call.id, "⚠️ ইতিমধ্যে প্রসেস হয়েছে।")
            conn.close()
            return
        usr_chat_id, p_id, p_name, pkg_label, _ = order
        if action == "approve":
            cursor.execute("UPDATE orders SET status='PAID' WHERE order_id=?", (order_id,))
            cursor.execute("SELECT download_link FROM products WHERE id=?", (p_id,))
            link_res = cursor.fetchone()
            download_link = link_res[0] if link_res else ""
            conn.commit()
            conn.close()
            markup_usr = InlineKeyboardMarkup()
            if download_link:
                markup_usr.add(InlineKeyboardButton("📥 Download Software", url=download_link))
            markup_usr.add(InlineKeyboardButton("📱 Submit Device ID", callback_data=f"dev_{order_id}"))
            bot.send_message(usr_chat_id,
                f"✅ *পেমেন্ট ভেরিফাইড!*\n\n🚀 *{p_name} ({pkg_label})*\n\nসফটওয়্যার ডাউনলোড করে Device ID সাবমিট করুন।",
                parse_mode='Markdown', reply_markup=markup_usr)
            try:
                bot.edit_message_text(f"✅ অর্ডার `{order_id}` অ্যাপ্রুভ!", chat_id, call.message.message_id, parse_mode='Markdown')
            except:
                pass
        else:
            cursor.execute("UPDATE orders SET status='REJECTED' WHERE order_id=?", (order_id,))
            conn.commit()
            conn.close()
            bot.send_message(usr_chat_id, "❌ TxID ম্যাচ করেনি। পেমেন্ট বাতিল।")
            try:
                bot.edit_message_text(f"❌ অর্ডার `{order_id}` রিজেক্ট!", chat_id, call.message.message_id, parse_mode='Markdown')
            except:
                pass

    bot.answer_callback_query(call.id)

# ──────────────────────────────────────────────
# অ্যাডমিন text input
# ──────────────────────────────────────────────
@bot.message_handler(func=lambda msg: msg.chat.id == ADMIN_ID and msg.chat.id in admin_state)
def handle_admin_inputs(msg):
    chat_id = msg.chat.id
    state = admin_state.get(chat_id, {})
    step = state.get("step")

    if step == "add_name":
        state["name"] = msg.text.strip()
        bot.send_message(chat_id, "📥 *Download Link* দিন:", parse_mode='Markdown')
        state["step"] = "add_link"
    elif step == "add_link":
        state["link"] = msg.text.strip()
        bot.send_message(chat_id, "🔗 *License API URL* দিন:", parse_mode='Markdown')
        state["step"] = "add_api_url"
    elif step == "add_api_url":
        state["api_url"] = msg.text.strip()
        bot.send_message(chat_id, "🔑 *Admin Secret Key* দিন:", parse_mode='Markdown')
        state["step"] = "add_secret"
    elif step == "add_secret":
        state["secret"] = msg.text.strip()
        bot.send_message(chat_id, "🎯 প্যাকেজ যোগ করুন।\n*ফরম্যাট:* `নাম,দিন`\nউদাহরণ: `৩০ দিন মেয়াদী,30`", parse_mode='Markdown')
        state["step"] = "add_pkg_label"
    elif step == "add_pkg_label":
        try:
            label, days = msg.text.split(",")
            state["current_pkg_label"] = label.strip()
            state["current_pkg_days"] = int(days.strip())
            bot.send_message(chat_id, f"💰 *'{label.strip()}'* এর দাম কত টাকা?", parse_mode='Markdown')
            state["step"] = "add_pkg_price"
        except:
            bot.send_message(chat_id, "❌ ফরম্যাট ভুল! উদাহরণ: `৩০ দিন মেয়াদী,30`", parse_mode='Markdown')
    elif step == "add_pkg_price":
        if not msg.text.strip().isdigit():
            bot.send_message(chat_id, "❌ শুধু সংখ্যা লিখুন:")
            return
        price = int(msg.text.strip())
        state["packages"].append({"label": state["current_pkg_label"], "days": state["current_pkg_days"], "price": price})
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ আরও প্যাকেজ", callback_data="p_add_more"))
        markup.add(InlineKeyboardButton("✅ সেভ করুন", callback_data="p_save_final"))
        bot.send_message(chat_id, f"✅ {state['current_pkg_label']} = {price} টাকা যুক্ত হয়েছে।\nআরও প্যাকেজ?", reply_markup=markup)
    elif step == "change_wallet":
        conn = sqlite3.connect('sk_tools.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value=? WHERE key='payment_info'", (msg.text.strip(),))
        conn.commit()
        conn.close()
        bot.send_message(chat_id, "✅ পেমেন্ট তথ্য আপডেট হয়েছে।")
        del admin_state[chat_id]

@bot.callback_query_handler(func=lambda call: call.data in ["p_add_more", "p_save_final"])
def handle_pkg_buttons(call):
    chat_id = call.message.chat.id
    if chat_id != ADMIN_ID or chat_id not in admin_state:
        return
    state = admin_state[chat_id]
    if call.data == "p_add_more":
        bot.edit_message_text("🎯 পরবর্তী প্যাকেজ:\n*ফরম্যাট:* `নাম,দিন`", chat_id, call.message.message_id, parse_mode='Markdown')
        state["step"] = "add_pkg_label"
    elif call.data == "p_save_final":
        conn = sqlite3.connect('sk_tools.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (name, download_link, license_api_url, admin_secret) VALUES (?, ?, ?, ?)",
                       (state["name"], state["link"], state["api_url"], state["secret"]))
        p_id = cursor.lastrowid
        for pkg in state["packages"]:
            cursor.execute("INSERT INTO packages (product_id, label, days, price) VALUES (?, ?, ?, ?)",
                           (p_id, pkg["label"], pkg["days"], pkg["price"]))
        conn.commit()
        conn.close()
        bot.edit_message_text(f"🎉 *'{state['name']}' — {len(state['packages'])}টি প্যাকেজসহ সেভ হয়েছে!*", chat_id, call.message.message_id, parse_mode='Markdown')
        del admin_state[chat_id]
    bot.answer_callback_query(call.id)

# ──────────────────────────────────────────────
# ইউজার callbacks
# ──────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("usr_") or call.data.startswith("dev_"))
def user_callbacks(call):
    chat_id = call.message.chat.id
    data = call.data

    if data == "usr_main":
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        cmd_start(call.message)

    elif data.startswith("usr_view_"):
        p_id = data.replace("usr_view_", "")
        conn = sqlite3.connect('sk_tools.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM products WHERE id=?", (p_id,))
        row = cursor.fetchone()
        if not row:
            bot.answer_callback_query(call.id, "পাওয়া যায়নি!")
            conn.close()
            return
        p_name = row[0]
        cursor.execute("SELECT id, label, price FROM packages WHERE product_id=?", (p_id,))
        pkgs = cursor.fetchall()
        conn.close()
        markup = InlineKeyboardMarkup(row_width=1)
        for pkg in pkgs:
            markup.add(InlineKeyboardButton(f"💳 {pkg[1]} — {pkg[2]} টাকা", callback_data=f"usr_buy_{pkg[0]}"))
        markup.add(InlineKeyboardButton("⬅️ মেইন মেনু", callback_data="usr_main"))
        bot.edit_message_text(f"📦 *{p_name}* — প্যাকেজ সিলেক্ট করুন:", chat_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    elif data.startswith("usr_buy_"):
        pkg_id = data.replace("usr_buy_", "")
        conn = sqlite3.connect('sk_tools.db')
        cursor = conn.cursor()
        cursor.execute("SELECT product_id, label, days, price FROM packages WHERE id=?", (pkg_id,))
        row = cursor.fetchone()
        if not row:
            bot.answer_callback_query(call.id, "পাওয়া যায়নি!")
            conn.close()
            return
        p_id, label, days, price = row
        cursor.execute("SELECT name FROM products WHERE id=?", (p_id,))
        p_name = cursor.fetchone()[0]
        conn.close()
        order_id = f"SK{random.randint(10000, 99999)}"
        conn = sqlite3.connect('sk_tools.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (order_id, chat_id, user_name, product_id, product_name, package_label, days, price, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_TXID', ?)",
            (order_id, chat_id, call.from_user.first_name, p_id, p_name, label, days, price, datetime.now().strftime('%Y-%m-%d %H:%M')))
        conn.commit()
        conn.close()
        pmnt_info = get_setting("payment_info")
        bot.edit_message_text(
            f"🛒 *অর্ডার সামারি:*\n🖥️ {p_name}\n🎯 {label}\n💰 {price} টাকা\n\n💵 *পেমেন্ট নিয়ম:*\n{pmnt_info}\n\n✅ পেমেন্ট করে TxID পাঠান:",
            chat_id, call.message.message_id, parse_mode='Markdown')
        admin_state[chat_id] = {"step": "submit_txid", "order_id": order_id}

    elif data.startswith("dev_"):
        order_id = data.replace("dev_", "")
        msg = bot.send_message(chat_id, "📱 অ্যাপ থেকে *Device ID* পাঠান:", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_user_device_id, order_id)

    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.chat.id in admin_state and admin_state[msg.chat.id].get("step") == "submit_txid")
def handle_user_txid(msg):
    chat_id = msg.chat.id
    txid = msg.text.strip().upper()
    order_id = admin_state[chat_id]["order_id"]
    conn = sqlite3.connect('sk_tools.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET txid=?, status='PENDING_APPROVAL' WHERE order_id=?", (txid, order_id))
    cursor.execute("SELECT product_name, package_label, price FROM orders WHERE order_id=?", (order_id,))
    p_name, label, price = cursor.fetchone()
    conn.commit()
    conn.close()
    del admin_state[chat_id]
    bot.send_message(chat_id, "⏳ TxID পাঠানো হয়েছে। ভেরিফিকেশনের জন্য অপেক্ষা করুন।")
    markup_adm = InlineKeyboardMarkup()
    markup_adm.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"adm_approve_{order_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"adm_reject_{order_id}"))
    bot.send_message(ADMIN_ID,
        f"🔔 *নতুন পেমেন্ট রিকোয়েস্ট!*\n\n👤 {msg.from_user.first_name}\n🖥️ {p_name}\n🎯 {label}\n💰 {price} টাকা\n🔑 TxID: `{txid}`",
        parse_mode='Markdown', reply_markup=markup_adm)

def process_user_device_id(msg, order_id):
    chat_id = msg.chat.id
    device_id = msg.text.strip().upper()
    conn = sqlite3.connect('sk_tools.db')
    cursor = conn.cursor()
    cursor.execute("SELECT product_id, days, status FROM orders WHERE order_id=?", (order_id,))
    order = cursor.fetchone()
    if not order or order[2] != "PAID":
        bot.send_message(chat_id, "❌ অর্ডার পাওয়া যায়নি বা পেমেন্ট ভেরিফাইড হয়নি।")
        conn.close()
        return
    p_id, days, _ = order
    c
