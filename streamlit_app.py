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

# --- Secrets設定 ---
try:
    TEAM_PASSWORD = st.secrets["team_password"]
    BOOKING_PASSWORD = st.secrets["booking_password"]
    USER_PROFILE = st.secrets["user_profile"]
except Exception:
    st.error("⚠️ Secretsの設定を確認してください。")
    st.stop()

TARGET_DEEL_FACILITIES = ["Sporthal Deel 1", "Sporthal Deel 2"]
LOGO_IMAGE = "High Ballers.png"

st.set_page_config(page_title="High Ballers 予約", page_icon="⚽", layout="centered")

# --- ロジック関数 ---
def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

def get_dutch_date_str(date_obj):
    nl_m = {1:"jan", 2:"feb", 3:"mrt", 4:"apr", 5:"mei", 6:"jun", 7:"jul", 8:"aug", 9:"sep", 10:"okt", 11:"nov", 12:"dec"}
    return f"{date_obj.day}-{nl_m[date_obj.month]}-{date_obj.year}"

def get_japanese_date_str(date_obj):
    w = ["月","火","水","木","金","土","日"][date_obj.weekday()]
    return f"{date_obj.strftime('%Y/%m/%d')}({w})"

def add_target():
    if 'p_date' in st.session_state:
        d = st.session_state.p_date
        pl = st.session_state.p_label
        p_val = {"Avond (夜)": "3", "Ochtend (朝)": "1", "Middag (昼)": "2"}[pl]
        if 'manual_targets' not in st.session_state: st.session_state.manual_targets = []
        item = {"date": d, "part": p_val, "disp": f"{get_japanese_date_str(d)} [{pl}]"}
        if not any(t['disp'] == item['disp'] for t in st.session_state.manual_targets):
            st.session_state.manual_targets.append(item)

# --- UIレイヤー ---
col_l, col_r = st.columns([1, 4])
with col_l: st.image(LOGO_IMAGE, width=80) if os.path.exists(LOGO_IMAGE) else st.write("⚽")
with col_r: st.markdown("### High Ballers 予約システム")

pw = st.text_input("パスワード", type="password")
if pw == TEAM_PASSWORD:
    st.success("認証OK")

    # --- モード選択 (ご要望通りの5項目に固定) ---
    st.markdown("##### 🔍 検索モードを選択")
    mode = st.radio("目的に合わせて選択してください", 
        [
            "Deel 日付指定 (複数可)", 
            "Deel 監視 (火木日)", 
            "Deel 平日夜一括検索", 
            "全施設 リサーチ (火木日基準)", 
            "全施設 日付指定 (複数可)"
        ], index=0)

    # 日付指定UIの表示判定
    if "日付指定" in mode:
        st.markdown("---")
        st.markdown("##### 📅 日付追加エリア")
        c1, c2 = st.columns(2)
        with c1: st.selectbox("① 時間帯を選んでください", ["Avond (夜)", "Ochtend (朝)", "Middag (昼)"], key="p_label")
        with c2: st.date_input("② 日付をクリックして追加", datetime.today(), key="p_date", on_change=add_target)
        
        if st.session_state.get('manual_targets'):
            df_t = pd.DataFrame(st.session_state.manual_targets)
            df_t["削除"] = False
            edit_t = st.data_editor(df_t[["削除", "disp"]], hide_index=True, use_container_width=True)
            if st.button("🗑️ 選択した日付をリストから削除"):
                st.session_state.manual_targets = [st.session_state.manual_targets[i] for i in edit_t[edit_t["削除"]==False].index]
                st.rerun()

    # --- 検索実行 ---
    st.markdown("---")
    if st.button("🚀 Step 1: 空き状況を検索する", type="primary", use_container_width=True):
        # ターゲット日付の組み立て
        targets = []
        today = datetime.now().date()
        
        if "日付指定" in mode:
            targets = st.session_state.get('manual_targets', [])
            if not targets: st.error("日付をリストに追加してください。")
        elif "監視" in mode or "リサーチ" in mode:
            rules = [{"ws":[1,3],"p":"3"},{"ws":[6],"p":"1"}] # 火木夜、日朝
            for i in range(60):
                d = today + timedelta(days=i)
                for r in rules:
                    if d.weekday() in r['ws']: targets.append({"date":d, "part":r['p'], "disp":get_japanese_date_str(d)})
        elif "平日夜" in mode:
            for i in range(60):
                d = today + timedelta(days=i)
                if d.weekday() < 5: targets.append({"date":d, "part":"3", "disp":get_japanese_date_str(d)})

        if targets:
            st.info(f"「{mode}」で検索を開始します...")
            # ここに検索・予約ロジックが続きます
else:
    if pw: st.error("パスワードが違います")
