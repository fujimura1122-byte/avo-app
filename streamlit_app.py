import streamlit as st
import time
import smtplib
import os
import pandas as pd
import re
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ==========================================
# 設定と認証
# ==========================================
try:
    TEAM_PASSWORD = st.secrets["team_password"]
    BOOKING_PASSWORD = st.secrets["booking_password"]
    USER_PROFILE = st.secrets["user_profile"]
except FileNotFoundError:
    st.error("⚠️ Secretsファイルが見つかりません。")
    st.stop()
except KeyError as e:
    st.error(f"⚠️ Secretsの設定が不足しています: {e}")
    st.stop()

# ★ターゲット施設
TARGET_DEEL_FACILITIES = ["Sporthal Deel 1", "Sporthal Deel 2"]
# ★ハイライト対象
HIGHLIGHT_TARGET_NAME = "De Scheg Sporthal Deel"
TARGET_ACTIVITY_VALUE = "53" 
LOGO_IMAGE = "High Ballers.png"

# ページ設定
st.set_page_config(
    page_title="High Ballers 予約監視", 
    page_icon=LOGO_IMAGE if os.path.exists(LOGO_IMAGE) else "⚽",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ==========================================
# ロジック関数
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
    return webdriver.Chrome(options=options)

def get_dutch_date_str(date_obj):
    return f"{date_obj.day}-{NL_MONTHS[date_obj.month]}-{date_obj.year}"

def get_japanese_date_str(date_obj):
    w = ["月","火","水","木","金","土","日"][date_obj.weekday()]
    return f"{date_obj.strftime('%Y/%m/%d')}({w})"

def calculate_site_weekday(date_obj):
    return str((date_obj.weekday() + 1) % 7)

def get_target_time_text(date_obj):
    if date_obj.weekday() == 6: # 6 = 日曜日
        return "09:00" 
    else:
        return "20:00" 

def take_error_snapshot(driver, container, error_message):
    try:
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"error_{timestamp}.png"
        driver.save_screenshot(filename)
        with container.expander("📸 エラー発生時の画面", expanded=True):
            st.error(f"エラー: {error_message}")
            st.image(filename)
    except: pass

# --- 金額抽出用ロジック（リスト表示用：概算） ---
def extract_price_estimate(text):
    # リスト上の "€ 25,52" を "€ 51.04" (2時間分) に変換して表示する
    try:
        # 数字部分を抽出 (カンマ対応)
        match = re.search(r"€\s*([\d,.]+)", text)
        if match:
            raw_val = match.group(1).replace('.', '').replace(',', '.') # 欧州形式をfloatへ
            val_float = float(raw_val)
            # ★重要: アプリは2時間予約固定なので、表示価格を2倍にする
            total_val = val_float * 2
            return f"€ {total_val:.2f}"
        return "-"
    except:
        return "-"

# ---------------------------------------------------------
# コールバック関数
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
            st.toast(f"✅ 追加: {get_japanese_date_str(date_val)}")
        else:
            st.toast("⚠️ 追加済みです")

# ---------------------------------------------------------
# 予約実行関数
# ---------------------------------------------------------
def perform_booking(driver, facility_name, date_obj, target_url, is_dry_run, container):
    date_str = get_japanese_date_str(date_obj)
    target_time_text = get_target_time_text(date_obj)
    max_retries = 3
    
    container.info(f"🚀 予約開始: {date_str} {facility_name}")
    
    for attempt in range(1, max_retries + 1):
        try:
            # 1. 施設選択
            found_element = None
            items = driver.find_elements(By.CLASS_NAME, "item")
            for item in items:
                if item.get_attribute("href") == target_url:
                    found_element = item
                    break
            
            if found_element:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", found_element)
                time.sleep(1)
                found_element.click()
            else:
                raise Exception("対象施設が見つかりません")

            # 2. 予約ボタンへ
            try:
                reserve_btn = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Naar reserveren')]"))
                )
                reserve_btn.click()
            except:
                raise Exception("予約ボタンが見つかりません")

            container.write("  -> 入力中...")
            time.sleep(2)
            
            # 3. 2時間選択
            Select(driver.find_element(By.ID, "selectedTimeLength")).select_by_value("2")
            time.sleep(2) # 金額反映待ち

            # 4. 時間枠選択
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
                container.warning(f"  -> ⚠️ {target_time_text}〜の枠が埋まりました。")
                return False 
            
            container.write(f"  -> 枠確保: {selected_text}")
            time.sleep(1)
            Select(driver.find_element(By.ID, "SelectedActivity")).select_by_value(TARGET_ACTIVITY_VALUE)
            
            # 5. 個人情報入力
            for key, val in USER_PROFILE.items():
                if key == "HouseNumberAddition" and val == "": continue
                driver.find_element(By.NAME, key).send_keys(val)
                
            # ★ここに修正追加: 正確な金額を hidden input から抽出
            exact_price_str = "不明"
            try:
                # <input id="tarief" value="51,33"> を取得
                tarief_input = driver.find_element(By.ID, "tarief")
                raw_val = tarief_input.get_attribute("value") # "51,33"
                if raw_val:
                    exact_price_str = raw_val.replace(',', '.') # "51.33"
            except:
                pass

            chk = driver.find_element(By.NAME, "voorwaarden")
            if not chk.is_selected():
                driver.execute_script("arguments[0].click();", chk)

            # 6. 確定
            if is_dry_run:
                container.success(f"🛑 【テスト成功】予約寸前で停止。 (予定金額: €{exact_price_str})")
                return True
            else:
                driver.find_element(By.ID, "ConfirmButton").click()
                time.sleep(5)
                # ログに正確な金額を含める
                container.success(f"✅ 予約確定！ (金額: €{exact_price_str})")
                return True

        except Exception as e:
            if attempt < max_retries:
                container.warning(f"⚠️ リトライ中 ({attempt}/{max_retries})...")
                time.sleep(3) 
                driver.back() 
                time.sleep(2)
            else:
                container.error(f"❌ 失敗: {e}")
                take_error_snapshot(driver, container, str(e))
                return False

