import streamlit as st
import google.generativeai as genai
import json
import os
import random
import pandas as pd
from PIL import Image

# --- 設定・データ管理 (セッション状態の初期化) ---
if "questions" not in st.session_state: st.session_state.questions = []
if "flashcards" not in st.session_state: st.session_state.flashcards = []
if "weaknesses" not in st.session_state: st.session_state.weaknesses = []
if "subjects" not in st.session_state: st.session_state.subjects = ["デフォルト科目"]

# Secretsの確認
if "GEMINI_API_KEY" not in st.secrets or "SPREADSHEET_URL" not in st.secrets:
    st.error("Streamlitの管理画面（Secrets）に GEMINI_API_KEY または SPREADSHEET_URL が設定されていません。")
    st.stop()

# Geminiの初期化
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-3.5-flash')

# 🔗 スプレッドシートのURLをCSVエクスポート用URLに安全に変換する関数
def get_csv_url(worksheet_name):
    base_url = st.secrets["SPREADSHEET_URL"].split("/edit")[0]
    return f"{base_url}/gviz/tq?tqx=out:csv&sheet={worksheet_name}"

# 🔄 1. データ読み込み関数 (超安定版：エラーが起きてもアプリを止めない)
def load_all_data():
    current_subj = st.session_state.get("selected_subject", "デフォルト科目")

    # --- 科目の読み込み (subjects シート) ---
    try:
        csv_url = get_csv_url("subjects")
        df_sub = pd.read_csv(csv_url)
        if not df_sub.empty and "subject" in df_sub.columns:
            st.session_state.subjects = df_sub["subject"].dropna().tolist()
            if not st.session_state.subjects:
                st.session_state.subjects = ["デフォルト科目"]
    except Exception as e:
        # 読み込めなくてもアプリを止めずに、デフォルト科目を入れる
        st.session_state.subjects = ["デフォルト科目"]

    # --- 類題と弱点タグの読み込み (questions シート) ---
    try:
        csv_url = get_csv_url("questions")
        df_q = pd.read_csv(csv_url)
        if not df_q.empty and "question" in df_q.columns:
            df_filtered = df_q[df_q["subject"] == current_subj]
            st.session_state.questions = df_filtered["question"].dropna().tolist()
            if "weakness" in df_filtered.columns:
                st.session_state.weaknesses = list(set(df_filtered["weakness"].dropna().tolist()))
        else:
            st.session_state.questions = []
            st.session_state.weaknesses = []
    except Exception as e:
        st.session_state.questions = []
        st.session_state.weaknesses = []

    # --- 暗記カードの読み込み (flashcards シート) ---
    try:
        csv_url = get_csv_url("flashcards")
        df_f = pd.read_csv(csv_url)
        if not df_f.empty and "front" in df_f.columns and "back" in df_f.columns:
            df_filtered_f = df_f[df_f["subject"] == current_subj]
            st.session_state.flashcards = df_filtered_f[["front", "back"]].dropna().to_dict(orient="records")
        else:
            st.session_state.flashcards = []
    except Exception as e:
        st.session_state.flashcards = []


# 💾 2. データ書き込み関数 (もし接続エラーになっても画面に優しいエラーを表示する)
def save_subjects():
    try:
        # 新しい接続ライブラリを使って裏で安全に更新
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection, spreadsheet=st.secrets["SPREADSHEET_URL"])
        df = pd.DataFrame({"subject": st.session_state.subjects})
        conn.update(worksheet="subjects", data=df)
    except Exception as e:
        st.error(f"スプレッドシートへの保存に失敗しました。共有設定が「編集者」になっているか確認してください。({e})")

def save_new_question(subject, question_text, weakness_text=""):
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection, spreadsheet=st.secrets["SPREADSHEET_URL"])
        try:
            df_existing = conn.read(worksheet="questions", ttl=0)
        except:
            df_existing = pd.DataFrame(columns=["subject", "question", "weakness"])
        new_data = pd.DataFrame([{"subject": subject, "question": question_text, "weakness": weakness_text}])
        df_combined = pd.concat([df_existing, new_data], ignore_index=True)
        conn.update(worksheet="questions", data=df_combined)
    except Exception as e:
        st.error(f"類題の保存に失敗しました。({e})")

def update_question_weakness(subject, question_text, new_weakness):
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection, spreadsheet=st.secrets["SPREADSHEET_URL"])
        df_existing = conn.read(worksheet="questions", ttl=0)
        if not df_existing.empty:
            mask = (df_existing["subject"] == subject) & (df_existing["question"] == question_text)
            if mask.any():
                df_existing.loc[mask, "weakness"] = new_weakness
                conn.update(worksheet="questions", data=df_existing)
    except Exception as e:
        st.error(f"弱点保存エラー: {e}")

