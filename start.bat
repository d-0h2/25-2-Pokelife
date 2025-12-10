@echo off
chcp 65001 > nul
title MyPocket 스트림릿 런처

echo ======================================
echo 🔧 1단계: 필요한 라이브러리 설치
echo ======================================
python -m pip install -r requirements.txt

echo.
echo ======================================
echo ⚙️ 2단계: 포켓몬 타입 상성 테이블 초기화
echo ======================================
python -c "from utils import init_type_effectiveness; init_type_effectiveness()"

echo.
echo ======================================
echo 🚀 3단계: Streamlit 앱 실행
echo ======================================
python -m streamlit run app.py

pause
