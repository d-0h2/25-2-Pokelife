import sqlite3
import pandas as pd
import json
import textwrap
import os
import io
import base64
import matplotlib.pyplot as plt
import matplotlib as mpl
from pathlib import Path
import base64
from matplotlib import font_manager as fm
from openai import OpenAI
from typing import Dict, Any, List, Optional, Tuple # Tuple 타입 추가

# app.py / utils.py 가 있는 폴더 기준
BASE_DIR = Path(__file__).resolve().parent
POKEMON_IMG_DIR = BASE_DIR / "data" / "pokemon_jpg"


# ------------------------------------------------
# 0. 경로 설정
# ------------------------------------------------
# __file__이 항상 존재한다고 가정하고 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "MyPocket.sqlite")

# ------------------------------------------------
# 1. Matplotlib 한글 폰트 설정
# ------------------------------------------------
FONT_PATH = os.path.join(BASE_DIR, "font", "neodgm.ttf")

if os.path.exists(FONT_PATH):
    try:
        fm.fontManager.addfont(FONT_PATH)
        # ✅ 폰트 파일에서 실제 family name을 읽어오기
        font_prop = fm.FontProperties(fname=FONT_PATH)
        real_name = font_prop.get_name()
        mpl.rcParams["font.family"] = real_name
        print(f"✅ Matplotlib 폰트 적용 완료: {real_name}")
    except Exception as e:
        print(f"❌ 폰트 등록 실패: {e}")
else:
    print(f"⚠️ 폰트 파일 없음: {FONT_PATH}")

mpl.rcParams["axes.unicode_minus"] = False


# ------------------------------------------------
# 2. 스키마 설명
# ------------------------------------------------
schema_description = textwrap.dedent("""
[데이터베이스 스키마]

1) pokemon
- dexnum (도감번호)
- name (포켓몬 이름)
- generation (세대)
- type1 (첫 번째 타입)
- type2 (두 번째 타입)
- species (종 분류)
- height (키)
- weight (몸무게)

- ability1 (특성 1)
- ability2 (특성 2)
- hidden_ability (숨겨진 특성)

- hp
- attack
- defense
- sp_atk
- sp_def
- speed
- total

- ev_yield (노력치)
- catch_rate (포획률)
- base_friendship (기초 친밀도)
- base_exp (기초 경험치)
- growth_rate (성장 속도)

- egg_group1 (알 그룹 1)
- egg_group2 (알 그룹 2)
- percent_male (수컷 비율)
- percent_female (암컷 비율)
- egg_cycles (알 부화 주기)
- special_group (특수 분류)

2) UserData
- User_id
- Username
- Favorite_type

3) UserPokemon
- user_pokemon_id
- user_id
- pokemon_id
- pokemon_name
- slot_no

4) type_effectiveness (자동 생성)
- attacking_type, defending_type, multiplier (공격 타입이 방어 타입에게 주는 피해 배율)
""") # type_effectiveness 스키마 추가

# ------------------------------------------------
# 3. 타입 한/영 변환
# ------------------------------------------------
TYPE_MAP_KO_TO_EN = {
    "전기": "Electric", "불꽃": "Fire", "물": "Water", "풀": "Grass",
    "얼음": "Ice", "격투": "Fighting", "에스퍼": "Psychic", "바위": "Rock",
    "땅": "Ground", "비행": "Flying", "노말": "Normal", "고스트": "Ghost",
    "악": "Dark", "강철": "Steel", "드래곤": "Dragon", "페어리": "Fairy",
    "벌레": "Bug", "독": "Poison"
}

def normalize_type_literals(sql: str) -> str:
    """SQL 쿼리 내의 한글 타입 리터럴을 영문으로 변환"""
    if not sql:
        return sql
    # 타입 리터럴('한글')을 찾아 영문('English')으로 대체
    for ko, en in TYPE_MAP_KO_TO_EN.items():
        # 작은따옴표로 감싸진 문자열만 대체하도록 정밀하게 처리 (예: '전기' -> 'Electric')
        sql = sql.replace(f"'{ko}'", f"'{en}'")
    return sql