def save_new_flashcard(subject, front, back):
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection, spreadsheet=st.secrets["SPREADSHEET_URL"])
        try:
            df_existing = conn.read(worksheet="flashcards", ttl=0)
        except:
            df_existing = pd.DataFrame(columns=["subject", "front", "back"])
        new_data = pd.DataFrame([{"subject": subject, "front": front, "back": back}])
        df_combined = pd.concat([df_existing, new_data], ignore_index=True)
        conn.update(worksheet="flashcards", data=df_combined)
    except Exception as e:
        st.error(f"暗記カードの保存に失敗しました。({e})")


# 🤖 3. Gemini通信関数
def call_gemini_with_lib(prompt, uploaded_files=None, is_multiple=False):
    try:
        contents = []
        if uploaded_files:
            if is_multiple:
                for f in uploaded_files:
                    img = Image.open(f)
                    contents.append(img)
            else:
                img = Image.open(uploaded_files)
                contents.append(img)
        contents.append(prompt)
        response = model.generate_content(contents)
        return response.text
    except Exception as e:
        raise Exception(f"Geminiエラー: {e}")


# --- 🖥️ メインのUI構築 ---
st.set_page_config(page_title="AI大学テスト対策", layout="wide")

if "data_loaded" not in st.session_state:
    load_all_data()
    st.session_state.data_loaded = True

# ⚙️ 左サイドバー設定
st.sidebar.header("⚙️ 設定・科目管理")
current_user = st.sidebar.text_input("ユーザー名を入力", value="user1")

st.sidebar.subheader("➕ 新しく科目を増やす")
new_subject = st.sidebar.text_input("科目の名前を入力")
if st.sidebar.button("科目を追加登録"):
    if new_subject and new_subject not in st.session_state.subjects:
        st.session_state.subjects.append(new_subject)
        save_subjects()
        st.sidebar.success(f"「{new_subject}」を追加しました！")
        st.rerun()

st.sidebar.subheader("📂 現在の対象科目")
old_selected = st.session_state.get("selected_subject", "デフォルト科目")
selected_subject = st.sidebar.selectbox(
    "科目を選択してください", 
    st.session_state.subjects, 
    index=st.session_state.subjects.index(old_selected) if old_selected in st.session_state.subjects else 0
)

if selected_subject != old_selected:
    st.session_state.selected_subject = selected_subject
    load_all_data()
    st.rerun()

st.session_state.selected_subject = selected_subject

# メイン画面
st.title(f"📚 {selected_subject} の学習ダッシュボード")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔥 過去問から類題", "📇 公式暗記カード", "⏱️ ミニ模試", "📝 答案を採点", "❌ 弱点克服モード"
])

# --- 1. 類題生成 タブ ---
with tab1:
    st.subheader("📷 過去問・レジュメから類題を作る")
    uploaded_imgs = st.file_uploader("問題画像 (複数可)", accept_multiple_files=True, type=["png", "jpg", "jpeg"], key="q_gen")
    num_q = st.slider("生成する問題数", 1, 10, 3)
    
    if st.button("🔥 類題を一括生成"):
        if uploaded_imgs:
            with st.spinner("Geminiが分析して類題を作成中..."):
                try:
                    prompt = f"以下の画像を分析し、類似した問題を{num_q}問作成してください。必ず各問題の先頭に「【問題】」という文字をつけてください。解答や解説は含めず、問題文のみを出力してください。"
                    res_text = call_gemini_with_lib(prompt, uploaded_imgs, is_multiple=True)
                    
                    for block in res_text.split("【問題】"):
                        if block.strip():
                            q_text = "【問題】" + block.strip()
                            st.session_state.questions.append(q_text)
                            save_new_question(selected_subject, q_text)
                    st.success("類題の生成が完了し、スプレッドシートに同期されました！")
                    st.rerun()
                except Exception as e:
                    st.error(f"{e}")
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
                    weak_input = st.text_input("弱点タグ (例: 微分, 熱力学)", key=f"weak_{i}", placeholder="弱点タグを追加...", label_visibility="collapsed")
                with col2:
                    if st.button("弱点を記録", key=f"btn_{i}"):
                        if weak_input:
                            update_question_weakness(selected_subject, q, weak_input)
                            st.toast(f"弱点「{weak_input}」を登録しました！")
                            load_all_data()
                            st.rerun()


