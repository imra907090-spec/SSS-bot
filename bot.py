import asyncio
import io
import re
import json
import html
import os
import httpx
import pyotp
import random
import string
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# ==================== CONFIG SECTION ====================

BOT_TOKEN = "8931384031:AAElSwSOL_CQdShaUgvwEBenkdmJPkiXZUc"
API_KEY = "api_key_by_mino"
BASE_URL = "https://mino-sms-panel.xyz"
USER_DATA_FILE = "users.json"
PAID_SMS_FILE = "paid_sms.json"
STATS_FILE = "user_stats.json"
REFERRAL_DATA_FILE = "referral_data.json"
BANNED_USERS_FILE = "banned_users.json"
WITHDRAW_DATA_FILE = "withdraw_requests.json"
ACTIVITY_LOGS_FILE = "activity_logs.json"
DATA_RANGE_FILE = "datarange.json"
CUSTOM_SERVICES_FILE = "custom_services.json"

# ==================== MULTIPLE ADMINS CONFIGURATION ====================
ADMINS = [8273597769]

OTP_GROUP_ID = -1003698770950

# ==================== WELCOME MESSAGE CONFIGURATION ====================
WELCOME_MESSAGE = """⚡ 𝗠𝗜𝗡𝗢 𝗦𝗠𝗦 𝗣𝗔𝗡𝗘𝗟 𝗕𝗢𝗧 ⚡ 
━━━━━━━━━━━━━━━━━━━━━━
🟢 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 & ⚡ 𝗙𝗮𝘀𝘁 𝗦𝗲𝗿𝘃𝗶𝗰𝗲 🟢"""

# ==================== OTP RATE CONFIGURATION ====================
OTP_RATE = 0.00

# ==================== REFERRAL / WITHDRAW CONFIGURATION ====================
REFERRAL_PRICE = 0
MIN_WITHDRAW = 50
MAX_WITHDRAW = 10000

# ==================== SUPPORT LINK (EDITABLE) ====================
SUPPORT_LINK = "https://t.me/MinoXSupport0"

request_queue = asyncio.Queue()
MAX_WORKERS = 50000000000000000000000000000

client_async = httpx.AsyncClient(
    http2=True,
    timeout=httpx.Timeout(connect=3.0, read=30.0, write=5.0, pool=15.0),
    headers={
        "X-API-Key": API_KEY,
        "api-key": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Connection": "keep-alive"
    },
    limits=httpx.Limits(max_connections=3000, max_keepalive_connections=1000)
)

active_numbers = {}
last_range = {}
CHECK_INTERVAL = 0.2

# ==================== HELPERS SECTION ====================

def get_bangladesh_time():
    return datetime.utcnow() + timedelta(hours=6)

def normalize_number(number):
    if not number:
        return ""
    return re.sub(r'\D', '', str(number))

def mask_number(number):
    num_str = str(number)
    if len(num_str) <= 6:
        return num_str
    return num_str[:4] + "****" + num_str[-2:]

def is_valid_bangladesh_number(number):
    clean = re.sub(r'\D', '', str(number))
    if len(clean) == 11 and clean.startswith("01"):
        return True
    if len(clean) == 13 and clean.startswith("8801"):
        return True
    return False

def format_balance(balance):
    try:
        return f"{float(balance):.2f}"
    except:
        return "0.00"

def get_date_reset_time():
    bd_now = get_bangladesh_time()
    return datetime(bd_now.year, bd_now.month, bd_now.day)

def is_range_request(param):
    if re.match(r'^\d+[xX]+$', str(param)):
        return True
    return False

def is_referral_request(param):
    if str(param).isdigit():
        return True
    return False

def extract_link_and_otp(full_sms):
    if not full_sms:
        return None, None
    otp_match = re.search(r'\b\d{4,8}\b', full_sms)
    otp = otp_match.group(0) if otp_match else None
    link_match = re.search(r'https?://[^\s]+', full_sms)
    link = link_match.group(0) if link_match else None
    return otp, link

def numbers_match(num1, num2):
    n1 = re.sub(r'\D', '', str(num1))
    n2 = re.sub(r'\D', '', str(num2))
    if not n1 or not n2:
        return False
    return n1 in n2 or n2 in n1

# ==================== TEXT BOLD / STYLIZED UNICODE HELPER ====================

def make_bold_unicode(text):
    out = []
    for char in text:
        codepoint = ord(char)
        if 65 <= codepoint <= 90:
            out.append(chr(codepoint - 65 + 0x1D5D4))
        elif 97 <= codepoint <= 122:
            out.append(chr(codepoint - 97 + 0x1D5EE))
        elif 48 <= codepoint <= 57:
            out.append(chr(codepoint - 48 + 0x1D7EC))
        else:
            out.append(char)
    return "".join(out)

def normalize_stylized_text(text):
    if not text:
        return ""
    out = []
    for char in text:
        cp = ord(char)
        if 0x1D5D4 <= cp <= 0x1D5ED:
            out.append(chr(cp - 0x1D5D4 + 65))
        elif 0x1D5EE <= cp <= 0x1D607:
            out.append(chr(cp - 0x1D5EE + 97))
        elif 0x1D7EC <= cp <= 0x1D7F5:
            out.append(chr(cp - 0x1D7EC + 48))
        else:
            out.append(char)
    return "".join(out)

def clean_country_display(val):
    if not val:
        return ""
    return re.sub(r'\s+', ' ', str(val)).strip().lower()

# ==================== CHECK IF USER IS ADMIN ====================

def is_admin(user_id):
    return user_id in ADMINS

# ==================== WITHDRAW DATA FUNCTIONS ====================

