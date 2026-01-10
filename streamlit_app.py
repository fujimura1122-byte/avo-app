import streamlit as st
import time
import smtplib
import os
import pandas as pd
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ==========================================
# 設定と認証 (Secretsから読み込み)
# ==========================================
try:
    TEAM_PASSWORD = st.secrets["team_password"]
    BOOKING_PASSWORD = st.secrets["booking_password"]
    USER_PROFILE = st.secrets["user_profile"]
except Exception:
    st.error("⚠️ Secretsの設定を確認してください。")
    st.stop()

TARGET_DEEL_FACILITIES = ["Sporthal Deel 1", "Sporthal Deel 2"]
TARGET_ACTIVITY_VALUE = "53" 
LOGO_IMAGE = "High Ballers.png"

st.set_page_config(page_title="High Ballers 予約監視", page_icon="⚽", layout="centered")

# ==========================================
# ロジック関数
# ==========================================
NL_MONTHS = {1: "jan", 2: "feb", 3: "mrt", 4: "apr", 5: "mei", 6: "jun", 7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec"}

def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)

def get_dutch_date_str(date_obj):
    return f"{date_obj.day}-{NL_MONTHS[date_obj.month]}-{date_obj.year}"

def get_japanese_date_str(date_obj):
    w = ["月","火","水","木","金","土","日"][date_obj.weekday()]
    return f"{date_obj.strftime('%Y/%m/%d')}({w})"

def get_target_time_text(date_obj):
    return "09:00" if date_obj.weekday() == 6 else "20:00"

