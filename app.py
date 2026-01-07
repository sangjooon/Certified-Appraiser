import streamlit as st
import requests
import uuid
import time
import json
import io

# ==========================================
# 1. 네이버 OCR 호출 함수 (기본)
# ==========================================
def call_naver_ocr(file_bytes, file_ext, api_url, secret_key):
    request_json = {
        'images': [{'format': file_ext, 'name': 'demo'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }
    
    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    headers = {'X-OCR-SECRET': secret_key}
    files = [('file', file_bytes)]

    try:
        response = requests.post(api_url, headers=headers, data=payload, files=files)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

# ==========================================
# 2. 핵심 로직: 줄글로 변환하기 📝
# ==========================================
def ocr_to_plain_text(ocr_json):
    if not ocr_json or 'images' not in ocr_json:
        return ""

    fields = ocr_json['images'][0]['fields']
    
    # 1. 데이터 추출 (글자 + Y좌표)
    # 네이버는 보통 읽는 순서대로 주지만, 확실하게 하기 위해 좌표도 같이 봅니다.
    extracted_data = []
    for field in fields:
        text = field['inferText']
        # 상단 Y좌표 (글자의 높이 위치)
        y = field['boundingPoly']['vertices'][0]['y']
        # 좌측 X좌표 (같은 줄에서 순서 정렬용)
        x = field['boundingPoly']['vertices'][0]['x']
        extracted_data.append({'text': text, 'x': x, 'y': y})

    # 2. Y좌표(세로 위치) 기준으로 정렬 -> 위에서 아래로 읽기 위함
    extracted_data.sort(key=lambda k: k['y'])

    # 3. 같은 줄끼리 묶어서 텍스트 생성
    full_text = ""
    if extracted_data:
        current_line = []
        last_y = extracted_data[0]['y']
        
        for item in extracted_data:
            # 줄 바꿈 판단 기준: 높이 차이가 15픽셀 이상 나면 "다음 줄"로 간주
            if abs(item['y'] - last_y) > 15:
                # 지금까지 모은 줄을 X좌표(왼쪽->오른쪽) 순으로 정렬
                current_line.sort(key=lambda k: k['x'])
                
                # 한 줄로 합치기 (단어 사이 띄어쓰기)
                line_str = " ".join([d['text'] for d in current_line])
                full_text += line_str + "\n"  # 엔터 추가
                
                # 초기화
                current_line = []
            
            current_line.append(item)
            last_y = item['y'] # 기준 높이 업데이트
        
        # 마지막 남은 줄 처리
        if current_line:
            current_line.sort(key=lambda k: k['x'])
            full_text += " ".join([d['text'] for d in current_line])

    return full_text

# ==========================================
# 3. Streamlit UI
# ==========================================
def main():
    st.set_page_config(page_title="텍스트 변환기", layout="centered")
    st.title("📝 문서 -> 줄글(Text) 변환기")
    st.markdown("PDF나 이미지를 올리면 **읽기 편한 텍스트**로 쭉 뽑아줍니다.")

    # 사이드바 설정
    with st.sidebar:
        try:
            api_url = st.secrets["NAVER_API_URL"]
            secret_key = st.secrets["NAVER_SECRET_KEY"]
        except:
            api_url = st.text_input("API URL")
            secret_key = st.text_input("Secret Key", type="password")

    uploaded_file = st.file_uploader("파일 업로드 (PDF/JPG)", type=['pdf', 'jpg', 'png'])

    if uploaded_file and st.button("텍스트 추출하기"):
        if not api_url:
            st.error("API 키가 없습니다.")
            return

        with st.spinner("텍스트를 읽어오는 중..."):
            file_bytes = uploaded_file.getvalue()
            ext = uploaded_file.name.split('.')[-1].lower()
            fmt = ext if ext in ['jpg', 'png'] else 'pdf'
            
            # OCR 호출
            result = call_naver_ocr(file_bytes, fmt, api_url, secret_key)
            
            if result:
                # 줄글 변환
                plain_text = ocr_to_plain_text(result)
                
                st.success("추출 완료!")
                
                # 1. 화면에 보여주기 (복사하기 좋게)
                st.text_area("추출된 내용", plain_text, height=400)
                
                # 2. txt 파일 다운로드
                st.download_button(
                    label="📥 텍스트 파일(.txt) 다운로드",
                    data=plain_text,
                    file_name=f"{uploaded_file.name}_변환.txt",
                    mime="text/plain"
                )
            else:
                st.error("OCR 분석 실패")

if __name__ == "__main__":
    main()