# ------------------------------------------------
# 4. LLM → SQL 변환 (OpenAI 클라이언트 및 API 키 관리 통합)
# ------------------------------------------------
def get_openai_client() -> Optional[OpenAI]:
    """OpenAI 클라이언트를 생성하고 API 키 부재 시 None 반환"""
    try:
        import streamlit as st
        api_key = st.secrets.get("openai_key")
    except Exception:
        api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        print("❌ OPENAI API 키가 설정되지 않았습니다.")
        return None
    
    return OpenAI(api_key=api_key)


def nl_to_sql(question: str, chat_history: Optional[List[str]] = None) -> Dict[str, Any]:
    """자연어를 SQL 쿼리로 변환하고 설명 추가"""
    client = get_openai_client()
    if not client:
        return {"sql": None, "explanation_ko": "❌ OPENAI API 키가 설정되지 않아 분석을 할 수 없네."}

    history_block = ""
    if chat_history:
        history_block = "\n".join([f"- {q}" for q in chat_history])

    system_prompt = f"""
당신은 포켓몬 연구소의 데이터 분석을 담당하는 '포켓몬 박사 오박사'입니다.
말투는 항상 오박사처럼 **친절하고 유쾌하며 약간 할아버지 느낌**으로 유지합니다.
예) "~하네", "~이지", "~일세", "호오?", "흥미로운 결과라네!", "자네도 한번 확인해보겠나?"

역할:
- 사용자의 질문을 기반으로 SQLite 데이터베이스에서 분석을 수행한다.
- 아래 포켓몬/사용자 데이터 스키마 정보를 이용하여 SQL SELECT 문을 작성한다.
- 그리고 생성된 SQL이 무엇을 하는지 **오박사 말투 한국어 설명(explanation_ko)**로 작성한다.

{schema_description}

[SQL 및 출력 규칙]
1. 항상 하나의 **SELECT** 문만 작성합니다. (INSERT/UPDATE/DELETE 등 금지)
2. JSON 함수(json_object, json_group_array 등) 절대 사용 금지.
3. 결과는 사람이 읽기 쉬운 표 형태가 되도록 SELECT 컬럼을 직접 나열합니다.
4. pokemon.type1/type2 비교 시 반드시 영어 타입명('Electric', 'Fire') 사용.
5.  **pokemon.name 컬럼에는 한국어 이름이 들어 있습니다.**
   - 예: '피카츄', '라이츄', '파이리', '이상해씨' 등
   - 사용자가 "피카츄", "라이츄"처럼 한국어로 포켓몬 이름을 말하면
     WHERE 조건에서도 반드시 그 **한국어 이름 그대로** 사용해야 합니다.
   - 'Pikachu', 'Raichu'처럼 영어 이름으로 바꾸지 마세요.
6. 포켓몬을 조회하는 SELECT 문에서는 가능하면 항상 dexnum도 함께 SELECT에 포함하세요. 
7. **JSON 문자열만 출력**하며, 반드시 아래 형식만 반환합니다.

[JSON Output Format]
{{
  "sql": "SELECT ...",
  "explanation_ko": "오박사 말투로 SQL이 어떤 분석인지 설명"
}}

⚠ 형식 외 텍스트 절대 출력하지 마세요.
⚠ explanation_ko는 반드시 오박사 말투로 작성하세요.

[포켓몬 타입 상성 테이블 설명]

type_effectiveness 테이블은 포켓몬 타입 간의 공격 상성을 나타냅니다.

- attacking_type : 공격하는 기술의 타입 (예: 'Fire', 'Water', 'Electric' 등, 영어)
- defending_type : 공격을 받는 포켓몬의 타입 (예: 'Grass', 'Poison', 'Flying' 등, 영어)
- multiplier     : 데미지 배율
    - 2.0  : 매우 효과적 (2배)
    - 1.0  : 보통
    - 0.5  : 효과가 별로 없음 (반감)
    - 0.0  : 효과 없음 (무효)

pokemon 테이블의 type1, type2는 각각 포켓몬의 첫 번째 타입과 두 번째 타입입니다.
type2가 NULL이면 단일 타입 포켓몬입니다.

[이중속성 계산 규칙 — 아주 중요]
- 포켓몬이 이중속성(type1, type2)을 가질 경우:
  - attacking_type → type1 에 대한 multiplier
  - attacking_type → type2 에 대한 multiplier
  이 두 값을 곱해서 최종 데미지 배율을 계산합니다.
- type2가 NULL이거나 상성 정보가 없으면 multiplier는 1.0으로 간주합니다.
- 최종 배율 공식:
  COALESCE(type1_multiplier, 1.0) * COALESCE(type2_multiplier, 1.0)

[SQL 작성 규칙 — 상성 관련 질문일 때]
- 반드시 type_effectiveness 테이블을 JOIN 해서 multiplier를 계산해야 합니다.
- 이중속성일 경우:
  - type1용 JOIN 1개
  - type2용 JOIN 1개
  총 2개의 LEFT JOIN을 사용하세요.
- 최종 데미지 배율은 total_multiplier 같은 별칭(alias)로 계산해서 SELECT에 포함하세요.

[포켓몬 vs 포켓몬 직접 전투 질의 처리 규칙]

사용자가 "피카츄가 누오를 공격하면?", "A가 B를 공격하면?" 같은 질문을 할 경우:

1. pokemon 테이블에서
   - atk: 공격자 포켓몬 (예: name = '피카츄')
   - def: 방어자 포켓몬 (예: name = '누오')
   를 각각 조회합니다.

2. 공격 타입은 atk.type1을 기본으로 사용합니다.
   (별도로 기술 타입이 주어지지 않았다면, 공격자는 자신의 첫 번째 타입으로 공격한다고 가정합니다.)

3. type_effectiveness 테이블을 사용하여
   - atk.type1 → def.type1 에 대한 multiplier (e1)
   - atk.type1 → def.type2 에 대한 multiplier (e2)
   를 LEFT JOIN으로 얻고,
   최종 배율은 COALESCE(e1.multiplier, 1.0) * COALESCE(e2.multiplier, 1.0) 으로 계산합니다.

4. SELECT 절에는
   - 공격자 이름, 타입
   - 방어자 이름, 타입1, 타입2
   - 최종 배율(total_multiplier)
   등을 포함하여 사람이 이해하기 쉬운 결과를 반환하도록 합니다.

"""

    user_prompt = f"{history_block}\n[현재 질문]\n{question}"

    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"} # JSON 형식 강제
        )

        raw = res.choices[0].message.content
        data = json.loads(raw)

        if data.get("sql"):
            # LLM이 한글 타입을 사용했을 경우를 대비하여 변환 로직 적용
            data["sql"] = normalize_type_literals(data["sql"])

        return data

    except Exception as e:
        return {"sql": None, "explanation_ko": f"LLM 오류: {e}"}

