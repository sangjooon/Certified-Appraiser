import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
from dataclasses import dataclass
from typing import List, Optional

# ==========================================
# 1. 데이터 구조 (4가지 서류 대응)
# ==========================================
@dataclass
class DocInfo:
    category: str       # '토지대장', '건축물대장', '토지등기', '건물등기'
    filename: str
    address: str
    area: float
    owners: List[str]
    raw_text: str

@dataclass
class CompareResult:
    target: str         # '토지(Land)' 또는 '건물(Building)'
    item: str           # 비교 항목 (소재지, 면적, 소유자)
    is_match: bool
    doc1_val: str       # 대장 값
    doc2_val: str       # 등기 값
    msg: str

# ==========================================
# 2. 통합 파싱 엔진 (AI 분류기 탑재)
# ==========================================
class MasterParser:
    @staticmethod
    def clean(text):
        if not text: return ""
        text = re.sub(r'([가-힣])\1', r'\1', text) # 중복 글자 제거
        return text.replace("\n", "").replace(" ", "").strip()

    @staticmethod
    def extract_number(text):
        """텍스트에서 면적 숫자 추출"""
        if not text: return 0.0
        matches = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)', str(text))
        valid = [float(m.replace(',', '')) for m in matches if float(m.replace(',', '')) > 0.5]
        return max(valid) if valid else 0.0

    @staticmethod
    def find_in_table(tables, keywords):
        """표에서 키워드 주변 값 찾기 (아래/오른쪽)"""
        for table in tables:
            for r in range(len(table)):
                for c in range(len(table[r])):
                    val = MasterParser.clean(str(table[r][c]))
                    if any(k in val for k in keywords):
                        # 1. 아래 확인
                        if r+1 < len(table):
                            num = MasterParser.extract_number(table[r+1][c])
                            if num > 0: return num
                        # 2. 오른쪽 확인
                        if c+1 < len(table[r]):
                            num = MasterParser.extract_number(table[r][c+1])
                            if num > 0: return num
        return 0.0

    @staticmethod
    def parse(file) -> DocInfo:
        filename = file.name
        full_text = ""
        
        # 1. 텍스트 추출 및 문서 종류 자동 식별
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                full_text += str(page.extract_text()) + "\n"
        
        # 문서 종류 판단 로직
        cat = "미식별"
        if "건축물대장" in full_text or "건물ID" in full_text:
            cat = "건축물대장"
            area_keys = ["연면적", "건축면적"]
        elif "토지대장" in full_text or "임야대장" in full_text:
            cat = "토지대장"
            area_keys = ["면적", "토지면적"]
        elif "등기사항전부증명서" in full_text:
            # 등기부는 토지/건물 구분이 필요함
            if "건물의표시" in full_text.replace(" ", "") or "[집합건물]" in full_text:
                cat = "건물등기"
            elif "토지의표시" in full_text.replace(" ", ""):
                cat = "토지등기"
            else:
                cat = "건물등기" # 기본값 (대부분 건물이 많음)
            area_keys = ["면적"]
        else:
            cat = "기타문서"
            area_keys = ["면적"]

        # 2. 데이터 추출 (표 + 텍스트 하이브리드)
        address = "인식실패"
        area = 0.0
        owners = []

        with pdfplumber.open(file) as pdf:
            # 면적 찾기 (표 우선)
            for page in pdf.pages:
                tables = page.extract_tables()
                if area == 0.0:
                    area = MasterParser.find_in_table(tables, area_keys)
                
                # 주소 찾기
                if address == "인식실패":
                    for table in tables:
                        for row in table:
                            r_clean = [MasterParser.clean(str(x)) for x in row]
                            if "소재지" in r_clean or "대지위치" in r_clean:
                                for cell in row:
                                    if cell and ("도" in str(cell) or "시" in str(cell)) and len(str(cell)) > 5:
                                        address = str(cell).replace("\n", " ").strip()
                                        address = re.sub(r'([가-힣])\1', r'\1', address) # 중복보정
                                        break
        
        # 표에서 못 찾았으면 텍스트 검색 (백업)
        if area == 0.0:
            match = re.search(r'(\d+(?:,\d+)*(?:\.\d+)?)\s*㎡', full_text)
            if match: area = float(match.group(1).replace(',', ''))

        # 소유자 추출
        if "등기" in cat:
            owners = list(set(re.findall(r'소유자\s+([가-힣]{2,4}|주식회사\S+)', full_text)))
        elif "건축물" in cat:
            owners = list(set(re.findall(r'성명\s*([가-힣]{3})', full_text)))
        elif "토지" in cat:
             # 토지대장은 '소유자명' 또는 '성명'
            owners = list(set(re.findall(r'([가-힣]{3})\s+\(\d{6}-\d{7}\)', full_text))) # 주민번호 패턴 앞 이름
            if not owners:
                owners = list(set(re.findall(r'성명\s*([가-힣]{3})', full_text)))
        
        if not owners: owners = ["(추출실패/미상)"]

        return DocInfo(cat, filename, address, area, owners, full_text)

