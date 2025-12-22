import streamlit as st
import pandas as pd
import pdfplumber
import re
from dataclasses import dataclass
from typing import List

# ==========================================
# 1. 데이터 구조
# ==========================================
@dataclass
class RealEstateDocument:
    doc_type: str
    source_name: str
    raw_text: str
    address: str
    area: float
    owners: List[str]
    doc_category: str

@dataclass
class AnalysisResult:
    category: str
    is_match: bool
    registry_val: str
    ledger_val: str
    message: str
    issue_type: str

# ==========================================
# 2. 파싱 엔진 (세로/가로 전방위 탐색)
# ==========================================
class RealParser:
    @staticmethod
    def clean_text(text):
        if not text: return ""
        text = re.sub(r'([가-힣])\1', r'\1', text) # 중복 글자 제거
        return text.replace("\n", "").replace(" ", "").strip() # 공백 싹 제거 (키워드 매칭용)

    @staticmethod
    def extract_number(text):
        """텍스트에서 가장 그럴듯한 면적 숫자 추출"""
        if not text: return 0.0
        # 1,540.0 또는 477 같은 패턴 찾기
        matches = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)', str(text))
        valid_nums = []
        for m in matches:
            val = float(m.replace(',', ''))
            if val > 1.0: valid_nums.append(val) # 0이나 1 같은 순번 제외
        
        return max(valid_nums) if valid_nums else 0.0

    @staticmethod
    def find_value_in_table(tables, keywords):
        """표에서 키워드를 찾고, [오른쪽] 또는 [아래]에 있는 값을 찾아냄"""
        found_val = 0.0
        
        for table in tables:
            # 테이블을 DataFrame처럼 생각해서 순회
            n_rows = len(table)
            n_cols = len(table[0]) if n_rows > 0 else 0
            
            for r in range(n_rows):
                for c in range(len(table[r])):
                    cell_text = RealParser.clean_text(str(table[r][c]))
                    
                    # 키워드 매칭 (예: "면적", "연면적")
                    if any(k in cell_text for k in keywords):
                        # 전략 1: 바로 아래 칸 확인 (토지이용계획, 건축물대장 세로형)
                        if r + 1 < n_rows:
                            val_below = RealParser.extract_number(table[r+1][c])
                            if val_below > 0: return val_below
                        
                        # 전략 2: 바로 옆 칸 확인 (가로형)
                        if c + 1 < len(table[r]):
                            val_right = RealParser.extract_number(table[r][c+1])
                            if val_right > 0: return val_right
                        
                        # 전략 3: 두 칸 아래 확인 (중간에 단위가 끼어있는 경우)
                        if r + 2 < n_rows:
                            val_below_2 = RealParser.extract_number(table[r+2][c])
                            if val_below_2 > 0: return val_below_2

        return 0.0

    @staticmethod
    def parse_universal(file, doc_hint) -> RealEstateDocument:
        filename = file.name
        full_text = ""
        address = "인식 실패"
        area = 0.0
        owners = []
        doc_category = "미식별"

        with pdfplumber.open(file) as pdf:
            # 1. 텍스트 추출 (Regex 백업용)
            for page in pdf.pages:
                full_text += str(page.extract_text()) + "\n"
            
            # 2. 문서 종류 판단
            if "토지이용" in full_text or "신청토지" in full_text:
                doc_category = "토지이용계획확인서"
                area_keywords = ["면적", "신청토지면적"]
            elif "건축물대장" in full_text or "건물ID" in full_text:
                doc_category = "건축물대장"
                area_keywords = ["연면적", "건축면적"] # 건축물대장은 연면적이 핵심
            else:
                doc_category = "등기부등본"
                area_keywords = ["면적"]

            # 3. 표(Table) 정밀 탐색 실행
            for page in pdf.pages:
                tables = page.extract_tables()
                
                # 면적 찾기
                if area == 0.0:
                    area = RealParser.find_value_in_table(tables, area_keywords)
                
                # 주소 찾기 (표 순회)
                if address == "인식 실패":
                    for table in tables:
                        for row in table:
                            row_clean = [RealParser.clean_text(str(x)) for x in row]
                            # 소재지, 대지위치 찾기
                            if "소재지" in row_clean:
                                idx = row_clean.index("소재지")
                                # 옆 칸 확인
                                if idx+1 < len(row) and row[idx+1]: 
                                    address = str(row[idx+1]).replace("\n"," ")
                            elif "대지위치" in row_clean:
                                idx = row_clean.index("대지위치")
                                if idx+1 < len(row) and row[idx+1]:
                                    address = str(row[idx+1]).replace("\n"," ")
                                    # 중복 글자 제거 (발발급급 이슈)
                                    address = re.sub(r'([가-힣])\1', r'\1', address)

        # 4. [최후의 수단] 표에서 0.0 나오면 텍스트에서 '㎡' 붙은 숫자 중 제일 큰 거 가져옴
        if area == 0.0:
            # "숫자 + ㎡" 패턴 모두 찾기
            matches = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)\s*㎡', full_text)
            nums = []
            for m in matches:
                val = float(m.replace(',', ''))
                if val > 1.0: nums.append(val)
            if nums:
                area = max(nums) # 보통 제일 큰 게 전체 면적임

        # 5. 소유자 (등기부만)
        if doc_category == "등기부등본":
            owners = list(set(re.findall(r'소유자\s+([가-힣]{2,4})', full_text)))
        elif doc_category == "건축물대장":
            # 건축물대장 소유자 (성명)
            owners = list(set(re.findall(r'성명\s*([가-힣]{3})', full_text)))

        return RealEstateDocument(doc_hint, filename, full_text, address, area, owners, doc_category)