# ------------------------------------------------
# 5. 자동 차트 생성 (스탯 컬럼 우선 선택 버전)
# ------------------------------------------------
def create_chart_base64(
    df: pd.DataFrame,
    x_col: str | None,
    y_col: str | None,
    title: str
) -> str:
    """Pandas DataFrame을 기반으로 차트를 생성하고 Base64 이미지 태그 반환"""

    if df is None or df.empty:
        return ""

    # 🔹 1) 컬럼 타입별로 분리
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    if not numeric_cols or not cat_cols:
        return ""

    # 🔹 2) x축 보정: 없거나 이상하면 첫 번째 범주형 컬럼으로
    if (not x_col) or (x_col not in df.columns):
        x_col = cat_cols[0]

    # 🔹 3) y축 보정: 스탯 컬럼(attack, hp, …)을 최우선으로 선택
    priority_numeric = ["attack", "hp", "defense", "sp_atk", "sp_def", "speed", "total"]

    # y_col이 없거나, 숫자 컬럼이 아니거나,
    #   OR 스탯 컬럼이 있는데 y_col이 스탯 컬럼이 아닐 때 → 스탯으로 덮어쓰기
    has_priority = any(col in numeric_cols for col in priority_numeric)
    if (
        (not y_col)
        or (y_col not in numeric_cols)
        or (has_priority and y_col not in priority_numeric)
    ):
        # 우선순위 리스트에서 처음으로 존재하는 컬럼 선택
        for col in priority_numeric:
            if col in numeric_cols:
                y_col = col
                break
        else:
            # 우선순위 스탯이 하나도 없으면, 그냥 첫 번째 숫자 컬럼 사용
            y_col = numeric_cols[0]

    # 그래도 y축이 이상하면 포기
    if y_col is None or not pd.api.types.is_numeric_dtype(df[y_col]):
        return ""

    # 🔹 4) 폰트 설정 (기존 유지)
    try:
        from matplotlib import rcParams
        rcParams["font.family"] = mpl.rcParams.get("font.family")
    except Exception:
        pass

    # 🔹 5) 실제 그래프 그리기
    plt.figure(figsize=(10, 5))

    if len(df) > 50:
        plt.plot(df[x_col], df[y_col], marker='o')
        plt.xticks(rotation=45, ha='right', fontsize=8)
    else:
        plt.bar(df[x_col], df[y_col])
        plt.xticks(rotation=45, ha='right')

    plt.title(title, fontsize=14, pad=20)
    plt.xlabel(x_col, fontsize=12)
    plt.ylabel(y_col, fontsize=12)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()

    png_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"<img src='data:image/png;base64,{png_base64}'>"

