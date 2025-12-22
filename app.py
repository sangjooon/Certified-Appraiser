import streamlit as st
import pandas as pd
import pdfplumber
import re
from dataclasses import dataclass
from typing import List

# ==========================================
# 1. 데이터 구조 정의
# ==========================================
@dataclass
class RealEstateDocument:
    doc_type: str       # 'registry'(등기/토지이용) or 'ledger'(대장)
    source_name: str    # 파일명
    raw_text: str       # 원본 텍스트 (디버깅용)
    address: str        # 주소
    area: float         # 면적
    owners: List[str]   # 소유자
    doc_category: str   # 상세 문서 종류 (등기부등본, 토지이용계획확인서, 건축물대장 등)

@dataclass
class AnalysisResult:
    category: str
    is_match: bool
    registry_val: str
    ledger_val: str
    message: str
    issue_type: str

# ==========================================
# 2. 전처리 및 파싱 엔진 (중복 글자 해결 + 표 인식)
# ==========================================
class RealParser:
    @staticmethod
    def clean_text(text):
        if not text: return ""
        # 1. '발발급급' -> '발급' (한글 중복 글자 제거 로직)
        # 한글이 연속으로 똑같이 2번 나오면 하나로 줄입니다.
        text = re.sub(r'([가-힣])\1', r'\1', text)
        
        # 2. 줄바꿈 및 불필요한 공백 제거
        text = text.replace("\n", " ").strip()
        text = re.sub(r'\s+', ' ', text)
        return text

    @staticmethod
    def parse_ledger(file) -> RealEstateDocument:
        """건축물대장 파싱 (표 형식 최적화 + 중복 글자 보정)"""
        filename = file.name
        full_text = ""
        
        address = "인식 실패"
        area = 0.0
        owners = []
        doc_cat = "건축물대장"

        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                # 텍스트 추출 (중복 제거 전처리 적용 - 디버깅용)
                extracted = page.extract_text()
                if extracted:
                    full_text += RealParser.clean_text(extracted) + "\n"

                # [표 추출 로직] - 건축물대장은 표(Grid)로 읽어야 정확합니다.
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        # 빈 칸(None) 처리 및 텍스트 정리
                        row_clean = []
                        for cell in row:
                            if cell:
                                # 셀 내부의 중복 글자도 보정 ('발발급급' -> '발급')
                                cleaned_cell = RealParser.clean_text(str(cell))
                                row_clean.append(cleaned_cell.replace(" ", "")) # 검색용은 공백 제거
                            else:
                                row_clean.append("")
                        
                        # (1) 주소 (대지위치) 찾기
                        if "대지위치" in row_clean:
                            try:
                                idx = row_clean.index("대지위치")
                                # 보통 대지위치 바로 다음 칸에 주소가 있음
                                if idx + 1 < len(row) and row[idx+1]:
                                    val = RealParser.clean_text(str(row[idx+1]))
                                    address = val
                            except: pass
                        
                        # (2) 연면적 찾기
                        if "연면적" in row_clean:
                            try:
                                idx = row_clean.index("연면적")
                                if idx + 1 < len(row) and row[idx+1]:
                                    # 숫자만 추출 (ex: 477 m -> 477.0)
                                    nums = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)', str(row[idx+1]))
                                    if nums: area = float(nums[0].replace(',', ''))
                            except: pass

                        # (3) 소유자 (성명) 찾기
                        # 표 안에 '성명'이라는 값이 있으면 그 행이나 다음 행의 값을 가져옴
                        if "성명" in row_clean or "성명(명칭)" in row_clean:
                            # 이 부분은 표 구조가 복잡하여 텍스트 검색으로 보완합니다.
                            pass

            # 소유자 추출 보완 (텍스트 패턴 매칭)
            # 건축물대장 패턴: "성명(명칭) ... 홍길동"
            if "성명" in full_text:
                # 성명 뒤에 나오는 한글 3글자(이름) 추출 시도
                matches = re.findall(r'성명.*?([가-힣]{3})\s', full_text)
                if matches:
                    owners.extend(matches)

        # 소유자 중복 제거 및 기본값
        owners = list(set(owners))
        if not owners: owners = ["(대장상 소유자 미상)"]

        return RealEstateDocument("ledger", filename, full_text, address, area, owners, doc_cat)

    @staticmethod
    def parse_registry_or_plan(file) -> RealEstateDocument:
        """등기부등본 또는 토지이용계획확인서 자동 판별 파싱"""
        filename = file.name
        full_text = ""
        address = "인식 실패"
        area = 0.0
        owners = []
        doc_cat = "문서 종류 미상"

        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    cleaned = RealParser.clean_text(extracted)
                    full_text += cleaned + "\n"

                # 표 추출
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        row_str = [str(c).replace("\n","").replace(" ","") if c else "" for c in row]
                        
                        # [문서 종류 판별] 토지이용계획확인서 키워드 확인
                        if "토지이용계획확인서" in row_str or "신청토지" in row_str:
                            doc_cat = "토지이용계획확인서"
                        
                        # (1) 주소 (소재지)
                        if "소재지" in row_str:
                            try:
                                idx = row_str.index("소재지")
                                if idx + 1 < len(row) and row[idx+1]:
                                    address = RealParser.clean_text(str(row[idx+1]))
                            except: pass
                        
                        # (2) 면적 (면적(㎡) 또는 면적)
                        if "면적(㎡)" in row_str or "면적" in row_str:
                            try:
                                for cell in row:
                                    if cell and re.search(r'\d', str(cell)):
                                        # 숫자 추출
                                        nums = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)', str(cell))
                                        if nums:
                                            val = float(nums[0].replace(',', ''))
                                            # 너무 작은 숫자(순번 등) 제외
                                            if val > 1.0: area = val
                            except: pass

        # 문서 종류 확정 (텍스트 기반 2차 확인)
        if "토지이용계획확인서" in full_text:
            doc_cat = "토지이용계획확인서"
        elif "등기사항전부증명서" in full_text:
            doc_cat = "등기부등본"

        # [소유자 찾기] 
        # 토지이용계획확인서에는 보통 '소유자' 칸이 없고 '신청인'만 있습니다.
        # 따라서 등기부등본인 경우에만 소유자를 찾습니다.
        if doc_cat == "등기부등본":
            found = re.findall(r'소유자\s+([가-힣]{2,4})', full_text)
            owners = list(set(found))
        else:
            owners = ["(토지이용계획서 - 소유자 정보 없음)"]

        return RealEstateDocument("registry", filename, full_text, address, area, owners, doc_cat)

