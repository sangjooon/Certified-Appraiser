import streamlit as st
import requests
import uuid
import time
import json
import re

# ==========================================
# 1. 설정: 네이버 API 키 가져오기
# ==========================================
# 배포 시엔 st.secrets를 쓰고, 로컬 테스트엔 사이드바 입력을 받도록 처리
def get_api_keys():
    try:
        api_url = st.secrets["NAVER_API_URL"]
        secret_key = st.secrets["NAVER_SECRET_KEY"]
        return api_url, secret_key
    except:
        return None, None

# ==========================================
# 2. 기능: 네이버 OCR 호출
# ==========================================
def call_naver_ocr(uploaded_file, api_url, secret_key):
    # 파일 확장자에 따라 포맷 결정
    file_ext = uploaded_file.name.split('.')[-1].lower()
    format_type = file_ext if file_ext in ['jpg', 'png', 'jpeg'] else 'pdf'

    request_json = {
        'images': [{'format': format_type, 'name': 'demo'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }

    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    headers = {'X-OCR-SECRET': secret_key}

    try:
        files = [('file', (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type))]
        response = requests.post(api_url, headers=headers, data=payload, files=files)
        
        if response.status_code == 200:
            result = response.json()
            full_text = ""
            for image in result.get("images", []):
                for field in image.get("fields", []):
                    full_text += field.get("inferText", "") + " "
            return full_text
        else:
            return None
    except Exception as e:
        return None

# ==========================================
# 3. 기능: 면적 숫자만 추출 (Regex)
# ==========================================
def find_land_area(text):
    if not text: return 0.0
    
    # 1. 숫자 + ㎡ 패턴 찾기 (예: 123.45㎡, 1,234.5 ㎡)
    # 토지 등기부의 핵심은 '표제부'의 면적이므로, 보통 문서 상단에 나오거나 
    # 여러 면적 중 가장 큰 값이 대지 면적일 확률이 높음.
    matches = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)\s*㎡', text)
    
    valid_areas = []
    for m in matches:
        clean_num = float(m.replace(',', ''))
        # 0.1㎡ 미만은 오인식일 수 있으니 제외
        if clean_num > 0.1:
            valid_areas.append(clean_num)
            
    if valid_areas:
        # 팁: 등기부엔 1층 면적, 2층 면적 등도 나올 수 있지만 
        # 토지 등기에서 가장 중요한 '대지권'이나 '토지 면적'은 보통 가장 큰 수치임.
        # (필요시 로직 수정 가능)
        return max(valid_areas)
    else:
        return 0.0

# ==========================================
# 4. 웹 화면 구성 (Streamlit)
# ==========================================
def main():
    st.set_page_config(page_title="토지 면적 계산기", page_icon="📐")

    st.title("📐 토지 등기 면적 자동 계산기")
    st.write("토지 등기부등본(PDF/이미지)을 올리면 **면적**만 찾아냅니다.")

    # 사이드바: API 키 설정
    with st.sidebar:
        st.header("설정")
        auto_url, auto_key = get_api_keys()
        
        if auto_url:
            st.success("API 키가 자동 로드되었습니다.")
            api_url = auto_url
            secret_key = auto_key
        else:
            st.warning("Secrets 설정이 없습니다. 직접 입력하세요.")
            api_url = st.text_input("API Gateway URL")
            secret_key = st.text_input("Secret Key", type="password")

    # 파일 업로드
    uploaded_file = st.file_uploader("토지 등기 파일 업로드", type=['pdf', 'jpg', 'png'])

    if uploaded_file and st.button("면적 계산하기", type="primary"):
        if not api_url or not secret_key:
            st.error("API 키를 먼저 설정해주세요.")
            return

        with st.spinner("네이버 AI가 문서를 읽고 있습니다..."):
            # 1. OCR 실행
            text_result = call_naver_ocr(uploaded_file, api_url, secret_key)
            
            if text_result:
                # 2. 면적 추출
                area_value = find_land_area(text_result)
                
                st.divider()
                if area_value > 0:
                    st.success("면적을 찾았습니다!")
                    
                    # 결과를 크고 잘 보이게 출력
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric(label="토지 면적 (㎡)", value=f"{area_value:,.2f} ㎡")
                    with col2:
                        # 평수 계산 (1㎡ = 0.3025평)
                        pyeong = area_value * 0.3025
                        st.metric(label="평수 환산 (평)", value=f"{pyeong:,.2f} 평")
                else:
                    st.warning("문서에서 '면적(㎡)' 패턴을 찾지 못했습니다.")
                    st.caption("문서가 깨끗한지, 올바른 등기부인지 확인해주세요.")
                
                # 디버깅용 텍스트 보기
                with st.expander("AI가 읽은 전체 텍스트 확인"):
                    st.text(text_result)
            else:
                st.error("OCR 분석에 실패했습니다. (API 키 또는 파일 확인)")

if __name__ == "__main__":
    main()
