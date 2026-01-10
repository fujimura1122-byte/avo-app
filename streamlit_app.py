import streamlit as st
import time
import pandas as pd
import os
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ==========================================
# 1. セキュリティ設定 (Secrets)
# ==========================================
try:
    TEAM_PASSWORD = st.secrets["team_password"]
    BOOKING_PASSWORD = st.secrets["booking_password"]
    USER_PROFILE = st.secrets["user_profile"]
except Exception:
    st.error("⚠️ Secretsの設定が不足しています。")
    st.stop()

TARGET_DEEL_FACILITIES = ["Sporthal Deel 1", "Sporthal Deel 2"]
TARGET_ACTIVITY_VALUE = "53" 
LOGO_IMAGE = "High Ballers.png"

st.set_page_config(page_title="High Ballers 予約", page_icon="⚽", layout="centered")

# ==========================================
# 2. ロジック関数 (ステルス・リトライ搭載)
# ==========================================
def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return webdriver.Chrome(options=options)

def get_dutch_date_str(date_obj):
    nl_m = {1:"jan", 2:"feb", 3:"mrt", 4:"apr", 5:"mei", 6:"jun", 7:"jul", 8:"aug", 9:"sep", 10:"okt", 11:"nov", 12:"dec"}
    return f"{date_obj.day}-{nl_m[date_obj.month]}-{date_obj.year}"

def get_japanese_date_str(date_obj):
    w = ["月","火","水","木","金","土","日"][date_obj.weekday()]
    return f"{date_obj.strftime('%Y/%m/%d')}({w})"

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
        driver.find_element(By.ID, "SearchButton").click()
        time.sleep(2)
        return True
    except: return False

def add_target():
    if 'p_date' in st.session_state:
        d = st.session_state.p_date
        pl = st.session_state.p_label
        p_val = {"Avond (夜)": "3", "Ochtend (朝)": "1", "Middag (昼)": "2"}[pl]
        if 'manual_targets' not in st.session_state: st.session_state.manual_targets = []
        item = {"date": d, "part": p_val, "disp": f"{get_japanese_date_str(d)} [{pl}]"}
        if not any(t['disp'] == item['disp'] for t in st.session_state.manual_targets):
            st.session_state.manual_targets.append(item)
            st.toast(f"✅ 追加: {item['disp']}")

# ==========================================
# 3. UIレイヤー (モバイルファースト)
# ==========================================
col_l, col_r = st.columns([1, 4])
with col_l: st.image(LOGO_IMAGE, width=80) if os.path.exists(LOGO_IMAGE) else st.write("⚽")
with col_r: st.markdown("### High Ballers 予約システム")

pw = st.text_input("認証パスワード", type="password")
if pw == TEAM_PASSWORD:
    st.success("認証OK")

    # --- モード選択 ---
    st.markdown("##### 🔍 検索モードを選択")
    mode = st.radio("目的に合わせて選択してください", 
        ["Deel 日付指定 (複数可)", "Deel 監視 (火木日)", "Deel 平日夜一括", "全施設 リサーチ", "全施設 日付指定 (複数可)"], 
        horizontal=False)

    # --- 日付指定UI (モードに応じて表示) ---
    if "日付指定" in mode:
        st.markdown("---")
        st.markdown("##### 📅 調べたい日付をリストに追加")
        c1, c2 = st.columns(2)
        with c1: st.selectbox("時間帯", ["Avond (夜)", "Ochtend (朝)", "Middag (昼)"], key="p_label")
        with c2: st.date_input("日付を選択", datetime.today(), key="p_date", on_change=add_target)
        
        if st.session_state.get('manual_targets'):
            df_t = pd.DataFrame(st.session_state.manual_targets)
            df_t["削除"] = False
            edit_t = st.data_editor(df_t[["削除", "disp"]], hide_index=True, use_container_width=True)
            if st.button("🗑️ 選択した日付を削除"):
                st.session_state.manual_targets = [st.session_state.manual_targets[i] for i in edit_t[edit_t["削除"]==False].index]
                st.rerun()

    # --- 検索実行 ---
    st.markdown("---")
    if st.button("🚀 Step 1: 空き状況を検索する", type="primary", use_container_width=True):
        targets = []
        today = datetime.now().date()
        if "日付指定" in mode:
            if not st.session_state.get('manual_targets'): st.error("日付をリストに追加してください。")
            else: targets = st.session_state.manual_targets
        elif "監視" in mode or "リサーチ" in mode:
            rules = [{"ws":[1,3],"p":"3"},{"ws":[6],"p":"1"}]
            for i in range(60):
                d = today + timedelta(days=i)
                for r in rules:
                    if d.weekday() in r['ws']: targets.append({"date":d, "part":r['p'], "disp":get_japanese_date_str(d)})
        elif "平日夜" in mode:
            for i in range(60):
                d = today + timedelta(days=i)
                if d.weekday() < 5: targets.append({"date":d, "part":"3", "disp":get_japanese_date_str(d)})

        if targets:
            st.session_state.found_slots = []
            driver = create_driver()
            prog = st.progress(0); status = st.empty()
            for i, t in enumerate(targets):
                prog.progress((i+1)/len(targets))
                status.text(f"検索中: {t.get('disp', t.get('date'))}")
                if search_on_site(driver, t['date'], t['part']):
                    items = driver.find_elements(By.CLASS_NAME, "item")
                    for item in items:
                        name = item.find_element(By.CLASS_NAME, "name").text.replace("\n", " ")
                        url = item.get_attribute("href")
                        is_deel = any(d in name for d in TARGET_DEEL_FACILITIES)
                        if "全施設" in mode or is_deel:
                            st.session_state.found_slots.append({"予約":False, "日付":t.get('disp', get_japanese_date_str(t['date'])), "施設名":name, "url":url, "date_obj":t['date'], "part":t['part']})
            driver.quit(); status.empty()
            if not st.session_state.found_slots: st.warning("空きは見つかりませんでした。")

    # --- 結果表示と予約実行 ---
    if st.session_state.get('found_slots'):
        st.markdown(f"##### ✨ 予約する枠を選択 ({len(st.session_state.found_slots)}件発見)")
        df_res = pd.DataFrame(st.session_state.found_slots)
        edited_res = st.data_editor(df_res[["予約", "日付", "施設名"]], hide_index=True, use_container_width=True)
        
        selected = [st.session_state.found_slots[i] for i in edited_res[edited_res["予約"]==True].index]
        if selected:
            st.markdown("---")
            rmode = st.radio("動作モード", ["✅ テスト", "🔥 本番"], horizontal=True)
            exec_pw = st.text_input("予約実行パスワード", type="password") if rmode == "🔥 本番" else "test"
            if st.button(f"🚀 {len(selected)}件を一括予約する", type="primary", use_container_width=True):
                if rmode == "🔥 本番" and exec_pw != BOOKING_PASSWORD: st.error("パスワード不正")
                else:
                    # ここに予約実行ロジック(perform_booking)
                    st.success("一括予約完了！(シミュレーション)")
                    st.balloons()
else:
    if pw: st.error("パスワードが違います")
