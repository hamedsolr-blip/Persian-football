import streamlit as st
import feedparser
import requests
from datetime import datetime

st.set_page_config(
    page_title="Persian Football",
    page_icon="⚽",
    layout="wide"
)

st.markdown("""
<style>
.stApp {
    background-color: #071629;
    color: white;
}
h1, h2, h3, p, label {
    color: white !important;
}
.news-card {
    background: #10243d;
    padding: 18px;
    border-radius: 12px;
    margin-bottom: 12px;
    border-right: 4px solid #d4af37;
}
.gold {
    color: #d4af37;
}
</style>
""", unsafe_allow_html=True)

st.markdown(
    "<h1 style='text-align:center;color:#d4af37'>⚽ PERSIAN FOOTBALL</h1>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center'>Football News & Transfer Center</p>",
    unsafe_allow_html=True
)

st.divider()

st.title("صف بررسی اخبار فوتبال")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("کل اخبار", "0")

with col2:
    st.metric("در انتظار بررسی", "0")

with col3:
    st.metric("تأیید شده", "0")

st.divider()

st.subheader("دسته‌بندی اخبار")

category = st.selectbox(
    "انتخاب دسته",
    [
        "همه اخبار",
        "فوتبال ایران",
        "فوتبال جهان",
        "نقل و انتقالات",
        "فوتبال پایه",
        "لیگ‌های ایران"
    ]
)

st.subheader("منابع خبری")

feeds = {
    "ورزش سه": "https://www.varzesh3.com/rss/all",
    "تسنیم": "https://www.tasnimnews.com/fa/rss/feed/0/7/0",
    "BBC Sport": "https://feeds.bbci.co.uk/sport/football/rss.xml"
}

if "approved" not in st.session_state:
    st.session_state.approved = []

if "rejected" not in st.session_state:
    st.session_state.rejected = []

if st.button("دریافت اخبار جدید"):
    st.session_state.news = []

    with st.spinner("در حال دریافت اخبار..."):
        for source, url in feeds.items():
            try:
                response = requests.get(
                    url,
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                parsed = feedparser.parse(response.content)

                for item in parsed.entries[:10]:
                    st.session_state.news.append({
                        "title": item.get("title", "بدون عنوان"),
                        "link": item.get("link", ""),
                        "source": source,
                        "summary": item.get("summary", "")
                    })

            except Exception:
                pass

if "news" not in st.session_state:
    st.session_state.news = []

news_list = st.session_state.news

st.write(f"تعداد اخبار دریافت‌شده: {len(news_list)}")

for index, news in enumerate(news_list):
    if category == "همه اخبار" or category == "فوتبال ایران":
        st.markdown(
            f"<div class='news-card'><h3>{news['title']}</h3>"
            f"<p>منبع: {news['source']}</p>"
            f"<p>{news['summary']}</p></div>",
            unsafe_allow_html=True
        )

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("✅ تأیید خبر", key=f"approve_{index}"):
            st.session_state.approved.append(news)
            st.success("خبر تأیید شد")

    with col_b:
        if st.button("❌ رد خبر", key=f"reject_{index}"):
            st.session_state.rejected.append(news)
            st.warning("خبر رد شد")

    if news["link"]:
        st.markdown(f"[مشاهده منبع اصلی]({news['link']})")

st.divider()

st.caption(
    "Persian Football | Football News & Transfer Center"
)
st.caption(
    "انتشار اخبار فقط پس از بررسی و تأیید مدیر انجام می‌شود."
)
