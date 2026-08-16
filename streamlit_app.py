import streamlit as st
import time
import pandas as pd
import re
import os
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ==========================================
# ⚙️ 設定と認証
# ==========================================
try:
    TEAM_PASSWORD = st.secrets["team_password"]
    BOOKING_PASSWORD = st.secrets["booking_password"]
    # 複数プロフィール対応: 新形式 user_profiles を優先し、
    # 無ければ旧形式 user_profile を「デフォルト」1人として扱う(後方互換)
    if "user_profiles" in st.secrets:
        USER_PROFILES = {name: dict(profile) for name, profile in st.secrets["user_profiles"].items()}
    else:
        USER_PROFILES = {"デフォルト": dict(st.secrets["user_profile"])}
except Exception:
    st.error("⚠️ Secrets Error")
    st.stop()

TARGET_DEEL_FACILITIES = ["Sporthal Deel 1", "Sporthal Deel 2"]
HIGHLIGHT_TARGET_NAME = "De Scheg Sporthal Deel"
TARGET_ACTIVITY_VALUE = "53" 
LOGO_IMAGE = "High Ballers.png"

st.set_page_config(
    page_title="High Ballers AI", 
    page_icon="⚽",
    layout="centered", # PCでもスマホでも中央寄せで見やすくする
    initial_sidebar_state="collapsed"
)

