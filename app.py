import streamlit as st
import json
import os
import random
import requests
import base64

# --- 設定・データ管理 (クラウド上でも動くようにセッションで簡易管理) ---
if "questions" not in st.session_state: st.session_state.questions = []
if "flashcards" not in st.session_state: st.session_state.flashcards = []
if "weaknesses" not in st.session_state: st.session_state.weaknesses = []
if "subjects" not in st.session_state: st.session_state.subjects = ["デフォルト科目"]

# --- ライブラリのバグを100%回避してGoogleサーバーと直接通信する関数 ---
def call_gemini_api(api_key, prompt, uploaded_file=None, is_multiple=False):
    # 【ここを修正】最新のキー(AQ...)に対応したURLの書き方に変更しました
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key  # キーをここに安全に乗せる形式にします
    }
    
    contents = []
    if uploaded_file:
        if is_multiple:
            for f in uploaded_file:
                base64_image = base64.b64encode(f.read()).decode('utf-8')
                f.seek(0)
                contents.append({"inline_data": {"mime_type": f.type, "data": base64_image}})
        else:
            base64_image = base64.b64encode(uploaded_file.read()).decode('utf-8')
            uploaded_file.seek(0)
            contents.append({"inline_data": {"mime_type": uploaded_file.type, "data": base64_image}})
            
    contents.append({"text": prompt})
    payload = {"contents": [{"parts": contents}]}
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    else:
        raise Exception(f"Googleエラー ({response.status_code}): {response.text}")

# --- メインのUI構築 ---
st.set_page_config(page_title="AI大学テスト対策", layout="wide")

# ⚙️ 左サイドバー
st.sidebar.header("⚙️ 設定・科目管理")
st.sidebar.subheader("🔑 API設定")
api_key = st.sidebar.text_input("Gemini APIキーを入力", type="password")

st.sidebar.divider()
st.sidebar.subheader("👤 ユーザー設定")
current_user = st.sidebar.text_input("ユーザー名を入力", value="user1")

st.sidebar.subheader("➕ 新しく科目を増やす")
new_subject = st.sidebar.text_input("科目の名前を入力")
if st.sidebar.button("科目を追加登録"):
    if new_subject and new_subject not in st.session_state.subjects:
        st.session_state.subjects.append(new_subject)
        st.sidebar.success(f"「{new_subject}」を追加しました！")

st.sidebar.subheader("📂 現在の対象科目")
selected_subject = st.sidebar.selectbox("科目を選択してください", st.session_state.subjects)

# APIキーが入力されていない場合は案内を出す
if not api_key:
    st.info("左側のメニューにGemini APIキー（コピーした文字列）を入力してください。")
    st.stop()

# 📂 メイン画面の表示
st.title(f"📚 {selected_subject} の学習ダッシュボード")

# タブの作成
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔥 過去問から類題", "📇 公式暗記カード", "⏱️ ミニ模試", "📝 答案を採点", "❌ 弱点克服モード"
])

# --- 1. 類題生成 ---
with tab1:
    st.subheader("📷 過去問・レジュメから類題を作る")
    uploaded_imgs = st.file_uploader("問題画像 (複数可)", accept_multiple_files=True, type=["png", "jpg", "jpeg"], key="q_gen")
    num_q = st.slider("生成する問題数", 1, 10, 3)
    
    if st.button("🔥 類題を一括生成"):
        if uploaded_imgs:
            with st.spinner("Geminiが分析して類題を作成中..."):
                try:
                    prompt = f"以下の画像を分析し、類似した問題を{num_q}問作成してください。必ず各問題の先頭に「【問題】」という文字をつけてください。解答や解説は含めず、問題文のみを出力してください。"
                    res_text = call_gemini_api(api_key, prompt, uploaded_imgs, is_multiple=True)
                    
                    for block in res_text.split("【問題】"):
                        if block.strip():
                            st.session_state.questions.append("【問題】" + block.strip())
                    st.success("類題の生成が完了し、履歴に保存されました！")
                except Exception as e:
                    st.error(f"エラー: {e}")
        else:
            st.warning("画像をアップロードしてください。")

    if st.session_state.questions:
        st.write("---")
        st.subheader("📂 作成した類題の履歴")
        for i, q in enumerate(st.session_state.questions):
            with st.expander(f"問題 {i+1}", expanded=True):
                st.write(q)
                col1, col2 = st.columns([3, 1])
                with col1:
                    weak_input = st.text_input("弱点タグ (例: 微分, 熱力学)", key=f"weak_{i}", label_visibility="collapsed", placeholder="弱点タグを追加...")
                with col2:
                    if st.button("弱点を記録", key=f"btn_{i}"):
                        if weak_input and weak_input not in st.session_state.weaknesses:
                            st.session_state.weaknesses.append(weak_input)
                            st.toast(f"弱点「{weak_input}」を記録しました！")

