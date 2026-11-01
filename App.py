
import streamlit as st
import feedparser
from datetime import datetime

st.set_page_config(
    page_title="PERSIAN FOOTBALL | Football News",
    page_icon="⚽",
    layout="wide"
)

st.markdown("""
<style>
.stApp {
    background-color: #081426;
    color: white;
}
h1, h2, h3, p, label {
    color: white !important;
}
</style>
""", unsafe_allow_html=True)

st.title("⚽ EASY TRANSFER")
st.subheader("Football News & Transfer Center")

st.info("ربات مدیریت اخبار و نقل‌وانتقالات فوتبال")

feeds = {
    "BBC Sport": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "Sky Sports": "https://www.skysports.com/rss/12040",
    "Google Football": "https://news.google.com/rss/search?q=football+transfers&hl=en&gl=US&ceid=US:en",
    "اخبار فوتبال ایران": "https://news.google.com/rss/search?q=اخبار+نقل+و+انتقالات+فوتبال+ایران&hl=fa&gl=IR&ceid=IR:fa"
}

st.write("### 📰 آخرین اخبار فوتبال")

selected = st.selectbox(
    "انتخاب منبع خبری",
    list(feeds.keys())
)

if st.button("دریافت اخبار"):
    with st.spinner("در حال دریافت اخبار..."):
        try:
            news = feedparser.parse(feeds[selected])

            if not news.entries:
                st.warning("خبری دریافت نشد.")
            else:
                for item in news.entries[:20]:
                    st.markdown("---")
                    st.markdown("### " + item.get("title", "بدون عنوان"))
                    st.write(item.get("published", ""))
                    st.write(item.get("summary", ""))
                    link = item.get("link", "")
                    if link:
                        st.markdown(f"[مشاهده خبر]({link})")

        except Exception as e:
            st.error(f"خطا در دریافت اخبار: {e}")

st.markdown("---")
st.subheader("✍️ آماده‌سازی پست")

post_text = st.text_area(
    "متن خبر یا پست پیشنهادی را وارد کنید:"
)

if st.button("آماده‌سازی پست"):
    if post_text.strip():
        st.session_state["draft"] = post_text
        st.success("پیش‌نویس آماده شد؛ قبل از انتشار بررسی کنید.")
    else:
        st.warning("ابتدا متن را وارد کنید.")

if "draft" in st.session_state:
    st.text_area(
        "پیش‌نویس قابل بررسی",
        value=st.session_state["draft"],
        height=180
    )

st.caption(
    "Easy Transfer | Football News Management | " +
    datetime.now().strftime("%Y-%m-%d %H:%M")
)
