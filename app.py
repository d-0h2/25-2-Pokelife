# app.py
import re
import streamlit as st
import pandas as pd
import sqlite3
import json
import textwrap
import os
import random  
import base64

# 필요한 모든 유틸리티 함수 임포트
from utils import nl_to_sql, DB_PATH, create_chart_base64, generate_final_report, get_pokemon_image_html_from_dexnum


# ------------------------------------------------
# 0. 기본 유틸리티
# ------------------------------------------------
def get_image_base64(path: str) -> str:
    """파일 경로에서 Base64 문자열을 인코딩하여 반환"""
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        print(f"⚠️ Warning: File not found at {path}.")
        return ""
    except Exception as e:
        print(f"❌ Error encoding {path}: {e}")
        return ""


# ------------------------------------------------
# 1. Streamlit 설정 및 초기화
# ------------------------------------------------

# Streamlit 초기 설정
st.set_page_config(
    page_title="오박사의 포켓몬 연구소",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = []
if "first_greeting_done" not in st.session_state:
    st.session_state.first_greeting_done = False


def set_background(image_file: str, bottom_img: str):
    """배경 이미지 및 커스텀 CSS 스타일을 설정"""
    
    def encode(path: str) -> str:
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except FileNotFoundError:
            print(f"⚠️ Warning: File not found at {path}. Using fallback CSS.")
            return ""
        except Exception as e:
            print(f"❌ Error encoding {path}: {e}")
            return ""

    bg = encode(image_file)
    bottom = encode(bottom_img)
    
    # 폰트 파일 Base64 인코딩 추가
    font_woff2 = encode("font/neodgm.woff2")
    font_woff = encode("font/neodgm.woff")

    st.markdown(
        f"""
        <style>

        /* ===============================
           0. 폰트 로딩 및 기본 스타일링 (기존 코드 유지)
           ================================*/
        @font-face {{
            font-family: 'NeoDGM';
            src: url(data:font/woff2;charset=utf-8;base64,{font_woff2}) format('woff2'),
                 url(data:font/woff;charset=utf-8;base64,{font_woff}) format('woff');
            font-weight: normal;
            font-style: normal;
        }}
        
        /* 폰트 적용 (전체) 및 글씨 크기/줄 간격 조절 */
        html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"],
        .stMarkdown,
        h1, h2, h3, h4, h5, h6,
        section[data-testid="stSidebar"] *,
        [data-testid="stChatMessage"] * {{
            font-family: 'NeoDGM', 'Malgun Gothic', sans-serif !important;
            font-size: 15px !important;
            line-height: 1.5 !important;
        }}
        
        /* -------------------------------------------
           0-1. 제목 스타일링 (윤곽선)
        ------------------------------------------- */
        /* H1: 메인 제목 (2px 윤곽선) */
        h1 {{
            font-size: 32px !important;
            color: black !important;
            text-shadow:
                -2px -2px 0 #FFFFFF,  
                 2px -2px 0 #FFFFFF,
                -2px  2px 0 #FFFFFF,
                 2px  2px 0 #FFFFFF;
        }}
        /* H2: 부제목 */
        h2 {{
            font-size: 24px !important;
            color: black !important;
            text-shadow:
                -1px -1px 0 #FFFFFF,  
                 1px -1px 0 #FFFFFF,
                -1px  1px 0 #FFFFFF,
                 1px  1px 0 #FFFFFF;
        }}
        /* 🔥 H3: 사이드바 부제목 ('예시 질의')에도 윤곽선 적용 (1px 윤곽선) */
        h3 {{
            font-size: 19px !important;
            color: black !important;
            text-shadow:
                -1px -1px 0 #FFFFFF,  
                 1px -1px 0 #FFFFFF,
                -1px  1px 0 #FFFFFF,
                 1px  1px 0 #FFFFFF;
        }}
        
        /* 1) 전체 페이지 배경 유지 */
        html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
            background-image: url("data:image/jpg;base64,{bg}") !important;
            background-repeat: repeat !important;
            background-size: auto !important;
        }}

        .block-container {{
            background-color: transparent !important;
        }}

        /* 2) 사이드바 */
        section[data-testid="stSidebar"] {{
            background-color: rgba(255, 255, 255, 0.5) !important;
            backdrop-filter: blur(10px);
            box-shadow: 0px 0px 10px rgba(0,0,0,0.12);
            border-right: 2px solid rgba(255,255,255,0.4);
        }}

        section[data-testid="stSidebar"] .block-container {{
            background-color: transparent !important;
            padding: 20px 15px !important;
        }}

        /* 3) 채팅 말풍선 */
        [data-testid="stChatMessage"] {{
            background-color: transparent !important;
        }}

        [data-testid="stChatMessage"] > div {{
            background-color: rgba(255, 255, 255, 0.35) !important;
            backdrop-filter: blur(8px);
            border-radius: 14px !important;
            padding: 14px 18px !important;
            margin-bottom: 12px !important;
            box-shadow: 0 2px 6px rgba(0,0,0,0.10);
        }}

        /* ===============================
           4) 하단 입력바 (스크롤, 정렬, 윤곽선 완벽 일치)
           ================================*/
        [data-testid="stBottomBlockContainer"] {{
            background-image: url("data:image/jpg;base64,{bottom}");
            background-size: cover;
            background-repeat: no-repeat;
        }}

        /* 가장 바깥쪽 컨테이너는 투명 유지 */
        [data-testid="stChatInput"],
        [data-testid="stChatInput"] > div {{
            background: transparent !important;
            box-shadow: none !important;
        }}

        /* -------------------------------------------
           4-1. 입력란 컨테이너 스타일링 (흰색 배경 및 둥근 모서리)
        ------------------------------------------- */
        /* Streamlit Input 컴포넌트가 들어있는 가장 바깥쪽의 Flex 컨테이너 */
        [data-testid="stChatInput"] > div > div:nth-child(2) {{
            /* 내부 요소(텍스트 영역 및 버튼)를 플렉스로 중앙 정렬 */
            display: flex !important;
            align-items: center !important;
            
            background-color: white !important;
            border-radius: 14px !important;
            border: 1px solid #d9d9d9 !important; /* 기본 회색 윤곽선 */
            padding: 4px 8px 4px 8px !important; /* 내부 패딩 */
            min-height: 40px;
            box-shadow: none !important; /* 기본 그림자 제거 */
        }}

        /* -------------------------------------------
           4-2. 입력란 좌측 아이콘 제거
        ------------------------------------------- */
        /* stChatInput의 첫 번째 자식 div는 말풍선 아이콘을 포함하는 컨테이너입니다. */
        [data-testid="stChatInput"] > div > div:first-child {{
            display: none !important;
        }}

        /* -------------------------------------------
           4-3. 실제 텍스트 입력 영역 (스크롤 아이콘 제거 및 두께 정렬)
        ------------------------------------------- */
        [data-baseweb="textarea"],
        [data-baseweb="textarea"] textarea {{
            background: white !important;
            box-shadow: none !important;
            color: black !important;
            font-family: 'NeoDGM', 'Malgun Gothic', sans-serif !important;
            
            /* 높이를 고정하고 스크롤바가 생기지 않도록 overflow 제어 */
            min-height: 28px !important;
            height: 28px !important;
            max-height: 28px !important;
            overflow-y: hidden !important; /* 스크롤 아이콘 제거 */
            
            padding-top: 5px !important;
            padding-bottom: 5px !important;
            padding-left: 0px !important;
            padding-right: 0px !important;
        }}
        
        /* -------------------------------------------
           4-4. 보내기 버튼 영역 (뒤의 겹쳐진 흰색 무언가 제거 및 정렬)
        ------------------------------------------- */
        /* 버튼 영역의 불필요한 배경/그림자/마진 제거 */
        [data-testid="stChatInput"] [data-testid="baseview-root"] > div > div:nth-child(2) > div:last-child {{
             background: transparent !important;
             box-shadow: none !important;
             margin-top: 0px !important;
             padding-bottom: 0px !important;
             margin-left: 8px !important; /* 텍스트 입력 필드와 간격 */
        }}
        
        /* -------------------------------------------
           4-5. 포커스 시 빨간색 윤곽선 (정확히 일치)
        ------------------------------------------- */
        /* 텍스트 입력란에 포커스가 갔을 때, 전체 입력란 컨테이너에 빨간색 윤곽선 적용 */
        [data-testid="stChatInput"] > div > div:nth-child(2):has([data-baseweb="textarea"]:focus) {{
            border-color: #f63366 !important; /* 빨간색 */
            border-width: 1px !important;
            border-style: solid !important;
            border-radius: 14px !important;
            /* 포커스 그림자도 빨간색으로 오버라이드 */
            box-shadow: 0 0 0 0.1rem rgba(246, 51, 102, 0.25) !important;
        }}

        /* ===============================
           5) 최종 리포트 박스 스타일
           ================================*/
        .report-container {{
            background-color: rgba(230, 245, 235, 0.95); /* 아주 연한 초록색 */
            border-radius: 18px;
            padding: 18px 22px;
            margin-top: 12px;
            margin-bottom: 28px;
            border: 1px solid rgba(0, 0, 0, 0.04);
            box-shadow: 0 4px 10px rgba(0,0,0,0.06);
        }}

        .report-container h2 {{
            margin-top: 4px;
            margin-bottom: 8px;
            font-size: 20px !important;
        }}

        .report-container h3 {{
            margin-top: 14px;
            margin-bottom: 6px;
            font-size: 17px !important;
        }}

        .report-container ul {{
            margin-left: 18px;
            margin-bottom: 8px;
        }}

        .report-container li {{
            margin-bottom: 4px;
        }}

        /* 강조 텍스트 스타일 */
        .report-container strong {{
            font-weight: 700;
            color: #146c43; /* 약간 짙은 초록색 */
        }}


        
        
        </style>
        """,
        unsafe_allow_html=True,
    )
def normalize_report_markdown(md: str) -> str:
    """
    LLM이 종종 '##1. 요약'처럼 # 뒤 공백 없이 쓰는 걸
    '## 1. 요약' 형태로 고쳐주는 함수
    """
    fixed_lines = []
    for line in md.splitlines():
        # 라인 맨 앞에서 ##1. 처럼 붙어 있는 패턴 찾기
        m = re.match(r'^(#+)(\d+\.)\s*(.*)$', line.strip())
        if m:
            hashes, numdot, rest = m.groups()
            # "## 1. 요약..." 형태로 다시 만들어줌
            line = f"{hashes} {numdot} {rest}".rstrip()
        fixed_lines.append(line)
    return "\n".join(fixed_lines)



# 실제로 배경 적용 (경로 확인 후 유지)
set_background("data/background.jpg", "data/background.jpg")


# ------------------------------------------------
# 2. 유틸리티 함수 (중복 제거 및 통합)
# ------------------------------------------------
def pick_chart_columns(df: pd.DataFrame):
    """범주형(문자) 1개 + 숫자 1개 컬럼 자동 선택"""
    if df is None or df.empty:
        return None, None

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    if not numeric_cols or not cat_cols:
        return None, None

    # x축: 첫 번째 범주형 컬럼, y축: 첫 번째 숫자 컬럼
    return cat_cols[0], numeric_cols[0]

def get_user_history(max_turns: int = 3):
    """세션에서 최근 사용자 질문 max_turns개만 리스트로 반환"""
    user_messages = [
        m["content"]
        for m in st.session_state.messages
        if m["role"] == "user"
    ]
    return user_messages[-max_turns:]


def execute_query_and_format_response(question: str) -> str:
    """
    자연어 질문을 받아 SQL로 변환, 실행 및 결과를 Markdown 형식으로 반환
    (✅ 누적 저장 로직 포함)
    """
    question = question.strip()
    if not question:
        return "질문을 입력해 주세요! 🙂"

    # 1. 자연어 → SQL  (이전 질문들도 함께 전달)
    history_questions = get_user_history(max_turns=3)
    data = nl_to_sql(question, chat_history=history_questions)
    sql = data.get("sql")
    explanation = data.get("explanation_ko", "설명을 생성하지 못했습니다.")

    if not sql:
        return (
            "⚠️ SQL을 생성하지 못했어요.\n\n"
            f"**설명:** {explanation}"
        )

    # 2. SQL 실행
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query(sql, conn)
    except Exception as e:
        return (
            "❌ SQL 실행 중 오류가 발생했어요.\n\n"
            f"**오류 메시지:** `{e}`\n\n"
            "아래 SQL을 참고해서 다시 질문을 바꿔보면 좋아요.\n\n"
            f"```sql\n{sql}\n```"
        )

    # 3. 분석 결과 누적 (최종 리포트용)
    st.session_state.analysis_results.append({
        "question": question,
        "df": df.copy()
    })

    # 4. 결과 테이블
    if df.empty:
        result_table = "조회된 결과가 없습니다.\n"
    else:
        table_md = df.head(10).to_markdown(index=False, tablefmt="pipe")
        result_table = (
            "### 🧪 오박사의 연구 기록\n"
            f"{table_md}\n\n"
        )

    # 5. 시각화 자동 생성
    chart_html = ""
    wants_chart = any(
        kw in question
        for kw in ["그래프", "막대그래프", "시각화", "그래프로", "그려줘"]
    )

    if wants_chart and not df.empty:
        x_col, y_col = pick_chart_columns(df)
        if x_col and y_col:
            title = f"{x_col}별 {y_col} 비교"
            img_tag = create_chart_base64(
                df.head(10),
                x_col=x_col,
                y_col=y_col,
                title=title,
            )
            if img_tag:
                chart_html = "### 📈 시각화 결과\n" + img_tag + "\n\n"

        # ✅ 6. 생성된 SQL 출력 섹션 (여기가 핵심!)
    sql_section = (
        "### 🔍 생성된 SQL (자동 타입 변환 적용)\n"
        f"```sql\n{sql}\n```\n\n"
    )

    # ✅ 7. 포켓몬 이미지 섹션 (dexnum → 이미지 매핑)
    image_html = ""
    # df가 비어있지 않고, dexnum 컬럼이 있으면 시도
    if not df.empty and "dexnum" in df.columns:
        # 중복 제거한 도감번호들
        unique_dex = df["dexnum"].dropna().unique()

        # 👉 결과에 포켓몬이 한 마리만 있을 때만 이미지 표시
        # (여러 마리일 때는 나중에 그리드로 예쁘게 확장할 수 있음)
        if len(unique_dex) == 1:
            dex = int(unique_dex[0])
            img_tag = get_pokemon_image_html_from_dexnum(dex)
            if img_tag:
                image_html = "### 📷 포켓몬 이미지\n" + img_tag + "\n\n"

    # ✅ 8. 섹션 최종 조합
    full_text = (
        f"호오~ 자네의 질문을 들으니 꽤 흥미롭구먼!\n\n"
        f"### 🧓 오박사의 답변\n"
        f"{explanation}\n\n"
        + sql_section
        + chart_html
        + image_html      # ← 여기서 이미지 붙이기!
        + result_table
    )

    return full_text




# ------------------------------------------------
# 3. Streamlit UI 렌더링
# ------------------------------------------------
logo_base64 = get_image_base64("data/research.png")

st.markdown(
    f"""
    <style>
    .title-container {{
        display: flex;
        align-items: center;
        gap: 14px;
        margin-top: 8px;
        margin-bottom: 8px;
    }}
    .title-container img {{
        width: 120px;
    }}
    </style>

    <div class="title-container">
        <img src="data:image/png;base64,{logo_base64}">
        <h1>오박사의 포켓몬 연구소</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("---")

# ------------------------------------------------
# 4. 사이드바 (리포트 버튼 추가)
# ------------------------------------------------
with st.sidebar:
    st.header("오박사의 포켓몬 연구소 소개")

    st.markdown("""
    오박사의 포켓몬 연구소 챗봇은 LLM을 통해 사용자의 한국어 질문을 SQL로 변환하여 포켓몬 데이터를 분석합니다. 
    """)

    st.markdown("""
    <hr style="border:1px solid rgba(255,255,255,0.4)">
    """, unsafe_allow_html=True)

    # 🔹 예시 질의 버튼을 사이드바로 이동
    st.subheader("예시 질의")

    sidebar_example_questions = [
        "고승주가 가진 포켓몬들의 평균 total 능력치를 보여줘",
        "전기 타입 포켓몬 중 speed가 가장 빠른 5마리를 알려줘",
        "불꽃 타입 포켓몬의 평균 공격력은?",
        "물 타입 포켓몬 중 방어력이 가장 높은 포켓몬은?"
    ]

    for q in sidebar_example_questions:
        if st.button(q, key=f"sidebar_ex_{q}"):
            st.session_state["pending_question"] = q
            st.rerun()

    st.markdown("""
    <hr style="border:1px solid rgba(255,255,255,0.4)">
    """, unsafe_allow_html=True)
    
       # ✅ 최종 분석 리포트 생성 버튼
    if st.button("📘 최종 분석 리포트 생성"):
        with st.spinner("리포트를 작성 중이에요..."):
            final_report_html = generate_final_report(
                st.session_state.analysis_results
            )
            st.session_state.final_report_html = final_report_html
            st.rerun()

    # 👇 대화 초기화 시에도 final_report_html 삭제
    if st.button("대화 초기화"):
        st.session_state.messages = []
        st.session_state.analysis_results = []
        if "final_report_html" in st.session_state:
            del st.session_state.final_report_html
        st.session_state.first_greeting_done = False
        st.rerun()

    
    st.markdown("---")

# ------------------------------------------------
# 5. 채팅 로그 출력
# ------------------------------------------------
for message in st.session_state.messages:
    role = message["role"]
    avatar = "data/professor.png" if role == "assistant" else "data/user.png"

    with st.chat_message(role, avatar=avatar):
        st.markdown(message["content"], unsafe_allow_html=True)




# ------------------------------------------------
# 7. 입력 처리 (pending_question 우선 처리)
# ------------------------------------------------
# 🚨 최종 해결책: st.chat_input()을 가장 먼저 호출하여 하단 입력창을 항상 렌더링합니다.

# 1. st.chat_input()을 호출하여 하단 입력창을 화면에 고정합니다.
#    - 예시 버튼 클릭(rerun) 시에도 이 코드는 실행되어 입력창을 유지합니다.
user_input_prompt = st.chat_input("분석할 질문을 입력하세요...")

prompt = None

# 2. 예시 버튼 클릭(pending_question)이 있으면 그 값을 우선 사용
if "pending_question" in st.session_state:
    prompt = st.session_state.pop("pending_question")

# 3. pending_question이 없고, 사용자가 직접 입력한 값이 있으면 그 값을 사용
elif user_input_prompt:
    prompt = user_input_prompt

if prompt:
    # ✅ 1. 사용자 메시지 저장
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="data/user.png"):
        st.markdown(prompt)

    # ✅ 2. 지금까지 사용자 질문 횟수 세기 (여기서 정의!)
    user_question_count = len([
        m for m in st.session_state.messages if m["role"] == "user"
    ])

    # ✅ 3. 10번째 질문 이스터에그 (랜덤 멘트)
    easter_egg = ""
    if user_question_count == 5:
        egg_messages = [
            """
---

🎓 **오박사의 조심스러운 권유**

흠… 자네, 지금까지 질문한 수준을 보니 그냥 트레이너가 아니라  
**연구자의 자질이 보이는군.**

어떤가… 이 연구가 끝나거든  
**우리 연구소 대학원 과정도 한 번… 진지하게 생각해보지 않겠나?** ☕  
(물론 졸업 논문은 포켓몬으로 쓰게 될 걸세…)
""",

            """
---

🧪 **오박사의 진지한 스카우트**

호오… 질문의 깊이가 점점 심상치 않구먼.  
이건 그냥 흥미 수준이 아니야.

자네, 혹시…  
**연구실에 들어올 생각은 없나?**  
내가 지도교수는 맡아주지. 흐음… 😏
""",

            """
---

📚 **오박사의 은근한 압박(?)**

자네 말일세…  
이 정도 분석력이면 이제 슬슬  
**레포트가 아니라 논문을 써야 할 때가 온 것 같군.**

어떤가,  
**“포켓몬 데이터 기반 메타 분석”으로 대학원 한 번 가보겠나?** ☕
""",

            """
---

🔥 **오박사의 확신**

이제 확신하겠네.  
자네는 트레이너가 아니라 **연구원 체질이야.**

앞으로의 질문들은…  
**석사 과정으로 인정해주도록 하지.** 😎
"""
        ]

        easter_egg = random.choice(egg_messages)

    # ✅ 4. assistant 응답 출력
    with st.chat_message("assistant", avatar="data/professor.png"):
        with st.spinner("오박사가 연구중이에요...🔍"):

            bot_response = execute_query_and_format_response(prompt) + easter_egg

            # ✅ 첫 질문일 때만 자기소개
            if not st.session_state.first_greeting_done:
                intro = "내 이름은 오박사. 포켓몬 연구소의 연구 책임자라네!\n\n"
                bot_response = intro + bot_response
                st.session_state.first_greeting_done = True

            st.markdown(bot_response, unsafe_allow_html=True)

    # ✅ 5. 대화 기록 저장
    st.session_state.messages.append({"role": "assistant", "content": bot_response})



# ------------------------------------------------
# 8. 최종 리포트 출력
# ------------------------------------------------
if "final_report_html" in st.session_state:
    st.markdown("---")
    st.markdown("## 📘 오박사의 최종 연구 리포트")

    st.markdown(
        f"""
        <div class="report-container">
            {st.session_state.final_report_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


