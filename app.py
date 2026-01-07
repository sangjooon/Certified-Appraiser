import streamlit as st
import requests
import pandas as pd
import uuid
import time
import json
import io

# ==========================================
# 1. 네이버 OCR 호출 함수
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
        else:
            st.error(f"OCR 통신 에러: {response.text}")
            return None
    except Exception as e:
        st.error(f"연결 실패: {str(e)}")
        return None

# ==========================================
# 2. 핵심: 좌표 기반 엑셀 변환 로직 🧠
# ==========================================
def json_to_excel_layout(ocr_json):
    if not ocr_json or 'images' not in ocr_json:
        return pd.DataFrame(), pd.DataFrame()

    fields = ocr_json['images'][0]['fields']
    
    # 1. 모든 글자에 Y좌표(높이) 정보를 추가해서 리스트로 만듦
    # boundingPoly.vertices[0].y 가 글자의 상단 Y좌표
    extracted_data = []
    for field in fields:
        text = field['inferText']
        x = field['boundingPoly']['vertices'][0]['x']
        y = field['boundingPoly']['vertices'][0]['y']
        extracted_data.append({'text': text, 'x': x, 'y': y})

    # 2. Y좌표(세로 위치) 기준으로 정렬
    extracted_data.sort(key=lambda k: k['y'])

    # 3. 같은 줄(Row)끼리 그룹화 (Y좌표 차이가 15픽셀 이내면 같은 줄로 간주)
    rows = []
    current_row = []
    if extracted_data:
        last_y = extracted_data[0]['y']
        
        for item in extracted_data:
            # 이전 글자와 높이 차이가 15px 보다 크면 -> 줄 바꿈
            if abs(item['y'] - last_y) > 15:
                # 지금까지 모은 줄을 X좌표 순으로 정렬하고 저장
                current_row.sort(key=lambda k: k['x'])
                rows.append([d['text'] for d in current_row])
                current_row = [] # 새 줄 시작
            
            current_row.append(item)
            last_y = item['y']
        
        # 마지막 줄 처리
        if current_row:
            current_row.sort(key=lambda k: k['x'])
            rows.append([d['text'] for d in current_row])

    # 4. 시각적 엑셀 데이터프레임 생성
    df_visual = pd.DataFrame(rows)
    
    # 5. (옵션) 원본 좌표 데이터프레임 (Raw Data)
    df_raw = pd.DataFrame(extracted_data)

    return df_visual, df_raw

# ==========================================
# 3. Streamlit UI
# ==========================================
def main():
    st.set_page_config(page_title="OCR 전체 변환기", layout="wide")
    st.title("📑 만능 문서 → 엑셀 변환기")
    st.markdown("OCR이 읽은 **모든 글자**를 빠짐없이 엑셀 좌표처럼 변환합니다.")

    # 사이드바 설정
    with st.sidebar:
        st.header("설정")
        try:
            api_url = st.secrets["NAVER_API_URL"]
            secret_key = st.secrets["NAVER_SECRET_KEY"]
            st.success("API 키 자동 로드됨")
        except:
            api_url = st.text_input("API URL")
            secret_key = st.text_input("Secret Key", type="password")

    uploaded_file = st.file_uploader("PDF나 이미지 파일을 올려주세요", type=['pdf', 'jpg', 'png'])

    if uploaded_file and st.button("전체 변환 실행"):
        if not api_url:
            st.error("API 키를 입력해주세요.")
            return

        with st.spinner("AI가 문서를 스캔하고 엑셀로 다시 그리는 중..."):
            file_bytes = uploaded_file.getvalue()
            ext = uploaded_file.name.split('.')[-1].lower()
            ocr_fmt = ext if ext in ['jpg', 'png'] else 'pdf'
            
            # 1. OCR 호출
            result_json = call_naver_ocr(file_bytes, ocr_fmt, api_url, secret_key)
            
            if result_json:
                # 2. 엑셀 레이아웃 변환
                df_view, df_raw = json_to_excel_layout(result_json)
                
                st.success("변환 완료!")
                
                # 화면에 미리보기
                st.subheader("👀 엑셀 미리보기 (상위 10줄)")
                st.dataframe(df_view.head(10), use_container_width=True)

                # 3. 엑셀 다운로드 (Sheet 2개로 분리)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_view.to_excel(writer, index=False, header=False, sheet_name='문서_레이아웃')
                    df_raw.to_excel(writer, index=False, sheet_name='좌표_원본데이터')
                
                st.download_button(
                    label="📥 전체 엑셀 다운로드",
                    data=output.getvalue(),
                    file_name=f"OCR_Full_Convert_{uploaded_file.name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                with st.expander("개발자용: JSON 원본 데이터 확인"):
                    st.json(result_json)

if __name__ == "__main__":
    main()