# ==========================================
# 3. 비교 분석기
# ==========================================
class RealEstateAnalyzer:
    def __init__(self, doc1: RealEstateDocument, doc2: RealEstateDocument):
        self.doc1 = doc1 # 등기/토지이용
        self.doc2 = doc2 # 대장

    def compare(self) -> List[AnalysisResult]:
        results = []
        
        # 1. 주소 비교
        # '경기도' 등 행정구역 명칭 제외하고 핵심 주소만 비교 (유연성 확보)
        addr1 = self.doc1.address.replace("경기도", "").replace(" ", "")
        addr2 = self.doc2.address.replace("경기도", "").replace(" ", "")
        
        match_addr = (addr1 in addr2) or (addr2 in addr1)
        if "실패" in self.doc1.address or "실패" in self.doc2.address:
            match_addr = False
            msg_addr = "⚠️ 주소 텍스트 추출 실패"
        else:
            msg_addr = "일치" if match_addr else "불일치 (확인 요망)"

        results.append(AnalysisResult("소재지", match_addr, self.doc1.address, self.doc2.address, msg_addr, "정상" if match_addr else "오기"))

        # 2. 면적 비교
        # 면적 차이 3.3㎡(1평) 미만은 일치로 간주
        diff = abs(self.doc1.area - self.doc2.area)
        match_area = diff < 3.3
        
        # 토지이용계획(토지면적) vs 건축물대장(연면적) 비교 시 불일치가 정상일 수 있음
        msg_area = "일치"
        if not match_area:
            msg_area = f"불일치 ({diff:.1f}㎡ 차이)"
            # 문서 종류에 따른 안내 메시지
            if "토지이용" in self.doc1.doc_category and "건축물" in self.doc2.doc_category:
                 msg_area += "\n(참고: 토지면적 vs 건물연면적 비교임)"

        results.append(AnalysisResult("면적(㎡)", match_area, str(self.doc1.area), str(self.doc2.area), msg_area, "확인필요"))

        # 3. 소유자 비교
        # 토지이용계획확인서인 경우 비교 제외
        if "토지이용" in self.doc1.doc_category:
            results.append(AnalysisResult("소유자", True, "-", str(self.doc2.owners), "비교 대상 아님 (토지이용계획서)", "-"))
        else:
            set1 = set(self.doc1.owners)
            set2 = set(self.doc2.owners)
            match_owner = not set1.isdisjoint(set2)
            results.append(AnalysisResult("소유자", match_owner, str(list(set1)), str(list(set2)), "일치" if match_owner else "불일치", "권리분석"))

        return results

