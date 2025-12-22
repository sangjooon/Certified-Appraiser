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
    raw_text: str       # 원본 텍스트
    address: str        # 주소
    area: float         # 면적
    owners: List[str]   # 소유자
    doc_category: str   # 문서 구분

@dataclass
class AnalysisResult:
    category: str
    is_match: bool
    registry_val: str
    ledger_val: str
    message: str
    issue_type: str

# ==========================================
# 2. 하이브리드 파싱 엔진 (표 검색 + 텍스트 검색)
# ==========================================
class RealParser:
    @staticmethod
    def clean_text(text):
        if not text: return ""
        # 중복 글자 제거 (발발급급 -> 발급)
        text = re.sub(r'([가-힣])\1', r'\1', text)
        # 줄바꿈 제거
        text = text.replace("\n", " ").strip()
        return re.sub(r'\s+', ' ', text)

    @staticmethod
    def extract_number(text):
        """문자열에서 콤마가 포함된 실수 추출"""
        if not text: return 0.0
        # 숫자 패턴 (1,234.56)
        matches = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)', str(text))
        if matches:
            # 가장 긴 숫자가 면적일 확률이 높음 (날짜 등 제외 위해)
            # 혹은 1.0 이상인 숫자 중 첫번째
            for num in matches:
                val = float(num.replace(',', ''))
                if val > 1.0: # 0이나 1 같은 순번 제외
                    return val
        return 0.0

    @staticmethod
    def parse_ledger(file) -> RealEstateDocument:
        """건축물대장 파싱"""
        filename = file.name
        full_text = ""
        address = "인식 실패"
        area = 0.0
        owners = []
        doc_cat = "건축물대장"

        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    full_text += RealParser.clean_text(extracted) + "\n"

                # 1. 표(Table) 기반 정밀 탐색
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        row_clean = [str(cell).replace("\n", "").replace(" ", "") if cell else "" for cell in row]
                        
                        # 대지위치
                        if "대지위치" in row_clean:
                            try:
                                idx = row_clean.index("대지위치")
                                if idx + 1 < len(row) and row[idx+1]:
                                    address = RealParser.clean_text(str(row[idx+1]))
                            except: pass
                        
                        # 연면적 (표 안에 있을 때)
                        if "연면적" in row_clean:
                            try:
                                idx = row_clean.index("연면적")
                                if idx + 1 < len(row):
                                    val = RealParser.extract_number(row[idx+1])
                                    if val > 0: area = val
                            except: pass

            # 2. 텍스트 기반 백업 탐색 (표에서 못 찾았을 경우)
            if area == 0.0:
                # '연면적' 글자 뒤에 나오는 숫자 찾기
                match = re.search(r'연면적\s*(\d+(?:,\d+)*(?:\.\d+)?)', full_text)
                if match:
                    area = float(match.group(1).replace(',', ''))

            # 소유자 (성명)
            matches = re.findall(r'성명.*?([가-힣]{3})\s', full_text)
            if matches: owners.extend(matches)

        owners = list(set(owners))
        if not owners: owners = ["(대장 소유자 미상)"]

        return RealEstateDocument("ledger", filename, full_text, address, area, owners, doc_cat)

    @staticmethod
    def parse_registry_or_plan(file) -> RealEstateDocument:
        """등기부/토지이용계획 파싱 (여기가 문제였음 - 강력 보완)"""
        filename = file.name
        full_text = ""
        address = "인식 실패"
        area = 0.0
        owners = []
        doc_cat = "문서 종류 미상"

        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text: full_text += RealParser.clean_text(text) + "\n"

                # 1. 표 탐색 (Vertical 구조 대응 추가)
                tables = page.extract_tables()
                for t_idx, table in enumerate(tables):
                    for r_idx, row in enumerate(table):
                        row_str = [str(c).replace("\n","").replace(" ","") if c else "" for c in row]
                        
                        # (1) 문서 종류 식별
                        if "토지이용계획확인서" in row_str or "신청토지" in row_str:
                            doc_cat = "토지이용계획확인서"
                        
                        # (2) 주소
                        if "소재지" in row_str:
                            try:
                                idx = row_str.index("소재지")
                                # Case A: 소재지 바로 옆칸 (가로 배치)
                                if idx + 1 < len(row) and row[idx+1]:
                                    val = str(row[idx+1])
                                    if len(val) > 5: address = RealParser.clean_text(val)
                                # Case B: 소재지 바로 아랫칸 (세로 배치 - 토지이용계획서 스타일)
                                elif r_idx + 1 < len(table):
                                    val = str(table[r_idx+1][idx])
                                    if len(val) > 5: address = RealParser.clean_text(val)
                            except: pass
                        
                        # (3) 면적 (여기가 핵심 수정)
                        if "면적" in row_str or "면적(㎡)" in row_str:
                            try:
                                # Case A: 가로 배치 (바로 옆)
                                for cell in row:
                                    val = RealParser.extract_number(cell)
                                    if val > 1.0: area = val; break
                                
                                # Case B: 세로 배치 (바로 아래 행) - 토지이용계획서 스타일
                                if area == 0.0 and r_idx + 1 < len(table):
                                    # 현재 행에서 '면적'이 몇 번째 칸인지 찾음
                                    col_indices = [i for i, x in enumerate(row_str) if "면적" in x]
                                    for col_idx in col_indices:
                                        val = RealParser.extract_number(table[r_idx+1][col_idx])
                                        if val > 1.0: area = val; break
                            except: pass

        # 2. 텍스트 기반 강력 백업 (표에서 실패시 무조건 찾음)
        # 이 부분이 예전에 잘 되던 그 로직입니다.
        if area == 0.0:
            # 패턴 1: 면적(㎡) 1,540.0
            match = re.search(r'면적.*?(\d+(?:,\d+)*(?:\.\d+)?)', full_text)
            if match:
                area = float(match.group(1).replace(',', ''))
            else:
                # 패턴 2: 숫자 + ㎡ (1540.0㎡)
                match = re.search(r'(\d+(?:,\d+)*(?:\.\d+)?)\s*㎡', full_text)
                if match:
                    area = float(match.group(1).replace(',', ''))

        # 문서 종류 재확인
        if "토지이용계획확인서" in full_text: doc_cat = "토지이용계획확인서"
        elif "등기사항전부증명서" in full_text: doc_cat = "등기부등본"

        # 소유자 찾기
        if doc_cat == "등기부등본":
            found = re.findall(r'소유자\s+([가-힣]{2,4})', full_text)
            owners = list(set(found))
        else:
            owners = ["(토지이용계획서 - 소유자 정보 없음)"]

        return RealEstateDocument("registry", filename, full_text, address, area, owners, doc_cat)