# ==========================================
# 🎨 UIデザイン (レスポンシブ対応版)
# ==========================================
st.markdown("""
    <style>
    /* --- 基本設定 --- */
    .stApp {
        background-color: #FFFFFF !important;
        color: #111827 !important;
    }

    /* --- テキスト設定 --- */
    h1, h2, h3, p, div, label, span {
        color: #111827 !important;
    }
    .header-text {
        font-weight: 900;
        color: #111827;
        letter-spacing: -0.5px;
        margin: 0;
    }
    .sub-header {
        font-size: 13px;
        color: #6B7280;
        margin-bottom: 20px;
    }

    /* --- カードデザイン (共通) --- */
    div[data-testid="stForm"], div[data-baseweb="select"] > div, .stDataEditor {
        border-radius: 12px !important;
        border: 1px solid #E5E7EB !important;
        background-color: #F9FAFB !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
    }
    
    /* --- 入力フィールド (共通) --- */
    .stTextInput input, .stDateInput input {
        border-radius: 8px !important;
        border: 2px solid #E5E7EB !important;
        color: #111827 !important;
        background-color: #FFFFFF !important;
    }
    .stTextInput input:focus, .stDateInput input:focus {
        border-color: #2563EB !important;
    }

    /* --- ボタン基本設定 (PC向けデフォルト) --- */
    .stButton > button {
        border-radius: 8px !important;
        padding: 10px 24px !important; /* PCは少し控えめなパディング */
        font-weight: 700 !important;
        font-size: 16px !important;
        border: none !important;
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2) !important;
        margin-top: 10px;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        background-color: #1D4ED8 !important;
        box-shadow: 0 6px 12px rgba(37, 99, 235, 0.3) !important;
        transform: translateY(-1px);
    }

    /* =========================================
       📱 スマホ・タブレット向けレスポンシブ設定 (幅768px以下)
       ========================================= */
    @media only screen and (max-width: 768px) {
        /* ヘッダーサイズ調整 */
        .header-text {
            font-size: 20px;
        }
        
        /* 入力欄をタップしやすく高くする */
        .stTextInput input, .stDateInput input {
            height: 50px !important;
            font-size: 16px !important;
        }

        /* ボタンを画面幅いっぱいにし、指で押しやすくする */
        .stButton > button {
            width: 100%;
            padding: 14px 24px !important;
            border-radius: 50px !important; /* スマホはピル型が押しやすい */
        }
        
        /* コンテナの余白調整 */
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 10rem !important;
        }
        
        /* カードの角丸を少し大きく */
        div[data-testid="stForm"] {
            border-radius: 16px !important;
        }
    }
    
    /* カレンダー表示位置調整 */
    div[data-baseweb="popover"], div[data-baseweb="calendar"] {
        z-index: 99999 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 🏎️ ロジック関数群
# ==========================================

NL_MONTHS = {
    1: "jan", 2: "feb", 3: "mrt", 4: "apr", 5: "mei", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec"
}

def create_driver():
    """ブラウザドライバの作成 (高速化設定付き)"""
    options = Options()
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # ステルス設定
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # 画像読み込みブロック (高速化)
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    return webdriver.Chrome(options=options)

def get_dutch_date_str(date_obj):
    return f"{date_obj.day}-{NL_MONTHS[date_obj.month]}-{date_obj.year}"

def get_japanese_date_str(date_obj):
    w = ["月","火","水","木","金","土","日"][date_obj.weekday()]
    return f"{date_obj.strftime('%Y/%m/%d')}({w})"

def calculate_site_weekday(date_obj):
    return str((date_obj.weekday() + 1) % 7)

def get_target_time_text(date_obj):
    # 土(5)・日(6)は朝(09:00)、それ以外は夜(20:00)
    if date_obj.weekday() in [5, 6]:
        return "09:00"
    else:
        return "20:00"

def take_error_snapshot(driver, container, error_message):
    try:
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"error_{timestamp}.png"
        driver.save_screenshot(filename)
        with container.expander("📸 エラー画面", expanded=True):
            st.error(f"エラー: {error_message}")
            st.image(filename)
    except: pass

def extract_price_estimate(text):
    try:
        match = re.search(r"€\s*([\d,.]+)", text)
        if match:
            raw_val = match.group(1).replace('.', '').replace(',', '.')
            val_float = float(raw_val)
            total_val = val_float * 2 
            return f"€ {total_val:.2f}"
        return "-"
    except:
        return "-"

# ---------------------------------------------------------
# コールバック関数 (日付追加)
# ---------------------------------------------------------
def add_manual_target():
    if 'picker_date' not in st.session_state or 'picker_part_label' not in st.session_state:
        return

    date_val = st.session_state.picker_date
    part_label = st.session_state.picker_part_label
    part_opts = {"Avond (夜)": "3", "Ochtend (朝)": "1", "Middag (昼)": "2"}
    
    if part_label not in part_opts:
        return

    part_val = part_opts[part_label]
    
    if 'manual_targets' not in st.session_state:
        st.session_state.manual_targets = []
        
    new_item = {
        "date": date_val,
        "part": part_val,
        "display_date": get_japanese_date_str(date_val),
        "display_part": part_label,
        "lbl": f"指定({part_label})"
    }
    is_duplicate = any(t['date'] == new_item['date'] and t['part'] == new_item['part'] for t in st.session_state.manual_targets)
    
    if not is_duplicate:
        st.session_state.manual_targets.append(new_item)
        st.toast(f"✅ 追加: {get_japanese_date_str(date_val)}")
    else:
        st.toast("⚠️ その枠は既に追加されています")

# ---------------------------------------------------------
# 予約実行処理
# ---------------------------------------------------------
def perform_booking(driver, facility_name, date_obj, target_url, is_dry_run, container, profile):
    date_str = get_japanese_date_str(date_obj)
    target_start_time = get_target_time_text(date_obj) # "09:00" or "20:00"

    # 終了時間を計算 (開始時間 + 2時間)
    start_dt = datetime.strptime(target_start_time, "%H:%M")
    end_dt = start_dt + timedelta(hours=2)
    target_end_time = end_dt.strftime("%H:%M") # "11:00" or "22:00"

    max_retries = 3
    
    container.info(f"🚀 予約開始: {date_str} {facility_name}")
    
    for attempt in range(1, max_retries + 1):
        try:
            found_element = None
            items = driver.find_elements(By.CLASS_NAME, "item")
            for item in items:
                if item.get_attribute("href") == target_url:
                    found_element = item
                    break
            
            if found_element:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", found_element)
                time.sleep(0.5) 
                found_element.click()
            else:
                raise Exception("施設が見つかりません")

            try:
                reserve_btn = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Naar reserveren')]"))
                )
                reserve_btn.click()
            except:
                raise Exception("予約ボタンが見つかりません")

            container.write("  -> 📝 情報入力中...")
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "selectedTimeLength")))
            Select(driver.find_element(By.ID, "selectedTimeLength")).select_by_value("2")
            time.sleep(1.5)

            # --- 時間枠の選択ロジック (厳密化版) ---
            time_select = Select(driver.find_element(By.ID, "customSelectedTimeSlot"))
            found_slot = False
            selected_text = ""
            for opt in time_select.options:
                text = opt.text.strip()
                # 開始時間で始まり、かつ終了時間が含まれる場合のみ選択
                if text.startswith(target_start_time) and target_end_time in text:
                    time_select.select_by_value(opt.get_attribute("value"))
                    selected_text = text
                    found_slot = True
                    break
            
            if not found_slot:
                container.warning(f"  -> ⚠️ {target_start_time}〜{target_end_time} の枠が埋まっています")
                return False 
            
            container.write(f"  -> 🕒 枠確保: {selected_text}")
            Select(driver.find_element(By.ID, "SelectedActivity")).select_by_value(TARGET_ACTIVITY_VALUE)
            
            for key, val in profile.items():
                if key == "HouseNumberAddition" and val == "": continue
                driver.find_element(By.NAME, key).send_keys(val)
                
            exact_price_str = "?"
            try:
                tarief_input = driver.find_element(By.ID, "tarief")
                raw_val = tarief_input.get_attribute("value")
                if raw_val: exact_price_str = raw_val.replace(',', '.')
            except: pass

            chk = driver.find_element(By.NAME, "voorwaarden")
            if not chk.is_selected():
                driver.execute_script("arguments[0].click();", chk)

            if is_dry_run:
                # --- テストモード時の確認用スクショ ---
                try:
                    time_element = driver.find_element(By.ID, "customSelectedTimeSlot")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", time_element)
                    time.sleep(0.5)
                except: pass

                timestamp = datetime.now().strftime("%H%M%S")
                filename = f"dry_run_check_{timestamp}.png"
                driver.save_screenshot(filename)
                
                container.image(filename, caption=f"📸 最終確認: {target_start_time}〜{target_end_time} が選択されているか確認してください")
                container.success(f"🛑 【テスト成功】予約寸前で停止 (金額: €{exact_price_str})")
                return True
            else:
                driver.find_element(By.ID, "ConfirmButton").click()
                time.sleep(5)
                container.success(f"✅ 予約確定！ (金額: €{exact_price_str})")
                return True

        except Exception as e:
            if attempt < max_retries:
                container.warning(f"⚠️ リトライ中 ({attempt}/{max_retries})...")
                time.sleep(2) 
                driver.back() 
                time.sleep(1)
            else:
                container.error(f"❌ 失敗: {e}")
                take_error_snapshot(driver, container, str(e))
                return False

# ---------------------------------------------------------
# 検索処理
# ---------------------------------------------------------
def search_on_site(driver, date_obj, part_id):
    target_url = "https://avo.hta.nl/uithoorn/"
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            driver.get(target_url)
            
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "SearchButton")))
            
            d_str = get_dutch_date_str(date_obj)
            date_input = driver.find_element(By.XPATH, "//div[@id='searchDateCalDiv']/preceding-sibling::input")
            try:
                driver.execute_script(f"$(arguments[0]).datepicker('setDate', '{d_str}');", date_input)
            except:
                driver.execute_script(f"arguments[0].value = '{d_str}';", date_input)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", date_input)
            
            Select(driver.find_element(By.ID, "DayOfTheWeek")).select_by_value(calculate_site_weekday(date_obj))
            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", driver.find_element(By.ID, "DayOfTheWeek"))
            Select(driver.find_element(By.ID, "Daypart")).select_by_value(part_id)
            Select(driver.find_element(By.ID, "Duration")).select_by_value("2")
            Select(driver.find_element(By.ID, "Activity")).select_by_value("53")
            driver.find_element(By.ID, "SearchButton").click()
            
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, "item")))
            return True
        except Exception:
            if attempt < max_retries:
                time.sleep(1)
                driver.refresh()
            else:
                return False

# ==========================================
# 📱 UIメイン構成
# ==========================================

col_logo, col_title = st.columns([1, 5]) 
with col_logo:
    if os.path.exists(LOGO_IMAGE):
        st.image(LOGO_IMAGE, width=55) 
    else:
        st.write("⚽")
with col_title:
    st.markdown("""
        <div style="padding-top: 0px;">
            <div class="header-text">High Ballers AI</div>
            <div class="sub-header">Automated Reservation System</div>
        </div>
    """, unsafe_allow_html=True)

# --- 総当たり対策 (失敗回数カウント + 失敗時遅延) ---
# ※ st.session_state によるセッション単位の簡易対策です。
#    ページを再読み込み(リロード)するとカウントはリセットされ、ロックも解除されます。
if 'auth_fail_count' not in st.session_state:
    st.session_state.auth_fail_count = 0

is_locked = st.session_state.auth_fail_count >= 3

if is_locked:
    # ロック状態: 入力欄を出さず、一致判定そのものを行わない
    password = ""
    st.warning("試行回数が上限に達しました。しばらく待ってからページを再読み込みしてください")
else:
    password = st.text_input("パスワード", type="password")

if (not is_locked) and password == TEAM_PASSWORD:
    st.session_state.auth_fail_count = 0  # 認証成功でリセット
    
    # 検索モードは「日付指定 (複数可) 全施設」(旧モード5) に固定。
    # モード選択UIは非表示化 (他モードの分岐ロジックは下に残っているが到達しない)
    mode = "5"

    if 'found_slots' not in st.session_state: st.session_state.found_slots = [] 
    if 'manual_targets' not in st.session_state: st.session_state.manual_targets = []

    # --- 日付追加エリア ---
    if mode in ["1", "5"]:
        st.markdown("---")
        st.markdown("#### 📅 TARGET DATE")
        
        # スマホ最適化: 垂直配置
        part_opts = {"Avond (夜)": "3", "Ochtend (朝)": "1", "Middag (昼)": "2"}
        
        st.selectbox(
            "1. 時間帯を選択", 
            list(part_opts.keys()), 
            key="picker_part_label",
            on_change=add_manual_target
        )
        
        st.date_input(
            "2. 日付を選択 (タップで追加)", 
            datetime.today(), 
            key="picker_date", 
            on_change=add_manual_target
        )
        
        if st.session_state.manual_targets:
            st.markdown(f"**現在のリスト: {len(st.session_state.manual_targets)} 件**")
            
            df = pd.DataFrame(st.session_state.manual_targets)
            df["削除"] = False
            df_disp = df[["削除", "display_date", "display_part"]].rename(columns={"display_date": "日付", "display_part": "時間"})
            
            edited_df = st.data_editor(
                df_disp, hide_index=True, use_container_width=True,
                column_config={"削除": st.column_config.CheckboxColumn(width="small")}
            )
            
            if st.button("🗑️ 選択した日付を削除", use_container_width=True):
                keep = edited_df[edited_df["削除"] == False].index
                st.session_state.manual_targets = [st.session_state.manual_targets[i] for i in keep]
                st.rerun()

    # --- 検索ボタン ---
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔍 検索開始 (START SEARCH)", type="primary", use_container_width=True):
        targets = []
        today = datetime.now().date()
        valid = True
        
        if mode in ["1", "5"]:
            if not st.session_state.manual_targets:
                st.error("日付リストが空です。日付を追加してください。")
                valid = False
            else:
                targets = st.session_state.manual_targets
        elif mode == "2":
            rules = [{"ws": [1, 3], "part": "3"}, {"ws": [6], "part": "1"}]
            for i in range(60):
                d = today + timedelta(days=i)
                for r in rules:
                    if d.weekday() in r['ws']: targets.append({"date": d, "part": r['part']})
        elif mode == "3":
            for i in range(60):
                d = today + timedelta(days=i)
                if d.weekday() in [0,1,2,3,4]: targets.append({"date": d, "part": "3"})
        elif mode == "4":
            rules = [{"ws": [1, 3], "part": "3"}, {"ws": [6], "part": "1"}]
            for i in range(60):
                d = today + timedelta(days=i)
                for r in rules:
                    if d.weekday() in r['ws']: targets.append({"date": d, "part": r['part']})

        if valid:
            st.session_state.found_slots = []
            status = st.empty()
            prog = st.progress(0)
            driver = None
            try:
                status.info("AIドライバを起動中...")
                driver = create_driver()
                total = len(targets)
                
                for i, t in enumerate(targets):
                    jp_date = get_japanese_date_str(t['date'])
                    status.markdown(f"**検索中...** `{jp_date}` ({i+1}/{total})")
                    prog.progress((i + 1) / total)
                    
                    if search_on_site(driver, t['date'], t['part']):
                        items = driver.find_elements(By.CLASS_NAME, "item")
                        for item in items:
                            try:
                                txt_content = item.text.replace("\n", " ")
                                txt_name = item.find_element(By.CLASS_NAME, "name").text.replace("\n", " ")
                                link = item.get_attribute("href")
                                is_deel = any(d in txt_name for d in TARGET_DEEL_FACILITIES)
                                
                                price_est = extract_price_estimate(txt_content)
                                display_name = txt_name
                                if mode in ["4", "5"]: 
                                    if HIGHLIGHT_TARGET_NAME in txt_name:
                                        display_name = "🔶 " + txt_name 

                                if (mode in ["1","2","3"] and is_deel) or (mode in ["4", "5"]):
                                    st.session_state.found_slots.append({
                                        "display": f"{jp_date} {txt_name}",
                                        "date_obj": t['date'],
                                        "facility": display_name, 
                                        "raw_facility": txt_name,
                                        "price": price_est,
                                        "part_id": t['part'],
                                        "url": link,
                                        "予約する": False 
                                    })
                            except: continue
                
                status.success("検索完了！")
                time.sleep(0.5)
                status.empty()
                prog.empty()
                if not st.session_state.found_slots: st.warning("条件に合う空きは見つかりませんでした")
            
            except Exception as e:
                st.error(f"システムエラー: {e}")
            finally:
                if driver: driver.quit()

    # --- 結果一覧 & 予約実行 ---
    if st.session_state.found_slots:
        st.markdown(f"#### ✨ 空き発見: {len(st.session_state.found_slots)} 件")
        st.caption("予約したい枠にチェックを入れてください")
        
        df_found = pd.DataFrame(st.session_state.found_slots)
        df_found["日付"] = df_found["date_obj"].apply(get_japanese_date_str)
        df_found_disp = df_found[["予約する", "日付", "facility", "price"]].rename(columns={"facility": "施設名", "price": "金額(2h)"})

        edited_found_df = st.data_editor(
            df_found_disp,
            hide_index=True,
            use_container_width=True,
            column_config={
                "予約する": st.column_config.CheckboxColumn(label="選択", width="small", default=False),
                "施設名": st.column_config.TextColumn(width="medium"),
                "金額(2h)": st.column_config.TextColumn(width="small"),
            }
        )
        
        selected_indices = edited_found_df[edited_found_df["予約する"] == True].index
        selected_slots = [st.session_state.found_slots[i] for i in selected_indices]
        
        if selected_slots:
            st.markdown("---")
            st.markdown("#### 🔐 予約実行")

            # 予約者の選択 (表示は名前のみ。プロフィールの中身はUI/ログに出さない)
            st.selectbox("👤 予約者を選択", options=list(USER_PROFILES.keys()), key="selected_booker")
            st.caption(f"この内容で {st.session_state.selected_booker} さんとして予約します")

            c_run1, c_run2 = st.columns([1, 2])
            with c_run1:
                run_mode = st.radio("実行モード", ["✅ テスト", "🔥 本番"], label_visibility="collapsed")
            
            is_dry = (run_mode == "✅ テスト")
            ready = True
            
            if not is_dry:
                with c_run2:
                    bp = st.text_input("実行パスワード", type="password")
                    bk = st.checkbox("予約を確定する")
                    ready = (bp == BOOKING_PASSWORD and bk)
            
            if st.button(f"🚀 {len(selected_slots)} 件を予約する", type="primary", use_container_width=True):
                if not ready:
                    st.error("パスワード認証エラー")
                else:
                    booker_name = st.session_state.selected_booker
                    selected_profile = USER_PROFILES[booker_name]
                    logs = []
                    status = st.empty()
                    prog = st.progress(0)
                    driver = None
                    try:
                        status.info("予約エージェントを起動中...")
                        driver = create_driver()
                        total = len(selected_slots)
                        for idx, slot in enumerate(selected_slots):
                            target_fac = slot.get('raw_facility', slot['facility'])
                            status.markdown(f"**実行中...** `{target_fac}` ({idx+1}/{total})")
                            prog.progress((idx + 1) / total)

                            if search_on_site(driver, slot['date_obj'], slot['part_id']):
                                if perform_booking(driver, target_fac, slot['date_obj'], slot['url'], is_dry, st, selected_profile):
                                    logs.append(f"✅ 成功: {slot['display']} by {booker_name}")
                                else:
                                    logs.append(f"❌ 失敗: {slot['display']}")
                            else:
                                logs.append(f"❌ 検索エラー: {slot['display']}")
                        
                        status.success("全処理完了！")
                        prog.empty()
                        st.balloons()
                        st.text_area("実行ログ", "\n".join(logs), height=200)
                    except Exception as e:
                        st.error(f"システムエラー: {e}")
                    finally:
                        if driver: driver.quit()

else:
    # 入力があって不一致のときのみカウント+遅延 (未入力・ロック中は何もしない)
    if (not is_locked) and password:
        st.session_state.auth_fail_count += 1
        time.sleep(2)
        st.error("パスワードが違います")
