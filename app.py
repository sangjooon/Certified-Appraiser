import streamlit as st
import requests
import pandas as pd
import uuid
import time
import json
import re
import io
from io import BytesIO

# --------------------------------------------------------------------------
# 1. 설정 및 네이버 OCR 호출 함수
# --------------------------------------------------------------------------


def call_naver_ocr(file_bytes, file_format, api_url, secret_key):
    """
    네이버 CLOVA OCR API를 호출하는 함수
    """
    request_json = {
        "images": [{"format": file_format, "name": "demo"}],
        "requestId": str(uuid.uuid4()),
        "version": "V2",
        "timestamp": int(round(time.time() * 1000)),
    }

    payload = {"message": json.dumps(request_json).encode("UTF-8")}
    files = [("file", file_bytes)]
    headers = {"X-OCR-SECRET": secret_key}

    try:
        response = requests.post(api_url, headers=headers, data=payload, files=files)
        response.raise_for_status()  # 에러 발생 시 예외 처리
        return response.json()
    except Exception as e:
        st.error(f"OCR API 호출 중 오류 발생: {str(e)}")
        return None


# --------------------------------------------------------------------------
# 2. 토지대장 파싱 로직 (핵심)
# --------------------------------------------------------------------------


def parse_land_ledger(ocr_result):
    """
    OCR 결과(JSON)에서 토지대장의 주요 항목을 추출하여 DataFrame으로 변환
    *참고: 실제 토지대장 양식에 따라 정규표현식(Regex)을 정교하게 다듬어야 합니다.*
    """
    if not ocr_result or "images" not in ocr_result:
        return pd.DataFrame()

    # 1. 전체 텍스트를 하나의 문자열로 결합 (위치 기반으로 정렬된 상태 가정)
    all_text = ""
    fields = ocr_result["images"][0]["fields"]

    # y좌표 순서대로 정렬 (줄 단위 인식) -> x좌표 순서대로 정렬
    # 네이버 OCR은 기본적으로 읽는 순서를 어느정도 맞춰주지만, 확실하게 하기 위함
    # fields.sort(key=lambda x: (x['boundingPoly']['vertices'][0]['y'], x['boundingPoly']['vertices'][0]['x']))

    for field in fields:
        all_text += field["inferText"] + " "

    # 2. 정규표현식을 이용한 데이터 추출 (예시)
    data = {}

    # (1) 소재지 추출 (예: 경기도 성남시...)
    # '소재지' 또는 '토지 소재' 뒤에 나오는 주소 패턴 찾기
    address_match = re.search(
        r"(소재지|토지\s*소재)\s*[:]?\s*([가-힣]+[시도].*?)(?=\s지\s*번|\s지\s*목|$)",
        all_text,
    )
    data["소재지"] = address_match.group(2).strip() if address_match else "인식 실패"

    # (2) 지목 추출 (예: 대, 전, 답, 임야)
    jimok_match = re.search(r"지\s*목\s*[:]?\s*([가-힣]+)", all_text)
    data["지목"] = jimok_match.group(1).strip() if jimok_match else "인식 실패"

    # (3) 면적 추출 (숫자와 ㎡)
    area_match = re.search(r"면\s*적\s*[:]?\s*([\d,.]+)", all_text)
    data["면적(㎡)"] = area_match.group(1).strip() if area_match else "인식 실패"

    # (4) 소유자 성명 추출 (단순 예시, 여러 명일 경우 복잡해짐)
    owner_match = re.search(r"(성명|소유자명)\s*[:]?\s*([가-힣]{2,4})", all_text)
    data["소유자"] = owner_match.group(2).strip() if owner_match else "인식 실패"

    # (5) 변동일자/원인 등 추가 항목은 표 구조가 복잡하여
    # Raw Data도 함께 제공하는 것이 좋습니다.
    data["전체_추출_텍스트"] = all_text[:500] + "..."  # 너무 길면 자름

    return pd.DataFrame([data])


# --------------------------------------------------------------------------
# 3. Streamlit UI 구성
# --------------------------------------------------------------------------


def main():
    st.set_page_config(page_title="토지대장 OCR 변환기", layout="wide")

    st.title("📄 토지대장 OCR to Excel 변환기")
    st.markdown(
        """
    네이버 CLOVA OCR을 이용하여 토지대장 이미지(PDF, JPG, PNG)를 업로드하면 
    주요 내용을 추출하여 엑셀 파일로 변환해줍니다.
    """
    )

    # 사이드바: API 키 설정 (Streamlit Cloud 배포 시 secrets에서 가져옴)
    with st.sidebar:
        st.header("⚙️ 설정")
        # Streamlit Secrets에서 가져오거나 직접 입력
        try:
            default_api_url = st.secrets["NAVER_API_URL"]
            default_secret_key = st.secrets["NAVER_SECRET_KEY"]
            api_url = default_api_url
            secret_key = default_secret_key
            st.success("API 키가 Secrets에서 로드되었습니다.")
        except FileNotFoundError:
            st.warning("로컬 테스트 중이거나 Secrets가 설정되지 않았습니다.")
            api_url = st.text_input("API Gateway URL")
            secret_key = st.text_input("Secret Key", type="password")

    # 파일 업로드
    uploaded_file = st.file_uploader(
        "토지대장 파일을 업로드하세요", type=["png", "jpg", "jpeg", "pdf"]
    )

    if uploaded_file is not None and api_url and secret_key:

        # 파일 형식 확인
        file_type = uploaded_file.name.split(".")[-1].lower()
        if file_type == "pdf":
            ocr_format = "pdf"
        else:
            ocr_format = file_type  # jpg, png 등

        if st.button("🔍 변환 시작"):
            with st.spinner("네이버 AI가 문서를 분석 중입니다..."):
                # 파일 바이트 읽기
                file_bytes = uploaded_file.getvalue()

                # 1. API 호출
                ocr_result = call_naver_ocr(file_bytes, ocr_format, api_url, secret_key)

                if ocr_result:
                    # 2. 결과 파싱
                    df = parse_land_ledger(ocr_result)

                    st.divider()
                    st.subheader("✅ 변환 결과")

                    # 데이터프레임 보여주기
                    st.dataframe(df, use_container_width=True)

                    # 3. 엑셀 다운로드 버튼
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                        df.to_excel(writer, index=False, sheet_name="토지대장_추출")

                    st.download_button(
                        label="📥 엑셀 파일 다운로드",
                        data=output.getvalue(),
                        file_name=f"토지대장_변환_{uploaded_file.name}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                    # (디버깅용) JSON 원본 보기
                    with st.expander("원본 OCR JSON 결과 보기"):
                        st.json(ocr_result)

    elif uploaded_file is not None:
        st.warning("사이드바에서 API URL과 Secret Key를 확인해주세요.")


if __name__ == "__main__":
    main()