def search_on_site(driver, date_obj, part_id):
    try:
        driver.get("https://avo.hta.nl/uithoorn/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "SearchButton")))
        d_str = get_dutch_date_str(date_obj)
        date_input = driver.find_element(By.XPATH, "//div[@id='searchDateCalDiv']/preceding-sibling::input")
        driver.execute_script(f"arguments[0].value = '{d_str}';", date_input)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", date_input)
        Select(driver.find_element(By.ID, "DayOfTheWeek")).select_by_value(str((date_obj.weekday() + 1) % 7))
        Select(driver.find_element(By.ID, "Daypart")).select_by_value(part_id)
        Select(driver.find_element(By.ID, "Duration")).select_by_value("2")
        Select(driver.find_element(By.ID, "Activity")).select_by_value("53")
        driver.find_element(By.ID, "SearchButton").click()
        time.sleep(2)
        return True
    except: return False

def perform_booking(driver, facility_name, date_obj, target_url, is_dry_run, container):
    target_time_text = get_target_time_text(date_obj)
    try:
        items = driver.find_elements(By.CLASS_NAME, "item")
        found = next((i for i in items if i.get_attribute("href") == target_url), None)
        if not found: return False
        driver.execute_script("arguments[0].click();", found)
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Naar reserveren')]"))).click()
        time.sleep(2)
        Select(driver.find_element(By.ID, "selectedTimeLength")).select_by_value("2")
        time.sleep(1)
        time_select = Select(driver.find_element(By.ID, "customSelectedTimeSlot"))
        slot = next((o for o in time_select.options if target_time_text in o.text), None)
        if not slot: return False
        time_select.select_by_value(slot.get_attribute("value"))
        Select(driver.find_element(By.ID, "SelectedActivity")).select_by_value(TARGET_ACTIVITY_VALUE)
        for k, v in USER_PROFILE.items():
            if k == "HouseNumberAddition" and v == "": continue
            driver.find_element(By.NAME, k).send_keys(v)
        chk = driver.find_element(By.NAME, "voorwaarden")
        if not chk.is_selected(): driver.execute_script("arguments[0].click();", chk)
        if is_dry_run: return True
        driver.find_element(By.ID, "ConfirmButton").click()
        time.sleep(3)
        return True
    except: return False

# ==========================================
# UI
# ==========================================
st.title("⚽ High Ballers 予約監視")
password = st.text_input("パスワード", type="password")

if password == TEAM_PASSWORD:
    st.success("認証OK")
    
    # 1. 日付指定エリア (共通)
    if 'manual_targets' not in st.session_state: st.session_state.manual_targets = []
    
    with st.expander("📅 検索する日付を追加 (複数可)", expanded=True):
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1: in_date = st.date_input("日付", datetime.today())
        with col2:
            p_opts = {"Avond (夜)": "3", "Ochtend (朝)": "1", "Middag (昼)": "2"}
            p_label = st.selectbox("時間帯", list(p_opts.keys()))
        with col3:
            st.write(" ")
            if st.button("追加"):
                st.session_state.manual_targets.append({"date": in_date, "part": p_opts[p_label], "lbl": p_label})
        
        if st.session_state.manual_targets:
            for i, t in enumerate(st.session_state.manual_targets):
                st.write(f"・{get_japanese_date_str(t['date'])} [{t['lbl']}]")
            if st.button("リストをクリア"): 
                st.session_state.manual_targets = []
                st.rerun()

    # 2. モード選択
    mode = st.radio("検索モード", ["1. 【Deel専用】指定日検索", "2. 【Deel専用】自動監視(火木日)", "3. 【全施設】リサーチ & 予約"], horizontal=True)

    if st.button("🔍 Step 1: 空き検索開始", type="primary", use_container_width=True):
        targets = []
        today = datetime.now().date()
        
        if "1." in mode or ("3." in mode and st.session_state.manual_targets):
            targets = st.session_state.manual_targets
        elif "2." in mode:
            rules = [{"ws": [1, 3], "part": "3", "lbl": "夜"}, {"ws": [6], "part": "1", "lbl": "朝"}]
            for i in range(60):
                d = today + timedelta(days=i)
                for r in rules:
                    if d.weekday() in r['ws']: targets.append({"date": d, "part": r['part'], "lbl": r['lbl']})
        elif "3." in mode: # 日付指定がない場合の全施設デフォルト
            rules = [{"ws": [1, 3], "part": "3", "lbl": "夜"}, {"ws": [6], "part": "1", "lbl": "朝"}]
            for i in range(30):
                d = today + timedelta(days=i)
                for r in rules:
                    if d.weekday() in r['ws']: targets.append({"date": d, "part": r['part'], "lbl": r['lbl']})

        if not targets:
            st.error("検索対象の日付がありません。")
        else:
            st.session_state.found_slots = []
            driver = create_driver()
            bar = st.progress(0)
            for i, t in enumerate(targets):
                bar.progress((i+1)/len(targets))
                if search_on_site(driver, t['date'], t['part']):
                    items = driver.find_elements(By.CLASS_NAME, "item")
                    for item in items:
                        f_name = item.find_element(By.CLASS_NAME, "name").text.replace("\n", " ")
                        url = item.get_attribute("href")
                        is_deel = any(d in f_name for d in TARGET_DEEL_FACILITIES)
                        if ("3." in mode) or is_deel:
                            st.session_state.found_slots.append({
                                "display": f"{get_japanese_date_str(t['date'])} {f_name}",
                                "date_obj": t['date'], "facility": f_name, "part_id": t['part'], "url": url
                            })
            driver.quit()
            if not st.session_state.found_slots: st.warning("空きなし")

    # 3. 予約実行
    if st.session_state.get('found_slots'):
        st.write("---")
        options = [s["display"] for s in st.session_state.found_slots]
        sel = st.multiselect("予約する枠を選択", options)
        
        if sel:
            run_m = st.radio("動作", ["テスト", "本番"], horizontal=True)
            bk_pass = st.text_input("実行パスワード", type="password")
            if st.button("🚀 Step 2: 予約実行", use_container_width=True):
                if run_m == "本番" and bk_pass != BOOKING_PASSWORD:
                    st.error("パスワード不正")
                else:
                    driver = create_driver()
                    for opt in sel:
                        data = next(s for s in st.session_state.found_slots if s["display"] == opt)
                        search_on_site(driver, data['date_obj'], data['part_id'])
                        if perform_booking(driver, data['facility'], data['date_obj'], data['url'], run_m=="テスト", st):
                            st.success(f"完了: {opt}")
                        else: st.error(f"失敗: {opt}")
                    driver.quit()
                    st.balloons()
