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
    USER_PROFILE = st.secrets["user_profile"]
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
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 🎨 UIデザイン (Waymo風: シンプル・クリーン・斬新)
# ==========================================
st.markdown("""
    <style>
    /* --- ベース設定: クリーンなホワイト --- */
    .stApp {
        background-color: #FFFFFF;
        color: #1F2937;
        font-family: 'Helvetica Neue', 'Arial', sans-serif;
    }

    /* --- ヘッダーテキスト: シンプルで力強い --- */
    .header-text {
        font-size: 2.0rem;
        font-weight: 800;
        color: #111827;
        letter-spacing: -0.5px;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 0.9rem;
        color: #6B7280;
        font-weight: 500;
        margin-bottom: 2rem;
    }

    /* --- カードデザイン: 大きな角丸とソフトな影 --- */
    div[role="radiogroup"], .stDataEditor, div[data-testid="stForm"] {
        background-color: #F3F4F6; /* 薄いグレー */
        border: none;
        border-radius: 24px; /* Waymoのような大きな丸み */
        padding: 24px;
        box-shadow: none; /* フラットに */
        margin-bottom: 20px;
    }
    
    /* --- 入力フィールド: 浮かび上がるような白 --- */
    .stTextInput input, .stSelectbox div[data-baseweb="select"], .stDateInput input {
        background-color: #FFFFFF !important;
        color: #1F2937 !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 16px !important;
        padding: 12px 16px !important;
        font-size: 1rem !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    
    /* --- ボタン: ピル型（カプセル）のエレクトリックブルー --- */
    .stButton > button {
        width: 100%;
        background-color: #2563EB; /* 鮮やかなブルー */
        color: white !important;
        border: none;
        border-radius: 9999px; /* 完全な丸み（ピル型） */
        padding: 14px 28px;
        font-weight: 700;
        font-size: 1rem;
        letter-spacing: 0.5px;
        transition: all 0.2s ease;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
    }
    .stButton > button:hover {
        background-color: #1D4ED8;
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.4);
    }
    .stButton > button:active {
        transform: scale(0.98);
    }

    /* --- ラジオボタンのラベル --- */
    div[role="radiogroup"] label {
        color: #374151 !important;
        font-weight: 600;
        background-color: white;
        padding: 10px 15px;
        border-radius: 12px;
        margin-bottom: 8px;
        border: 1px solid #F3F4F6;
        transition: all 0.2s;
    }
    div[role="radiogroup"] label:hover {
        border-color: #2563EB;
    }

    /* --- データエディタ (リスト) --- */
    div[data-testid="stDataEditor"] {
        background-color: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 16px;
    }

    /* --- トースト通知 --- */
    div[data-testid="stToast"] {
        background-color: #FFFFFF;
        color: #1F2937;
        border-radius: 16px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        border: 1px solid #E5E7EB;
    }
    
    /* --- アイコン強調 --- */
    .highlight-icon {
        font-size: 1.2rem;
        margin-right: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 🏎️ ロジック関数 (高速化維持)
# ==========================================

NL_MONTHS = {
    1: "jan", 2: "feb", 3: "mrt", 4: "apr", 5: "mei", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec"
}

def create_driver():
    """ブラウザ起動 (画像ブロックで超高速化)"""
    options = Options()
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # 画像読み込みブロック
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
    return "09:00" if date_obj.weekday() == 6 else "20:00" 

def take_error_snapshot(driver, container, error_message):
    try:
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"error_{timestamp}.png"
        driver.save_screenshot(filename)
        with container.expander("📸 Error Snapshot", expanded=True):
            st.error(f"Error: {error_message}")
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
# コールバック
# ---------------------------------------------------------
def add_manual_target():
    if 'picker_date' in st.session_state and 'picker_part_label' in st.session_state:
        date_val = st.session_state.picker_date
        part_label = st.session_state.picker_part_label
        part_opts = {"Avond (夜)": "3", "Ochtend (朝)": "1", "Middag (昼)": "2"}
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
            st.toast(f"Added: {get_japanese_date_str(date_val)}")
        else:
            st.toast("Already in list")

# ---------------------------------------------------------
# 予約実行処理
# ---------------------------------------------------------
def perform_booking(driver, facility_name, date_obj, target_url, is_dry_run, container):
    date_str = get_japanese_date_str(date_obj)
    target_time_text = get_target_time_text(date_obj)
    max_retries = 3
    
    container.info(f"🚀 Starting Booking: {date_str} {facility_name}")
    
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
                raise Exception("Facility not found")

            try:
                reserve_btn = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Naar reserveren')]"))
                )
                reserve_btn.click()
            except:
                raise Exception("Reserve button missing")

            container.write("  -> 📝 Inputting details...")
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "selectedTimeLength")))
            Select(driver.find_element(By.ID, "selectedTimeLength")).select_by_value("2")
            time.sleep(1.5)

            time_select = Select(driver.find_element(By.ID, "customSelectedTimeSlot"))
            found_slot = False
            selected_text = ""
            for opt in time_select.options:
                if target_time_text in opt.text:
                    time_select.select_by_value(opt.get_attribute("value"))
                    selected_text = opt.text
                    found_slot = True
                    break
            
            if not found_slot:
                container.warning(f"  -> ⚠️ Slot {target_time_text} is taken")
                return False 
            
            container.write(f"  -> 🕒 Secured: {selected_text}")
            Select(driver.find_element(By.ID, "SelectedActivity")).select_by_value(TARGET_ACTIVITY_VALUE)
            
            for key, val in USER_PROFILE.items():
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
                container.success(f"🛑 [TEST MODE] Stopped before confirm. (Price: €{exact_price_str})")
                return True
            else:
                driver.find_element(By.ID, "ConfirmButton").click()
                time.sleep(5)
                container.success(f"✅ BOOKED! (Price: €{exact_price_str})")
                return True

        except Exception as e:
            if attempt < max_retries:
                container.warning(f"⚠️ Retry {attempt}/{max_retries}...")
                time.sleep(2) 
                driver.back() 
                time.sleep(1)
            else:
                container.error(f"❌ Failed: {e}")
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
            if target_url not in driver.current_url:
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

col_logo, col_title = st.columns([1, 4]) 
with col_logo:
    if os.path.exists(LOGO_IMAGE):
        st.image(LOGO_IMAGE, width=80) 
    else:
        st.markdown("# ⚽")
with col_title:
    st.markdown('<div class="header-text">High Ballers AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Automated Reservation System</div>', unsafe_allow_html=True)

password = st.text_input("ACCESS KEY", type="password")

if password == TEAM_PASSWORD:
    
    # モード選択
    mode_map = {
        "1. Deel日付指定 (複数可)": "1",
        "2. Deel監視 (火木日)": "2",
        "3. Deel平日夜一括": "3",
        "4. 全施設リサーチ": "4",
        "5. 日付指定 (複数可) 全施設": "5"
    }
    mode_display = st.radio("SEARCH MODE", list(mode_map.keys())) 
    mode = mode_map[mode_display]

    if 'found_slots' not in st.session_state: st.session_state.found_slots = [] 
    if 'manual_targets' not in st.session_state: st.session_state.manual_targets = []

    # --- 日付追加エリア ---
    if mode in ["1", "5"]:
        st.markdown("#### 📅 TARGET DATE")
        c1, c2 = st.columns([1, 2])
        with c1:
            part_opts = {"Avond (夜)": "3", "Ochtend (朝)": "1", "Middag (昼)": "2"}
            st.selectbox("TIME", list(part_opts.keys()), key="picker_part_label", label_visibility="collapsed")
        with c2:
            st.date_input("DATE", datetime.today(), key="picker_date", on_change=add_manual_target, label_visibility="collapsed")
        
        if st.session_state.manual_targets:
            df = pd.DataFrame(st.session_state.manual_targets)
            df["削除"] = False
            df_disp = df[["削除", "display_date", "display_part"]].rename(columns={"display_date": "DATE", "display_part": "TIME"})
            
            edited_df = st.data_editor(
                df_disp, hide_index=True, use_container_width=True,
                column_config={"削除": st.column_config.CheckboxColumn(width="small")}
            )
            
            if st.button("🗑️ Clear Selected Dates", use_container_width=True):
                keep = edited_df[edited_df["削除"] == False].index
                st.session_state.manual_targets = [st.session_state.manual_targets[i] for i in keep]
                st.rerun()

    # --- 検索ボタン ---
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔍 START SEARCH", type="primary", use_container_width=True):
        targets = []
        today = datetime.now().date()
        valid = True
        
        if mode in ["1", "5"]:
            if not st.session_state.manual_targets:
                st.error("Please add dates first.")
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
                status.info("Driver Initialized...")
                driver = create_driver()
                total = len(targets)
                
                for i, t in enumerate(targets):
                    jp_date = get_japanese_date_str(t['date'])
                    status.markdown(f"**Scanning...** `{jp_date}` ({i+1}/{total})")
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
                
                status.success("Done!")
                time.sleep(0.5)
                status.empty()
                prog.empty()
                if not st.session_state.found_slots: st.warning("No slots found.")
            
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if driver: driver.quit()

    # --- 結果一覧 & 予約実行 ---
    if st.session_state.found_slots:
        st.markdown(f"#### ✨ Available Slots: {len(st.session_state.found_slots)}")
        
        df_found = pd.DataFrame(st.session_state.found_slots)
        df_found["日付"] = df_found["date_obj"].apply(get_japanese_date_str)
        df_found_disp = df_found[["予約する", "日付", "facility", "price"]].rename(columns={"facility": "FACILITY", "price": "PRICE(2h)", "日付": "DATE"})

        edited_found_df = st.data_editor(
            df_found_disp,
            hide_index=True,
            use_container_width=True,
            column_config={
                "予約する": st.column_config.CheckboxColumn(label="PICK", width="small", default=False),
                "FACILITY": st.column_config.TextColumn(width="medium"),
                "PRICE(2h)": st.column_config.TextColumn(width="small"),
            }
        )
        
        selected_indices = edited_found_df[edited_found_df["予約する"] == True].index
        selected_slots = [st.session_state.found_slots[i] for i in selected_indices]
        
        if selected_slots:
            st.markdown("---")
            st.markdown("#### 🔐 EXECUTION")
            
            c_run1, c_run2 = st.columns([1, 2])
            with c_run1:
                run_mode = st.radio("MODE", ["✅ TEST", "🔥 REAL"], label_visibility="collapsed")
            
            is_dry = (run_mode == "✅ TEST")
            ready = True
            
            if not is_dry:
                with c_run2:
                    bp = st.text_input("BOOKING PASSWORD", type="password")
                    bk = st.checkbox("Confirm Booking")
                    ready = (bp == BOOKING_PASSWORD and bk)
            
            if st.button(f"🚀 BOOK {len(selected_slots)} SLOTS", type="primary", use_container_width=True):
                if not ready:
                    st.error("Auth Failed")
                else:
                    logs = []
                    status = st.empty()
                    prog = st.progress(0)
                    driver = None
                    try:
                        status.info("Initializing Agent...")
                        driver = create_driver()
                        total = len(selected_slots)
                        for idx, slot in enumerate(selected_slots):
                            target_fac = slot.get('raw_facility', slot['facility'])
                            status.markdown(f"**Processing...** `{target_fac}` ({idx+1}/{total})")
                            prog.progress((idx + 1) / total)
                            
                            if search_on_site(driver, slot['date_obj'], slot['part_id']):
                                if perform_booking(driver, target_fac, slot['date_obj'], slot['url'], is_dry, st):
                                    logs.append(f"✅ SUCCESS: {slot['display']}")
                                else:
                                    logs.append(f"❌ FAILED: {slot['display']}")
                            else:
                                logs.append(f"❌ NOT FOUND: {slot['display']}")
                        
                        status.success("Finished!")
                        prog.empty()
                        st.balloons()
                        st.text_area("LOGS", "\n".join(logs), height=200)
                    except Exception as e:
                        st.error(f"Error: {e}")
                    finally:
                        if driver: driver.quit()

else:
    if password: st.error("Invalid Key")