# --- 2. 暗記カード ---
with tab2:
    st.subheader("📇 画像から暗記カードを自動生成")
    flash_imgs = st.file_uploader("公式やレジュメの画像", accept_multiple_files=True, type=["png", "jpg", "jpeg"], key="f_gen")
    if st.button("カードを生成"):
        if flash_imgs:
            with st.spinner("重要なキーワードと公式を抽出中..."):
                try:
                    prompt = "画像に含まれる重要な公式や英単語、専門用語を抽出し、暗記カード形式で出力してください。「【用語/公式】: その説明や意味」という形式で1行ずつ箇条書きにしてください。"
                    res_text = call_gemini_api(api_key, prompt, flash_imgs, is_multiple=True)
                    cards = [line.strip() for line in res_text.split('\n') if line.strip() and "】" in line]
                    st.session_state.flashcards.extend(cards if cards else [res_text])
                    st.success("暗記カードを作成しました！")
                except Exception as e:
                    st.error(f"エラー: {e}")
        else:
            st.warning("画像をアップロードしてください。")
    
    for c in st.session_state.flashcards:
        st.info(c)

# --- 3. ミニ模試 ---
with tab3:
    st.subheader("⏱️ ミニ模試の作成")
    st.write("保存されている類題の中から、ランダムで5〜7問を出題します。")
    total_q = len(st.session_state.questions)
    
    if st.button("ミニ模試を出題する"):
        if total_q >= 5:
            num = min(total_q, random.randint(5, 7))
            mock_exam = random.sample(st.session_state.questions, num)
            st.success(f"全 {num} 問のミニ模試を作成しました！")
            for i, q in enumerate(mock_exam):
                st.markdown(f"**第 {i+1} 問**")
                st.write(q)
                st.divider()
        else:
            st.warning(f"現在履歴にある類題は {total_q} 問です。ミニ模試を作るには、タブ1で類題を5問以上生成してください。")

# --- 4. 答案採点 ---
with tab4:
    st.subheader("📝 AIによる答案採点")
    ans_img = st.file_uploader("自分の答案画像", type=["png", "jpg", "jpeg"], key="ans_grade")
    if st.button("答案を採点"):
        if ans_img:
            with st.spinner("採点中..."):
                try:
                    prompt = "この画像の答案を採点し、100点満点で点数をつけてください。また、どこが間違っているか、どう直せばよいかの解説を丁寧に記述してください。"
                    res = call_gemini_api(api_key, prompt, ans_img, is_multiple=False)
                    st.success("採点が完了しました！")
                    st.write(res)
                except Exception as e:
                    st.error(f"エラー: {e}")
        else:
            st.warning("答案の画像をアップロードしてください。")

# --- 5. 弱点克服 ---
with tab5:
    st.subheader("❌ 弱点克服モード")
    weak_list = list(set(st.session_state.weaknesses))
    if weak_list:
        target = st.multiselect("克服したい弱点を選択", weak_list)
        if st.button("弱点特化の類題を生成"):
            if target:
                with st.spinner("専用の特化問題を生成中..."):
                    try:
                        prompt = f"ユーザーの現在の弱点分野は「{', '.join(target)}」です。この弱点をピンポイントで克服するための特化型問題を1問作成し、その後に詳しい解説を記述してください。"
                        w_q = call_gemini_api(api_key, prompt)
                        st.success("生成完了！")
                        st.write(w_q)
                    except Exception as e:
                        st.error(f"エラー: {e}")
            else:
                st.warning("弱点を選択してください。")
    else:
        st.info("現在記録されている弱点はありません。タブ1の履歴から「弱点を記録」してください。")
