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
# 1. セキュリティ設定 (Secretsから取得)
# ==========================================
try:
    TEAM_PASSWORD = st.secrets["team_password"]
    BOOKING_PASSWORD = st.secrets["booking_password"]
    USER_PROFILE = st.secrets["user_profile"]
except Exception:
    st.error("⚠️ Secretsの設定（パスワードや個人情報）が不足しています。")
    st.stop()

TARGET_DEEL_FACILITIES = ["Sporthal Deel 1", "Sporthal Deel 2"]
TARGET_ACTIVITY_VALUE = "53" 
LOGO_IMAGE = "High Ballers.png"

st.set_page_config(page_title="High Ballers 予約", page_icon="⚽", layout="centered")

# ==========================================
# 2. ロジック関数
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

def get_japanese_date_str(date_obj):
    w = ["月","火","水","木","金","土","日"][date_obj.weekday()]
    return f"{date_obj.strftime('%Y/%m/%d')}({w})"

# 日付追加用のコールバック
def add_target():
    if 'p_date' in st.session_state:
        d = st.session_state.p_date
        pl = st.session_state.p_label
        p_val = {"Avond (夜)": "3", "Ochtend (朝)": "1", "Middag (昼)": "2"}[pl]
        if 'manual_targets' not in st.session_state: st.session_state.manual_targets = []
        item = {"date": d, "part": p_val, "disp": f"{get_japanese_date_str(d)} [{pl}]"}
        if not any(t['disp'] == item['disp'] for t in st.session_state.manual_targets):
            st.session_state.manual_targets.append(item)

# ==========================================
# 3. UIレイヤー (ここを差し替えてください)
# ==========================================
col_l, col_r = st.columns([1, 4])
with col_l:
    if os.path.exists(LOGO_IMAGE): st.image(LOGO_IMAGE, width=80)
    else: st.write("⚽")
with col_r:
    st.markdown("### High Ballers 予約システム")

pw = st.text_input("認証パスワード", type="password")
if pw == TEAM_PASSWORD:
    st.success("認証OK")

    # --- 検索モード選択 (ここがご要望の5項目です) ---
    st.markdown("##### 🔍 検索モードを選択")
    mode = st.radio("目的に合わせて選択してください", 
        [
            "Deel 日付指定 (複数可)", 
            "Deel 監視 (火木日)", 
            "Deel 平日夜一括", 
            "全施設 リサーチ", 
            "全施設 日付指定 (複数可)"
        ], 
        horizontal=False)

    # --- 日付指定UI (モードに応じて表示) ---
    if "日付指定" in mode:
        st.markdown("---")
        st.markdown("##### 📅 調べたい日付をリストに追加")
        c1, c2 = st.columns(2)
        with c1: st.selectbox("時間帯", ["Avond (夜)", "Ochtend (朝)", "Middag (昼)"], key="p_label")
        with c2: st.date_input("日付を選択", datetime.today(), key="p_date", on_change=add_target)
        
        if st.session_state.get('manual_targets'):
            st.caption(f"現在のリスト: {len(st.session_state.manual_targets)}件")
            df_t = pd.DataFrame(st.session_state.manual_targets)
            df_t["削除"] = False
            edit_t = st.data_editor(df_t[["削除", "disp"]], hide_index=True, use_container_width=True)
            if st.button("🗑️ 選択した日付を削除"):
                st.session_state.manual_targets = [st.session_state.manual_targets[i] for i in edit_t[edit_t["削除"]==False].index]
                st.rerun()

    # --- 検索実行ボタン ---
    st.markdown("---")
    if st.button("🚀 Step 1: 空き状況を検索する", type="primary", use_container_width=True):
        # ... (以下、検索ロジック)
        st.info(f"「{mode}」で検索を開始します...")

else:
    if pw: st.error("パスワードが違います")
