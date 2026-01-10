import streamlit as st
import time
import os
import pandas as pd
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# =====================================================
# 🔐 Secrets（必須）
# =====================================================
try:
    TEAM_PASSWORD = st.secrets["team_password"]
    BOOKING_PASSWORD = st.secrets["booking_password"]
    USER_PROFILE = st.secrets["user_profile"]
except Exception:
    st.error("⚠️ secrets.toml の設定が不足しています")
    st.stop()

# =====================================================
# 定数
# =====================================================
TARGET_DEEL_FACILITIES = ["Sporthal Deel 1", "Sporthal Deel 2"]
TARGET_ACTIVITY_VALUE = "53"
LOGO_IMAGE = "High Ballers.png"
TARGET_URL = "https://avo.hta.nl/uithoorn/"

NL_MONTHS = {
    1: "jan", 2: "feb", 3: "mrt", 4: "apr",
    5: "mei", 6: "jun", 7: "jul", 8: "aug",
    9: "sep", 10: "okt", 11: "nov", 12: "dec"
}

# =====================================================
# Selenium Driver（ステルス）
# =====================================================
def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)

# =====================================================
# Utility
# =====================================================
def get_dutch_date(d): return f"{d.day}-{NL_MONTHS[d.month]}-{d.year}"
def get_jp_date(d): return d.strftime("%Y/%m/%d") + "（" + "月火水木金土日"[d.weekday()] + "）"
def site_weekday(d): return str((d.weekday() + 1) % 7)
def target_time(d): return "09:00" if d.weekday() == 6 else "20:00"

# =====================================================
# 検索
# =====================================================
def search(driver, date_obj, part_id):
    driver.get(TARGET_URL)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "SearchButton")))

    d_str = get_dutch_date(date_obj)
    date_input = driver.find_element(By.XPATH, "//div[@id='searchDateCalDiv']/preceding-sibling::input")
    driver.execute_script(f"arguments[0].value='{d_str}';arguments[0].dispatchEvent(new Event('change'));", date_input)

    Select(driver.find_element(By.ID, "DayOfTheWeek")).select_by_value(site_weekday(date_obj))
    Select(driver.find_element(By.ID, "Daypart")).select_by_value(part_id)
    Select(driver.find_element(By.ID, "Duration")).select_by_value("2")
    Select(driver.find_element(By.ID, "Activity")).select_by_value(TARGET_ACTIVITY_VALUE)
    driver.find_element(By.ID, "SearchButton").click()
    time.sleep(2)
    return driver.find_elements(By.CLASS_NAME, "item")

# =====================================================
# 予約
# =====================================================
def book(driver, slot, dry_run):
    driver.get(slot["url"])
    WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.LINK_TEXT, "Naar reserveren"))).click()
    time.sleep(2)

    Select(driver.find_element(By.ID, "selectedTimeLength")).select_by_value("2")
    time.sleep(1)

    ts = Select(driver.find_element(By.ID, "customSelectedTimeSlot"))
    for opt in ts.options:
        if target_time(slot["date"]) in opt.text:
            ts.select_by_value(opt.get_attribute("value"))
            break
    else:
        return False

    Select(driver.find_element(By.ID, "SelectedActivity")).select_by_value(TARGET_ACTIVITY_VALUE)

    for k, v in USER_PROFILE.items():
        if v:
            driver.find_element(By.NAME, k).send_keys(v)

    chk = driver.find_element(By.NAME, "voorwaarden")
    if not chk.is_selected():
        driver.execute_script("arguments[0].click();", chk)

    if dry_run:
        return True

    driver.find_element(By.ID, "ConfirmButton").click()
    time.sleep(3)
    return True

# =====================================================
# UI
# =====================================================
st.set_page_config(page_title="High Ballers 予約", layout="centered")

st.markdown("### ⚽ High Ballers 予約")

password = st.text_input("パスワード", type="password")

if password != TEAM_PASSWORD:
    if password:
        st.error("パスワードが違います")
    st.stop()

# =====================================================
# モード
# =====================================================
st.error("DEBUG: 新しい mode_map が読み込まれています")
mode_map = {
    "1. Deel日付指定 (複数可)": "1",
    "2. Deel監視 (火木日)": "2",
    "3. Deel平日夜一括": "3",
    "4. 全施設リサーチ": "4",
    "5. 日付指定 (複数可) 全施設": "5",
}
mode = mode_map[st.radio("検索モード", list(mode_map.keys()), horizontal=True)]

if "manual_targets" not in st.session_state:
    st.session_state.manual_targets = []

# =====================================================
# 日付指定UI（mode 1 & 5）
# =====================================================
if mode in ["1", "5"]:
    col1, col2 = st.columns(2)
    with col1:
        part_label = st.selectbox("時間帯", ["夜", "朝", "昼"])
    with col2:
        d = st.date_input("日付", datetime.today())

    if st.button("➕ 追加"):
        part_map = {"朝": "1", "昼": "2", "夜": "3"}
        st.session_state.manual_targets.append({
            "date": d,
            "part": part_map[part_label]
        })

# =====================================================
# 検索
# =====================================================
if st.button("🔍 検索開始", type="primary"):
    targets = []
    today = datetime.today().date()

    if mode in ["1", "5"]:
        targets = st.session_state.manual_targets

    elif mode == "2":
        for i in range(60):
            d = today + timedelta(days=i)
            if d.weekday() in [1, 3]:
                targets.append({"date": d, "part": "3"})
            if d.weekday() == 6:
                targets.append({"date": d, "part": "1"})

    elif mode == "3":
        for i in range(60):
            d = today + timedelta(days=i)
            if d.weekday() < 5:
                targets.append({"date": d, "part": "3"})

    elif mode == "4":
        for i in range(60):
            d = today + timedelta(days=i)
            targets.append({"date": d, "part": "3"})

    found = []
    driver = create_driver()
    is_deel_only = mode in ["1", "2", "3"]

    for t in targets:
        items = search(driver, t["date"], t["part"])
        for it in items:
            name = it.find_element(By.CLASS_NAME, "name").text
            if (is_deel_only and any(x in name for x in TARGET_DEEL_FACILITIES)) or not is_deel_only:
                found.append({
                    "date": t["date"],
                    "facility": name,
                    "url": it.get_attribute("href"),
                    "予約する": False
                })

    driver.quit()
    st.session_state.found = found

# =====================================================
# 予約
# =====================================================
if "found" in st.session_state and st.session_state.found:
    df = pd.DataFrame(st.session_state.found)
    df["日付"] = df["date"].apply(get_jp_date)

    edited = st.data_editor(df[["予約する", "日付", "facility"]], hide_index=True)

    selected = edited[edited["予約する"] == True].index.tolist()
    slots = [st.session_state.found[i] for i in selected]

    if slots:
        run = st.radio("実行モード", ["テスト", "本番"], horizontal=True)
        if run == "本番":
            if st.text_input("予約パスワード", type="password") != BOOKING_PASSWORD:
                st.stop()

        if st.button("🚀 予約実行"):
            driver = create_driver()
            for s in slots:
                book(driver, s, run == "テスト")
            driver.quit()
            st.success("完了しました")

