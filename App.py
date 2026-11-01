
import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
import sqlite3
import json
import re

APP_NAME = "Football Persian"
DB_FILE = "football_persian.db"

DEFAULT_SOURCES = {
    "websites": [
        "https://www.varzesh3.com",
        "https://www.dsport.ir",
        "https://www.tabefotbal.ir",
        "https://www.football360.ir",
        "https://www.fbtv3.ir"
    ],
    "telegram": [
        "estedadefootball",
        "tabefotbal",
        "dsport_lige2",
        "varzesh3",
        "omidbaghooli7"
    ],
    "instagram": [
        "varzesh3",
        "estedadefootball",
        "tabefotbal",
        "ft360_ir",
        "fbtv_ir",
        "dsport_lige2",
        "omidbaghooli77"
    ],
    "interval": 15
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FootballPersian/1.0)"
}


# ---------------- DATABASE ----------------

def connect_db():
    con = sqlite3.connect(DB_FILE, check_same_thread=False)

    con.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE,
            source TEXT,
            category TEXT,
            status TEXT DEFAULT 'در انتظار بررسی',
            created_at TEXT
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    con.commit()
    return con


def get_setting(key, default=None):
    con = connect_db()
    row = con.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,)
    ).fetchone()
    con.close()

    if row:
        return json.loads(row[0])

    return default


def set_setting(key, value):
    con = connect_db()
    con.execute(
        "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
        (key, json.dumps(value, ensure_ascii=False))
    )
    con.commit()
    con.close()


def get_sources():
    return get_setting("sources", DEFAULT_SOURCES)


def save_sources(data):
    set_setting("sources", data)


# ---------------- NEWS MANAGEMENT ----------------

def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def detect_category(title):
    text = title.lower()

    transfer_words = [
        "انتقال", "نقل و انتقال", "قرارداد",
        "جذب", "تمدید", "فسخ", "لیگ برتر",
        "transfer", "signing"
    ]

    player_words = [
        "بازیکن", "فوتبالیست", "مهاجم",
        "دروازه بان", "مدافع", "هافبک",
        "player"
    ]

    club_words = [
        "باشگاه", "تیم", "سرمربی",
        "مربی", "club", "coach"
    ]

    if any(word in text for word in transfer_words):
        return "نقل‌وانتقالات"

    if any(word in text for word in player_words):
        return "بازیکنان"

    if any(word in text for word in club_words):
        return "باشگاه‌ها"

    return "سایر اخبار فوتبال"


