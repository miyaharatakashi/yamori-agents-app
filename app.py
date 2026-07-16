import re
import io
import json
from datetime import datetime
from pathlib import Path

import anthropic
import streamlit as st

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

COMMANDS_DIR = Path(__file__).resolve().parent / "commands"

CATEGORY_ORDER = ["strategy", "biz-dev", "management", "business", "arch", "pr", "hr", "ops", "free"]

CMD_LABELS = {
    "run":           "全工程実行",
    "planning":      "企画立案",
    "validate":      "事業検証",
    "financials":    "収支計画",
    "critic":        "批判・レビュー",
    "proposal":      "企画書作成",
    "research":      "リサーチ",
    "analyze":       "分析",
    "strategist":    "戦略立案",
    "report":        "レポート作成",
    "gather":        "数値収集",
    "issues":        "課題抽出",
    "minutes":       "議事録作成",
    "finance":       "財務分析",
    "strategy":      "事業戦略",
    "hearing":       "ヒアリング",
    "code-check":    "法規確認",
    "concept":       "コンセプト立案",
    "design-review": "設計レビュー",
    "checkin":       "チェックイン対応",
    "trouble":       "トラブル対応",
    "daily":         "日報・週報作成",
    "shift":         "シフト管理",
    "onboarding":    "オンボーディング",
    "interview":     "面接サポート",
    "job-post":      "求人票作成",
    "sns":           "SNS投稿文作成",
    "event":         "イベント企画",
    "code":          "コード生成・ツール開発",
    "general":       "自由相談・なんでも",
}

CATEGORY_LABELS = {
    "strategy":   "経営戦略",
    "biz-dev":    "事業開発",
    "management": "経営管理",
    "business":   "日常業務",
    "arch":       "建築設計",
    "pr":         "広報・PR",
    "hr":         "採用・人材",
    "ops":        "現場運営",
    "free":       "その他・自由入力",
}

DRIVE_FOLDER_ID = "1uppvoXFMxclbDMhMVeKniTgIHlw585do"

SYSTEM_PROMPT = """あなたはワカヤマヤモリ舎（和歌山市のエリアプロデュース会社）のAIエージェントです。
Vision「まちを元気に、もっとおもしろく」のもと、地域に根ざした提案を行ってください。
会社情報：
- 事業：Guesthouse RICO、una rama de RICO（Bar&Dining）、Studio RICO（コワーキング）、シェアハウス希望荘、Charlie's Bed（サイクリスト特化型宿泊）、大新ピクニック（マーケットイベント）、建築設計・不動産
- 所在地：和歌山市中之島
- 代表：宮原 崇"""


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def parse_md(path: Path) -> dict:
    """フロントマターとプロンプト本文をパース"""
    text = path.read_text(encoding="utf-8")
    description = ""
    argument_hint = ""

    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        m = re.search(r"description:\s*(.+)", fm)
        if m:
            description = m.group(1).strip()
        m = re.search(r"argument-hint:\s*(.+)", fm)
        if m:
            argument_hint = m.group(1).strip().strip("[]")

    prompt = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()

    return {
        "description": description,
        "argument_hint": argument_hint,
        "prompt": prompt,
    }


def load_commands() -> dict:
    """全カテゴリ・コマンドを読み込む"""
    result = {}
    for cat in CATEGORY_ORDER:
        cat_dir = COMMANDS_DIR / cat
        if not cat_dir.exists():
            continue
        cmds = {}
        files = sorted(cat_dir.glob("*.md"), key=lambda p: (p.stem != "run", p.stem))
        for f in files:
            cmds[f.stem] = parse_md(f)
        if cmds:
            result[cat] = cmds
    return result


def save_to_drive(content: str, category: str, command: str) -> str | None:
    """Google DriveにMarkdownファイルを保存してURLを返す"""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload

        creds_info = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=creds)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"{category}_{command}_{timestamp}.md"

        file_metadata = {
            "name": filename,
            "parents": [DRIVE_FOLDER_ID],
            "mimeType": "text/plain",
        }
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")),
            mimetype="text/plain",
        )
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
        ).execute()

        return file.get("webViewLink")
    except Exception as e:
        st.warning(f"Drive保存に失敗しました: {e}")
        return None


def stream_response(client: anthropic.Anthropic, messages: list) -> str:
    """APIを呼び出してストリーミングで返す"""
    full_response = ""
    placeholder = st.empty()
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            full_response += text
            placeholder.markdown(full_response)
    return full_response


# ---------------------------------------------------------------------------
# 認証
# ---------------------------------------------------------------------------