def get_pokemon_image_html_from_dexnum(dexnum: int, width: int = 200) -> str | None:
    """
    도감번호(dexnum)에 해당하는 포켓몬 이미지를 찾아
    <img> 태그(베이스64 인코딩)를 리턴한다.
    이미지가 없으면 None 리턴.
    """
    # 확장자 여러 개 시도 (jpg / jpeg / png)
    for ext in [".jpg", ".jpeg", ".png"]:
        img_path = POKEMON_IMG_DIR / f"{dexnum}{ext}"   # 예: data/pokemon_jpg/25.jpg
        if img_path.exists():
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")

            mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
            html = f"<img src='data:{mime};base64,{b64}' alt='포켓몬 이미지' width='{width}'>"
            return html

    # 파일이 하나도 없으면
    return None


# ------------------------------------------------
# 6. ✅ 타입 상성 데이터 (전체 데이터로 확장)
# ------------------------------------------------
# 포켓몬 공식 게임의 1세대~5세대 기준 기본 상성 데이터를 반영합니다.
# 이 데이터는 type_effectiveness 테이블을 초기화하는 데 사용됩니다.
TYPES = [
    "Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison",
    "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark",
    "Steel", "Fairy"
]

# (공격 타입: [효과가 굉장한 방어 타입들]) -> 데미지 2배
SUPER_EFFECTIVE = {
    "Normal": [],
    "Fire": ["Grass", "Ice", "Bug", "Steel"],
    "Water": ["Fire", "Ground", "Rock"],
    "Electric": ["Water", "Flying"],
    "Grass": ["Water", "Ground", "Rock"],
    "Ice": ["Grass", "Ground", "Flying", "Dragon"],
    "Fighting": ["Normal", "Ice", "Rock", "Dark", "Steel"],
    "Poison": ["Grass", "Fairy"],
    "Ground": ["Fire", "Electric", "Poison", "Rock", "Steel"],
    "Flying": ["Grass", "Fighting", "Bug"],
    "Psychic": ["Fighting", "Poison"],
    "Bug": ["Grass", "Psychic", "Dark"],
    "Rock": ["Fire", "Ice", "Flying", "Bug"],
    "Ghost": ["Psychic", "Ghost"],
    "Dragon": ["Dragon"],
    "Dark": ["Psychic", "Ghost"],
    "Steel": ["Ice", "Rock", "Fairy"],
    "Fairy": ["Fighting", "Dragon", "Dark"]
}

# (공격 타입: [효과가 별로인 방어 타입들]) -> 데미지 0.5배
NOT_VERY_EFFECTIVE = {
    "Normal": ["Rock", "Steel"],
    "Fire": ["Fire", "Water", "Rock", "Dragon"],
    "Water": ["Water", "Grass", "Dragon"],
    "Electric": ["Electric", "Grass", "Dragon"],
    "Grass": ["Fire", "Grass", "Poison", "Flying", "Bug", "Dragon", "Steel"],
    "Ice": ["Fire", "Water", "Ice", "Steel"],
    "Fighting": ["Poison", "Flying", "Psychic", "Bug", "Fairy"],
    "Poison": ["Poison", "Ground", "Rock", "Ghost"],
    "Ground": ["Grass", "Bug"],
    "Flying": ["Electric", "Rock", "Steel"],
    "Psychic": ["Steel", "Psychic"],
    "Bug": ["Fire", "Fighting", "Poison", "Flying", "Ghost", "Steel", "Fairy"],
    "Rock": ["Fighting", "Ground", "Steel"],
    "Ghost": ["Dark", "Steel"],
    "Dragon": ["Steel"],
    "Dark": ["Fighting", "Dark", "Fairy"],
    "Steel": ["Fire", "Water", "Electric", "Steel"],
    "Fairy": ["Fire", "Poison", "Steel"]
}