# ---------------------------------------------------------
# 検索関数
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
            time.sleep(2)
            return True
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
                driver.refresh()
            else:
                return False

# ==========================================
# UI構成
# ==========================================

col_logo, col_title = st.columns([1, 4]) 
with col_logo:
    if os.path.exists(LOGO_IMAGE):
        st.image(LOGO_IMAGE, width=80) 
    else:
        st.markdown("⚽")
with col_title:
    st.markdown("### High Ballers 予約")

password = st.text_input("パスワード", type="password")

if password == TEAM_PASSWORD:
    st.success("認証OK")

    mode_map = {
        "1. Deel日付指定 (複数可)": "1",
        "2. Deel監視 (火木日)": "2",
        "3. Deel平日夜一括": "3",
        "4. 全施設リサーチ": "4",
        "5. 日付指定 (複数可) 全施設": "5"
    }
    mode_display = st.radio("検索モード", list(mode_map.keys())) 
    mode = mode_map[mode_display]

    if 'found_slots' not in st.session_state: st.session_state.found_slots = [] 
    if 'manual_targets' not in st.session_state: st.session_state.manual_targets = []

    # --- 日付指定UI ---
    if mode in ["1", "5"]:
        with st.container(): 
            st.markdown("##### 📅 日付追加")
            col_p1, col_p2 = st.columns([1, 1])
            with col_p1:
                part_opts = {"Avond (夜)": "3", "Ochtend (朝)": "1", "Middag (昼)": "2"}
                st.selectbox("時間", list(part_opts.keys()), key="picker_part_label", label_visibility="collapsed")
            with col_p2:
                st.date_input("日付", datetime.today(), key="picker_date", on_change=add_manual_target, label_visibility="collapsed")
            
            if st.session_state.manual_targets:
                st.caption(f"現在のリスト: {len(st.session_state.manual_targets)}件")
                df = pd.DataFrame(st.session_state.manual_targets)
                df["削除"] = False
                df_disp = df[["削除", "display_date", "display_part"]].rename(columns={"display_date": "日付", "display_part": "時間"})
                
                edited_df = st.data_editor(
                    df_disp, hide_index=True, use_container_width=True,
                    column_config={"削除": st.column_config.CheckboxColumn(width="small")}
                )
                
                if st.button("🗑️ 削除実行", use_container_width=True):
                    rows_to_keep = edited_df[edited_df["削除"] == False].index
                    st.session_state.manual_targets = [st.session_state.manual_targets[i] for i in rows_to_keep]
                    st.rerun()

    # --- Step 1: 検索 ---
    st.markdown("---")
    if st.button("🔍 Step 1: 空き検索スタート", type="primary", use_container_width=True):
        targets = []
        today = datetime.now().date()
        valid = True
        
        if mode in ["1", "5"]:
            if not st.session_state.manual_targets:
                st.error("日付を追加してください")
                valid = False
            else:
                targets = st.session_state.manual_targets
                for t in targets: t['lbl'] = t.get('lbl', '指定')

        elif mode == "2":
            rules = [{"ws": [1, 3], "part": "3", "lbl": "夜"}, {"ws": [6], "part": "1", "lbl": "朝"}]
            for i in range(60):
                d = today + timedelta(days=i)
                for r in rules:
                    if d.weekday() in r['ws']: targets.append({"date": d, "part": r['part'], "lbl": r['lbl']})

        elif mode == "3":
            for i in range(60):
                d = today + timedelta(days=i)
                if d.weekday() in [0,1,2,3,4]: targets.append({"date": d, "part": "3", "lbl": "平日夜"})

        elif mode == "4":
            rules = [{"ws": [1, 3], "part": "3", "lbl": "火/木夜"}, {"ws": [6], "part": "1", "lbl": "日朝"}]
            for i in range(60):
                d = today + timedelta(days=i)
                for r in rules:
                    if d.weekday() in r['ws']: targets.append({"date": d, "part": r['part'], "lbl": r['lbl']})

        if valid:
            st.session_state.found_slots = []
            status = st.empty()
            prog = st.progress(0)
            driver = None
            try:
                status.info("検索中...")
                driver = create_driver()
                total = len(targets)
                for i, t in enumerate(targets):
                    jp_date = get_japanese_date_str(t['date'])
                    status.text(f"検索中 ({i+1}/{total}): {jp_date}")
                    prog.progress((i + 1) / total)
                    
                    if search_on_site(driver, t['date'], t['part']):
                        items = driver.find_elements(By.CLASS_NAME, "item")
                        for item in items:
                            try:
                                txt_content = item.text.replace("\n", " ")
                                txt_name = item.find_element(By.CLASS_NAME, "name").text.replace("\n", " ")
                                link = item.get_attribute("href")
                                is_deel = any(d in txt_name for d in TARGET_DEEL_FACILITIES)
                                
                                # ★修正: リスト用には「表示価格×2」で概算を表示 (高速化のため)
                                price_est = extract_price_estimate(txt_content)

                                # ★修正: 全施設リサーチ時のソフトなハイライト
                                display_name = txt_name
                                if mode == "4": 
                                    if HIGHLIGHT_TARGET_NAME in txt_name:
                                        display_name = "🔸 " + txt_name

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
                status.empty()
                prog.empty()
                if not st.session_state.found_slots: st.warning("空きなし")
            except Exception as e:
                st.error(f"エラー: {e}")
                if driver: take_error_snapshot(driver, st, "SearchError")
            finally:
                if driver: driver.quit()

    # --- Step 2: 結果確認 & 予約 ---
    if st.session_state.found_slots:
        st.markdown(f"##### ✨ 空き発見: {len(st.session_state.found_slots)}件")
        st.info("予約する枠にチェックを入れてください")
        
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
            st.write("---")
            st.markdown("#### 🔐 実行設定")
            
            run_mode = st.radio("モード", ["✅ テスト", "🔥 本番"], horizontal=True, label_visibility="collapsed")
            is_dry = (run_mode == "✅ テスト")
            ready = True
            
            if not is_dry:
                bp = st.text_input("実行パスワード", type="password")
                bk = st.checkbox("予約確定しますか？")
                ready = (bp == BOOKING_PASSWORD and bk)
            
            if st.button(f"🚀 {len(selected_slots)}件を予約する", type="primary", use_container_width=True):
                if not ready:
                    st.error("パスワード確認不足")
                else:
                    logs = []
                    status = st.empty()
                    prog = st.progress(0)
                    driver = None
                    try:
                        status.info("予約開始...")
                        driver = create_driver()
                        total = len(selected_slots)
                        for idx, slot in enumerate(selected_slots):
                            # アイコンなしの正式名称を使う
                            target_fac = slot.get('raw_facility', slot['facility'])
                            status.text(f"処理中 ({idx+1}/{total}): {target_fac}")
                            prog.progress((idx + 1) / total)
                            
                            if search_on_site(driver, slot['date_obj'], slot['part_id']):
                                if perform_booking(driver, target_fac, slot['date_obj'], slot['url'], is_dry, st):
                                    logs.append(f"✅ 成功: {slot['display']}")
                                else:
                                    logs.append(f"❌ 失敗: {slot['display']}")
                            else:
                                logs.append(f"❌ 検索失敗: {slot['display']}")
                        
                        status.success("完了!")
                        prog.empty()
                        st.balloons()
                        st.text_area("結果ログ", "\n".join(logs))
                    except Exception as e:
                        st.error(f"エラー: {e}")
                        if driver: take_error_snapshot(driver, st, "BookingError")
                    finally:
                        if driver: driver.quit()

else:
    if password: st.error("パスワード違い")