# ==========================================
# 4. 웹 UI
# ==========================================
def main():
    st.set_page_config(page_title="부동산 서류 정밀 분석기", layout="wide")
    st.title("📑 부동산 공부 서류 정밀 분석기 (Final Ver.)")
    st.markdown("""
    **기능 개선 사항:**
    1. `발발급급` 같은 **중복 글자 오류 자동 수정**
    2. **토지이용계획확인서** 자동 인식 및 분석 지원
    3. 표(Table) 인식 엔진 적용으로 정확도 향상
    """)

    with st.sidebar:
        st.header("파일 업로드")
        file_reg = st.file_uploader("1. 등기부등본 또는 토지이용계획확인서", type=["pdf"])
        file_led = st.file_uploader("2. 건축물대장", type=["pdf"])
        run_btn = st.button("분석 실행", type="primary")

    if run_btn and file_reg and file_led:
        with st.spinner('문서를 정밀 분석 중입니다...'):
            # 파싱
            doc1 = RealParser.parse_registry_or_plan(file_reg)
            doc2 = RealParser.parse_ledger(file_led)
            
            # 분석
            analyzer = RealEstateAnalyzer(doc1, doc2)
            results = analyzer.compare()

            # 결과 화면
            c1, c2 = st.columns(2)
            with c1:
                st.info(f"**📂 파일 1 인식결과: [{doc1.doc_category}]**\n- 주소: {doc1.address}\n- 면적: {doc1.area}㎡")
            with c2:
                st.success(f"**📂 파일 2 인식결과: [{doc2.doc_category}]**\n- 주소: {doc2.address}\n- 면적: {doc2.area}㎡")

            st.divider()
            st.subheader("📊 분석 결과 리포트")
            
            data = []
            for r in results:
                data.append({
                    "항목": r.category,
                    "판정": "✅ Pass" if r.is_match else "⚠️ Check",
                    "파일 1 값": r.registry_val,
                    "파일 2 값": r.ledger_val,
                    "상세 내용": r.message
                })
            st.table(pd.DataFrame(data))

            # 디버깅용 텍스트 확인 (중복 제거된 텍스트 확인)
            with st.expander("🔍 AI가 읽은 보정된 텍스트 확인 (중복 글자 제거됨)"):
                st.text_area(f"{doc1.doc_category} Raw Text", doc1.raw_text[:1000], height=200)
                st.text_area(f"{doc2.doc_category} Raw Text", doc2.raw_text[:1000], height=200)

if __name__ == "__main__":
    main()
