import streamlit as st
import os
import google.generativeai as genai
from PIL import Image
import pickle

# 1. 無料のAPIキーを設定
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

st.title("🎓 限界突破：大学テスト対策・オールインワンアプリ")

# --- ⚙️ 全体設定（サイドバー） ---
st.sidebar.header("⚙️ ユーザー設定")

# 【解決策】自分でユーザー名を決めてログインする仕組み
user_name = st.sidebar.text_input("👤 ユーザー名（英数字）：", value="user1").strip()

if not user_name:
    st.warning("👈 左側のサイドバーにユーザー名を入力してください。")
    st.stop()

# ユーザー専用のデータ保存フォルダのパスを設定（これでネット上でも消えません）
DATA_DIR = os.path.join("study_data", user_name)
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# --- 🗂️ 科目リストを保存・管理する仕組み ---
SUBJECTS_FILE = os.path.join(DATA_DIR, "subject_list.pkl")

# 保存されている科目リストがあれば読み込む
if "user_custom_subjects" not in st.session_state or st.session_state.get("last_user") != user_name:
    st.session_state.last_user = user_name
    try:
        with open(SUBJECTS_FILE, "rb") as f:
            st.session_state.user_custom_subjects = pickle.load(f)
    except FileNotFoundError:
        st.session_state.user_custom_subjects = []

# 1. 科目を新しく増やすフォーム
st.sidebar.subheader("➕ 科目を新しく増やす")
new_subject = st.sidebar.text_input("追加したい科目の名前を入力：", placeholder="例：マクロ経済学、有機化学", key="new_sub_input")

if st.sidebar.button("✨ この科目を追加登録", key="add_btn"):
    if new_subject:
        new_subject_clean = new_subject.strip()
        if new_subject_clean not in st.session_state.user_custom_subjects:
            st.session_state.user_custom_subjects.append(new_subject_clean)
            with open(SUBJECTS_FILE, "wb") as f:
                pickle.dump(st.session_state.user_custom_subjects, f)
            st.sidebar.success(f"「{new_subject_clean}」を追加しました！")
            st.rerun()
        else:
            st.sidebar.warning("その科目はすでに登録されています。")
    else:
        st.sidebar.error("名前を入力してください。")

st.sidebar.markdown("---")

# 2. 登録された科目から選ぶセレクトボックス
if st.session_state.user_custom_subjects:
    subject = st.sidebar.selectbox("現在の対策科目：", st.session_state.user_custom_subjects)
else:
    st.sidebar.info("💡 まずは上のフォームに科目名を入れて登録してください。")
    subject = None

difficulty = st.sidebar.select_slider("難易度：", options=["基礎", "標準", "発展"], value="標準")

