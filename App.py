
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
    "User-Agent": "Mozilla/5.0 (compatible; FootballPersian/2.0)"
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

    # ارتقای جدول قبلی بدون حذف اخبار موجود
    columns = [
        row[1] for row in
        con.execute("PRAGMA table_info(news)").fetchall()
    ]

    new_columns = {
        "source_text": "TEXT",
        "rewritten_title": "TEXT",
        "rewritten_body": "TEXT",
        "updated_at": "TEXT"
    }

    for column, data_type in new_columns.items():
        if column not in columns:
            con.execute(
                f"ALTER TABLE news ADD COLUMN {column} {data_type}"
            )

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


# ---------------- NEWS ----------------

def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def detect_category(title):
    text = title.lower()

    transfer_words = [
        "انتقال", "نقل و انتقال", "قرارداد",
        "جذب", "تمدید", "فسخ", "transfer", "signing"
    ]

    player_words = [
        "بازیکن", "فوتبالیست", "مهاجم",
        "دروازه بان", "مدافع", "هافبک", "player"
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
            detect_category(title),
            "در انتظار بررسی",
            datetime.now(timezone.utc).isoformat()
        ))

        con.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        con.close()


def get_news(search="", status="همه"):
    con = connect_db()

    sql = """
        SELECT id, title, url, source, category, status,
               created_at, source_text, rewritten_title,
               rewritten_body
        FROM news
    """

    conditions = []
    params = []

    if status != "همه":
        conditions.append("status=?")
        params.append(status)

    if search:
        conditions.append("(title LIKE ? OR source LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY id DESC LIMIT 300"

    rows = con.execute(sql, params).fetchall()
    con.close()

    return rows


def save_article_text(news_id, source_text):
    con = connect_db()
    con.execute("""
        UPDATE news
        SET source_text=?, updated_at=?
        WHERE id=?
    """, (
        source_text,
        datetime.now(timezone.utc).isoformat(),
        news_id
    ))
    con.commit()
    con.close()


def save_rewrite(news_id, new_title, new_body):
    con = connect_db()
    con.execute("""
        UPDATE news
        SET rewritten_title=?, rewritten_body=?, updated_at=?
        WHERE id=?
    """, (
        new_title,
        new_body,
        datetime.now(timezone.utc).isoformat(),
        news_id
    ))
    con.commit()
    con.close()


def update_news_status(news_id, status):
    con = connect_db()
    con.execute(
        "UPDATE news SET status=?, updated_at=? WHERE id=?",
        (status, datetime.now(timezone.utc).isoformat(), news_id)
    )
    con.commit()
    con.close()


# ---------------- SMART EDITOR ----------------

def make_rewrite_prompt(title, source, article_text):
    return f"""
تو دبیر تحریریه حرفه‌ای رسانه فوتبال فارسی هستی.

وظیفه تو بازنویسی مستقل خبر زیر است.

قوانین مهم:
1. متن را با جمله‌بندی تازه و متفاوت بنویس.
2. متن را عیناً از منبع کپی نکن.
3. تیتر جذاب، حرفه‌ای و خبری تولید کن.
4. اطلاعات واقعی، نام اشخاص، باشگاه‌ها، اعداد و تاریخ‌ها را حفظ کن.
5. هیچ اطلاعات، نقل‌قول یا اتفاقی را از خودت اضافه نکن.
6. اگر بخشی از خبر مبهم یا تأییدنشده است، آن را قطعی جلوه نده.
7. لحن رسمی، روان و مناسب رسانه ورزشی فارسی باشد.
8. از بزرگ‌نمایی و تیتر گمراه‌کننده خودداری کن.
9. متن نهایی مستقل و قابل انتشار باشد.

خروجی را دقیقاً در دو بخش بده:

تیتر پیشنهادی:
[تیتر جدید]

متن بازنویسی‌شده:
[متن کامل خبر]

عنوان اولیه:
{title}

منبع:
{source}

متن اصلی خبر:
{article_text}
"""


# ---------------- COLLECT SOURCES ----------------

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


# ---------------- PAGE SETTINGS ----------------

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

if "prompts" not in st.session_state:
    st.session_state.prompts = {}

st.title("⚽ Football Persian")

st.caption(
    "سامانه پایش اخبار فوتبال و تحریریه هوشمند"
)

st.info(
    "اخبار از منابع معرفی‌شده دریافت می‌شوند. "
    "بازنویسی و تأیید نهایی با نظارت مدیر انجام می‌شود."
)

sources = get_sources()


# ---------------- AUTOMATIC CHECK ----------------

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
            f"بررسی انجام شد؛ {new_count} مطلب جدید ذخیره شد."
        )


