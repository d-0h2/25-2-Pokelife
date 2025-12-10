import sqlite3
import pandas as pd
import os

# 기본 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "MyPocket.sqlite")

print("✅ DB 만들기 시작:", DB_PATH)
print("📂 DATA_DIR:", DATA_DIR)
print("📄 data 폴더 파일:", os.listdir(DATA_DIR))


def read_csv_auto(path):
    """여러 인코딩을 시도해서 CSV를 안전하게 읽기"""
    encodings = ["utf-8-sig", "cp949", "euc-kr"]
    last_err = None
    for enc in encodings:
        try:
            print(f"👉 {os.path.basename(path)} 를 {enc} 로 읽는 중...")
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError as e:
            print(f"   ⚠ {enc} 실패: {e}")
            last_err = e
    raise last_err


def find_file(keyword):
    """data 폴더에서 keyword 를 포함한 파일을 찾아서 전체 경로 반환"""
    for f in os.listdir(DATA_DIR):
        if keyword.lower() in f.lower():
            return os.path.join(DATA_DIR, f)
    raise FileNotFoundError(f"'{keyword}' 를 포함한 파일을 data 폴더에서 찾지 못했습니다.")


# SQLite 연결
conn = sqlite3.connect(DB_PATH)

# 1) pokemon 테이블
pokemon_csv = find_file("pokemon_data")
df_pokemon = read_csv_auto(pokemon_csv)
df_pokemon.to_sql("pokemon", conn, if_exists="replace", index=False)
print("✅ pokemon 테이블 생성 완료")

# 2) UserData 테이블
userdata_csv = find_file("userdata")
df_user = read_csv_auto(userdata_csv)
df_user.to_sql("UserData", conn, if_exists="replace", index=False)
print("✅ UserData 테이블 생성 완료")

# 3) UserPokemon 테이블
userpokemon_csv = find_file("user_pokemon")
df_user_pokemon = read_csv_auto(userpokemon_csv)
df_user_pokemon.to_sql("UserPokemon", conn, if_exists="replace", index=False)
print("✅ UserPokemon 테이블 생성 완료")

conn.close()
print("🎉 모든 작업 완료! →", DB_PATH)

# build_db.py 파일의 1) pokemon 테이블, 2) user 테이블, 3) user_pokemon 테이블 생성 로직 다음에 추가

# =======================================================
# 4) POKEMON_IMAGES 테이블 생성 (사진 매핑) - 번호 또는 번호.확장자 지원
# =======================================================
IMAGE_FOLDER_NAME = "pokemon_jpg"
# data 폴더 아래의 pokemon_jpg 폴더 경로를 정확하게 지정합니다.
IMAGE_FOLDER_PATH = os.path.join(DATA_DIR, IMAGE_FOLDER_NAME)

image_data_list = []
# 지원할 확장자 목록은 여전히 중요합니다. (파일이 번호만 있는 경우에도 시스템 파일 제외)
SUPPORTED_EXTENSIONS = ('jpg', 'jpeg', 'png', 'webp', 'gif', '') # 💡 확장자가 없는 경우를 위해 '' 추가!

print(f"\n====================================")
print(f"🔎 4) POKEMON_IMAGES 테이블 생성 시작")
print(f"   - 이미지 폴더 경로: {IMAGE_FOLDER_PATH}")
print(f"====================================")

if os.path.exists(IMAGE_FOLDER_PATH):
    file_list = os.listdir(IMAGE_FOLDER_PATH)
    print(f"✅ 폴더 접근 성공. 총 파일 수: {len(file_list)}개")
    
    for filename in file_list:
        parts = filename.split('.')
        
        # 1. 파일 이름이 '.'을 포함하지 않을 수도 있으므로, 파일 이름 자체를 첫 번째 부분으로 간주
        filename_base = parts[0]
        
        # 2. 파일 이름의 첫 부분이 숫자인지 확인
        if filename_base.isdigit():
            
            # 3. 확장자 검사: parts 리스트의 길이가 1이면 확장자가 없음. 2 이상이면 parts[-1]이 확장자.
            # 확장자가 없는 경우 (len(parts) == 1): 확장자 부분은 빈 문자열('')이 되어 SUPPORTED_EXTENSIONS에 포함됨
            # 확장자가 있는 경우 (len(parts) > 1): 확장자 부분(parts[-1])이 SUPPORTED_EXTENSIONS에 포함되어야 함
            file_ext = parts[-1].lower() if len(parts) > 1 else ''
            
            if file_ext in SUPPORTED_EXTENSIONS:
                
                pokemon_id_str = filename_base.lstrip('0')
                try:
                    pokemon_id = int(pokemon_id_str)
                    image_data_list.append({
                        'pokemon_id': pokemon_id,
                        'file_name': filename,
                        'full_path': os.path.join(IMAGE_FOLDER_PATH, filename),
                    })
                except ValueError:
                    continue
            
    df_images = pd.DataFrame(image_data_list)
    
    print(f"🔎 매핑 성공한 이미지 수: {len(df_images)}개")
    
    if not df_images.empty:
        df_images.to_sql("POKEMON_IMAGES", conn, if_exists="replace", index=False)
        print(f"✅ POKEMON_IMAGES 테이블 생성 및 매핑 완료.")
    else:
        print("❌ 이미지 매핑 실패: 파일 이름 형식이 잘못되었거나 폴더에 이미지 파일이 없습니다.")
else:
    print(f"❌ 폴더 접근 실패: 경로가 잘못되었습니다. 경로: {IMAGE_FOLDER_PATH}")


# [기존 build_db.py 코드]
# conn.commit() # 변경사항 저장
# conn.close() # DB 연결 종료
# print("✅ DB 연결 종료 및 저장 완료.")