# --- 2. 暗記カード タブ ---
with tab2:
    st.subheader("📇 画像から一問一答カードを自動生成")
    flash_imgs = st.file_uploader("公式やレジュメの画像", accept_multiple_files=True, type=["png", "jpg", "jpeg"], key="f_gen")
    
    if st.button("カードを生成"):
        if flash_imgs:
            with st.spinner("重要なキーワードと公式を一問一答形式で抽出中..."):
                try:
                    prompt = """
                    画像から重要な用語、公式、定義、英単語などを抽出して「一問一答の暗記カード」にしてください。
                    
                    必ず以下のJSONフォーマットの配列で出力してください。他の文字は一切含めないでください。
                    [
                      {"front": "問題（例：〇〇の公式は？）", "back": "解答（例：E = mc^2）"},
                      {"front": "問題2", "back": "解答2"}
                    ]
                    """
                    res_text = call_gemini_with_lib(prompt, flash_imgs, is_multiple=True)
                    
                    cleaned_json = res_text.strip()
                    if cleaned_json.startswith("```json"):
                        cleaned_json = cleaned_json.split("```json")[1].split("```")[0].strip()
                    elif cleaned_json.startswith("```"):
                        cleaned_json = cleaned_json.split("```")[1].split("```")[0].strip()
                        
                    new_cards = json.loads(cleaned_json)
                    
                    for card in new_cards:
                        front = card.get("front", "").strip()
                        back = card.get("back", "").strip()
                        if front and back:
                            save_new_flashcard(selected_subject, front, back)
                    
                    st.success("一問一答暗記カードを作成し、スプレッドシートに同期しました！")
                    load_all_data()
                    st.rerun()
                except Exception as e:
                    st.error(f"カードの解析に失敗しました。もう一度お試しください。({e})")
        else:
            st.warning("画像をアップロードしてください。")
    
    if st.session_state.flashcards:
        st.write("---")
        st.subheader(f"📂 {selected_subject} の一問一答カード (タップで解答表示)")
        
        for idx, c in enumerate(st.session_state.flashcards):
            with st.container():
                st.markdown(f"### 🎴 暗記カード {idx+1}")
                st.info(f"**【問】** {c['front']}")
                with st.expander("👉 解答を確認する"):
                    st.success(f"**【答】** {c['back']}")
                st.divider()


# --- 3. ミニ模試 タブ ---
with tab3:
    st.subheader("⏱️ ミニ模試の作成")
    st.write("保存されている類題の中から、ランダムで5〜7問をテストとして出題します。")
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
            st.warning(f"現在、この科目の類題はスプレッドシートに {total_q} 問しかありません。ミニ模試を作るには、タブ1で類題を5問以上作成してください。")


# --- 4. 答案採点 タブ ---
with tab4:
    st.subheader("📝 AIによる答案採点")
    ans_img = st.file_uploader("自分の答案画像", type=["png", "jpg", "jpeg"], key="ans_grade")
    if st.button("答案を採点"):
        if ans_img:
            with st.spinner("採点中..."):
                try:
                    prompt = "この画像の答案を採点し、100点満点で点数をつけてください。また、どこが間違っているか、どう直せばよいかの解説を丁寧に記述してください。"
                    res = call_gemini_with_lib(prompt, ans_img, is_multiple=False)
                    st.success("採点が完了しました！")
                    st.write(res)
                except Exception as e:
                    st.error(f"{e}")
        else:
            st.warning("答案の画像をアップロードしてください。")


# --- 5. 弱点克服 タブ ---
with tab5:
    st.subheader("❌ 弱点克服モード")
    weak_list = list(set(st.session_state.weaknesses))
    
    if weak_list:
        target = st.multiselect("克服したい弱点を選択", weak_list)
        if st.button("弱点特化の類題を生成"):
            if target:
                with st.spinner("専用 of 特化問題を生成中..."):
                    try:
                        prompt = f"ユーザーの現在の弱点分野は「{', '.join(target)}」です。この弱点をピンポイントで克服するための特化型問題を1問作成し、その後に詳しい解説を記述してください。"
                        w_q = call_gemini_with_lib(prompt)
                        st.success("生成完了！")
                        st.write(w_q)
                    except Exception as e:
                        st.error(f"{e}")
            else:
                st.warning("弱点を選択してください。")
    else:
        st.info("現在この科目に登録されている弱点はありません。タブ1の履歴から「弱点を記録」してください。")