def load_withdraw_requests():
    if not os.path.exists(WITHDRAW_DATA_FILE):
        with open(WITHDRAW_DATA_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(WITHDRAW_DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_withdraw_requests(data):
    with open(WITHDRAW_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def generate_payment_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))

# ==================== BANNED USERS FUNCTIONS ====================

def load_banned_users():
    if not os.path.exists(BANNED_USERS_FILE):
        with open(BANNED_USERS_FILE, "w") as f:
            json.dump([], f)
        return []
    try:
        with open(BANNED_USERS_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_banned_users(banned_list):
    with open(BANNED_USERS_FILE, "w") as f:
        json.dump(banned_list, f, indent=4)

def is_user_banned(uid):
    banned_list = load_banned_users()
    return str(uid) in banned_list

def ban_user(uid):
    banned_list = load_banned_users()
    uid_str = str(uid)
    if uid_str not in banned_list:
        banned_list.append(uid_str)
        save_banned_users(banned_list)
        return True
    return False

def unban_user(uid):
    banned_list = load_banned_users()
    uid_str = str(uid)
    if uid_str in banned_list:
        banned_list.remove(uid_str)
        save_banned_users(banned_list)
        return True
    return False

# ==================== REFERRAL DATA FUNCTIONS ====================

def load_referral_data():
    if not os.path.exists(REFERRAL_DATA_FILE):
        with open(REFERRAL_DATA_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(REFERRAL_DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_referral_data(data):
    with open(REFERRAL_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def update_referral_count(uid, count):
    referral_data = load_referral_data()
    uid_str = str(uid)
    if uid_str not in referral_data:
        referral_data[uid_str] = {"referral_count": 0}
    referral_data[uid_str]["referral_count"] = count
    save_referral_data(referral_data)

def get_referral_count(uid):
    referral_data = load_referral_data()
    uid_str = str(uid)
    return referral_data.get(uid_str, {}).get("referral_count", 0)

# ==================== DATA RANGE FILE ====================

def load_range_db():
    if not os.path.exists(DATA_RANGE_FILE):
        return {}
    try:
        with open(DATA_RANGE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_range_db(data):
    with open(DATA_RANGE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_number_range_info(uid, number, range_text):
    db = load_range_db()
    flag, name = get_country_info(number)
    db[normalize_number(number)] = {
        "user_id": str(uid),
        "number": f"+{normalize_number(number)}",
        "range": range_text,
        "country": f"{flag} {name}"
    }
    save_range_db(db)

# ==================== CUSTOM SERVICE CONFIG ====================

def load_custom_services():
    if not os.path.exists(CUSTOM_SERVICES_FILE):
        with open(CUSTOM_SERVICES_FILE, "w") as f:
            json.dump([], f)
        return []
    try:
        with open(CUSTOM_SERVICES_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_custom_services(data):
    with open(CUSTOM_SERVICES_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ==================== COUNTRY MAPPING SECTION ====================

def get_country_info(number):
    number = str(number).strip()

    country_map = {
        "2376": ("🇨🇲", "Cameroon"),
        "2250": ("🇨🇮", "Ivory Coast"),
        "2613": ("🇲🇬", "Madagascar"),
        "4077": ("🇷🇴", "Romania"),
        "237": ("🇨🇲", "Cameroon"),
        "225": ("🇨🇮", "Ivory Coast"),
        "261": ("🇲🇬", "Madagascar"),
        "20": ("🇪🇬", "Egypt"),
        "27": ("🇿🇦", "South Africa"),
        "234": ("🇳🇬", "Nigeria"),
        "254": ("🇰🇪", "Kenya"),
        "233": ("🇬🇭", "Ghana"),
        "212": ("🇲🇦", "Morocco"),
        "213": ("🇩🇿", "Algeria"),
        "216": ("🇹🇳", "Tunisia"),
        "218": ("🇱🇾", "Libya"),
        "249": ("🇸🇩", "Sudan"),
        "251": ("🇪🇹", "Ethiopia"),
        "252": ("🇸🇴", "Somalia"),
        "253": ("🇩🇯", "Djibouti"),
        "255": ("🇹🇿", "Tanzania"),
        "256": ("🇺🇬", "Uganda"),
        "257": ("🇧🇮", "Burundi"),
        "258": ("🇲🇿", "Mozambique"),
        "260": ("🇿🇲", "Zambia"),
        "263": ("🇿🇼", "Zimbabwe"),
        "264": ("🇳🇦", "Namibia"),
        "265": ("🇲🇼", "Malawi"),
        "266": ("🇱🇸", "Lesotho"),
        "267": ("🇧🇼", "Botswana"),
        "268": ("🇸🇿", "Swaziland"),
        "269": ("🇰🇲", "Comoros"),
        "220": ("🇬🇲", "Gambia"),
        "221": ("🇸🇳", "Senegal"),
        "222": ("🇲🇷", "Mauritania"),
        "223": ("🇲🇱", "Mali"),
        "224": ("🇬🇳", "Guinea"),
        "226": ("🇧🇫", "Burkina Faso"),
        "227": ("🇳🇪", "Niger"),
        "228": ("🇹🇬", "Togo"),
        "229": ("🇧🇯", "Benin"),
        "230": ("🇲🇺", "Mauritius"),
        "231": ("🇱🇷", "Liberia"),
        "232": ("🇸🇱", "Sierra Leone"),
        "235": ("🇹🇩", "Chad"),
        "236": ("🇨🇫", "Central African Republic"),
        "238": ("🇨🇻", "Cape Verde"),
        "239": ("🇸🇹", "Sao Tome and Principe"),
        "240": ("🇬🇶", "Equatorial Guinea"),
        "241": ("🇬🇦", "Gabon"),
        "242": ("🇨🇬", "Congo"),
        "243": ("🇨🇩", "DR Congo"),
        "244": ("🇦🇴", "Angola"),
        "245": ("🇬🇼", "Guinea-Bissau"),
        "247": ("🇸🇭", "Saint Helena"),
        "248": ("🇸🇨", "Seychelles"),
        "250": ("🇷🇼", "Rwanda"),
        "290": ("🇸🇭", "Saint Helena"),
        "291": ("🇪🇷", "Eritrea"),
        "40": ("🇷🇴", "Romania"),
        "44": ("🇬🇧", "United Kingdom"),
        "33": ("🇫🇷", "France"),
        "49": ("🇩🇪", "Germany"),
        "39": ("🇮🇹", "Italy"),
        "34": ("🇪🇸", "Spain"),
        "31": ("🇳🇱", "Netherlands"),
        "32": ("🇧🇪", "Belgium"),
        "41": ("🇨🇭", "Switzerland"),
        "43": ("🇦🇹", "Austria"),
        "46": ("🇸🇪", "Sweden"),
        "47": ("🇳🇴", "Norway"),
        "45": ("🇩🇰", "Denmark"),
        "358": ("🇫🇮", "Finland"),
        "351": ("🇵🇹", "Portugal"),
        "353": ("🇮🇪", "Ireland"),
        "36": ("🇭🇺", "Hungary"),
        "48": ("🇵🇱", "Poland"),
        "380": ("🇺🇦", "Ukraine"),
        "370": ("🇱🇹", "Lithuania"),
        "371": ("🇱🇻", "Latvia"),
        "372": ("🇪🇪", "Estonia"),
        "373": ("🇲🇩", "Moldova"),
        "374": ("🇦🇲", "Armenia"),
        "375": ("🇧🇾", "Belarus"),
        "376": ("🇦🇩", "Andorra"),
        "377": ("🇲🇨", "Monaco"),
        "381": ("🇷🇸", "Serbia"),
        "382": ("🇲🇪", "Montenegro"),
        "385": ("🇭🇷", "Croatia"),
        "386": ("🇸🇮", "Slovenia"),
        "387": ("🇧🇦", "Bosnia and Herzegovina"),
        "389": ("🇲🇰", "North Macedonia"),
        "350": ("🇬🇮", "Gibraltar"),
        "352": ("🇱🇺", "Luxembourg"),
        "354": ("🇮🇸", "Iceland"),
        "355": ("🇦🇱", "Albania"),
        "356": ("🇲🇹", "Malta"),
        "357": ("🇨🇾", "Cyprus"),
        "359": ("🇧🇬", "Bulgaria"),
        "421": ("🇸🇰", "Slovakia"),
        "420": ("🇨🇿", "Czech Republic"),
        "298": ("🇫🇴", "Faroe Islands"),
        "299": ("🇬🇱", "Greenland"),
        "1": ("🇺🇸", "United States"),
        "7": ("🇷🇺", "Russia"),
        "91": ("🇮🇳", "India"),
        "92": ("🇵🇰", "Pakistan"),
        "880": ("🇧🇩", "Bangladesh"),
        "86": ("🇨🇳", "China"),
        "81": ("🇯🇵", "Japan"),
        "82": ("🇰🇷", "South Korea"),
        "84": ("🇻🇳", "Vietnam"),
        "66": ("🇹🇭", "Thailand"),
        "62": ("🇮🇩", "Indonesia"),
        "60": ("🇲🇾", "Malaysia"),
        "65": ("🇸🇬", "Singapore"),
        "63": ("🇵🇭", "Philippines"),
        "95": ("🇲🇲", "Myanmar"),
        "94": ("🇱🇰", "Sri Lanka"),
        "977": ("🇳🇵", "Nepal"),
        "93": ("🇦🇫", "Afghanistan"),
        "98": ("🇮🇷", "Iran"),
        "90": ("🇹🇷", "Turkey"),
        "964": ("🇮🇶", "Iraq"),
        "963": ("🇸🇾", "Syria"),
        "961": ("🇱🇧", "Lebanon"),
        "962": ("🇯🇴", "Jordan"),
        "965": ("🇰🇼", "Kuwait"),
        "966": ("🇸🇦", "Saudi Arabia"),
        "967": ("🇾🇪", "Yemen"),
        "968": ("🇴🇲", "Oman"),
        "971": ("🇦🇪", "United Arab Emirates"),
        "972": ("🇮🇱", "Israel"),
        "973": ("🇧🇭", "Bahrain"),
        "974": ("🇶🇦", "Qatar"),
        "994": ("🇦🇿", "Azerbaijan"),
        "995": ("🇬🇪", "Georgia"),
        "996": ("🇰🇬", "Kyrgyzstan"),
        "992": ("🇹🇯", "Tajikistan"),
        "993": ("🇹🇲", "Turkmenistan"),
        "998": ("🇺🇿", "Uzbekistan"),
        "855": ("🇰🇭", "Cambodia"),
        "856": ("🇱🇦", "Laos"),
        "976": ("🇲🇳", "Mongolia"),
        "850": ("🇰🇵", "North Korea"),
        "55": ("🇧🇷", "Brazil"),
        "52": ("🇲🇽", "Mexico"),
        "54": ("🇦🇷", "Argentina"),
        "57": ("🇨🇴", "Colombia"),
        "51": ("🇵🇪", "Peru"),
        "58": ("🇻🇪", "Venezuela"),
        "56": ("🇨🇱", "Chile"),
        "593": ("🇪🇨", "Ecuador"),
        "591": ("🇧🇴", "Bolivia"),
        "595": ("🇵🇾", "Paraguay"),
        "598": ("🇺🇾", "Uruguay"),
        "502": ("🇬🇹", "Guatemala"),
        "503": ("🇸🇻", "El Salvador"),
        "504": ("🇭🇳", "Honduras"),
        "506": ("🇨🇷", "Costa Rica"),
        "507": ("🇵🇦", "Panama"),
        "509": ("🇭🇹", "Haiti"),
        "501": ("🇧🇿", "Belize"),
        "61": ("🇦🇺", "Australia"),
        "64": ("🇳🇿", "New Zealand"),
        "675": ("🇵🇬", "Papua New Guinea"),
        "679": ("🇫🇯", "Fiji"),
        "1246": ("🇧🇧", "Barbados"),
        "1876": ("🇯🇲", "Jamaica"),
        "53": ("🇨🇺", "Cuba"),
        "592": ("🇬🇾", "Guyana"),
    }

    clean_num = str(number).replace('+', '').replace(' ', '').replace('-', '').strip()
    sorted_prefixes = sorted(country_map.keys(), key=len, reverse=True)

    for prefix in sorted_prefixes:
        if clean_num.startswith(prefix):
            return country_map[prefix]

    return ("🌍", "Unknown")

# ==================== SERVICE DETECTION SECTION ====================

def detect_service(full_sms):
    if not full_sms:
        return "SMS SERVICE"

    sms_lower = full_sms.lower()

    service_keywords = {
        "facebook": "FACEBOOK", "fb": "FACEBOOK",
        "instagram": "INSTAGRAM", "insta": "INSTAGRAM",
        "tiktok": "TIKTOK",
        "twitter": "TWITTER", "x.com": "TWITTER",
        "snapchat": "SNAPCHAT", "snap": "SNAPCHAT",
        "whatsapp": "WHATSAPP",
        "telegram": "TELEGRAM",
        "discord": "DISCORD",
        "messenger": "MESSENGER",
        "linkedin": "LINKEDIN",
        "google": "GOOGLE", "gmail": "GOOGLE",
        "amazon": "AMAZON",
        "microsoft": "MICROSOFT", "outlook": "MICROSOFT",
        "yahoo": "YAHOO",
        "paypal": "PAYPAL",
        "binance": "BINANCE",
        "coinbase": "COINBASE",
        "spotify": "SPOTIFY",
        "netflix": "NETFLIX",
        "uber": "UBER",
        "apple": "APPLE", "icloud": "APPLE",
        "bkash": "BKASH",
        "nagad": "NAGAD",
        "stripe": "STRIPE",
        "line": "LINE",
        "wechat": "WECHAT",
        "viber": "VIBER",
        "signal": "SIGNAL",
        "pubg": "PUBG",
        "free fire": "FREE FIRE",
    }

    for keyword, service_name in sorted(service_keywords.items(), key=lambda x: len(x[0]), reverse=True):
        if keyword in sms_lower:
            return service_name

    return "SMS SERVICE"

# ==================== KEYBOARDS SECTION ====================
# ✅ FIX: সব style="..." প্যারামিটার সরানো হয়েছে

def main_keyboard(user_id):
    keyboard = [
        [KeyboardButton(text=f"📞 {make_bold_unicode('GET NUMBER')}")],
        [
            KeyboardButton(text=f"👥 {make_bold_unicode('REFER AND EARN')}"),
            KeyboardButton(text=f"👤 {make_bold_unicode('PROFILE')}")
        ],
        [KeyboardButton(text=f"🏆 {make_bold_unicode('LEADERBOARD')}")],
        [KeyboardButton(text=f"💬 {make_bold_unicode('SUPPORT')}")]
    ]

    if is_admin(user_id):
        keyboard.append([KeyboardButton(text=f"⚙️ {make_bold_unicode('ADMIN PANEL')} ⚙️")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def cancel_keyboard():
    keyboard = [[KeyboardButton(f"❌ {make_bold_unicode('CANCEL')}")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def withdraw_method_keyboard():
    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton(f"📱 {make_bold_unicode('BKASH')}"), KeyboardButton(f"💵 {make_bold_unicode('NAGAD')}")],
        [KeyboardButton(f"🚀 {make_bold_unicode('ROCKET')}"), KeyboardButton(f"🏦 {make_bold_unicode('BINANCE')}")],
        [KeyboardButton(f"❌ {make_bold_unicode('CANCEL')}")]
    ], resize_keyboard=True)
    return keyboard

# ==================== DYNAMIC SERVICE COLOR MATCHING ====================

def get_service_button_style(service_name):
    return "primary"

# ==================== COMPREHENSIVE INLINE ADMIN PANEL FLOW ====================

def get_grouped_countries_for_service(service):
    grouped = {}
    for r in service.get("ranges", []):
        r_text = r.get("range", "")
        country_display = r.get("country", "")
        
        match = re.match(r'^([^\w\s]*)\s*(.*)$', country_display)
        if match:
            flag = match.group(1).strip()
            cname = match.group(2).strip()
        else:
            flag = "🌍"
            cname = "Unknown"
            
        if not cname:
            cname = "Unknown"
            
        if cname not in grouped:
            grouped[cname] = {"flag": flag, "ranges": []}
        if r_text not in grouped[cname]["ranges"]:
            grouped[cname]["ranges"].append(r_text)
    return grouped

def build_admin_main_inline_keyboard():
    buttons = [
        [InlineKeyboardButton(make_bold_unicode("👥 USER MANAGEMENT"), callback_data="adm_menu_user_mgnt")],
        [InlineKeyboardButton(make_bold_unicode("⚙️ SYSTEM CONFIGURATION"), callback_data="adm_menu_sys_config")],
        [InlineKeyboardButton(make_bold_unicode("🛠️ MANAGE SERVICES"), callback_data="manage_svc_back_to_list")],
        [InlineKeyboardButton(make_bold_unicode("🔙 BACK TO MAIN MENU"), callback_data="adm_menu_back_to_main")]
    ]
    return InlineKeyboardMarkup(buttons)

def build_user_management_inline_keyboard():
    buttons = [
        [InlineKeyboardButton(make_bold_unicode("📢 BROADCAST TO ALL"), callback_data="adm_usermgnt_broadcast")],
        [InlineKeyboardButton(make_bold_unicode("🆔 GET ALL USER ID"), callback_data="adm_usermgnt_get_ids")],
        [InlineKeyboardButton(make_bold_unicode("💰 ALL USER BALANCE"), callback_data="adm_usermgnt_all_balance")],
        [InlineKeyboardButton(make_bold_unicode("🔙 BACK"), callback_data="adm_menu_back_to_admin")]
    ]
    return InlineKeyboardMarkup(buttons)

def build_system_config_inline_keyboard():
    buttons = [
        [
            InlineKeyboardButton(make_bold_unicode("📈 SYSTEM STATS"), callback_data="adm_sys_stats"),
            InlineKeyboardButton(make_bold_unicode("👤 USER CHECK"), callback_data="adm_sys_user_check")
        ],
        [
            InlineKeyboardButton(make_bold_unicode("⛔ BAN USER"), callback_data="adm_sys_ban"),
            InlineKeyboardButton(make_bold_unicode("🔓 UNBAN USER"), callback_data="adm_sys_unban")
        ],
        [InlineKeyboardButton(make_bold_unicode("📜 BANNED LIST"), callback_data="adm_sys_banned_list")],
        [
            InlineKeyboardButton(make_bold_unicode("➕ ADD BALANCE"), callback_data="adm_sys_add_bal"),
            InlineKeyboardButton(make_bold_unicode("➖ REMOVE BALANCE"), callback_data="adm_sys_rem_bal")
        ],
        [InlineKeyboardButton(make_bold_unicode("🔙 BACK"), callback_data="adm_menu_back_to_admin")]
    ]
    return InlineKeyboardMarkup(buttons)

def build_manage_services_inline_keyboard():
    custom_svcs = load_custom_services()
    buttons = []
    for s in custom_svcs:
        sid = s.get("sid", "UNKNOWN")
        buttons.append([InlineKeyboardButton(make_bold_unicode(f"📁 {sid.upper()}"), callback_data=f"manage_svc_view_{sid}")])
    buttons.append([InlineKeyboardButton(make_bold_unicode("➕ ADD SERVICE"), callback_data="manage_svc_add")])
    buttons.append([InlineKeyboardButton(make_bold_unicode("🔙 BACK"), callback_data="adm_menu_back_to_admin")])
    return InlineKeyboardMarkup(buttons)

def build_service_detail_keyboard(service_name):
    custom_svcs = load_custom_services()
    target_svc = next((s for s in custom_svcs if s.get("sid", "").upper() == service_name.upper()), None)
    if not target_svc:
        return None
        
    grouped = get_grouped_countries_for_service(target_svc)
    buttons = []
    
    for cname, info in grouped.items():
        flag = info["flag"]
        buttons.append([InlineKeyboardButton(make_bold_unicode(f"{flag} {cname.upper()}"), callback_data=f"manage_svc_country_view_{service_name}_{cname}")])
        
    buttons.append([
        InlineKeyboardButton(make_bold_unicode("➕ ADD RANGE"), callback_data=f"manage_svc_add_range_{service_name}"),
        InlineKeyboardButton(make_bold_unicode("✏️ RENAME"), callback_data=f"manage_svc_rename_init_{service_name}")
    ])
    buttons.append([
        InlineKeyboardButton(make_bold_unicode("🗑️ DELETE SERVICE"), callback_data=f"manage_svc_delete_init_{service_name}")
    ])
    buttons.append([InlineKeyboardButton(make_bold_unicode("🔙 BACK"), callback_data="manage_svc_back_to_list")])
    return InlineKeyboardMarkup(buttons)

def build_country_detail_keyboard(service_name, country_name):
    custom_svcs = load_custom_services()
    target_svc = next((s for s in custom_svcs if s.get("sid", "").upper() == service_name.upper()), None)
    if not target_svc:
        return None
        
    grouped = get_grouped_countries_for_service(target_svc)
    info = grouped.get(country_name, {"flag": "🌍", "ranges": []})
    
    buttons = []
    for r_val in info["ranges"]:
        buttons.append([
            InlineKeyboardButton(make_bold_unicode(f"❌ {r_val}"), callback_data=f"manage_svc_delete_range_{service_name}_{country_name}_{r_val}"),
            InlineKeyboardButton(make_bold_unicode("✏️ EDIT"), callback_data=f"manage_svc_edit_range_init_{service_name}_{country_name}_{r_val}")
        ])
        
    buttons.append([
        InlineKeyboardButton(make_bold_unicode("➕ ADD RANGE"), callback_data=f"manage_svc_add_range_{service_name}_{country_name}"),
        InlineKeyboardButton(make_bold_unicode("✏️ RENAME COUNTRY"), callback_data=f"manage_svc_rename_country_init_{service_name}_{country_name}")
    ])
    buttons.append([InlineKeyboardButton(make_bold_unicode("🗑️ DELETE COUNTRY"), callback_data=f"manage_svc_delete_country_confirm_{service_name}_{country_name}")])
    buttons.append([InlineKeyboardButton(make_bold_unicode("🔙 BACK"), callback_data=f"manage_svc_view_{service_name}")])
    return InlineKeyboardMarkup(buttons)

def get_admin_panel_text():
    users_list = get_all_users()
    users = len(users_list)
    banned = len(load_banned_users())
    
    custom_svcs = load_custom_services()
    total_ranges = sum(len(s.get("ranges", [])) for s in custom_svcs)
    
    stats_data = load_stats()
    total_otps = 0
    for u in stats_data.values():
        total_otps += len(u.get("otps_received", []))
    
    text = (
        "👑 <b>ADMIN CONTROL PANEL</b> 👑\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>REAL-TIME DATABASE STATS</b>\n\n"
        f"👥 <b>Total Users:</b> <code>{users}</code>\n"
        f"📶 <b>Active Ranges:</b> <code>{total_ranges}</code>\n"
        f"🔑 <b>Processed OTPs:</b> <code>{total_otps}</code>\n"
        f"🚫 <b>Banned Accounts:</b> <code>{banned}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💎 <i>Mino X SMS Bot • Live & Operating</i>"
    )
    return text

# ==================== CHAT GUARD AND SAFETY FILTER ====================

def is_state_cancelling_input(text_input):
    if not text_input:
        return False
    clean_text = text_input.strip().upper()
    if clean_text.startswith("/"):
        return True
    
    cancelling_keywords = [
        "👥 USER MANAGEMENT", "⚙️ SYSTEM CONFIGURATION", "🛠️ MANAGE SERVICES",
        "🔙 BACK TO MAIN", "⚙️ ADMIN PANEL ⚙️", "📞 GET NUMBER", "💰 BALANCE",
        "👥 REFER AND EARN", "👤 PROFILE", "🏆 LEADERBOARD", "💬 SUPPORT", "❌ CANCEL"
    ]
    return clean_text in cancelling_keywords

# ==================== DATABASE FUNCTIONS SECTION ====================

def load_data(filename=USER_DATA_FILE):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data, filename=USER_DATA_FILE):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

def get_user(uid):
    uid = str(uid)
    data = load_data()
    if uid not in data:
        data[uid] = {"user_id": uid, "balance": 0.0, "total_numbers": 0, "referral_count": 0}
        save_data(data)
    return data[uid]

async def update_db_balance(uid, amount):
    uid = str(uid)
    data = load_data()
    if uid in data:
        data[uid]["balance"] = round(data[uid].get("balance", 0.0) + amount, 2)
        save_data(data)
        return data[uid]["balance"]
    return 0.0

def get_all_users():
    data = load_data(USER_DATA_FILE)
    return list(data.keys()) if data else []

def user_exists(uid):
    data = load_data(USER_DATA_FILE)
    return str(uid) in data

# ==================== STATS FUNCTIONS SECTION ====================

def load_stats():
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=4)

def add_number_taken(uid, count=1):
    uid = str(uid)
    stats = load_stats()
    if uid not in stats:
        stats[uid] = {"numbers_taken": [], "otps_received": []}
    if "numbers_taken" not in stats[uid]:
        stats[uid]["numbers_taken"] = []
    now = get_bangladesh_time().isoformat()
    for _ in range(count):
        stats[uid]["numbers_taken"].append(now)
    log_global_activity(uid, "NUMBER_TAKEN", {"count": count})
    save_stats(stats)

def add_otp_received(uid):
    uid = str(uid)
    stats = load_stats()
    if uid not in stats:
        stats[uid] = {"numbers_taken": [], "otps_received": []}
    if "otps_received" not in stats[uid]:
        stats[uid]["otps_received"] = []
    stats[uid]["otps_received"].append(get_bangladesh_time().isoformat())
    save_stats(stats)

def get_user_stats(uid):
    uid = str(uid)
    stats = load_stats()
    user_stats = stats.get(uid, {"numbers_taken": [], "otps_received": []})

    now = get_bangladesh_time()
    today_midnight = get_date_reset_time()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    numbers_taken = user_stats.get("numbers_taken", [])
    otps_received = user_stats.get("otps_received", [])

    today_numbers = 0
    today_otps = 0
    last24h_numbers = 0
    last24h_otps = 0
    last7d_numbers = 0
    last7d_otps = 0

    for t in numbers_taken:
        try:
            dt = datetime.fromisoformat(t)
            if dt >= today_midnight: today_numbers += 1
            if dt > last_24h: last24h_numbers += 1
            if dt > last_7d: last7d_numbers += 1
        except:
            continue

    for t in otps_received:
        try:
            dt = datetime.fromisoformat(t)
            if dt >= today_midnight: today_otps += 1
            if dt > last_24h: last24h_otps += 1
            if dt > last_7d: last7d_otps += 1
        except:
            continue

    total_numbers = len(numbers_taken)
    total_otps = len(otps_received)

    return {
        "total_numbers": total_numbers, "total_otps": total_otps,
        "today_numbers": today_numbers, "today_otps": today_otps,
        "last24h_numbers": last24h_numbers, "last24h_otps": last24h_otps,
        "last7d_numbers": last7d_numbers, "last7d_otps": last7d_otps
    }

def log_global_activity(uid, action, details):
    if not os.path.exists(ACTIVITY_LOGS_FILE):
        with open(ACTIVITY_LOGS_FILE, "w") as f:
            json.dump([], f)
    try:
        with open(ACTIVITY_LOGS_FILE, "r") as f:
            logs = json.load(f)
    except:
        logs = []
    now = get_bangladesh_time()
    logs.append({
        "uid": str(uid), "action": action, "details": details,
        "timestamp": now.isoformat(),
        "date": now.strftime("%d/%m/%Y"),
        "time": now.strftime("%H:%M:%S")
    })
    with open(ACTIVITY_LOGS_FILE, "w") as f:
        json.dump(logs, f, indent=4)

def get_global_system_stats():
    stats = load_stats()
    now = get_bangladesh_time()
    today_midnight = datetime(now.year, now.month, now.day)
    last_7d = now - timedelta(days=7)
    total_n = total_o = today_n = today_o = seven_n = seven_o = 0
    for uid in stats:
        u = stats[uid]
        n_list = u.get("numbers_taken", [])
        o_list = u.get("otps_received", [])
        total_n += len(n_list)
        total_o += len(o_list)
        for t in n_list:
            try:
                dt = datetime.fromisoformat(t)
                if dt >= today_midnight: today_n += 1
                if dt >= last_7d: seven_n += 1
            except:
                continue
        for t in o_list:
            try:
                dt = datetime.fromisoformat(t)
                if dt >= today_midnight: today_o += 1
                if dt >= last_7d: seven_o += 1
            except:
                continue
    return today_n, today_o, seven_n, seven_o, total_n, total_o

# ==================== LEADERBOARD SECTION ====================

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("🚫 YOU ARE BANNED 🚫", reply_markup=main_keyboard(uid))
        return

    stats_data = load_stats()
    today_midnight = get_date_reset_time()
    user_data_all = load_data(USER_DATA_FILE)

    user_today_counts = []

    for uid_str, user_stats in stats_data.items():
        otps_received = user_stats.get("otps_received", [])
        today_count = 0
        for ts in otps_received:
            try:
                dt = datetime.fromisoformat(ts)
                if dt >= today_midnight:
                    today_count += 1
            except:
                continue
        if today_count > 0:
            name = user_data_all.get(uid_str, {}).get("full_name")
            if not name:
                name = user_data_all.get(uid_str, {}).get("username")
            if not name:
                name = f"User {uid_str}"
            user_today_counts.append((uid_str, today_count, html.escape(name)))

    user_today_counts.sort(key=lambda x: x[1], reverse=True)
    top10 = user_today_counts[:10]

    if not top10:
        msg = (
            "<b>🏆 TOP 10 OTP LEADERBOARD 🏆</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ আজ পর্যন্ত কেউ OTP পায়নি।\n"
        )
    else:
        msg = (
            "<b>🏆 TOP 10 OTP RECEIVERS (TODAY) 🏆</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        for idx, (uid_str, count, name) in enumerate(top10, 1):
            if idx == 1:
                medal = "🥇"
            elif idx == 2:
                medal = "🥈"
            elif idx == 3:
                medal = "🥉"
            else:
                medal = f"{idx}️⃣"
            msg += f"{medal} <b>{name}</b>\n   🔑 <code>{count}</code> OTPs\n\n"
        msg += (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📊 <i>প্রতিদিন রাত ১২টায় রিসেট হয়</i>"
        )

    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=main_keyboard(uid))

# ==================== GET NUMBER — SERVICE SELECTION ====================

def _build_services_keyboard(services):
    temp_btns = []
    for i, svc in enumerate(services):
        sid   = svc.get("sid", f"Service {i+1}")
        ranges = svc.get("ranges", [])
        label  = f"🚀 {sid} ({len(ranges)})"
        temp_btns.append(InlineKeyboardButton(label, callback_data=f"svc_{i}"))
        
    rows = [temp_btns[j:j+2] for j in range(0, len(temp_btns), 2)]
    return InlineKeyboardMarkup(rows)

def _build_countries_keyboard(ranges, service_idx):
    btns = []
    seen = {}
    for i, r_item in enumerate(ranges[:24]):
        r_text = r_item.get("range", "")
        country_display = r_item.get("country", "")
        if not country_display:
            prefix = re.sub(r'[xX]+$', '', str(r_text)).strip()
            prefix_clean = re.sub(r'\D', '', prefix)
            flag, cname = get_country_info(prefix_clean)
            country_display = f"{flag} {cname}"

        label = f"{country_display}"
        if label not in seen:
            seen[label] = i
            btns.append(InlineKeyboardButton(label, callback_data=f"rng_{i}"))
    rows = [btns[j:j+2] for j in range(0, len(btns), 2)]
    rows.append([InlineKeyboardButton("◀️ BACK", callback_data="back_services")])
    return InlineKeyboardMarkup(rows)

async def show_app_selection(update, context):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("🚫 YOU ARE BANNED 🚫", reply_markup=main_keyboard(uid))
        return

    services = load_custom_services()

    if not services:
        await update.message.reply_text(
            "⚠️ <b>দুঃখিত, এই মুহূর্তে কোনো সার্ভিস উপলব্ধ নেই।</b>\n⏳ অ্যাডমিন কর্তৃক সার্ভিস অ্যাড করার জন্য অপেক্ষা করুন।",
            parse_mode="HTML",
            reply_markup=main_keyboard(uid)
        )
        return

    context.user_data["la_services"] = services
    keyboard = _build_services_keyboard(services)
    await update.message.reply_text(
        "📞 <b>GET NUMBER</b>\n\n"
        "<blockquote>✨ নিচ থেকে আপনার পছন্দের <b>Service</b> নির্বাচন করুন:</blockquote>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ==================== AUTO OTP MONITOR SECTION ====================

async def monitor_loop(app):
    while True:
        try:
            r = await client_async.get(f"{BASE_URL}/success_otp?api_key={API_KEY}")
            if r.status_code != 200:
                print(f"Monitor API Error: HTTP Status {r.status_code}")
                await asyncio.sleep(CHECK_INTERVAL)
                continue
                
            try:
                res = r.json()
            except json.JSONDecodeError:
                raw_text = r.text.strip()
                if raw_text and raw_text != "no_otp":
                    print(f"Monitor raw API non-JSON response: {raw_text[:100]}")
                await asyncio.sleep(CHECK_INTERVAL)
                continue
            
            otps = []
            if isinstance(res, dict):
                if "data" in res and isinstance(res["data"], dict) and "otps" in res["data"]:
                    otps = res["data"]["otps"]
                elif "otps" in res:
                    otps = res["otps"]
                elif "data" in res and isinstance(res["data"], list):
                    otps = res["data"]
            elif isinstance(res, list):
                otps = res

            if otps:
                paid_data = load_data(PAID_SMS_FILE)
                range_db = load_data(DATA_RANGE_FILE)
                paid_keys_set = set(paid_data.keys())
                processed_in_session = set()

                for otp in otps:
                    num = normalize_number(otp.get("number") or otp.get("phone") or otp.get("to") or "")
                    full_sms = (
                        otp.get('message') or 
                        otp.get('otp') or 
                        otp.get('sms') or 
                        otp.get('text') or 
                        otp.get('msg') or 
                        otp.get('content') or 
                        "No SMS Content"
                    )
                    
                    ext_otp, ext_link = extract_link_and_otp(full_sms)
                    otp_code = otp.get("otp_code") or otp.get("otp") or ext_otp
                    
                    otp_id = str(otp.get("otp_id", ""))
                    sms_key = otp_id if otp_id else f"{num}_{full_sms}"

                    matched_key = None
                    for active_num in active_numbers.keys():
                        if numbers_match(num, active_num):
                            matched_key = active_num
                            break

                    if (matched_key is not None and
                            sms_key not in paid_keys_set and
                            sms_key not in processed_in_session):

                        details = active_numbers[matched_key]
                        paid_keys_set.add(sms_key)
                        processed_in_session.add(sms_key)
                        paid_data[sms_key] = {"uid": details["uid"], "otp": otp_code}

                        await update_db_balance(details["uid"], OTP_RATE)
                        add_otp_received(details["uid"])
                        log_global_activity(details["uid"], "OTP_RECEIVED", {"number": matched_key, "otp": otp_code, "sms": full_sms})

                        num_range_info = range_db.get(matched_key, {}).get("range", "")
                        if not num_range_info:
                            num_range_info = active_numbers.get(matched_key, {}).get("range", "")
                        if not num_range_info and matched_key:
                            _d = re.sub(r'\D', '', str(matched_key))
                            num_range_info = (_d[:-3] + 'XXX') if len(_d) > 3 else (_d + 'XXX')

                        country_flag, country_name = get_country_info(matched_key)
                        service_name = detect_service(full_sms)
                        clean_num = matched_key.replace('+', '').strip()
                        full_number = f"+{clean_num}"
                        masked_number = f"+{mask_number(clean_num)}"

                        safe_full_sms = html.escape(str(full_sms))
                        safe_otp_code = html.escape(str(otp_code))

                        link_section = ""
                        if ext_link:
                            link_section = f"<blockquote>🔗 <b>LINK:</b> <a href='{ext_link}'>{ext_link}</a></blockquote>\n"

                        user_msg = (
                            f"✅ <b>OTP RECEIVE SUCCESSFUL</b> ✅\n\n"
                            f"<blockquote>🌍 COUNTRY: <code>{country_flag} {country_name}</code></blockquote>\n"
                            f"<blockquote>📱 SERVICE: <code>{service_name}</code></blockquote>\n"
                            f"<blockquote>📞 NUMBER: <code>{full_number}</code></blockquote>\n"
                            f"<blockquote>🔑 OTP: <code>{safe_otp_code}</code></blockquote>\n"
                            f"{link_section}\n"
                            f"<blockquote>📩 FULL SMS:\n<code>{safe_full_sms}</code></blockquote>\n\n"
                            f"<b>💵 ADD BALANCE FOR {OTP_RATE:.2f} BDT</b>"
                        )

                        group_msg = (
                            f"✅ <b>OTP RECEIVE SUCCESSFUL</b> ✅\n\n"
                            f"<blockquote>📶 RANGE: <code>{num_range_info}</code></blockquote>\n"
                            f"<blockquote>🌍 COUNTRY: <code>{country_flag} {country_name}</code></blockquote>\n"
                            f"<blockquote>📱 SERVICE: <code>{service_name}</code></blockquote>\n"
                            f"<blockquote>📞 NUMBER: <code>{masked_number}</code></blockquote>\n"
                            f"<blockquote>🔑 OTP: <code>{safe_otp_code}</code></blockquote>\n"
                            f"{link_section}\n"
                            f"<blockquote>📩 FULL SMS:\n<code>{safe_full_sms}</code></blockquote>"
                        )

                        group_buttons = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("‼️ PANEL", url="https://t.me/MinoXSupport0"),
                                InlineKeyboardButton("📢 CHANNEL", url="https://t.me/MinoXSupport0")
                            ]
                        ])

                        try:
                            await app.bot.send_message(details["uid"], user_msg, parse_mode="HTML")
                        except Exception as e:
                            print(f"❌ User Message Send Fail: {e}")

                        try:
                            await app.bot.send_message(OTP_GROUP_ID, group_msg, parse_mode="HTML", reply_markup=group_buttons)
                        except Exception as e:
                            print(f"❌ Group Send Fail: {e}")

                        save_data(paid_data, PAID_SMS_FILE)

                current_time = datetime.now()
                for num_key in list(active_numbers.keys()):
                    entry = active_numbers[num_key]
                    if 'timestamp' not in entry:
                        entry['timestamp'] = current_time
                    elif (current_time - entry['timestamp']).total_seconds() > 3600:
                        del active_numbers[num_key]

        except Exception as e:
            print(f"Monitor Error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

# ==================== WORKER & API SECTION ====================

async def fetch_number_async(range_str):
    try:
        url = f"{BASE_URL}/getnumber?api_key={API_KEY}&rid={range_str}&range={range_str}&target={range_str}&national=1&remove_plus=1"
        r = await client_async.get(url)
        
        if r.status_code != 200:
            print(f"fetch_number_async Error: HTTP {r.status_code}")
            return None
            
        raw_text = r.text.strip()
        if not raw_text:
            return None
            
        err_keywords = ["NO_NUMBERS", "NO_NUMBER", "OUT_OF_STOCK", "BANNED", "LIMIT", "ERROR", "BALANCE", "EMPTY", "SQL"]
        if any(err in raw_text.upper() for err in err_keywords):
            return None

        try:
            data = r.json()
            if isinstance(data, dict):
                if str(data.get("status")).lower() in ["error", "fail", "false"]:
                    return None
                
                d = data.get("data") if isinstance(data.get("data"), dict) else data
                number = d.get("full_number") or d.get("number") or d.get("phone") or d.get("phoneNumber") or d.get("mobile")
                if number:
                    return {
                        "number": str(number),
                        "otp_now": bool(d.get("otp_now", False) or d.get("otp")),
                        "otp": d.get("otp"),
                        "sms": d.get("sms") or d.get("message"),
                    }
        except:
            pass

        parts = re.split(r'[:|]', raw_text)
        for part in reversed(parts):
            clean_part = re.sub(r'\D', '', part.strip())
            if len(clean_part) >= 7 and len(clean_part) <= 15 and clean_part.isdigit():
                return {"number": clean_part, "otp_now": False, "otp": None, "sms": None}
                    
        clean_all = re.sub(r'\D', '', raw_text)
        if len(clean_all) >= 7 and len(clean_all) <= 15 and clean_all.isdigit():
            return {"number": clean_all, "otp_now": False, "otp": None, "sms": None}

    except httpx.ReadTimeout:
        print(f"Fetch number error: ReadTimeout for range {range_str}. Server took too long to respond.")
    except Exception as e:
        print(f"Fetch number error: {e}")
    return None

async def fast_allocate_number_multi(query, context, ranges_list, sid):
    uid = query.from_user.id

    if is_user_banned(uid):
        await query.message.edit_text("🚫 YOU ARE BANNED 🚫")
        return

    try:
        await query.message.edit_text(
            "⚡ <b>ALLOCATING YOUR NUMBER</b> ⚡\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔍 <i>Searching active pool... Please wait.</i>",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Edit loading state error: {e}")

    res = None
    successful_range = None
    for r_text in ranges_list:
        try:
            res = await fetch_number_async(r_text)
            if res and res.get("number"):
                successful_range = r_text
                break
        except Exception as e:
            print(f"Error trying range {r_text}: {e}")
            continue

    if not res or not res.get("number"):
        try:
            await query.message.edit_text(
                "❌ <b>Number পাওয়া যায়নি।</b>\n\n"
                "<blockquote>⚠️ এই range/country-তে এখন number নেই বা server busy।\n"
                "অন্য কোনো সার্ভিস বা কান্ট্রি চেষ্টা করুন।</blockquote>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 BACK", callback_data="back_services")
                ]])
            )
        except:
            pass
        return

    clean_num = normalize_number(res["number"])
    add_number_taken(uid, 1)
    last_range[uid] = successful_range
    active_numbers[clean_num] = {"uid": uid, "range": successful_range, "timestamp": datetime.now()}
    save_number_range_info(uid, clean_num, successful_range)

    country_flag, country_name = get_country_info(clean_num)

    if res.get("otp_now") and res.get("otp"):
        otp_safe = html.escape(str(res["otp"]))
        sms_safe  = html.escape(str(res.get("sms") or ""))
        add_otp_received(uid)
        text = (
            f"✅ <b>YOUR NUMBER</b> ✅\n\n"
            f"<blockquote>🌍 COUNTRY: <code>{country_flag} {html.escape(country_name)}</code></blockquote>\n"
            f"<blockquote>📶 RANGE: <code>{successful_range}</code></blockquote>\n"
            f"<blockquote>📞 NUMBER: <code>+{clean_num}</code></blockquote>\n"
            f"<blockquote>🔑 OTP: <code>{otp_safe}</code></blockquote>"
            + (f"\n<blockquote>📩 SMS: <code>{sms_safe}</code></blockquote>" if sms_safe else "")
            + "\n\n<b>✅ OTP RECEIVED INSTANTLY!</b>"
        )
    else:
        text = (
            f"✅ <b>YOUR NUMBER</b> ✅\n\n"
            f"<blockquote>🌍 COUNTRY: <code>{country_flag} {html.escape(country_name)}</code></blockquote>\n"
            f"<blockquote>📶 RANGE: <code>{successful_range}</code></blockquote>\n"
            f"<blockquote>📞 NUMBER: <code>+{clean_num}</code></blockquote>\n\n"
            f"<b>📩 SMS STATUS: ⏳ WAITING...</b>"
        )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 SAME RANGE", callback_data="same_range")],
        [InlineKeyboardButton("🔙 BACK TO SERVICES", callback_data="back_services")]
    ])

    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        print(f"Edit final number message error: {e}")

# ==================== START COMMAND ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user
    username = user.username or ""
    full_name = user.full_name or ""

    # ইউজার ডাটাবেসে সেভ
    get_user(uid)
    data = load_data()
    if str(uid) in data:
        data[str(uid)]["username"] = username
        data[str(uid)]["full_name"] = full_name
        save_data(data)

    # রেফারেল চেক
    if context.args:
        ref_arg = context.args[0]
        if ref_arg.isdigit() and int(ref_arg) != uid:
            referrer = str(ref_arg)
            ref_data = load_referral_data()
            if referrer not in ref_data:
                ref_data[referrer] = {"referral_count": 0, "referred_users": []}
            referred_users = ref_data[referrer].get("referred_users", [])
            if str(uid) not in referred_users:
                referred_users.append(str(uid))
                ref_data[referrer]["referred_users"] = referred_users
                new_count = len(referred_users)
                ref_data[referrer]["referral_count"] = new_count
                save_referral_data(ref_data)
                if REFERRAL_PRICE > 0:
                    await update_db_balance(int(referrer), REFERRAL_PRICE)

    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode="HTML",
        reply_markup=main_keyboard(uid)
    )

# ==================== PROFILE COMMAND ====================

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("🚫 YOU ARE BANNED 🚫", reply_markup=main_keyboard(uid))
        return

    user_data = get_user(uid)
    balance = format_balance(user_data.get("balance", 0.0))
    stats = get_user_stats(uid)
    ref_count = get_referral_count(uid)

    msg = (
        "👤 <b>YOUR PROFILE</b> 👤\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
        f"💰 <b>Balance:</b> <code>{balance} BDT</code>\n"
        f"📞 <b>Numbers Taken:</b> <code>{stats['total_numbers']}</code>\n"
        f"🔑 <b>OTPs Received:</b> <code>{stats['total_otps']}</code>\n"
        f"👥 <b>Referrals:</b> <code>{ref_count}</code>\n\n"
        f"📊 <b>Today:</b> <code>{stats['today_numbers']}</code> nums / <code>{stats['today_otps']}</code> OTPs\n"
        f"📊 <b>Last 24h:</b> <code>{stats['last24h_numbers']}</code> nums / <code>{stats['last24h_otps']}</code> OTPs\n"
        f"📊 <b>Last 7d:</b> <code>{stats['last7d_numbers']}</code> nums / <code>{stats['last7d_otps']}</code> OTPs\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=main_keyboard(uid))

# ==================== SUPPORT COMMAND ====================

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"💬 <b>SUPPORT</b>\n\n"
        f"🔗 <a href='{SUPPORT_LINK}'>ক্লিক করুন সাপোর্টের জন্য</a>",
        parse_mode="HTML",
        reply_markup=main_keyboard(uid)
    )

# ==================== REFERRAL COMMAND ====================

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_user_banned(uid):
        await update.message.reply_text("🚫 YOU ARE BANNED 🚫", reply_markup=main_keyboard(uid))
        return

    ref_count = get_referral_count(uid)
    earned = ref_count * REFERRAL_PRICE

    msg = (
        "👥 <b>REFER AND EARN</b> 👥\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 <b>Your Referral Link:</b>\n<code>https://t.me/{context.bot.username}?start={uid}</code>\n\n"
        f"👥 <b>Total Referrals:</b> <code>{ref_count}</code>\n"
        f"💰 <b>Earned:</b> <code>{format_balance(earned)} BDT</code>\n"
        f"💎 <b>Per Referral:</b> <code>{REFERRAL_PRICE} BDT</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=main_keyboard(uid))

# ==================== CALLBACK QUERY HANDLER ====================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    data = query.data

    # --- GET NUMBER flow ---
    if data.startswith("svc_"):
        idx = int(data.split("_")[1])
        services = context.user_data.get("la_services", [])
        if idx < len(services):
            svc = services[idx]
            context.user_data["la_current_service_idx"] = idx
            ranges = svc.get("ranges", [])
            if not ranges:
                await query.message.edit_text(
                    "⚠️ <b>এই সার্ভিসে কোনো Range নেই।</b>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ BACK", callback_data="back_services")]])
                )
                return
            context.user_data["la_current_ranges"] = ranges
            keyboard = _build_countries_keyboard(ranges, idx)
            await query.message.edit_text(
                f"🌐 <b>Select Country for {svc.get('sid', 'Service').upper()}</b>\n\n"
                f"<blockquote>🟢 Available: <code>{len(ranges)}</code> ranges</blockquote>",
                parse_mode="HTML",
                reply_markup=keyboard
            )

    elif data.startswith("rng_"):
        idx = int(data.split("_")[1])
        ranges = context.user_data.get("la_current_ranges", [])
        services = context.user_data.get("la_services", [])
        svc_idx = context.user_data.get("la_current_service_idx", 0)
        sid = services[svc_idx].get("sid", "UNKNOWN") if svc_idx < len(services) else "UNKNOWN"
        
        if idx < len(ranges):
            r_item = ranges[idx]
            r_text = r_item.get("range", "")
            country_display = r_item.get("country", "")
            if not country_display:
                prefix = re.sub(r'[xX]+$', '', str(r_text)).strip()
                prefix_clean = re.sub(r'\D', '', prefix)
                flag, cname = get_country_info(prefix_clean)
                country_display = f"{flag} {cname}"

            # সেই কান্ট্রির সব ranges বের করা
            country_ranges = []
            for r in ranges:
                r_country = r.get("country", "")
                if not r_country:
                    rp = re.sub(r'[xX]+$', '', str(r.get("range", ""))).strip()
                    rpc = re.sub(r'\D', '', rp)
                    fl, cn = get_country_info(rpc)
                    r_country = f"{fl} {cn}"
                if r_country == country_display:
                    country_ranges.append(r.get("range", ""))
            
            if country_ranges:
                await fast_allocate_number_multi(query, context, country_ranges, sid)
            else:
                await fast_allocate_number_multi(query, context, [r_text], sid)

    elif data == "same_range":
        ranges = context.user_data.get("la_current_ranges", [])
        services = context.user_data.get("la_services", [])
        svc_idx = context.user_data.get("la_current_service_idx", 0)
        sid = services[svc_idx].get("sid", "UNKNOWN") if svc_idx < len(services) else "UNKNOWN"
        if ranges:
            first_range = ranges[0].get("range", "")
            await fast_allocate_number_multi(query, context, [first_range], sid)

    elif data == "back_services":
        services = context.user_data.get("la_services", [])
        if services:
            keyboard = _build_services_keyboard(services)
            await query.message.edit_text(
                "📞 <b>GET NUMBER</b>\n\n"
                "<blockquote>✨ নিচ থেকে আপনার পছন্দের <b>Service</b> নির্বাচন করুন:</blockquote>",
                parse_mode="HTML",
                reply_markup=keyboard
            )

    # --- ADMIN PANEL flow ---
    elif data == "adm_menu_back_to_main":
        await query.message.delete()
        await context.bot.send_message(uid, WELCOME_MESSAGE, parse_mode="HTML", reply_markup=main_keyboard(uid))

    elif data == "adm_menu_user_mgnt":
        await query.message.edit_text(
            "👥 <b>USER MANAGEMENT</b>\n━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
            reply_markup=build_user_management_inline_keyboard()
        )

    elif data == "adm_menu_sys_config":
        await query.message.edit_text(
            "⚙️ <b>SYSTEM CONFIGURATION</b>\n━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
            reply_markup=build_system_config_inline_keyboard()
        )

    elif data == "adm_menu_back_to_admin":
        await query.message.edit_text(
            get_admin_panel_text(),
            parse_mode="HTML",
            reply_markup=build_admin_main_inline_keyboard()
        )

    elif data == "manage_svc_back_to_list":
        await query.message.edit_text(
            "🛠️ <b>MANAGE SERVICES</b>\n━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML",
            reply_markup=build_manage_services_inline_keyboard()
        )

    elif data.startswith("manage_svc_view_"):
        svc_name = data.replace("manage_svc_view_", "")
        kb = build_service_detail_keyboard(svc_name)
        if kb:
            await query.message.edit_text(
                f"📁 <b>SERVICE: {svc_name.upper()}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "<blockquote>🌍 Select a country to manage ranges:</blockquote>",
                parse_mode="HTML",
                reply_markup=kb
            )

    elif data.startswith("manage_svc_country_view_"):
        parts = data.replace("manage_svc_country_view_", "").split("_", 1)
        if len(parts) == 2:
            svc_name, country_name = parts
            kb = build_country_detail_keyboard(svc_name, country_name)
            if kb:
                custom_svcs = load_custom_services()
                target_svc = next((s for s in custom_svcs if s.get("sid", "").upper() == svc_name.upper()), None)
                range_count = 0
                if target_svc:
                    grouped = get_grouped_countries_for_service(target_svc)
                    range_count = len(grouped.get(country_name, {}).get("ranges", []))
                await query.message.edit_text(
                    f"📁 <b>{svc_name.upper()}</b> → 🌍 <b>{country_name.upper()}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📶 <b>Total Ranges:</b> <code>{range_count}</code>",
                    parse_mode="HTML",
                    reply_markup=kb
                )

    elif data.startswith("manage_svc_delete_range_"):
        parts = data.replace("manage_svc_delete_range_", "").rsplit("_", 1)
        if len(parts) == 2:
            prefix_and_country = parts[0]
            range_val = parts[1]
            # prefix_and_country = "svcname_countryname"
            last_underscore = prefix_and_country.rfind("_")
            if last_underscore > 0:
                svc_name = prefix_and_country[:last_underscore]
                country_name = prefix_and_country[last_underscore+1:]
                
                custom_svcs = load_custom_services()
                target = next((s for s in custom_svcs if s.get("sid", "").upper() == svc_name.upper()), None)
                if target:
                    new_ranges = [r for r in target.get("ranges", []) if r.get("range") != range_val]
                    target["ranges"] = new_ranges
                    save_custom_services(custom_svcs)
                    
                    kb = build_country_detail_keyboard(svc_name, country_name)
                    if kb:
                        await query.message.edit_text(
                            f"✅ <b>Range deleted!</b>\n\n"
                            f"📁 <b>{svc_name.upper()}</b> → 🌍 <b>{country_name.upper()}</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"📶 <b>Total Ranges:</b> <code>{len(new_ranges)}</code>",
                            parse_mode="HTML",
                            reply_markup=kb
                        )

    elif data.startswith("manage_svc_delete_country_confirm_"):
        parts = data.replace("manage_svc_delete_country_confirm_", "").split("_", 1)
        if len(parts) == 2:
            svc_name, country_name = parts
            custom_svcs = load_custom_services()
            target = next((s for s in custom_svcs if s.get("sid", "").upper() == svc_name.upper()), None)
            if target:
                grouped = get_grouped_countries_for_service(target)
                country_ranges = grouped.get(country_name, {}).get("ranges", [])
                new_ranges = [r for r in target.get("ranges", []) if r.get("range") not in country_ranges]
                target["ranges"] = new_ranges
                save_custom_services(custom_svcs)
                
                kb = build_service_detail_keyboard(svc_name)
                if kb:
                    await query.message.edit_text(
                        f"✅ <b>Country {country_name.upper()} deleted!</b>\n\n"
                        f"📁 <b>SERVICE: {svc_name.upper()}</b>\n━━━━━━━━━━━━━━━━━━━━━━",
                        parse_mode="HTML",
                        reply_markup=kb
                    )

    elif data.startswith("manage_svc_delete_init_"):
        svc_name = data.replace("manage_svc_delete_init_", "")
        context.user_data["pending_delete_svc"] = svc_name
        await query.message.edit_text(
            f"⚠️ <b>DELETE SERVICE: {svc_name.upper()}</b>\n\n"
            "<blockquote>আপনি কি নিশ্চিত এই সার্ভিস মুছে ফেলতে চান?\n"
            "এটি সব ranges সহ মুছে যাবে।</blockquote>\n\n"
            "টাইপ করুন: <code>CONFIRM_DELETE</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 CANCEL", callback_data=f"manage_svc_view_{svc_name}")]])
        )

    elif data.startswith("manage_svc_add_range_"):
        parts = data.replace("manage_svc_add_range_", "").split("_", 1)
        svc_name = parts[0] if parts else ""
        country_name = parts[1] if len(parts) > 1 else ""
        context.user_data["pending_add_range_svc"] = svc_name
        context.user_data["pending_add_range_country"] = country_name
        await query.message.edit_text(
            f"➕ <b>ADD RANGE</b>\n\n"
            f"📁 Service: <code>{svc_name.upper()}</code>\n"
            f"🌍 Country: <code>{country_name.upper() if country_name else 'NEW'}</code>\n\n"
            "<blockquote>Format: <code>range_text</code>\n"
            "Example: <code>8801XXXXXXXXX</code></blockquote>\n\n"
            "টাইপ করুন range:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 CANCEL", callback_data=f"manage_svc_view_{svc_name}")]])
        )

    elif data.startswith("manage_svc_add"):
        context.user_data["pending_add_svc"] = True
        await query.message.edit_text(
            "➕ <b>ADD NEW SERVICE</b>\n\n"
            "<blockquote>টাইপ করুন Service Name (SID):\n"
            "Example: <code>FACEBOOK</code></blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 CANCEL", callback_data="manage_svc_back_to_list")]])
        )

    elif data.startswith("manage_svc_rename_init_"):
        svc_name = data.replace("manage_svc_rename_init_", "")
        context.user_data["pending_rename_svc"] = svc_name
        await query.message.edit_text(
            f"✏️ <b>RENAME SERVICE</b>\n\n"
            f"Current: <code>{svc_name.upper()}</code>\n\n"
            "<blockquote>টাইপ করুন নতুন নাম:</blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 CANCEL", callback_data=f"manage_svc_view_{svc_name}")]])
        )

    elif data.startswith("manage_svc_rename_country_init_"):
        parts = data.replace("manage_svc_rename_country_init_", "").split("_", 1)
        if len(parts) == 2:
            svc_name, country_name = parts
            context.user_data["pending_rename_country_svc"] = svc_name
            context.user_data["pending_rename_country_old"] = country_name
            await query.message.edit_text(
                f"✏️ <b>RENAME COUNTRY</b>\n\n"
                f"Current: <code>{country_name.upper()}</code>\n\n"
                "<blockquote>টাইপ করুন নতুন নাম:</blockquote>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 CANCEL", callback_data=f"manage_svc_view_{svc_name}")]])
            )

    elif data.startswith("manage_svc_edit_range_init_"):
        parts = data.replace("manage_svc_edit_range_init_", "").rsplit("_", 1)
        if len(parts) == 2:
            prefix_and_country = parts[0]
            old_range = parts[1]
            last_us = prefix_and_country.rfind("_")
            if last_us > 0:
                svc_name = prefix_and_country[:last_us]
                country_name = prefix_and_country[last_us+1:]
                context.user_data["pending_edit_range_svc"] = svc_name
                context.user_data["pending_edit_range_country"] = country_name
                context.user_data["pending_edit_range_old"] = old_range
                await query.message.edit_text(
                    f"✏️ <b>EDIT RANGE</b>\n\n"
                    f"Current: <code>{old_range}</code>\n\n"
                    "<blockquote>টাইপ করুন নতুন range:</blockquote>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 CANCEL", callback_data=f"manage_svc_view_{svc_name}")]])
                )

    # --- ADMIN SYSTEM CONFIG ---
    elif data == "adm_sys_stats":
        today_n, today_o, seven_n, seven_o, total_n, total_o = get_global_system_stats()
        users = len(get_all_users())
        msg = (
            "📈 <b>SYSTEM STATS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 Total Users: <code>{users}</code>\n\n"
            f"📊 <b>Today:</b>\n   📞 Numbers: <code>{today_n}</code>\n   🔑 OTPs: <code>{today_o}</code>\n\n"
            f"📊 <b>Last 7 Days:</b>\n   📞 Numbers: <code>{seven_n}</code>\n   🔑 OTPs: <code>{seven_o}</code>\n\n"
            f"📊 <b>All Time:</b>\n   📞 Numbers: <code>{total_n}</code>\n   🔑 OTPs: <code>{total_o}</code>"
        )
        await query.message.edit_text(msg, parse_mode="HTML", reply_markup=build_system_config_inline_keyboard())

    elif data == "adm_sys_ban":
        context.user_data["admin_action"] = "ban_user"
        await query.message.edit_text(
            "⛔ <b>BAN USER</b>\n\n<blockquote>টাইপ করুন User ID:</blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="adm_menu_sys_config")]])
        )

    elif data == "adm_sys_unban":
        context.user_data["admin_action"] = "unban_user"
        await query.message.edit_text(
            "🔓 <b>UNBAN USER</b>\n\n<blockquote>টাইপ করুন User ID:</blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="adm_menu_sys_config")]])
        )

    elif data == "adm_sys_banned_list":
        banned = load_banned_users()
        if not banned:
            msg = "📜 <b>BANNED LIST</b>\n\n✅ কোনো ইউজার ব্যান নেই।"
        else:
            msg = "📜 <b>BANNED LIST</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for i, b_uid in enumerate(banned, 1):
                msg += f"{i}. <code>{b_uid}</code>\n"
        await query.message.edit_text(msg, parse_mode="HTML", reply_markup=build_system_config_inline_keyboard())

    elif data == "adm_sys_add_bal":
        context.user_data["admin_action"] = "add_balance"
        await query.message.edit_text(
            "➕ <b>ADD BALANCE</b>\n\n<blockquote>Format: <code>USER_ID AMOUNT</code>\nExample: <code>123456789 100</code></blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="adm_menu_sys_config")]])
        )

    elif data == "adm_sys_rem_bal":
        context.user_data["admin_action"] = "remove_balance"
        await query.message.edit_text(
            "➖ <b>REMOVE BALANCE</b>\n\n<blockquote>Format: <code>USER_ID AMOUNT</code>\nExample: <code>123456789 50</code></blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="adm_menu_sys_config")]])
        )

    elif data == "adm_sys_user_check":
        context.user_data["admin_action"] = "user_check"
        await query.message.edit_text(
            "👤 <b>USER CHECK</b>\n\n<blockquote>টাইপ করুন User ID:</blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="adm_menu_sys_config")]])
        )

    # --- ADMIN USER MANAGEMENT ---
    elif data == "adm_usermgnt_broadcast":
        context.user_data["admin_action"] = "broadcast"
        await query.message.edit_text(
            "📢 <b>BROADCAST</b>\n\n<blockquote>টাইপ করুন মেসেজ যা সব ইউজারকে পাঠাতে চান:</blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="adm_menu_user_mgnt")]])
        )

    elif data == "adm_usermgnt_get_ids":
        all_users = get_all_users()
        if not all_users:
            msg = "🆔 <b>ALL USER IDs</b>\n\n❌ কোনো ইউজার নেই।"
        else:
            msg = f"🆔 <b>ALL USER IDs (Total: {len(all_users)})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for i, u_id in enumerate(all_users, 1):
                msg += f"{i}. <code>{u_id}</code>\n"
        await query.message.edit_text(msg, parse_mode="HTML", reply_markup=build_user_management_inline_keyboard())

    elif data == "adm_usermgnt_all_balance":
        all_data = load_data()
        if not all_data:
            msg = "💰 <b>ALL USER BALANCE</b>\n\n❌ কোনো ইউজার নেই।"
        else:
            msg = f"💰 <b>ALL USER BALANCE (Total: {len(all_data)})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for i, (u_id, u_data) in enumerate(all_data.items(), 1):
                bal = format_balance(u_data.get("balance", 0))
                msg += f"{i}. <code>{u_id}</code> → <code>{bal}</code> BDT\n"
        await query.message.edit_text(msg, parse_mode="HTML", reply_markup=build_user_management_inline_keyboard())