def check_password():
    if st.session_state.get("authenticated"):
        return

    st.markdown(
        "<h1 style='font-size:160%;line-height:1.4;'>AI Agent<br><span style='font-size:70%;'>for Wakayama Yamorisha Co., Ltd.</span></h1>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    pw = st.text_input("パスワード", type="password", placeholder="パスワードを入力")
    if st.button("ログイン", type="primary"):
        correct = st.secrets.get("PASSWORD", "")
        if pw == correct:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    st.stop()


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="ワカヤマヤモリ舎 AIエージェント",
        layout="wide",
    )

    st.markdown("""
        <style>
        .stMarkdown h1 { font-size: 1.4rem !important; }
        .stMarkdown h2 { font-size: 1.2rem !important; }
        .stMarkdown h3 { font-size: 1.0rem !important; }
        .stMarkdown h4 { font-size: 0.95rem !important; }
        .stMarkdown p, .stMarkdown li { font-size: 0.9rem !important; }
        </style>
    """, unsafe_allow_html=True)

    check_password()

    st.markdown(
        "<h1 style='font-size:160%;line-height:1.4;'>AI Agent<br><span style='font-size:70%;'>for Wakayama Yamorisha Co., Ltd.</span></h1>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    commands = load_commands()

    if not commands:
        st.error(f"コマンドファイルが見つかりません。\nパス: `{COMMANDS_DIR}`")
        st.stop()

    # セッション初期化
    if "messages" not in st.session_state:
        st.session_state.messages = []

    col1, col2 = st.columns([1, 2])

    with col1:
        # カテゴリ選択
        cat_keys = list(commands.keys())
        cat_labels = [CATEGORY_LABELS.get(k, k) for k in cat_keys]
        selected_cat_label = st.selectbox("カテゴリ", cat_labels)
        selected_cat = cat_keys[cat_labels.index(selected_cat_label)]

        # コマンド選択
        cmds = commands[selected_cat]
        selected_cmd = st.selectbox(
            "コマンド",
            list(cmds.keys()),
            format_func=lambda k: CMD_LABELS.get(k, k),
        )

        cmd_data = cmds[selected_cmd]
        st.info(cmd_data["description"])

        # 入力フォーム
        user_input = st.text_area(
            "入力内容",
            placeholder=cmd_data["argument_hint"],
            height=250,
        )

        run = st.button("実行する", type="primary", use_container_width=True)

        # 会話リセットボタン（会話中のみ表示）
        if st.session_state.messages:
            if st.button("会話をリセット", use_container_width=True):
                st.session_state.messages = []
                st.rerun()

    with col2:
        st.subheader("結果")

        try:
            client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
        except Exception:
            st.error("APIキーが設定されていません。")
            return

        # 実行ボタン押下：新しい会話を開始
        if run:
            if not user_input.strip():
                st.warning("入力内容を記入してください")
            else:
                full_prompt = cmd_data["prompt"].replace("$ARGUMENTS", user_input)
                st.session_state.messages = [{"role": "user", "content": full_prompt}]

                with st.chat_message("assistant"):
                    with st.spinner("実行中..."):
                        try:
                            response = stream_response(client, st.session_state.messages)
                            st.session_state.messages.append({"role": "assistant", "content": response})
                            # ダウンロードボタン
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                            filename = f"{selected_cat}_{selected_cmd}_{timestamp}.md"
                            st.download_button(
                                label="ファイルをダウンロード (.md)",
                                data=response.encode("utf-8"),
                                file_name=filename,
                                mime="text/markdown",
                            )
                        except anthropic.APIError as e:
                            st.error(f"APIエラー: {e}")

        # 会話履歴の表示（初回以降のメッセージ）
        elif st.session_state.messages:
            for msg in st.session_state.messages[1:]:  # 最初のシステムプロンプトはスキップ
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

        else:
            st.markdown(
                "<div style='color:#aaa;padding:2rem;text-align:center;'>"
                "左でカテゴリ・コマンドを選んで<br>入力内容を記入し「実行する」を押してください"
                "</div>",
                unsafe_allow_html=True,
            )

        # チャット入力（会話中のみ表示）
        if st.session_state.messages:
            if follow_up := st.chat_input("追加の質問・深掘りを入力してください"):
                st.session_state.messages.append({"role": "user", "content": follow_up})

                with st.chat_message("user"):
                    st.markdown(follow_up)

                with st.chat_message("assistant"):
                    try:
                        response = stream_response(client, st.session_state.messages)
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    except anthropic.APIError as e:
                        st.error(f"APIエラー: {e}")


if __name__ == "__main__":
    main()
