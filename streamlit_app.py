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
# 🎨 UIデザイン (Config.toml対応・モバイルレイアウト修正版)
# ==========================================
st.markdown("""
    <style>
    /* --- スマホでの表示崩れを防ぐための余白調整 --- */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 10rem !important; /* カレンダー用に下部余白を大きく確保 */
        max-width: 100% !important;
    }

    /* --- ヘッダー --- */
    .header-text {
        font-size: 22px;
        font-weight: 900;
        color: #111827;
        letter-spacing: -0.5px;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 13px;
        color: #6B7280;
        margin-bottom: 20px;
    }

    /* --- カードスタイル (角丸・枠線) --- */
    div[data-testid="stForm"], div[data-baseweb="select"] > div, .stDataEditor {
        border-radius: 16px !important;
        border: 1px solid #E5E7EB !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
    }
    
    /* --- 入力フィールド (スマホで見切れ対策：高さを確保) --- */
    .stTextInput input, .stDateInput input {
        border-radius: 12px !important;
        height: 50px !important;
        font-size: 16px !important; /* iOSでズームされないサイズ */
    }

    /* --- ボタン (タップしやすい大きさ) --- */
    .stButton > button {
        width: 100%;
        border-radius: 50px !important;
        padding: 14px 24px !important;
        font-weight: 700 !important;
        font-size: 16px !important;
        border: none !important;
        box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2) !important;
        margin-top: 10px;
    }

    /* --- カレンダーのポップアップ位置修正 (z-index) --- */
    div[data-baseweb="popover"], div[data-baseweb="calendar"] {
        z-index: 9999 !important;
    }
    
    /* --- トースト通知 --- */
    div[data-testid="stToast"] {
        border-radius: 12px;
        border: 1px solid #E5E7EB;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 🏎️ ロジック関数
# ==========================================

NL_MONTHS = {
    1: "jan", 2: "feb", 3: "mrt", 4: "apr", 5: "mei", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec"
}

def create_driver():
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
# コールバック
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
        st.toast(f"✅ リストに追加: {get_japanese_date_str(date_val)}")
    else:
        st.toast("⚠️ その枠は既に追加されています")

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

password = st.text_input("パスワード", type="password")

if password == TEAM_PASSWORD:
    
    st.markdown("#### ⚙️ SEARCH MODE")
    mode_map = {
        "1. Deel日付指定 (複数可)": "1",
        "2. Deel監視 (火木日)": "2",
        "3. Deel平日夜一括": "3",
        "4. 全施設リサーチ": "4",
        "5. 日付指定 (複数可) 全施設": "5"
    }
    mode_display = st.selectbox("検索モードを選択", list(mode_map.keys()), label_visibility="collapsed") 
    mode = mode_map[mode_display]

    if 'found_slots' not in st.session_state: st.session_state.found_slots = [] 
    if 'manual_targets' not in st.session_state: st.session_state.manual_targets = []

    # --- 日付追加エリア ---
    if mode in ["1", "5"]:
        st.markdown("---")
        st.markdown("#### 📅 TARGET DATE")
        
        # スマホでの表示崩れを防ぐため、st.columnsを使わずに垂直配置
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
                                if perform_booking(driver, target_fac, slot['date_obj'], slot['url'], is_dry, st):
                                    logs.append(f"✅ 成功: {slot['display']}")
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
    if password: st.error("パスワードが違います")
