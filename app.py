import streamlit as st
import pandas as pd
import pdfplumber
import requests
import uuid
import time
import json
import re
import io
from dataclasses import dataclass
from typing import List, Optional

# ==========================================
# 🛑 [보안 설정] API 키 로드 (secrets.toml)
# ==========================================
# 주의: 이 코드를 실행하려면 .streamlit/secrets.toml 파일이 필요합니다.
# 만약 로컬에서 바로 테스트하려면 아래 변수에 직접 문자열을 넣으세요. (배포 시엔 지워야 함)
try:
    NAVER_API_URL = st.secrets["NAVER_API_URL"]
    NAVER_SECRET_KEY = st.secrets["NAVER_SECRET_KEY"]
except:
    # secrets 파일이 없을 경우를 대비한 기본값 (경고 표시용)
    NAVER_API_URL = ""
    NAVER_SECRET_KEY = ""


# ==========================================
# 1. 데이터 구조 정의
# ==========================================
@dataclass
class DocInfo:
    category: str
    filename: str
    address: str
    area: float
    owners: List[str]
    raw_text: str


@dataclass
class CompareResult:
    target: str
    item: str
    is_match: bool
    doc1_val: str
    doc2_val: str
    msg: str


# ==========================================
# 2. 파싱 엔진 (네이버 OCR + 웹 파일 처리)
# ==========================================
class MasterParser:
    @staticmethod
    def call_naver_ocr(uploaded_file):
        """웹에서 업로드된 파일 객체를 네이버 OCR로 전송"""
        if not NAVER_API_URL or not NAVER_SECRET_KEY:
            return ""

        # 파일 포맷 확인
        file_ext = uploaded_file.name.split(".")[-1].lower()
        format_type = file_ext if file_ext in ["jpg", "jpeg", "png", "pdf"] else "pdf"

        # 요청 데이터 생성
        request_json = {
            "images": [{"format": format_type, "name": "demo"}],
            "requestId": str(uuid.uuid4()),
            "version": "V2",
            "timestamp": int(round(time.time() * 1000)),
        }

        payload = {"message": json.dumps(request_json).encode("UTF-8")}
        headers = {"X-OCR-SECRET": NAVER_SECRET_KEY}

        try:
            # Streamlit UploadedFile은 'getvalue()'로 바이너리 데이터를 읽습니다.
            files = [
                (
                    "file",
                    (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type),
                )
            ]

            response = requests.post(
                NAVER_API_URL, headers=headers, data=payload, files=files
            )

            if response.status_code == 200:
                result = response.json()
                full_text = ""
                for image in result.get("images", []):
                    for field in image.get("fields", []):
                        full_text += field.get("inferText", "") + " "
                return full_text
            else:
                return ""  # OCR 실패
        except Exception:
            return ""  # 통신 에러

    @staticmethod
    def parse(uploaded_file) -> DocInfo:
        filename = uploaded_file.name
        full_text = ""

        # 1. 네이버 OCR 시도
        full_text = MasterParser.call_naver_ocr(uploaded_file)

        # 2. 실패 시(또는 키 설정 안 됨) 무료 엔진(pdfplumber) 백업 실행
        if not full_text:
            try:
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        full_text += str(page.extract_text()) + "\n"
            except:
                pass  # 이미지 파일이면 pdfplumber 실패할 수 있음

        # 3. 문서 종류 식별
        cat = "미식별"
        if "건축물대장" in full_text or "건물ID" in full_text:
            cat = "건축물대장"
        elif "토지대장" in full_text or "임야대장" in full_text:
            cat = "토지대장"
        elif "등기사항전부증명서" in full_text:
            if "건물의표시" in full_text.replace(" ", "") or "[집합건물]" in full_text:
                cat = "건물등기"
            elif "토지의표시" in full_text.replace(" ", ""):
                cat = "토지등기"
            else:
                cat = "건물등기"
        else:
            cat = "기타문서"

        # 4. 데이터 추출
        address = "인식실패"
        area = 0.0
        owners = []

        # (1) 주소
        addr_match = re.search(
            r"(소재지|대지위치)\s*[:]?\s*([가-힣]+[시도].*?)\s", full_text
        )
        if addr_match:
            address = addr_match.group(2).strip()
        else:
            addr_match2 = re.search(
                r"([가-힣]+[시도]\s+[가-힣]+[구시군]\s+[가-힣]+[읍면동].*?)\s",
                full_text,
            )
            if addr_match2:
                address = addr_match2.group(1).strip()

        # (2) 면적
        area_matches = re.findall(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*㎡", full_text)
        valid_areas = [
            float(m.replace(",", ""))
            for m in area_matches
            if float(m.replace(",", "")) > 1.0
        ]
        if valid_areas:
            area = max(valid_areas)

        # (3) 소유자
        if "등기" in cat:
            owners = list(
                set(re.findall(r"소유자\s+([가-힣]{2,4}|주식회사\S+)", full_text))
            )
        elif "건축물" in cat:
            owners = list(set(re.findall(r"성명\s*([가-힣]{3})", full_text)))
        elif "토지" in cat:
            owners = list(set(re.findall(r"([가-힣]{3})\s+\(\d{6}-\d{7}\)", full_text)))
            if not owners:
                owners = list(set(re.findall(r"성명\s*([가-힣]{3})", full_text)))

        if not owners:
            owners = ["(미상)"]

        return DocInfo(cat, filename, address, area, owners, full_text)


# ==========================================
# 3. 비교 분석기 (로직 동일)
# ==========================================
class CrossAnalyzer:
    def __init__(self, ll, lr, bl, br):
        self.ll = ll
        self.lr = lr
        self.bl = bl
        self.br = br

    def compare_pair(
        self, doc1: DocInfo, doc2: DocInfo, target_name: str
    ) -> List[CompareResult]:
        res = []
        if not doc1 or not doc2:
            return [
                CompareResult(target_name, "문서없음", False, "-", "-", "파일 누락")
            ]

        a1 = doc1.address.replace("경기도", "").replace(" ", "")
        a2 = doc2.address.replace("경기도", "").replace(" ", "")
        match_addr = (a1 in a2) or (a2 in a1)
        res.append(
            CompareResult(
                target_name,
                "소재지",
                match_addr,
                doc1.address,
                doc2.address,
                "일치" if match_addr else "확인필요",
            )
        )

        diff = abs(doc1.area - doc2.area)
        match_area = diff < 3.3
        res.append(
            CompareResult(
                target_name,
                "면적(㎡)",
                match_area,
                str(doc1.area),
                str(doc2.area),
                "일치" if match_area else f"오차 {diff:.1f}",
            )
        )

        s1 = set(doc1.owners)
        s2 = set(doc2.owners)
        match_owner = not s1.isdisjoint(s2)
        res.append(
            CompareResult(
                target_name,
                "소유자",
                match_owner,
                str(list(s1)),
                str(list(s2)),
                "일치" if match_owner else "불일치",
            )
        )
        return res

    def run(self):
        return self.compare_pair(self.ll, self.lr, "[토지]") + self.compare_pair(
            self.bl, self.br, "[건물]"
        )


# ==========================================
# 4. Streamlit 웹 UI
# ==========================================
def main():
    st.set_page_config(page_title="부동산 AI 분석기", layout="wide", page_icon="🏘️")

    st.title("🏘️ 부동산 4대 서류 AI 통합 분석기")
    st.markdown(
        """
    **토지/건축물 대장**과 **등기부등본**을 업로드하면, **네이버 AI**가 서류를 읽고 교차 검증합니다.
    """
    )

    # API 키 상태 확인
    if not NAVER_API_URL or not NAVER_SECRET_KEY:
        st.warning(
            "⚠️ 네이버 OCR API 키가 설정되지 않았습니다. 결과가 정확하지 않을 수 있습니다."
        )

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.header("1. 토지 (Land)")
        f_ll = st.file_uploader(
            "📂 토지대장 업로드", type=["pdf", "jpg", "png"], key="ll"
        )
        f_lr = st.file_uploader(
            "📂 토지등기 업로드", type=["pdf", "jpg", "png"], key="lr"
        )

    with col2:
        st.header("2. 건물 (Building)")
        f_bl = st.file_uploader(
            "📂 건축물대장 업로드", type=["pdf", "jpg", "png"], key="bl"
        )
        f_br = st.file_uploader(
            "📂 건물등기 업로드", type=["pdf", "jpg", "png"], key="br"
        )

    st.divider()

    if st.button("🚀 AI 정밀 분석 실행", type="primary", use_container_width=True):
        if not (f_ll or f_lr or f_bl or f_br):
            st.error("최소한 하나의 파일은 업로드해야 합니다!")
            return

        with st.spinner("AI가 서류를 읽고 분석 중입니다... (약 10초 소요)"):
            # 파싱 (파일 객체를 그대로 넘김)
            d_ll = MasterParser.parse(f_ll) if f_ll else None
            d_lr = MasterParser.parse(f_lr) if f_lr else None
            d_bl = MasterParser.parse(f_bl) if f_bl else None
            d_br = MasterParser.parse(f_br) if f_br else None

            # 비교 분석
            analyzer = CrossAnalyzer(d_ll, d_lr, d_bl, d_br)
            results = analyzer.run()

            # 데이터프레임 변환
            data_rows = []
            for r in results:
                data_rows.append(
                    {
                        "대상": r.target,
                        "검증 항목": r.item,
                        "판정": "✅ 통과" if r.is_match else "⚠️ 확인 필요",
                        "대장 내용 (Fact)": r.doc1_val,
                        "등기 내용 (Right)": r.doc2_val,
                        "비고": r.msg,
                    }
                )

            df = pd.DataFrame(data_rows)

            # 결과 화면 출력
            st.success("분석이 완료되었습니다!")
            st.dataframe(df, use_container_width=True)

            # 엑셀 다운로드 버튼
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False)

            st.download_button(
                label="📥 분석 결과 엑셀 다운로드",
                data=output.getvalue(),
                file_name="부동산_AI_분석결과.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

            # (옵션) 디버깅용 추출 텍스트 보기
            with st.expander("🔍 AI가 읽은 원본 텍스트 보기"):
                c1, c2 = st.columns(2)
                if d_ll:
                    c1.text_area("토지대장 내용", d_ll.raw_text[:500], height=150)
                if d_lr:
                    c1.text_area("토지등기 내용", d_lr.raw_text[:500], height=150)
                if d_bl:
                    c2.text_area("건축물대장 내용", d_bl.raw_text[:500], height=150)
                if d_br:
                    c2.text_area("건물등기 내용", d_br.raw_text[:500], height=150)


if __name__ == "__main__":
    main()