# (공격 타입: [효과가 없는 방어 타입들]) -> 데미지 0.0배
NO_EFFECT = {
    "Normal": ["Ghost"],
    "Fighting": ["Ghost"],
    "Poison": ["Steel"],
    "Ground": ["Flying"],
    "Ghost": ["Normal"],
    "Psychic": ["Dark"],
    "Dragon": ["Fairy"],
    "Steel": [],
    "Fire": [], "Water": [], "Electric": [], "Grass": [], "Ice": [],
    "Flying": [], "Bug": [], "Rock": [], "Dark": [], "Fairy": []
}


def init_type_effectiveness():
    """type_effectiveness 테이블을 초기화하고 상성 데이터를 삽입"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 테이블 생성 쿼리 (기존 로직 유지)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS type_effectiveness (
            attacking_type TEXT,
            defending_type TEXT,
            multiplier REAL,
            PRIMARY KEY (attacking_type, defending_type)
        )
    """)

    cur.execute("DELETE FROM type_effectiveness") # 기존 데이터 삭제

    rows: List[Tuple[str, str, float]] = []

    for atk in TYPES:
        for df in TYPES:
            mult = 1.0
            
            # 상성 계산 로직 (기존 로직 확장 및 정리)
            if df in SUPER_EFFECTIVE.get(atk, []):
                mult = 2.0
            elif df in NOT_VERY_EFFECTIVE.get(atk, []):
                mult = 0.5
            elif df in NO_EFFECT.get(atk, []):
                mult = 0.0
            # 1.0은 기본값으로 유지

            rows.append((atk, df, mult))

    cur.executemany(
        "INSERT INTO type_effectiveness VALUES (?, ?, ?)", rows
    )

    conn.commit()
    conn.close()
    print("✅ type_effectiveness 테이블 자동 생성 및 전체 상성 데이터 삽입 완료")

