import streamlit as st
import time
import pandas as pd
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# =====================================================
# 🔐 Secrets & 定数
# =====================================================
try:
    TEAM_PASSWORD = st.secrets["team_password"]
    BOOKING_PASSWORD = st.secrets["booking_password"]
    USER_PROFILE = st.secrets["user_profile"]
except Exception:
    st.error("⚠️ secrets.toml の設定が不足しています")
    st.stop()

TARGET_DEEL_FACILITIES = ["Sporthal Deel 1", "Sporthal Deel 2"]
TARGET_ACTIVITY_VALUE = "53"
TARGET_URL = "https://avo.hta.nl/uithoorn/"

NL_MONTHS = {
    1: "jan", 2: "feb", 3: "mrt", 4: "apr",
    5: "mei", 6: "jun", 7: "jul", 8: "aug",
    9: "sep", 10: "okt", 11: "nov", 12: "dec"
}

# =====================================================
# Utility & Callback
# =====================================================
def get_dutch_date(d):
    return f"{d.day}-{NL_MONTHS[d.month]}-{d.year}"

def get_jp_date(d):
    return d.strftime("%Y/%m/%d") + "（" + "月火水木金土日"[d.weekday()] + "）"

def site_weekday(d):
    return str((d.weekday() + 1) % 7)

def get_time_text_by_part(part_id):
    if part_id == "1": return "09:00"
    if part_id == "2": return "13:00"
    return "20:00"

# ★ここが修正ポイント: 日付が変更されたら即座に追加する関数
def add_target_callback():
    # セッションステートから値を取得
    if "picker_date" in st.session_state and "picker_part" in st.session_state:
        selected_date = st.session_state.picker_date
        part_label = st.session_state.picker_part
        
        part_map = {"朝": "1", "昼": "2", "夜": "3"}
        part_id = part_map[part_label]
        
        if "manual_targets" not in st.session_state:
            st.session_state.manual_targets = []
            
        # 重複チェック
        is_exist = any(
            t["date"] == selected_date and t["part"] == part_id 
            for t in st.session_state.manual_targets
        )
        
        if not is_exist:
            st.session_state.manual_targets.append({
                "date": selected_date,
                "part": part_id,
                "label": part_label
            })
            # トーストで通知（画面上部にピョコっと出る）
            st.toast(f"✅ 追加しました: {get_jp_date(selected_date)} [{part_label}]")
        else:
            st.toast("⚠️ その枠は既に追加されています")

# =====================================================
# Selenium Driver
# =====================================================
def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

# =====================================================
# 検索機能
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
# 予約機能
# =====================================================
def book(driver, slot, dry_run):
    try:
        driver.get(slot["url"])
        WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.LINK_TEXT, "Naar reserveren"))).click()
        time.sleep(2)
        Select(driver.find_element(By.ID, "selectedTimeLength")).select_by_value("2")
        time.sleep(1)

        target_time_str = get_time_text_by_part(slot["part_id"])
        ts = Select(driver.find_element(By.ID, "customSelectedTimeSlot"))
        found_opt = False
        for opt in ts.options:
            if target_time_str in opt.text:
                ts.select_by_value(opt.get_attribute("value"))
                found_opt = True
                break
        
        if not found_opt:
            return False, f"時間枠({target_time_str}~)なし"

        Select(driver.find_element(By.ID, "SelectedActivity")).select_by_value(TARGET_ACTIVITY_VALUE)
        for k, v in USER_PROFILE.items():
            if v: driver.find_element(By.NAME, k).send_keys(v)

        chk = driver.find_element(By.NAME, "voorwaarden")
        if not chk.is_selected():
            driver.execute_script("arguments[0].click();", chk)

        if dry_run:
            return True, "テスト成功"

        driver.find_element(By.ID, "ConfirmButton").click()
        time.sleep(3)
        return True, "予約完了"
    except Exception as e:
        return False, str(e)

# =====================================================
# UI構成
# =====================================================
st.set_page_config(page_title="High Ballers 予約", layout="centered")
st.markdown("### ⚽ High Ballers 予約")

password = st.text_input("パスワード", type="password")
if password != TEAM_PASSWORD:
    if password: st.error("パスワードが違います")
    st.stop()

# --- モード選択 ---
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