def save_news(title, url, source):
    title = clean_text(title)

    if not title or not url:
        return False

    category = detect_category(title)

    con = connect_db()

    try:
        con.execute("""
            INSERT INTO news
            (title, url, source, category, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            title,
            url,
            source,
            category,
            "در انتظار بررسی",
            datetime.now(timezone.utc).isoformat()
        ))

        con.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        con.close()


def scan_website(site):
    count = 0

    try:
        response = requests.get(
            site,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        host = urlparse(site).netloc

        for link in soup.select("a[href]"):

            title = clean_text(
                link.get_text(" ", strip=True)
            )

            url = urljoin(site, link.get("href", ""))
            parsed = urlparse(url)

            if len(title) < 18:
                continue

            if parsed.scheme not in ["http", "https"]:
                continue

            if parsed.netloc != host:
                continue

            if any(word in url.lower() for word in [
                "login", "register", "javascript:"
            ]):
                continue

            if save_news(title, url, host):
                count += 1

    except Exception as error:
        st.session_state.errors.append(
            f"{site}: {str(error)[:150]}"
        )

    return count


def scan_telegram(channel):
    count = 0

    url = f"https://t.me/s/{channel}"

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        posts = soup.select(".tgme_widget_message")

        for post in posts:

            text_element = post.select_one(
                ".tgme_widget_message_text"
            )

            if not text_element:
                continue

            title = clean_text(
                text_element.get_text(" ", strip=True)
            )

            link = post.select_one(
                "a.tgme_widget_message_date"
            )

            post_url = link.get("href") if link else ""

            if not post_url:
                post_id = post.get("data-post", "")
                if post_id:
                    post_url = "https://t.me/" + post_id

            if title and post_url:
                if save_news(
                    title[:500],
                    post_url,
                    "Telegram @" + channel
                ):
                    count += 1

    except Exception as error:
        st.session_state.errors.append(
            f"Telegram @{channel}: {str(error)[:150]}"
        )

    return count


def collect_news():
    sources = get_sources()

    st.session_state.errors = []

    total = 0

    jobs = (
        sources.get("websites", [])
        + ["telegram:" + x for x in sources.get("telegram", [])]
    )

    progress = st.progress(0)

    for index, item in enumerate(jobs):

        if item.startswith("telegram:"):
            channel = item.replace("telegram:", "", 1)
            total += scan_telegram(channel)
        else:
            total += scan_website(item)

        progress.progress((index + 1) / max(len(jobs), 1))

    set_setting(
        "last_scan",
        datetime.now(timezone.utc).isoformat()
    )

    return total


def get_news(search="", status="همه"):
    con = connect_db()

    sql = """
        SELECT id, title, url, source, category, status, created_at
        FROM news
    """

    conditions = []
    params = []

    if status != "همه":
        conditions.append("status=?")
        params.append(status)

    if search:
        conditions.append("(title LIKE ? OR source LIKE ?)")
        params.extend([
            f"%{search}%",
            f"%{search}%"
        ])

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY id DESC LIMIT 300"

    rows = con.execute(sql, params).fetchall()

    con.close()

    return rows


def update_news_status(news_id, status):
    con = connect_db()

    con.execute(
        "UPDATE news SET status=? WHERE id=?",
        (status, news_id)
    )

    con.commit()
    con.close()


# ---------------- USER INTERFACE ----------------

st.set_page_config(
    page_title=APP_NAME,
    page_icon="⚽",
    layout="wide"
)

st.markdown("""
<style>
html, body, [class*="css"] {
    direction: rtl;
}
.block-container {
    padding-top: 2rem;
}
</style>
""", unsafe_allow_html=True)

connect_db()

if "errors" not in st.session_state:
    st.session_state.errors = []

st.title("⚽ Football Persian")

st.caption(
    "سامانه هوشمند پایش اخبار فوتبال و نقل‌وانتقالات"
)

st.info(
    "مطالب فقط از منابع معرفی‌شده توسط شما دریافت می‌شوند. "
    "هیچ خبری بدون تأیید شما منتشر نخواهد شد."
)

sources = get_sources()

# Automatic check every 15 minutes while app is open
@st.fragment(run_every="15m")
def automatic_check():

    last_scan = get_setting("last_scan")

    should_scan = False

    if not last_scan:
        should_scan = True
    else:
        try:
            previous = datetime.fromisoformat(last_scan)
            elapsed = (
                datetime.now(timezone.utc) - previous
            ).total_seconds()

            if elapsed >= sources.get("interval", 15) * 60:
                should_scan = True

        except Exception:
            should_scan = True

    if should_scan:
        with st.spinner("در حال بررسی خودکار منابع..."):
            new_count = collect_news()

        st.success(
            f"بررسی خودکار انجام شد؛ {new_count} مطلب جدید ذخیره شد."
        )

automatic_check()


with st.sidebar:

    st.header("⚽ منوی اصلی")

    page = st.radio(
        "انتخاب بخش",
        [
            "داشبورد اخبار",
            "مدیریت منابع",
            "درباره برنامه"
        ]
    )

    st.divider()

    if st.button(
        "🔄 بررسی دستی منابع",
        use_container_width=True
    ):

        with st.spinner("در حال دریافت اخبار..."):
            new_count = collect_news()

        st.success(
            f"{new_count} خبر جدید دریافت شد."
        )

        st.rerun()


# ---------------- DASHBOARD ----------------

if page == "داشبورد اخبار":

    rows = get_news()

    waiting = sum(
        1 for row in rows
        if row[5] == "در انتظار بررسی"
    )

    approved = sum(
        1 for row in rows
        if row[5] == "تأیید شده"
    )

    col1, col2, col3 = st.columns(3)

    col1.metric("کل اخبار", len(rows))
    col2.metric("در انتظار بررسی", waiting)
    col3.metric("اخبار تأییدشده", approved)

    st.divider()

    st.subheader("اخبار دریافت‌شده")

    search = st.text_input(
        "جستجو در اخبار"
    )

    status_filter = st.selectbox(
        "فیلتر وضعیت",
        [
            "همه",
            "در انتظار بررسی",
            "تأیید شده",
            "رد شده"
        ]
    )

    news = get_news(search, status_filter)

    if not news:
        st.info(
            "هنوز خبری ثبت نشده است. "
            "دکمه بررسی منابع را بزن."
        )

    for item in news:

        news_id, title, url, source, category, status, created = item

        with st.container(border=True):

            st.markdown(f"**{title}**")

            st.caption(
                f"منبع: {source} | دسته: {category} | وضعیت: {status}"
            )

            st.markdown(
                f"[مشاهده خبر اصلی]({url})"
            )

            col1, col2 = st.columns(2)

            with col1:

                if st.button(
                    "✅ تأیید خبر",
                    key=f"approve_{news_id}"
                ):

                    update_news_status(
                        news_id,
                        "تأیید شده"
                    )

                    st.rerun()

            with col2:

                if st.button(
                    "❌ رد خبر",
                    key=f"reject_{news_id}"
                ):

                    update_news_status(
                        news_id,
                        "رد شده"
                    )

                    st.rerun()


# ---------------- SOURCE MANAGEMENT ----------------

elif page == "مدیریت منابع":

    st.subheader("مدیریت منابع خبری")

    st.write(
        "منابع را می‌توانی تغییر بدهی، حذف کنی یا منبع جدید اضافه کنی."
    )

    websites = st.text_area(
        "وب‌سایت‌ها (هر آدرس در یک خط)",
        "\n".join(sources.get("websites", [])),
        height=150
    )

    telegram = st.text_area(
        "کانال‌های عمومی تلگرام (بدون @)",
        "\n".join(sources.get("telegram", [])),
        height=130
    )

    instagram = st.text_area(
        "پیج‌های اینستاگرام (ثبت منبع؛ دریافت هنوز فعال نیست)",
        "\n".join(sources.get("instagram", [])),
        height=130
    )

    interval = st.number_input(
        "فاصله بررسی خودکار به دقیقه",
        min_value=5,
        max_value=1440,
        value=int(sources.get("interval", 15)),
        step=5
    )

    if st.button(
        "💾 ذخیره منابع",
        type="primary"
    ):

        sources["websites"] = [
            x.strip()
            for x in websites.splitlines()
            if x.strip()
        ]

        sources["telegram"] = [
            x.strip().lstrip("@")
            for x in telegram.splitlines()
            if x.strip()
        ]

        sources["instagram"] = [
            x.strip().lstrip("@")
            for x in instagram.splitlines()
            if x.strip()
        ]

        sources["interval"] = int(interval)

        save_sources(sources)

        st.success("منابع با موفقیت ذخیره شدند.")

        st.rerun()


# ---------------- ABOUT ----------------

elif page == "درباره برنامه":

    st.subheader("درباره Football Persian")

    st.write("""
    نسخه اولیه سامانه Football Persian

    امکانات فعلی:
    - پایش صفحه اصلی وب‌سایت‌های معرفی‌شده
    - دریافت پیش‌نمایش کانال‌های عمومی تلگرام
    - جلوگیری از ثبت دوباره لینک یک خبر
    - دسته‌بندی اولیه اخبار
    - تأیید یا رد خبر توسط مدیر
    - مدیریت منابع خبری
    - بررسی دوره‌ای در زمان باز بودن برنامه

    محدودیت‌ها:
    - دریافت مستقیم اخبار اینستاگرام هنوز فعال نیست.
    - برخی سایت‌ها ممکن است دسترسی ربات را محدود کنند.
    - کانال‌های تلگرام باید پیش‌نمایش عمومی داشته باشند.
    - دسته‌بندی فعلی بر اساس کلمات کلیدی است و هنوز هوش مصنوعی ندارد.
    - انتشار خودکار در اینستاگرام فعال نیست.
    - ذخیره‌سازی فعلی روی پایگاه داده محلی برنامه است؛
      برای استفاده پایدار و بلندمدت باید بعداً پایگاه داده دائمی متصل شود.
    """)

    if st.session_state.errors:

        with st.expander("گزارش خطاهای منابع"):

            for error in st.session_state.errors:
                st.write(error)