automatic_check()


# ---------------- SIDEBAR ----------------

with st.sidebar:
    st.header("⚽ منوی اصلی")

    page = st.radio(
        "انتخاب بخش",
        [
            "داشبورد اخبار",
            "تحریریه هوشمند",
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

        st.success(f"{new_count} خبر جدید دریافت شد.")
        st.rerun()


# ---------------- DASHBOARD ----------------

if page == "داشبورد اخبار":

    rows = get_news()

    waiting = sum(1 for row in rows if row[5] == "در انتظار بررسی")
    approved = sum(1 for row in rows if row[5] == "تأیید شده")
    rejected = sum(1 for row in rows if row[5] == "رد شده")

    col1, col2, col3 = st.columns(3)

    col1.metric("کل اخبار", len(rows))
    col2.metric("در انتظار بررسی", waiting)
    col3.metric("تأییدشده", approved)

    st.caption(f"اخبار ردشده: {rejected}")

    st.divider()

    search = st.text_input("جستجو در اخبار")

    status_filter = st.selectbox(
        "فیلتر وضعیت",
        ["همه", "در انتظار بررسی", "تأیید شده", "رد شده"]
    )

    news = get_news(search, status_filter)

    if not news:
        st.info("خبری برای نمایش وجود ندارد.")

    for item in news:
        (
            news_id, title, url, source, category,
            status, created, source_text,
            rewritten_title, rewritten_body
        ) = item

        with st.container(border=True):
            st.markdown(f"**{title}**")

            st.caption(
                f"منبع: {source} | دسته: {category} | وضعیت: {status}"
            )

            st.markdown(f"[مشاهده خبر اصلی]({url})")

            if rewritten_title and rewritten_body:
                st.success("نسخه بازنویسی‌شده آماده است.")
                st.markdown(f"**{rewritten_title}**")
                st.write(rewritten_body)

            col1, col2 = st.columns(2)

            with col1:
                if st.button("✍️ باز کردن در تحریریه", key=f"edit_{news_id}"):
                    st.session_state.selected_news = news_id
                    st.session_state.current_page = "تحریریه هوشمند"
                    st.rerun()

            with col2:
                if status == "تأیید شده":
                    st.success("این خبر تأیید شده است.")
                elif status == "رد شده":
                    st.warning("این خبر رد شده است.")


# ---------------- SMART EDITOR ----------------

elif page == "تحریریه هوشمند":

    st.subheader("✍️ تحریریه هوشمند Football Persian")

    st.write(
        "در این بخش متن اصلی خبر را وارد می‌کنی، "
        "دستور بازنویسی می‌گیری و نتیجه را برای بررسی ذخیره می‌کنی."
    )

    all_news = get_news()

    if not all_news:
        st.info("هنوز خبری دریافت نشده است.")
    else:
        options = {
            f"{row[0]} - {row[1][:75]}": row
            for row in all_news
        }

        default_index = 0
        selected_id = st.session_state.get("selected_news")

        if selected_id:
            for i, row in enumerate(all_news):
                if row[0] == selected_id:
                    default_index = i
                    break

        selected_label = st.selectbox(
            "انتخاب خبر",
            list(options.keys()),
            index=default_index
        )

        item = options[selected_label]

        (
            news_id, title, url, source, category,
            status, created, source_text,
            rewritten_title, rewritten_body
        ) = item

        st.markdown(f"**تیتر اولیه:** {title}")
        st.caption(f"منبع: {source} | دسته: {category}")
        st.markdown(f"[باز کردن خبر اصلی]({url})")

        article_input = st.text_area(
            "متن کامل خبر اصلی را اینجا وارد کن",
            value=source_text or "",
            height=250,
            placeholder="متن کامل خبر را از سایت یا کانال اصلی کپی و اینجا وارد کن..."
        )

        if st.button(
            "ساخت دستور بازنویسی",
            type="primary",
            use_container_width=True
        ):
            if len(article_input.strip()) < 50:
                st.warning("لطفاً متن کامل‌تری از خبر وارد کن.")
            else:
                save_article_text(news_id, article_input)

                prompt = make_rewrite_prompt(
                    title,
                    source,
                    article_input
                )

                st.session_state.prompts[news_id] = prompt

                st.success(
                    "دستور بازنویسی آماده شد. آن را کپی کن و در ChatGPT وارد کن."
                )

        prompt = st.session_state.prompts.get(news_id)

        if prompt:
            st.markdown("### دستور آماده برای ChatGPT")

            st.text_area(
                "متن دستور را انتخاب و کپی کن",
                value=prompt,
                height=300,
                key=f"prompt_{news_id}"
            )

            st.caption(
                "این متن را در یک گفت‌وگوی ChatGPT وارد کن و نتیجه بازنویسی را بگیر."
            )

        st.divider()

        st.markdown("### ثبت نتیجه بازنویسی")

        new_title = st.text_input(
            "تیتر جدید",
            value=rewritten_title or "",
            key=f"new_title_{news_id}"
        )

        new_body = st.text_area(
            "متن بازنویسی‌شده",
            value=rewritten_body or "",
            height=250,
            key=f"new_body_{news_id}"
        )

        if st.button(
            "💾 ذخیره نسخه بازنویسی‌شده",
            type="primary",
            use_container_width=True
        ):
            if not new_title.strip() or not new_body.strip():
                st.warning("تیتر و متن بازنویسی‌شده را وارد کن.")
            else:
                save_rewrite(
                    news_id,
                    new_title.strip(),
                    new_body.strip()
                )

                st.success("نسخه بازنویسی‌شده ذخیره شد.")
                st.rerun()

        st.divider()

        st.markdown("### تأیید نهایی خبر")

        if rewritten_title and rewritten_body:
            st.markdown(f"**{rewritten_title}**")
            st.write(rewritten_body)

            if st.button(
                "✅ تأیید نهایی خبر",
                type="primary",
                use_container_width=True
            ):
                update_news_status(news_id, "تأیید شده")
                st.success("خبر تأیید شد.")
                st.rerun()
        else:
            st.info(
                "ابتدا نسخه بازنویسی‌شده را ذخیره کن؛ "
                "سپس امکان تأیید نهایی فعال می‌شود."
            )

        if st.button(
            "❌ رد کردن این خبر",
            use_container_width=True
        ):
            update_news_status(news_id, "رد شده")
            st.warning("خبر رد شد.")
            st.rerun()


# ---------------- SOURCE MANAGEMENT ----------------

elif page == "مدیریت منابع":

    st.subheader("مدیریت منابع خبری")

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

    if st.button("💾 ذخیره منابع", type="primary"):
        sources["websites"] = [
            x.strip() for x in websites.splitlines() if x.strip()
        ]

        sources["telegram"] = [
            x.strip().lstrip("@")
            for x in telegram.splitlines() if x.strip()
        ]

        sources["instagram"] = [
            x.strip().lstrip("@")
            for x in instagram.splitlines() if x.strip()
        ]

        sources["interval"] = int(interval)

        save_sources(sources)

        st.success("منابع ذخیره شدند.")
        st.rerun()


# ---------------- ABOUT ----------------

elif page == "درباره برنامه":

    st.subheader("درباره Football Persian")

    st.write("""
    نسخه دوم سامانه Football Persian

    امکانات:
    - دریافت اخبار از وب‌سایت‌های معرفی‌شده
    - دریافت مطالب کانال‌های عمومی تلگرام
    - جلوگیری از ثبت دوباره لینک یک خبر
    - دسته‌بندی اولیه اخبار
    - تحریریه برای بازنویسی دستی با کمک ChatGPT
    - ذخیره متن اصلی و نسخه بازنویسی‌شده
    - تأیید یا رد خبر توسط مدیر
    - مدیریت منابع خبری

    محدودیت‌ها:
    - دریافت مستقیم اینستاگرام هنوز فعال نیست.
    - بازنویسی خودکار API هنوز متصل نشده است.
    - بررسی دوره‌ای فقط هنگام فعال بودن برنامه انجام می‌شود.
    - برای ذخیره‌سازی پایدار در بلندمدت، پایگاه داده دائمی لازم است.
    """)

    if st.session_state.errors:
        with st.expander("گزارش خطاهای منابع"):
            for error in st.session_state.errors:
                st.write(error)