# ==================== MESSAGE HANDLER ====================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    if not text:
        return

    if is_user_banned(uid):
        await update.message.reply_text("🚫 YOU ARE BANNED 🚫", reply_markup=main_keyboard(uid))
        return

    # --- ADMIN PANEL BUTTON ---
    clean_text = text.strip()
    if clean_text == f"⚙️ {make_bold_unicode('ADMIN PANEL')} ⚙️":
        if is_admin(uid):
            await update.message.reply_text(
                get_admin_panel_text(),
                parse_mode="HTML",
                reply_markup=build_admin_main_inline_keyboard()
            )
        return

    # --- MAIN MENU BUTTONS ---
    if clean_text == f"📞 {make_bold_unicode('GET NUMBER')}":
        await show_app_selection(update, context)
        return

    if clean_text == f"👤 {make_bold_unicode('PROFILE')}":
        await profile_command(update, context)
        return

    if clean_text == f"💬 {make_bold_unicode('SUPPORT')}":
        await support_command(update, context)
        return

    if clean_text == f"🏆 {make_bold_unicode('LEADERBOARD')}":
        await leaderboard_command(update, context)
        return

    if clean_text == f"👥 {make_bold_unicode('REFER AND EARN')}":
        await referral_command(update, context)
        return

    if clean_text == f"❌ {make_bold_unicode('CANCEL')}":
        context.user_data.clear()
        await update.message.reply_text("✅ <b>Cancelled!</b>", parse_mode="HTML", reply_markup=main_keyboard(uid))
        return

    # --- ADMIN TEXT INPUT HANDLERS ---
    if is_admin(uid):
        admin_action = context.user_data.get("admin_action")

        if admin_action == "ban_user":
            target_id = text.strip()
            if target_id.isdigit():
                if ban_user(target_id):
                    await update.message.reply_text(f"✅ <b>User {target_id} BANNED!</b>", parse_mode="HTML")
                else:
                    await update.message.reply_text(f"⚠️ <b>Already banned or error.</b>", parse_mode="HTML")
            context.user_data.pop("admin_action", None)
            await update.message.reply_text(get_admin_panel_text(), parse_mode="HTML", reply_markup=build_admin_main_inline_keyboard())
            return

        elif admin_action == "unban_user":
            target_id = text.strip()
            if target_id.isdigit():
                if unban_user(target_id):
                    await update.message.reply_text(f"✅ <b>User {target_id} UNBANNED!</b>", parse_mode="HTML")
                else:
                    await update.message.reply_text(f"⚠️ <b>Not banned or error.</b>", parse_mode="HTML")
            context.user_data.pop("admin_action", None)
            await update.message.reply_text(get_admin_panel_text(), parse_mode="HTML", reply_markup=build_admin_main_inline_keyboard())
            return

        elif admin_action == "add_balance":
            parts = text.strip().split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].replace(".", "", 1).isdigit():
                target_uid = parts[0]
                amount = float(parts[1])
                new_bal = await update_db_balance(int(target_uid), amount)
                await update.message.reply_text(f"✅ <b>Added {amount} BDT to {target_uid}\nNew Balance: {format_balance(new_bal)} BDT</b>", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ <b>Wrong format! Use: USER_ID AMOUNT</b>", parse_mode="HTML")
            context.user_data.pop("admin_action", None)
            await update.message.reply_text(get_admin_panel_text(), parse_mode="HTML", reply_markup=build_admin_main_inline_keyboard())
            return

        elif admin_action == "remove_balance":
            parts = text.strip().split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].replace(".", "", 1).isdigit():
                target_uid = parts[0]
                amount = float(parts[1])
                new_bal = await update_db_balance(int(target_uid), -amount)
                await update.message.reply_text(f"✅ <b>Removed {amount} BDT from {target_uid}\nNew Balance: {format_balance(new_bal)} BDT</b>", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ <b>Wrong format! Use: USER_ID AMOUNT</b>", parse_mode="HTML")
            context.user_data.pop("admin_action", None)
            await update.message.reply_text(get_admin_panel_text(), parse_mode="HTML", reply_markup=build_admin_main_inline_keyboard())
            return

        elif admin_action == "user_check":
            target_id = text.strip()
            data = load_data()
            if target_id in data:
                u = data[target_id]
                stats = get_user_stats(target_id)
                msg = (
                    f"👤 <b>USER INFO</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🆔 ID: <code>{target_id}</code>\n"
                    f"📝 Name: <code>{html.escape(u.get('full_name', 'N/A'))}</code>\n"
                    f"👤 Username: <code>@{u.get('username', 'N/A')}</code>\n"
                    f"💰 Balance: <code>{format_balance(u.get('balance', 0))} BDT</code>\n"
                    f"📞 Numbers: <code>{stats['total_numbers']}</code>\n"
                    f"🔑 OTPs: <code>{stats['total_otps']}</code>\n"
                    f"🚫 Banned: <code>{'YES' if is_user_banned(target_id) else 'NO'}</code>"
                )
            else:
                msg = f"❌ <b>User {target_id} not found.</b>"
            context.user_data.pop("admin_action", None)
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=build_admin_main_inline_keyboard())
            return

        elif admin_action == "broadcast":
            all_users = get_all_users()
            sent = 0
            failed = 0
            for u_id in all_users:
                try:
                    await context.bot.send_message(int(u_id), text, parse_mode="HTML")
                    sent += 1
                except:
                    failed += 1
            await update.message.reply_text(
                f"📢 <b>BROADCAST COMPLETE</b>\n\n✅ Sent: <code>{sent}</code>\n❌ Failed: <code>{failed}</code>",
                parse_mode="HTML",
                reply_markup=build_admin_main_inline_keyboard()
            )
            context.user_data.pop("admin_action", None)
            return

        # --- SERVICE MANAGEMENT TEXT INPUTS ---
        if context.user_data.get("pending_add_svc"):
            svc_name = text.strip().upper()
            custom_svcs = load_custom_services()
            exists = any(s.get("sid", "").upper() == svc_name for s in custom_svcs)
            if exists:
                await update.message.reply_text("❌ <b>Service already exists!</b>", parse_mode="HTML")
            else:
                custom_svcs.append({"sid": svc_name, "ranges": []})
                save_custom_services(custom_svcs)
                await update.message.reply_text(f"✅ <b>Service '{svc_name}' added!</b>", parse_mode="HTML")
            context.user_data.pop("pending_add_svc", None)
            await update.message.reply_text(
                "🛠️ <b>MANAGE SERVICES</b>\n━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
                reply_markup=build_manage_services_inline_keyboard()
            )
            return

        if context.user_data.get("pending_delete_svc"):
            if text.strip().upper() == "CONFIRM_DELETE":
                svc_name = context.user_data["pending_delete_svc"]
                custom_svcs = load_custom_services()
                custom_svcs = [s for s in custom_svcs if s.get("sid", "").upper() != svc_name.upper()]
                save_custom_services(custom_svcs)
                await update.message.reply_text(f"✅ <b>Service '{svc_name}' deleted!</b>", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ <b>Cancelled.</b>", parse_mode="HTML")
            context.user_data.pop("pending_delete_svc", None)
            await update.message.reply_text(
                "🛠️ <b>MANAGE SERVICES</b>\n━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
                reply_markup=build_manage_services_inline_keyboard()
            )
            return

        if context.user_data.get("pending_rename_svc"):
            new_name = text.strip().upper()
            old_name = context.user_data["pending_rename_svc"]
            custom_svcs = load_custom_services()
            target = next((s for s in custom_svcs if s.get("sid", "").upper() == old_name.upper()), None)
            if target:
                target["sid"] = new_name
                save_custom_services(custom_svcs)
                await update.message.reply_text(f"✅ <b>Renamed to '{new_name}'!</b>", parse_mode="HTML")
            context.user_data.pop("pending_rename_svc", None)
            kb = build_service_detail_keyboard(new_name)
            if kb:
                await update.message.reply_text(
                    f"📁 <b>SERVICE: {new_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━",
                    parse_mode="HTML",
                    reply_markup=kb
                )
            return

        if context.user_data.get("pending_rename_country_old"):
            new_country = text.strip().title()
            old_country = context.user_data["pending_rename_country_old"]
            svc_name = context.user_data["pending_rename_country_svc"]
            custom_svcs = load_custom_services()
            target = next((s for s in custom_svcs if s.get("sid", "").upper() == svc_name.upper()), None)
            if target:
                for r in target.get("ranges", []):
                    if r.get("country", "") == old_country or r.get("country", "") == f"🌍 {old_country}":
                        r["country"] = f"🌍 {new_country}"
                save_custom_services(custom_svcs)
                await update.message.reply_text(f"✅ <b>Country renamed to '{new_country}'!</b>", parse_mode="HTML")
            context.user_data.pop("pending_rename_country_old", None)
            context.user_data.pop("pending_rename_country_svc", None)
            kb = build_country_detail_keyboard(svc_name, new_country)
            if kb:
                await update.message.reply_text(
                    f"📁 <b>{svc_name.upper()}</b> → 🌍 <b>{new_country.upper()}</b>",
                    parse_mode="HTML",
                    reply_markup=kb
                )
            return

        if context.user_data.get("pending_add_range_svc"):
            range_text = text.strip()
            svc_name = context.user_data["pending_add_range_svc"]
            country_name = context.user_data.get("pending_add_range_country", "")
            
            prefix = re.sub(r'[xX]+$', '', range_text).strip()
            prefix_clean = re.sub(r'\D', '', prefix)
            flag, cname = get_country_info(prefix_clean)
            
            if not country_name:
                country_name = cname
                country_display = f"{flag} {cname}"
            else:
                country_display = f"🌍 {country_name}"
            
            custom_svcs = load_custom_services()
            target = next((s for s in custom_svcs if s.get("sid", "").upper() == svc_name.upper()), None)
            if target:
                target["ranges"].append({"range": range_text, "country": country_display})
                save_custom_services(custom_svcs)
                await update.message.reply_text(f"✅ <b>Range '{range_text}' added to {country_display}!</b>", parse_mode="HTML")
            
            context.user_data.pop("pending_add_range_svc", None)
            context.user_data.pop("pending_add_range_country", None)
            kb = build_service_detail_keyboard(svc_name)
            if kb:
                await update.message.reply_text(
                    f"📁 <b>SERVICE: {svc_name.upper()}</b>\n━━━━━━━━━━━━━━━━━━━━━━",
                    parse_mode="HTML",
                    reply_markup=kb
                )
            return

        if context.user_data.get("pending_edit_range_old"):
            new_range = text.strip()
            old_range = context.user_data["pending_edit_range_old"]
            svc_name = context.user_data["pending_edit_range_svc"]
            country_name = context.user_data["pending_edit_range_country"]
            
            custom_svcs = load_custom_services()
            target = next((s for s in custom_svcs if s.get("sid", "").upper() == svc_name.upper()), None)
            if target:
                for r in target.get("ranges", []):
                    if r.get("range") == old_range:
                        r["range"] = new_range
                        break
                save_custom_services(custom_svcs)
                await update.message.reply_text(f"✅ <b>Range updated to '{new_range}'!</b>", parse_mode="HTML")
            
            context.user_data.pop("pending_edit_range_old", None)
            context.user_data.pop("pending_edit_range_svc", None)
            context.user_data.pop("pending_edit_range_country", None)
            kb = build_country_detail_keyboard(svc_name, country_name)
            if kb:
                await update.message.reply_text(
                    f"📁 <b>{svc_name.upper()}</b> → 🌍 <b>{country_name.upper()}</b>",
                    parse_mode="HTML",
                    reply_markup=kb
                )
            return

# ==================== ERROR HANDLER ====================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"Error: {context.error}")

# ==================== MAIN FUNCTION ====================

async def post_init(app):
    asyncio.create_task(monitor_loop(app))

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)

    print("🚀 Mino SMS Bot Started Successfully!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