# ==========================================
# 3. 비교 로직
# ==========================================
class RealEstateAnalyzer:
    def __init__(self, d1, d2):
        self.d1 = d1
        self.d2 = d2

    def compare(self) -> List[AnalysisResult]:
        results = []
        
        # 주소
        a1 = self.d1.address.replace("경기도","").replace(" ","")
        a2 = self.d2.address.replace("경기도","").replace(" ","")
        match_addr = (a1 in a2) or (a2 in a1)
        results.append(AnalysisResult("주소", match_addr, self.d1.address, self.d2.address, "일치" if match_addr else "확인 필요", "주소"))

        # 면적
        diff = abs(self.d1.area - self.d2.area)
        # 토지(1540) vs 건물(477)이면 당연히 다름 -> 경고 메시지만 다르게
        match_area = diff < 3.3
        msg = "일치" if match_area else f"불일치 ({diff:.1f}㎡ 차이)"
        if "토지" in self.d1.doc_category and "건축물" in self.d2.doc_category:
            msg += "\n(토지면적 vs 연면적 비교됨)"
        
        results.append(AnalysisResult("면적(㎡)", match_area, str(self.d1.area), str(self.d2.area), msg, "면적"))

        return results

# ==========================================
# 4. 실행
# ==========================================
def main():
    st.set_page_config(page_title="부동산 분석기 Fix", layout="wide")
    st.title("📑 부동산 서류 분석기 (면적 인식 강화판)")
    
    with st.sidebar:
        f1 = st.file_uploader("1. 등기부/토지이용계획", type=["pdf"])
        f2 = st.file_uploader("2. 건축물대장", type=["pdf"])
        btn = st.button("분석 실행", type="primary")

    if btn and f1 and f2:
        d1 = RealParser.parse_universal(f1, "doc1")
        d2 = RealParser.parse_universal(f2, "doc2")
        
        res = RealEstateAnalyzer(d1, d2).compare()

        c1, c2 = st.columns(2)
        c1.success(f"**{d1.doc_category}**\n\n주소: {d1.address}\n면적: {d1.area}㎡")
        c2.info(f"**{d2.doc_category}**\n\n주소: {d2.address}\n면적: {d2.area}㎡")

        st.table(pd.DataFrame([
            {"항목":r.category, "결과":"✅" if r.is_match else "⚠️", "문서1":r.registry_val, "문서2":r.ledger_val, "내용":r.message}
            for r in res
        ]))

if __name__ == "__main__":
    main()