# --- 日付指定UI (自動追加機能付き) ---
if mode in ["1", "5"]:
    st.markdown("---")
    st.markdown("##### 📅 カレンダーをタップして追加")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        # 時間帯を選んでおく
        st.selectbox("時間帯", ["夜", "朝", "昼"], key="picker_part")
    with col2:
        # ★ここが重要: on_change でコールバック関数を呼ぶ
        st.date_input(
            "日付を選択 (タップで追加)", 
            datetime.today(), 
            key="picker_date", 
            on_change=add_target_callback
        )

    # 追加済みリスト表示
    if st.session_state.manual_targets:
        st.info(f"現在 {len(st.session_state.manual_targets)} 件の日付を選択中")
        
        df_display = pd.DataFrame(st.session_state.manual_targets).assign(
            日付=lambda x: x["date"].apply(get_jp_date)
        )[["日付", "label"]]
        
        st.table(df_display)
        
        if st.button("リストをクリア"):
            st.session_state.manual_targets = []
            st.rerun()

# --- 検索処理 ---
st.markdown("---")
if st.button("🔍 検索開始", type="primary"):
    targets = []
    today = datetime.today().date()

    if mode in ["1", "5"]:
        targets = st.session_state.manual_targets
    elif mode == "2": 
        for i in range(60):
            d = today + timedelta(days=i)
            if d.weekday() in [1, 3]: targets.append({"date": d, "part": "3"})
            if d.weekday() == 6: targets.append({"date": d, "part": "1"})
    elif mode == "3": 
        for i in range(60):
            d = today + timedelta(days=i)
            if d.weekday() < 5: targets.append({"date": d, "part": "3"})
    elif mode == "4": 
        for i in range(60):
            d = today + timedelta(days=i)
            if d.weekday() in [1, 3]: targets.append({"date": d, "part": "3"})
            if d.weekday() == 6: targets.append({"date": d, "part": "1"})

    if not targets:
        st.warning("検索対象がありません。日付を指定するかモードを変更してください。")
    else:
        found = []
        driver = create_driver()
        is_deel_only = mode in ["1", "2", "3"]
        
        progress = st.progress(0)
        status = st.empty()

        for i, t in enumerate(targets):
            progress.progress((i + 1) / len(targets))
            status.text(f"検索中... {get_jp_date(t['date'])}")
            try:
                items = search(driver, t["date"], t["part"])
                for it in items:
                    name = it.find_element(By.CLASS_NAME, "name").text.replace("\n", " ")
                    if (is_deel_only and any(x in name for x in TARGET_DEEL_FACILITIES)) or not is_deel_only:
                        found.append({
                            "date": t["date"],
                            "facility": name,
                            "url": it.get_attribute("href"),
                            "part_id": t["part"],
                            "予約する": False
                        })
            except: pass

        driver.quit()
        status.empty()
        progress.empty()
        st.session_state.found = found
        
        if not found:
            st.warning("空きは見つかりませんでした")

# --- 予約処理 ---
if "found" in st.session_state and st.session_state.found:
    st.subheader(f"✨ 発見: {len(st.session_state.found)} 件")
    df = pd.DataFrame(st.session_state.found)
    df["日付"] = df["date"].apply(get_jp_date)
    df["時間帯"] = df["part_id"].map({"1":"朝", "2":"昼", "3":"夜"})

    edited = st.data_editor(
        df[["予約する", "日付", "時間帯", "facility"]], 
        hide_index=True,
        column_config={"予約する": st.column_config.CheckboxColumn(default=False)}
    )

    selected_indices = edited.index[edited["予約する"]].tolist()
    slots = [st.session_state.found[i] for i in selected_indices]

    if slots:
        st.markdown("---")
        run_mode = st.radio("実行モード", ["テスト", "本番"], horizontal=True)
        can_run = True
        if run_mode == "本番":
            if st.text_input("予約パスワード", type="password") != BOOKING_PASSWORD:
                can_run = False
        
        if st.button("🚀 予約実行", type="primary", disabled=not can_run):
            driver = create_driver()
            results = []
            progress_bar = st.progress(0)
            for i, s in enumerate(slots):
                progress_bar.progress((i+1)/len(slots))
                success, msg = book(driver, s, run_mode == "テスト")
                icon = "✅" if success else "❌"
                results.append(f"{icon} {s['facility']} ({get_jp_date(s['date'])}): {msg}")
            
            driver.quit()
            progress_bar.empty()
            st.markdown("### 実行結果")
            st.text("\n".join(results))
            if any("✅" in r for r in results):
                st.balloons()
