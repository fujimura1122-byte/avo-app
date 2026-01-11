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
# Utility
# =====================================================
def get_dutch_date(d):
    # 日付のゼロ埋め等のフォーマット揺れを防ぐため念の為str変換
    return f"{d.day}-{NL_MONTHS[d.month]}-{d.year}"

def get_jp_date(d):
    return d.strftime("%Y/%m/%d") + "（" + "月火水木金土日"[d.weekday()] + "）"

def site_weekday(d):
    return str((d.weekday() + 1) % 7)

# ★修正点: 時間帯IDから、予約枠の検索テキスト（目安）を返す
def get_time_text_by_part(part_id):
    # 1=朝, 2=昼, 3=夜
    if part_id == "1": return "09:00" # 朝の代表値
    if part_id == "2": return "13:00" # 昼の代表値 (施設の枠によるが仮置き)
    return "20:00" # 夜の代表値

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
    
    # webdriver_managerを使用（Cloud環境での安定性向上）
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

        # ★修正: 検索時に使ったpart_idに対応する時間を探す
        target_time_str = get_time_text_by_part(slot["part_id"])
        
        ts = Select(driver.find_element(By.ID, "customSelectedTimeSlot"))
        found_opt = False
        for opt in ts.options:
            # 部分一致で探す
            if target_time_str in opt.text:
                ts.select_by_value(opt.get_attribute("value"))
                found_opt = True
                break
        
        # 見つからない場合、バックアップ（20:00で見つからなくても19:00や21:00があるかもなので先頭を選ぶ等のロジックも可だが今回はエラーにする）
        if not found_opt:
            return False, f"時間枠({target_time_str}~)が見つかりませんでした"

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

# --- 日付指定UI ---
if mode in ["1", "5"]:
    col1, col2 = st.columns(2)
    with col1: part_label = st.selectbox("時間帯", ["夜", "朝", "昼"])
    with col2: d = st.date_input("日付", datetime.today())

    if st.button("➕ 追加"):
        part_map = {"朝": "1", "昼": "2", "夜": "3"}
        st.session_state.manual_targets.append({
            "date": d,
            "part": part_map[part_label],
            "label": part_label
        })
    
    # 追加済みリスト表示
    if st.session_state.manual_targets:
        st.caption("検索リスト:")
        st.table(pd.DataFrame(st.session_state.manual_targets).assign(
            日付=lambda x: x["date"].apply(get_jp_date)
        )[["日付", "label"]])
        if st.button("クリア"):
            st.session_state.manual_targets = []
            st.rerun()

# --- 検索処理 ---
if st.button("🔍 検索開始", type="primary"):
    targets = []
    today = datetime.today().date()

    if mode in ["1", "5"]:
        targets = st.session_state.manual_targets

    elif mode == "2": # Deel監視
        for i in range(60):
            d = today + timedelta(days=i)
            if d.weekday() in [1, 3]: targets.append({"date": d, "part": "3"}) # 火木夜
            if d.weekday() == 6: targets.append({"date": d, "part": "1"})      # 日朝

    elif mode == "3": # 平日夜
        for i in range(60):
            d = today + timedelta(days=i)
            if d.weekday() < 5: targets.append({"date": d, "part": "3"})

    elif mode == "4": # 全施設リサーチ (★修正: 日曜朝も追加)
        for i in range(60):
            d = today + timedelta(days=i)
            if d.weekday() in [1, 3]: targets.append({"date": d, "part": "3"})
            if d.weekday() == 6: targets.append({"date": d, "part": "1"})

    if not targets:
        st.warning("検索対象がありません")
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
                            "part_id": t["part"], # ★重要: 検索した時間帯(ID)を保存
                            "予約する": False
                        })
            except:
                pass # エラーでも次へ

        driver.quit()
        status.empty()
        progress.empty()
        st.session_state.found = found
        
        if not found:
            st.warning("空きは見つかりませんでした")

# --- 予約処理 ---
if "found" in st.session_state and st.session_state.found:
    df = pd.DataFrame(st.session_state.found)
    # 表示用にデータを整形
    df["日付"] = df["date"].apply(get_jp_date)
    df["時間帯"] = df["part_id"].map({"1":"朝", "2":"昼", "3":"夜"})

    edited = st.data_editor(
        df[["予約する", "日付", "時間帯", "facility"]], 
        hide_index=True,
        column_config={"予約する": st.column_config.CheckboxColumn(default=False)}
    )

    # チェックされた行を取得
    selected_indices = edited.index[edited["予約する"]].tolist()
    # 元のデータリストから抽出（データエディタの並び替えに対応するため、本来はID管理推奨だが簡易的に）
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
                
                # ★修正: 予約実行結果を受け取る
                success, msg = book(driver, s, run_mode == "テスト")
                icon = "✅" if success else "❌"
                results.append(f"{icon} {s['facility']} ({get_jp_date(s['date'])}): {msg}")
            
            driver.quit()
            progress_bar.empty()
            st.markdown("### 実行結果")
            st.text("\n".join(results))
            if any("✅" in r for r in results):
                st.balloons()