# ------------------------------------------------
# 7. ✅ 최종 리포트 생성 (세대/타입 필터 추가 버전)
# ------------------------------------------------
def generate_final_report(all_results: list, gen_filter=None, type_filter=None) -> str:
    """누적된 분석 결과들을 기반으로 최종 리포트를 HTML로 생성"""
    if not all_results:
        return "아직 분석된 결과가 없어서 최종 리포트를 만들 수 없네."

    client = get_openai_client()
    if not client:
        return "⚠️ OPENAI API 키가 없어 리포트를 생성할 수 없네."

    # 1) 질문 + 데이터프레임 요약을 보기 좋게 정리 (LLM에게 넘길 용도)
    sections = []
    for i, item in enumerate(all_results, 1):
        q = item.get("question", "")
        df = item.get("df")

        section = f"[분석 {i}] 질문: {q}\n"

        if df is not None and not df.empty:
            section += "상위 5개 결과 미리보기:\n"
            section += df.head(5).to_markdown(index=False)
        else:
            section += "조회된 결과가 없었습니다."

        sections.append(section)

    analyses_block = "\n\n---\n\n".join(sections)

    # 2) 🔥 필터 설명 텍스트 만들기
    filter_desc = []
    if gen_filter is not None:
        filter_desc.append(f"- 세대: {gen_filter}세대 중심으로 해석")
    if type_filter:
        filter_desc.append(f"- 타입: {', '.join(type_filter)} 타입 위주로 인사이트 정리")

    filter_block = "\n".join(filter_desc) if filter_desc else "별도의 필터는 적용하지 않는다."

    # 3) 🧓 오박사 말투 + HTML 리포트 프롬프트
    system_prompt = f"""
당신은 포켓몬 연구소의 책임 연구원인 **오박사**입니다.

말투는 항상 오박사처럼 **친절하고 유쾌하며 약간 할아버지 느낌**으로 유지합니다.
예) "~하네", "~이지", "~일세", "호오?", "흥미로운 결과라네!", "자네도 한번 확인해보겠나?"

아래 여러 번의 질의/분석 결과를 토대로,
**오박사가 직접 작성한 느낌의 '최종 연구 리포트'** 를 만들어 주세요.

[분석 필터 조건]
{filter_block}

▶ 리포트에서는 위 필터 조건에 맞는 세대/타입을 중심으로,
  중요 인사이트를 강조해서 정리하세요.
▶ 단, 원본 데이터 전체를 참고하되,
  예시·비교·강조 포인트에서 필터에 맞는 포켓몬/세대/타입을 우선적으로 언급하세요.

⚠ 출력 형식은 반드시 유효한 HTML이어야 합니다.
- <html>, <body> 태그는 쓰지 마세요. (조각만 반환)
- 전체 구조는 아래와 같이 해주세요:

<h2>🧓 오박사의 최종 연구 보고서</h2>
<p>
호오~ 자네가 지금까지 수행한 여러 분석 결과를 한데 모아 살펴보았네. <br>
그럼 이제 내가 오박사가 최종 연구 내용을 정리해서 들려주도록 하지.
</p>

<h2>1. 요약</h2>
<p>이번 분석의 전체적인 흐름과 핵심 결과를 3~5줄 정도로 정리합니다.</p>

<h2>2. 주요 발견</h2>
<ul>
  <li>중요한 인사이트를 한 줄씩 정리합니다.</li>
  <li>중요 수치나 핵심 키워드는 <strong>태그</strong>로 감싸 강조합니다.</li>
  <li>필터(세대/타입)가 있다면, 해당 조건을 중심으로 특징을 설명합니다.</li>
</ul>

<h2>3. 질문별 분석 정리</h2>
<p>
자네가 던졌던 각 질문을 오박사가 다시 되짚어보듯 정리해 주게. <br>
예: "자네가 첫 번째로 던졌던 질문에서는 이런 흥미로운 점이 드러났네."
</p>

<h3>질문 A 제목 또는 요약</h3>
<p>해당 질문에 대한 분석 내용을 오박사 말투로 설명합니다.</p>

<h3>질문 B 제목 또는 요약</h3>
<p>해당 질문에 대한 분석 내용을 오박사 말투로 설명합니다.</p>

(필요한 만큼 질문별 섹션을 추가합니다.)

<h2>4. 결론 및 오박사의 제안</h2>
<ul>
  <li>플레이어/연구자에게 유용한 전략이나 행동 제안을 2~4개 정리합니다.</li>
  <li>가능하면 근거가 된 수치나 패턴을 함께 언급합니다.</li>
  <li>
    마지막에는 오박사다운 따뜻한 마무리 멘트를 추가합니다. <br>
    예: "앞으로도 함께 포켓몬 세계의 비밀을 하나씩 파헤쳐 보세, 자네!"
  </li>
</ul>

요청 사항:
- 전체 문장은 자연스럽고 친근한 한국어로 작성합니다.
- 전체 리포트는 처음부터 끝까지 **오박사 말투**를 유지합니다.
- 너무 장황하지 않게, 또렷하게 정리된 보고서 느낌을 내 주세요.
- 중요한 부분은 <strong>...</strong>로 강조해 주세요.
"""

    user_prompt = f"[질문 및 분석 결과]\n\n{analyses_block}"

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )

        # 👉 이 값은 그대로 HTML로 사용할 예정
        return resp.choices[0].message.content.strip()

    except Exception as e:
        return f"❌ 최종 리포트 생성 실패: {e}"



# ------------------------------------------------
# 8. 최초 실행 시 타입 상성 자동 생성
# ------------------------------------------------
if __name__ == "__main__":
    init_type_effectiveness()
    print("\n--- 환경 정보 ---")
    print("🔍 DB 경로:", DB_PATH)
    print("📂 DB 파일 존재 여부:", os.path.exists(DB_PATH))



def add_pokemon_to_user(user_id: int, pokemon_name: str):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        # 다음 슬롯 번호 계산
        cur.execute(
            "SELECT COALESCE(MAX(slot_no) + 1, 1) FROM UserPokemon WHERE user_id = ?",
            (user_id,)
        )
        next_slot = cur.fetchone()[0]

        # 포켓몬 기본 정보 가져오기
        cur.execute(
            "SELECT dexnum, name FROM pokemon WHERE name = ?",
            (pokemon_name,)
        )
        row = cur.fetchone()
        if not row:
            return False, f"{pokemon_name} 이(가) pokemon 테이블에 없네."

        dexnum, name = row

        # 실제 INSERT
        cur.execute(
            """
            INSERT INTO UserPokemon (user_id, pokemon_id, pokemon_name, slot_no)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, dexnum, name, next_slot)
        )
        conn.commit()
    return True, f"{pokemon_name} 를(을) 새로운 포켓몬으로 등록했네!"

