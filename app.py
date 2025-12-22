import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
from dataclasses import dataclass
from typing import List

# ==========================================
# 1. 데이터 구조 정의
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
# 2. 파싱 엔진 (세로/가로 전방위 탐색 - 성능 유지)
# ==========================================
class RealParser:
    @staticmethod
    def clean_text(text):
        if not text: return ""
        text = re.sub(r'([가-힣])\1', r'\1', text) # 중복 글자 제거
        return text.replace("\n", "").replace(" ", "").strip()

    @staticmethod
    def extract_number(text):
        """텍스트에서 면적 숫자 추출"""
        if not text: return 0.0
        matches = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)', str(text))
        valid_nums = []
        for m in matches:
            val = float(m.replace(',', ''))
            if val > 1.0: valid_nums.append(val)
        return max(valid_nums) if valid_nums else 0.0

    @staticmethod
    def find_value_in_table(tables, keywords):
        """표에서 키워드 주변 값 찾기 (아래, 오른쪽, 두칸 아래)"""
        for table in tables:
            n_rows = len(table)
            for r in range(n_rows):
                for c in range(len(table[r])):
                    cell_text = RealParser.clean_text(str(table[r][c]))
                    if any(k in cell_text for k in keywords):
                        # 1. 바로 아래 (세로형)
                        if r + 1 < n_rows:
                            val = RealParser.extract_number(table[r+1][c])
                            if val > 0: return val
                        # 2. 바로 옆 (가로형)
                        if c + 1 < len(table[r]):
                            val = RealParser.extract_number(table[r][c+1])
                            if val > 0: return val
                        # 3. 두 칸 아래 (단위가 껴있는 경우)
                        if r + 2 < n_rows:
                            val = RealParser.extract_number(table[r+2][c])
                            if val > 0: return val
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
            # 텍스트 추출
            for page in pdf.pages:
                full_text += str(page.extract_text()) + "\n"
            
            # 문서 종류 판단
            if "토지이용" in full_text or "신청토지" in full_text:
                doc_category = "토지이용계획확인서"
                area_keywords = ["면적", "신청토지면적"]
            elif "건축물대장" in full_text or "건물ID" in full_text:
                doc_category = "건축물대장"
                area_keywords = ["연면적", "건축면적"]
            else:
                doc_category = "등기부등본"
                area_keywords = ["면적"]

            # 표 정밀 탐색
            for page in pdf.pages:
                tables = page.extract_tables()
                if area == 0.0:
                    area = RealParser.find_value_in_table(tables, area_keywords)
                
                # 주소 찾기
                if address == "인식 실패":
                    for table in tables:
                        for row in table:
                            row_clean = [RealParser.clean_text(str(x)) for x in row]
                            if "소재지" in row_clean:
                                idx = row_clean.index("소재지")
                                if idx+1 < len(row) and row[idx+1]: 
                                    address = str(row[idx+1]).replace("\n"," ")
                            elif "대지위치" in row_clean:
                                idx = row_clean.index("대지위치")
                                if idx+1 < len(row) and row[idx+1]:
                                    address = str(row[idx+1]).replace("\n"," ")
                                    address = re.sub(r'([가-힣])\1', r'\1', address)

        # 백업: 텍스트에서 면적 찾기
        if area == 0.0:
            matches = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)\s*㎡', full_text)
            nums = [float(m.replace(',', '')) for m in matches if float(m.replace(',', '')) > 1.0]
            if nums: area = max(nums)

        # 소유자 찾기
        if doc_category == "등기부등본":
            owners = list(set(re.findall(r'소유자\s+([가-힣]{2,4})', full_text)))
        elif doc_category == "건축물대장":
            owners = list(set(re.findall(r'성명\s*([가-힣]{3})', full_text)))
        else:
            owners = ["(정보 없음)"]

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
        
        # 1. 소재지
        a1 = self.d1.address.replace("경기도","").replace(" ","")
        a2 = self.d2.address.replace("경기도","").replace(" ","")
        match_addr = (a1 in a2) or (a2 in a1)
        results.append(AnalysisResult("소재지", match_addr, self.d1.address, self.d2.address, "일치" if match_addr else "확인 필요", "주소"))

        # 2. 면적
        diff = abs(self.d1.area - self.d2.area)
        match_area = diff < 3.3
        msg = "일치" if match_area else f"오차 {diff:.1f}㎡"
        if "토지" in self.d1.doc_category and "건축물" in self.d2.doc_category:
            msg += "\n(참고: 토지 vs 건물)"
        results.append(AnalysisResult("면적(㎡)", match_area, str(self.d1.area), str(self.d2.area), msg, "면적"))

        # 3. 소유자
        if "토지이용" in self.d1.doc_category:
             results.append(AnalysisResult("소유자", True, "-", str(self.d2.owners), "비교 제외 (토지이용계획)", "-"))
        else:
            match_owner = not set(self.d1.owners).isdisjoint(set(self.d2.owners))
            results.append(AnalysisResult("소유자", match_owner, str(self.d1.owners), str(self.d2.owners), "일치" if match_owner else "불일치", "권리"))

        return results

# ==========================================
# 4. 웹 UI (엑셀 버튼 복구 완료!)
# ==========================================
def main():
    st.set_page_config(page_title="부동산 정밀 분석기", layout="wide")
    st.title("📑 부동산 공부 서류 정밀 분석기")
    st.markdown("---")

    # 사이드바
    with st.sidebar:
        st.header("📂 파일 업로드")
        f1 = st.file_uploader("1. 등기부/토지이용계획", type=["pdf"])
        f2 = st.file_uploader("2. 건축물대장", type=["pdf"])
        btn = st.button("분석 실행", type="primary")

    if btn and f1 and f2:
        with st.spinner('문서 분석 및 엑셀 생성 중...'):
            d1 = RealParser.parse_universal(f1, "doc1")
            d2 = RealParser.parse_universal(f2, "doc2")
            
            analyzer = RealEstateAnalyzer(d1, d2)
            res = analyzer.compare()

            # 1. 요약 정보 카드
            c1, c2 = st.columns(2)
            c1.success(f"**📄 {d1.doc_category}**\n\n- 주소: {d1.address}\n- 면적: {d1.area}㎡")
            c2.info(f"**📄 {d2.doc_category}**\n\n- 주소: {d2.address}\n- 면적: {d2.area}㎡")

            st.divider()

            # 2. 상세 결과 데이터프레임 생성
            st.subheader("📊 분석 결과 리포트")
            
            data_rows = []
            for r in res:
                data_rows.append({
                    "분석 항목": r.category,
                    "판정": "✅ Pass" if r.is_match else "❌ Check",
                    "문서1 내용": r.registry_val,
                    "문서2 내용": r.ledger_val,
                    "비고 (분석결과)": r.message
                })
            
            df = pd.DataFrame(data_rows)
            st.table(df)

            # 3. 엑셀 다운로드 버튼 (부활!)
            st.subheader("💾 리포트 다운로드")
            
            # 엑셀 파일 메모리 생성
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='분석결과')
            
            st.download_button(
                label="📥 엑셀 파일로 다운로드 (.xlsx)",
                data=output.getvalue(),
                file_name="부동산_분석_결과.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # 4. 디버깅용 텍스트
            with st.expander("🔍 원본 텍스트 확인하기"):
                st.text_area("문서 1 Raw Text", d1.raw_text[:500])
                st.text_area("문서 2 Raw Text", d2.raw_text[:500])

if __name__ == "__main__":
    main()