# ==========================================
# 3. 비교 분석기 (토지 vs 토지 / 건물 vs 건물)
# ==========================================
class CrossAnalyzer:
    def __init__(self, land_ledger, land_reg, build_ledger, build_reg):
        self.ll = land_ledger # 토지대장
        self.lr = land_reg    # 토지등기
        self.bl = build_ledger # 건축물대장
        self.br = build_reg    # 건물등기

    def compare_pair(self, doc1: DocInfo, doc2: DocInfo, target_name: str) -> List[CompareResult]:
        res = []
        if not doc1 or not doc2:
            return [CompareResult(target_name, "문서누락", False, "-", "-", "비교할 문서가 없습니다")]

        # 1. 주소
        a1 = doc1.address.replace("경기도","").replace(" ","")
        a2 = doc2.address.replace("경기도","").replace(" ","")
        match_addr = (a1 in a2) or (a2 in a1)
        res.append(CompareResult(target_name, "소재지", match_addr, doc1.address, doc2.address, "일치" if match_addr else "확인필요"))

        # 2. 면적
        diff = abs(doc1.area - doc2.area)
        match_area = diff < 3.3
        res.append(CompareResult(target_name, "면적(㎡)", match_area, str(doc1.area), str(doc2.area), "일치" if match_area else f"오차 {diff:.1f}㎡"))

        # 3. 소유자
        s1 = set(doc1.owners)
        s2 = set(doc2.owners)
        match_owner = not s1.isdisjoint(s2) # 교집합이 있으면 Pass
        res.append(CompareResult(target_name, "소유자", match_owner, str(list(s1)), str(list(s2)), "일치" if match_owner else "불일치"))

        return res

    def run(self):
        land_res = self.compare_pair(self.ll, self.lr, "[토지] 대장 vs 등기")
        build_res = self.compare_pair(self.bl, self.br, "[건물] 대장 vs 등기")
        return land_res + build_res

# ==========================================
# 4. 웹 UI (4분할 업로드)
# ==========================================
def main():
    st.set_page_config(page_title="부동산 4대 서류 통합 분석기", layout="wide")
    st.title("🏘️ 부동산 4대 공부 서류 통합 분석기")
    st.markdown("토지대장, 건축물대장, 토지등기, 건물등기를 모두 업로드하여 교차 검증합니다.")
    st.divider()

    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("1. 토지 서류 (땅)")
        f_land_ledger = st.file_uploader("📂 토지대장 업로드", type=["pdf"], key="f1")
        f_land_reg = st.file_uploader("📂 토지등기부 업로드", type=["pdf"], key="f2")

    with col2:
        st.subheader("2. 건물 서류 (집)")
        f_build_ledger = st.file_uploader("📂 건축물대장 업로드", type=["pdf"], key="f3")
        f_build_reg = st.file_uploader("📂 건물등기부 업로드", type=["pdf"], key="f4")

    if st.button("🔍 통합 정밀 분석 실행", type="primary"):
        if not (f_land_ledger and f_land_reg and f_build_ledger and f_build_reg):
            st.warning("⚠️ 정확한 분석을 위해 4개의 파일을 모두 업로드해주세요. (일부만 있으면 있는 것끼리만 분석합니다)")

        with st.spinner("AI가 4개의 문서를 동시에 해독하고 있습니다..."):
            # 파싱
            d_ll = MasterParser.parse(f_land_ledger) if f_land_ledger else None
            d_lr = MasterParser.parse(f_land_reg) if f_land_reg else None
            d_bl = MasterParser.parse(f_build_ledger) if f_build_ledger else None
            d_br = MasterParser.parse(f_build_reg) if f_build_reg else None

            # 분석
            analyzer = CrossAnalyzer(d_ll, d_lr, d_bl, d_br)
            results = analyzer.run()

            # 결과 리포트
            st.subheader("📊 교차 검증 리포트")

            # 데이터프레임 변환
            rows = []
            for r in results:
                rows.append({
                    "분석 대상": r.target,
                    "항목": r.item,
                    "판정": "✅ Pass" if r.is_match else "⚠️ Check",
                    "대장 내용 (Fact)": r.doc1_val,
                    "등기 내용 (Right)": r.doc2_val,
                    "비고": r.msg
                })
            
            df = pd.DataFrame(rows)
            st.table(df)

            # 엑셀 다운로드
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            
            st.download_button("📥 통합 리포트 엑셀 다운로드", output.getvalue(), "부동산_통합분석.xlsx")

            # 상세 텍스트 확인 (디버깅)
            with st.expander("🔍 원본 데이터 추출 현황 보기"):
                c1, c2, c3, c4 = st.columns(4)
                if d_ll: c1.text_area("토지대장", d_ll.raw_text[:300])
                if d_lr: c2.text_area("토지등기", d_lr.raw_text[:300])
                if d_bl: c3.text_area("건축물대장", d_bl.raw_text[:300])
                if d_br: c4.text_area("건물등기", d_br.raw_text[:300])

if __name__ == "__main__":
    main()