# ==========================================
# 3. 분석기 (이전과 동일)
# ==========================================
class RealEstateAnalyzer:
    def __init__(self, doc1, doc2):
        self.doc1 = doc1
        self.doc2 = doc2

    def compare(self) -> List[AnalysisResult]:
        results = []
        
        # 주소
        addr1 = self.doc1.address.replace("경기도", "").replace(" ", "")
        addr2 = self.doc2.address.replace("경기도", "").replace(" ", "")
        match_addr = (addr1 in addr2) or (addr2 in addr1)
        results.append(AnalysisResult("소재지", match_addr, self.doc1.address, self.doc2.address, "일치" if match_addr else "확인 필요", "주소분석"))

        # 면적
        diff = abs(self.doc1.area - self.doc2.area)
        match_area = diff < 3.3
        msg_area = "일치" if match_area else f"오차 {diff:.1f}㎡"
        if "토지이용" in self.doc1.doc_category and "건축물" in self.doc2.doc_category:
            msg_area += " (토지 vs 건물)"
        
        results.append(AnalysisResult("면적(㎡)", match_area, str(self.doc1.area), str(self.doc2.area), msg_area, "물적분석"))

        # 소유자
        if "토지이용" in self.doc1.doc_category:
             results.append(AnalysisResult("소유자", True, "-", str(self.doc2.owners), "비교 대상 아님", "-"))
        else:
            match_owner = not set(self.doc1.owners).isdisjoint(set(self.doc2.owners))
            results.append(AnalysisResult("소유자", match_owner, str(self.doc1.owners), str(self.doc2.owners), "일치" if match_owner else "불일치", "권리분석"))

        return results

# ==========================================
# 4. 메인 UI
# ==========================================
def main():
    st.set_page_config(page_title="부동산 정밀 분석기", layout="wide")
    st.title("📑 부동산 공부 서류 정밀 분석기 (Fix Ver.)")

    with st.sidebar:
        st.header("파일 업로드")
        f1 = st.file_uploader("1. 등기부/토지이용계획", type=["pdf"])
        f2 = st.file_uploader("2. 건축물대장", type=["pdf"])
        btn = st.button("분석 실행", type="primary")

    if btn and f1 and f2:
        with st.spinner('문서를 샅샅이 뒤지고 있습니다...'):
            d1 = RealParser.parse_registry_or_plan(f1)
            d2 = RealParser.parse_ledger(f2)
            
            analyzer = RealEstateAnalyzer(d1, d2)
            res = analyzer.compare()

            # 결과 UI
            c1, c2 = st.columns(2)
            c1.info(f"**[{d1.doc_category}]**\n- 주소: {d1.address}\n- 면적: {d1.area}㎡")
            c2.success(f"**[{d2.doc_category}]**\n- 주소: {d2.address}\n- 면적: {d2.area}㎡")
            
            # 리포트 테이블
            rows = []
            for r in res:
                rows.append({"항목": r.category, "결과": "✅ Pass" if r.is_match else "⚠️ Check", "문서1": r.registry_val, "문서2": r.ledger_val, "비고": r.message})
            st.table(pd.DataFrame(rows))

            with st.expander("텍스트 원본 확인"):
                st.text_area("Doc1", d1.raw_text[:500])
                st.text_area("Doc2", d2.raw_text[:500])

if __name__ == "__main__":
    main()
