import streamlit as st
import time
import pandas as pd
from datetime import datetime, timedelta
# Selenium関連は既存のものをそのまま使用

# --- 設定読み込み ---
TEAM_PASSWORD = st.secrets["team_password"]
BOOKING_PASSWORD = st.secrets["booking_password"]
USER_PROFILE = st.secrets["user_profile"]

TARGET_DEEL_FACILITIES = ["Sporthal Deel 1", "Sporthal Deel 2"]

st.set_page_config(page_title="High Ballers 予約", page_icon="⚽", layout="centered")

# --- UIレイヤー ---
st.markdown("### ⚽ High Ballers 予約システム")
password = st.text_input("認証パスワード", type="password")

if password == TEAM_PASSWORD:
    st.success("認証OK")

    # --- 1. あなたのイメージ通りの検索モード選択 ---
    st.markdown("##### 🔍 検索モードを選択")
    mode = st.radio(
        "目的に合わせて選択してください",
        [
            "Deel 日付指定 (複数可)", 
            "Deel 監視 (火木日)", 
            "Deel 平日夜一括", 
            "全施設 リサーチ", 
            "全施設 日付指定 (複数可)"
        ],
        horizontal=False # スマホで見やすいよう縦並びに
    )

    # --- 2. 日付指定が必要なモードの場合のみカレンダーを表示 ---
    use_manual_date = "日付指定" in mode
    
    if use_manual_date:
        if 'manual_targets' not in st.session_state: st.session_state.manual_targets = []
        st.markdown("---")
        st.markdown("##### 📅 調べたい日付をリストに追加")
        c1, c2 = st.columns(2)
        with c1: p_label = st.selectbox("時間帯", ["Avond (夜)", "Ochtend (朝)", "Middag (昼)"])
        with c2: 
            target_date = st.date_input("日付を選択")
            if st.button("リストに追加"):
                p_val = {"Avond (夜)": "3", "Ochtend (朝)": "1", "Middag (昼)": "2"}[p_label]
                st.session_state.manual_targets.append({"date": target_date, "part": p_val, "disp": f"{target_date.strftime('%m/%d')}({p_label})"})
        
        if st.session_state.manual_targets:
            st.table(pd.DataFrame(st.session_state.manual_targets)[["disp"]])
            if st.button("リストをクリア"): 
                st.session_state.manual_targets = []
                st.rerun()

    # --- 3. 検索実行ボタン ---
    st.markdown("---")
    if st.button("🚀 この内容で空きを検索する", type="primary", use_container_width=True):
        targets = []
        today = datetime.now().date()
        is_all_facilities = "全施設" in mode
        
        # モードに応じた検索ターゲットの組み立て
        if use_manual_date:
            targets = st.session_state.manual_targets
        elif "監視" in mode or "リサーチ" in mode:
            rules = [{"ws":[1,3],"p":"3"},{"ws":[6],"p":"1"}]
            for i in range(60):
                d = today + timedelta(days=i)
                for r in rules:
                    if d.weekday() in r['ws']: targets.append({"date":d, "part":r['p'], "disp":d.strftime('%m/%d')})
        elif "平日夜" in mode:
            for i in range(60):
                d = today + timedelta(days=i)
                if d.weekday() < 5: targets.append({"date":d, "part":"3", "disp":d.strftime('%m/%d')})

        # --- 検索ロジック (driverの起動〜結果取得) ---
        if not targets:
            st.error("日付が指定されていません。")
        else:
            # ここに検索処理（search_on_site）を記述
            # is_all_facilities が True なら Deel 以外も結果に追加、False なら Deel のみ抽出
            st.info("検索を開始します...")
            # ... (中略) ...

else:
    st.info("パスワードを入力してください。")
