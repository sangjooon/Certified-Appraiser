# 이 코드는 개발용 코드임

import streamlit as st
import requests
import pandas as pd
import uuid
import time
import json
import re
import io

from typing import List, Tuple

# ==========================================
# 0. [유틸] PDF 쪼개기 함수
# ==========================================
def split_pdf_into_chunks(pdf_bytes: bytes, chunk_size: int = 10) -> List[Tuple[bytes, int, int]]:
    """
    PDF bytes를 chunk_size 페이지 단위로 쪼개서
    [(chunk_pdf_bytes, start_page(1-indexed), end_page(1-indexed)), ...] 형태로 반환
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        # 예전 환경 호환용
        from PyPDF2 import PdfReader, PdfWriter  # type: ignore

    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    chunks: List[Tuple[bytes, int, int]] = []

    for start in range(0, total_pages, chunk_size):
        end = min(start + chunk_size, total_pages)

        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])

        buf = io.BytesIO()
        writer.write(buf)
        chunks.append((buf.getvalue(), start + 1, end))

    return chunks



# ==========================================
# 1. [설정] 네이버 API 연결
# ==========================================
def call_naver_ocr(file_bytes, file_ext, api_url, secret_key):
    """네이버 OCR을 호출해서 JSON 결과를 받아옵니다."""
    request_json = {
        "images": [{"format": file_ext, "name": "demo"}],
        "requestId": str(uuid.uuid4()),
        "version": "V2",
        "timestamp": int(round(time.time() * 1000)),
    }

    payload = {"message": json.dumps(request_json)}
    headers = {"X-OCR-SECRET": secret_key}

    content_type = "application/pdf" if file_ext == "pdf" else "image/jpeg"
    files = {"file": (f"upload.{file_ext}", file_bytes, content_type)}

    try:
        r = requests.post(api_url, headers=headers, data=payload, files=files, timeout=60)

        return {
            "ok": (r.status_code == 200),
            "status_code": r.status_code,
            "text": r.text[:2000],
            "json": (r.json() if "application/json" in r.headers.get("Content-Type", "") else None),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
    
    
# ==========================================
# 2. [전처리] JSON -> 줄글 텍스트 변환
# ==========================================
def json_to_text_lines(ocr_json, line_y_threshold=15):
    """
    OCR 결과(JSON)의 모든 페이지(images)를 순서대로 텍스트로 합칩니다.
    각 페이지는 '위->아래, 좌->우' 정렬 후 줄 단위로 재구성합니다.
    """
    if not ocr_json or "images" not in ocr_json:
        return ""

    pages_text = []

    for page_idx, img in enumerate(ocr_json["images"], start=1):
        fields = img.get("fields", [])
        extracted_data = []

        for field in fields:
            text = field.get("inferText", "")
            verts = field.get("boundingPoly", {}).get("vertices", [])
            if not verts:
                continue
            x = verts[0].get("x", 0)
            y = verts[0].get("y", 0)
            extracted_data.append({"text": text, "x": x, "y": y})

        extracted_data.sort(key=lambda k: k["y"])

        full_text = ""
        if extracted_data:
            current_line = []
            last_y = extracted_data[0]["y"]

            for item in extracted_data:
                if abs(item["y"] - last_y) > line_y_threshold:
                    current_line.sort(key=lambda k: k["x"])
                    full_text += " ".join([d["text"] for d in current_line]).strip() + "\n"
                    current_line = []

                current_line.append(item)
                last_y = item["y"]

            if current_line:
                current_line.sort(key=lambda k: k["x"])
                full_text += " ".join([d["text"] for d in current_line]).strip()

        pages_text.append(f"\n===== PAGE {page_idx} =====\n{full_text}".strip())

    return "\n".join(pages_text).strip()


# ==========================================
# 3. [핵심] 절대 규칙(Rule)으로 데이터 뽑기 ⚡
# ==========================================
def extract_data_by_rules(text):
    """
    텍스트 덩어리에서 정규표현식(Regex)을 이용해 핵심 데이터를 추출합니다.
    *여기에 파트너님이 원하는 규칙을 추가하면 됩니다.*
    """
    data = {}

    # --- 규칙 1: 소재지 (주소) ---
    # "소재지" 라는 글자 뒤에 나오는 "경기도 ~~~" 패턴을 찾음
    # (?m)은 멀티라인 모드, ^는 줄 시작
    addr_match = re.search(
        r"(소재지|대지위치)\s*[:]?\s*([가-힣]+[시도].*?)(?=\s지\s*번|\s면\s*적|\s지\s*목|$)",
        text,
    )
    data["소재지"] = addr_match.group(2).strip() if addr_match else "찾지 못함"

    # --- 규칙 2: 지목 (땅의 용도) ---
    # "지목" 뒤에 나오는 한글 단어 (예: 대, 전, 답, 임야)
    jimok_match = re.search(r"지\s*목\s*[:]?\s*([가-힣]+)", text)
    data["지목"] = jimok_match.group(1).strip() if jimok_match else "찾지 못함"

    # --- 규칙 3: 면적 (숫자 + ㎡) ---
    # 콤마(,)와 소수점(.)을 포함한 숫자 뒤에 "㎡"가 있는 것
    area_matches = re.findall(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*㎡", text)
    # 팁: 문서에 면적이 여러 개 나오면 보통 제일 큰 게 전체 면적임
    if area_matches:
        valid_areas = [float(a.replace(",", "")) for a in area_matches]
        data["면적(㎡)"] = max(valid_areas)  # 가장 큰 값 선택
    else:
        data["면적(㎡)"] = "찾지 못함"

    # --- 규칙 4: 소유자 (이름) ---
    # "성명" 또는 "소유자" 뒤에 오는 이름 (보통 3글자)
    owner_match = re.search(r"(성명|소유자)\s*[:]?\s*([가-힣]{3})", text)
    data["소유자"] = owner_match.group(2).strip() if owner_match else "찾지 못함"

    # --- 규칙 5: (옵션) 원본 텍스트 일부 저장 ---
    data["원본_요약"] = text[:100].replace("\n", " ") + "..."

    return data


# main 함수
def main():

    # 페이지 상단 및 설정
    st.set_page_config(
        page_title="문서 비서",
        page_icon="📄",  # 이모지 유니코드: U+1F4C4
        layout="wide",
    )

    # 제목
    st.title("문서 비서📄 dev")

    # 개발 단계
    st.subheader("토지의 소재지를 출력하는 프로토타입 v0.1")

    # 서비스 설명
    st.markdown(
        """
        문서 비서는 다양한 형식의 문서를 텍스트로 변환하고, 
        사용자가 원하는 핵심 데이터를 추출하는 도구입니다.
        """
    )

    # 비밀번호(임시)
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if password != "alohomora":
        st.warning("비밀번호가 올바르지 않습니다.")
        return

    st.success("환영합니다! 문서 비서를 시작합니다.")

    # 사이드바 API 설정
    with st.sidebar:
        try:
            api_url = st.secrets["NAVER_API_URL"]
            secret_key = st.secrets["NAVER_SECRET_KEY"]
        except:
            api_url = st.text_input("API URL")
            secret_key = st.text_input("Secret Key", type="password")

    # 파일 업로드
    uploaded_file = st.file_uploader("문서파일을 업로드하세요", type=["pdf"])
    if uploaded_file is not None:
        st.success("파일이 업로드되었습니다.")

    #  파일 업로드 및 추출 시작
    if uploaded_file and st.button("🔍 데이터 추출 시작"):
        if not api_url:
            st.error("API 키 확인 필요")
            return

        with st.spinner("1단계: 문서를 텍스트로 변환 중..."):
            file_bytes = uploaded_file.getvalue()
            ext = uploaded_file.name.split(".")[-1].lower()
            fmt = ext if ext in ["jpg", "png"] else "pdf"

            # 1) PDF를 10페이지씩 분할
            chunks = split_pdf_into_chunks(file_bytes, chunk_size=10)

            st.info(f"PDF 총 {len(chunks)}개 묶음(최대 10페이지씩)으로 나눠서 OCR 진행합니다.")

            all_raw_text_parts = []
            progress = st.progress(0)
            status = st.empty()

            for idx, (chunk_bytes, start_p, end_p) in enumerate(chunks, start=1):
                status.write(f"🔎 OCR 진행 중: {idx}/{len(chunks)} (페이지 {start_p}~{end_p})")

                # OCR 호출 (항상 pdf로 보냄)
                result = call_naver_ocr(chunk_bytes, "pdf", api_url, secret_key)

                if not result["ok"]:
                    st.error(f"OCR 실패: 묶음 {idx} (페이지 {start_p}~{end_p})")
                    st.error(f"status_code: {result.get('status_code')}")
                    st.code(result.get("text") or result.get("error"))
                    return

                ocr_json = result["json"]
                if not ocr_json:
                    st.error(f"OCR 응답은 200인데 JSON 파싱이 안 됐어요: 묶음 {idx} (페이지 {start_p}~{end_p})")
                    st.code(result.get("text"))
                    return

                # 이 chunk의 텍스트 변환
                chunk_text = json_to_text_lines(ocr_json)

                # 원래 전체 문서 페이지 범위 라벨을 더 명확히 남김
                all_raw_text_parts.append(f"\n######## PDF PAGES {start_p}-{end_p} ########\n{chunk_text}".strip())

                progress.progress(int(idx / len(chunks) * 100))

            status.write("✅ OCR 완료")

            # 최종 Raw Text 합치기
            raw_text = "\n\n".join(all_raw_text_parts)


            with st.spinner("2단계: 규칙에 맞춰 데이터 뽑는 중..."):
                # 3. 텍스트 -> 엑셀 데이터 (규칙 적용)
                extracted_data = extract_data_by_rules(raw_text)

                # 결과 보여주기
                st.divider()
                col1, col2 = st.columns([1, 1])

                with col1:
                    st.subheader("✅ 추출 결과 (Excel)")
                    df = pd.DataFrame(
                        [extracted_data]
                    )  # 리스트로 감싸서 행으로 만듦
                    st.dataframe(
                        df.T, use_container_width=True
                    )  # 보기 좋게 행/열 바꿔서 표시

                    # 엑셀 다운로드
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                        df.to_excel(writer, index=False)

                    st.download_button(
                        label="📥 엑셀 파일 다운로드",
                        data=output.getvalue(),
                        file_name=f"규칙추출_{uploaded_file.name}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                with col2:
                    st.subheader("📄 AI가 읽은 원본 텍스트")
                    st.text_area("OCR Raw Text", raw_text, height=400)

            

# 실행
if __name__ == "__main__":
    main()