# --- 💡 科目が選ばれている場合のみメイン処理を行う ---
if subject:
    SAVE_FILE = os.path.join(DATA_DIR, f"{subject}.pkl")

    if "current_subject" not in st.session_state or st.session_state.current_subject != subject or st.session_state.get("last_loaded_user") != user_name:
        st.session_state.current_subject = subject
        st.session_state.last_loaded_user = user_name
        try:
            with open(SAVE_FILE, "rb") as f:
                saved_data = pickle.load(f)
                st.session_state.generated_data = saved_data.get("generated_data", [])
                st.session_state.wrong_list = saved_data.get("wrong_list", [])
                st.session_state.flashcards = saved_data.get("flashcards", [])
                st.session_state.mock_exam = saved_data.get("mock_exam", None)
        except FileNotFoundError:
            st.session_state.generated_data = []
            st.session_state.wrong_list = []
            st.session_state.flashcards = []
            st.session_state.mock_exam = None

    def save_data():
        with open(SAVE_FILE, "wb") as f:
            pickle.dump({
                "generated_data": st.session_state.generated_data,
                "wrong_list": st.session_state.wrong_list,
                "flashcards": st.session_state.flashcards,
                "mock_exam": st.session_state.mock_exam
            }, f)

    if st.sidebar.button(f"⚠️ {subject} のデータのみ削除"):
        if os.path.exists(SAVE_FILE):
            os.remove(SAVE_FILE)
        st.session_state.generated_data = []
        st.session_state.wrong_list = []
        st.session_state.flashcards = []
        st.session_state.mock_exam = None
        st.sidebar.success(f"{subject} のデータをリセットしました！")

    # タブの作成
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔥 過去問から類題・模試", 
        "📝 自分の答案を採点", 
        "📇 公式暗記カード",
        "❌ 弱点克服モード",
        "🕒 ミニ模試（時間制限）"
    ])

    # --- タブ1：通常の類題生成 ＆ 模試作成 ---
    with tab1:
        st.subheader("📷 過去問・レジュメから問題を作る")
        uploaded_files = st.file_uploader("問題画像（複数可）", type=["png", "jpg", "jpeg"], accept_multiple_files=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔥 類題を一括生成"):
                if api_key:
                    st.info("類題を生成中...")
                    st.session_state.generated_data = []
                    
                    if uploaded_files:
                        for i, uploaded_file in enumerate(uploaded_files):
                            image = Image.open(uploaded_file)
                            try:
                                model = genai.GenerativeModel('gemini-2.5-flash')
                                prompt = f"大学の定期テストにおける【{subject}】の【{difficulty}】レベルの類題を1問作成し、その後に詳細な解答と解説を出力してください。数式は LaTeX ($...$) を使用してください。"
                                response = model.generate_content([prompt, image])
                                st.session_state.generated_data.append({
                                    "id": f"{subject}_{i}", "subject": subject, "has_image": True, "result": response.text
                                })
                            except Exception as e: st.error(f"エラー: {e}")
                    else:
                        try:
                            model = genai.GenerativeModel('gemini-2.5-flash')
                            prompt = f"大学の定期テストにおける【{subject}】の【{difficulty}】レベルの典型的な問題を1問ゼロから作成し、詳細な解答と解説を出力してください。数式は LaTeX ($...$) を使用してください。"
                            response = model.generate_content(prompt)
                            st.session_state.generated_data.append({
                                "id": f"{subject}_text", "subject": subject, "has_image": False, "result": response.text
                            })
                        except Exception as e: st.error(f"エラー: {e}")
                    
                    save_data()
                    st.success(f"{subject} の類題を保存しました！")
                        
        with col2:
            if st.button("⏱️ ミニ模試（3問構成）を作成"):
                if api_key:
                    st.info("本番用の模試を作成中...")
                    try:
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        prompt = f"大学の定期テスト【{subject}】の【{difficulty}】レベルの「模擬試験（大問3問）」を作成してください。まずは問題のみを制限時間「60分」の案内と共に出力し、解答・解説は後半に隠して出力してください。"
                        
                        if uploaded_files:
                            images = [Image.open(f) for f in uploaded_files[:3]]
                            response = model.generate_content([prompt] + images)
                        else:
                            response = model.generate_content(prompt)
                            
                        st.session_state.mock_exam = response.text
                        save_data()
                        st.success("ミニ模試が作成されました！『ミニ模試』タブを開いて挑戦してください！")
                    except Exception as e: st.error(f"エラー: {e}")

        for data in st.session_state.generated_data:
            st.markdown("---")
            st.markdown(data["result"])
            if st.button("❌ 間違えた！弱点リストに登録", key=f"w_{data['id']}"):
                if data not in st.session_state.wrong_list:
                    st.session_state.wrong_list.append(data)
                    save_data()
                    st.success("弱点リストに追加＆保存しました！")

    # --- タブ2：自分の答案を採点 ---
    with tab2:
        st.subheader("📝 自分のノート・答案の自動添削")
        ans_file = st.file_uploader("自分の答案（ノート）の写真", type=["png", "jpg", "jpeg"], key="user_ans")
        if st.button("💯 採点・添削してもらう"):
            if ans_file and api_key:
                st.info("あなたの記述を採点中...")
                try:
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    img = Image.open(ans_file)
                    prompt = f"大学の【{subject}】のテスト答案として、このノートの記述を採点してください。どこまでが合っていて、どこで計算ミスや論理の飛躍があるかを指摘し、100点満点中何点かを出し、合格のためのアドバイスを記述してください。"
                    response = model.generate_content([prompt, img])
                    st.markdown("### 📊 採点結果")
                    st.markdown(response.text)
                except Exception as e: st.error(f"エラー: {e}")

    # --- タブ3：公式暗記カード ---
    with tab3:
        st.subheader("📇 重要公式フラッシュカード")
        if st.button("✨ 重要公式カードを自動生成"):
            if api_key:
                st.info("公式を作成・抽出中...")
                try:
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    prompt = f"大学の【{subject}】のテストで必須となる重要公式や定義を5つ抽出し、'公式名: その内容や意味' の形式でリストアップしてください。"
                    if uploaded_files:
                        images = [Image.open(f) for f in uploaded_files]
                        response = model.generate_content([prompt] + images)
                    else:
                        response = model.generate_content(prompt)
                    lines = response.text.strip().split("\n")
                    st.session_state.flashcards = [l for l in lines if l]
                    save_data()
                    st.success("カードが完成＆保存されました！")
                except Exception as e: st.error(f"エラー: {e}")

        if st.session_state.flashcards:
            st.write("💡 タップ（クリック）すると答え（意味・公式）が見えます")
            for idx, card in enumerate(st.session_state.flashcards):
                with st.expander(f"🔮 キーワード {idx+1}"):
                    st.markdown(card)

    # --- タブ4：弱点克服モード ---
    with tab4:
        st.subheader("📋 弱点克服リスト")
        if not st.session_state.wrong_list: st.write("弱点はありません！")
        for idx, item in enumerate(st.session_state.wrong_list):
            st.markdown(f"### 📌 弱点 {idx+1}")
            st.markdown(item["result"])
            if st.button("🔄 この弱点を克服する類題を出す", key=f"ret_{idx}"):
                model = genai.GenerativeModel('gemini-2.5-flash')
                res = model.generate_content(f"ユーザーはこの問題({item['result']})を間違えました。弱点克服のためのアドバイス付き類題と解説を作ってください。")
                st.markdown(res.text)

    # --- タブ5：ミニ模試モード ---
    with tab5:
        st.subheader("⏱ 本番想定ミニ模試ルーム")
        if st.session_state.mock_exam:
            st.markdown(st.session_state.mock_exam)
        else:
            st.write("「過去問から類題・模試」タブで問題を作成すると、ここに模試が表示されます。")
else:
    st.info("👈左側のサイドバーにある「＋ 科目を新しく増やす」から、まずは対策したい科目を登録してください！")
