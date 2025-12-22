import streamlit as st
import pandas as pd
import pdfplumber
import io
import re
from dataclasses import dataclass
from typing import List

# ==========================================
# 1. 데이터 구조 (도메인 스키마)
# ==========================================
@dataclass
class RealEstateDocument:
    doc_type: str       # 'registry'(등기) or 'ledger'(대장)
    source_name: str    # 파일명
    raw_text: str       # 원본 텍스트 (디버깅용)
    address: str        # 주소 (대지위치/소재지)
    area: float         # 면적
    owners: List[str]   # 소유자
    main_usage: str     # 주용도 (대장 전용)

@dataclass
class AnalysisResult:
    category: str
    is_match: bool
    registry_val: str
    ledger_val: str
    message: str
    issue_type: str

# ==========================================
# 2. 강력해진 파싱 엔진 (표 인식 기능 추가)
# ==========================================
class RealParser:
    @staticmethod
    def clean_text(text):
        """지저분한 공백 제거 및 키워드 정규화"""
        if not text: return ""
        # 1. 줄바꿈 제거
        text = text.replace("\n", "")
        # 2. '소 재 지' -> '소재지' 처럼 띄어쓰기된 키워드 붙이기
        text = text.replace("소 재 지", "소재지").replace("대 지 위 치", "대지위치").replace("면 적", "면적")
        # 3. 다중 공백 하나로 통일
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def parse_ledger(file) -> RealEstateDocument:
        """건축물대장 전용 파서 (표 인식 사용)"""
        filename = file.name
        full_text = ""
        
        # 추출할 데이터 초기값
        address = "인식 실패"
        area = 0.0
        owners = []
        main_usage = "-"

        with pdfplumber.open(file) as pdf:
            # 1. 전체 텍스트 추출 (백업용)
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"
                
                # 2. **표(Table) 추출 로직** (핵심 업그레이드)
                tables = page.extract_tables()
                
                for table in tables:
                    # table은 [['항목', '값'], ['항목', '값']] 형태의 리스트입니다.
                    for i, row in enumerate(table):
                        # 빈 값이 있을 수 있으므로 None 처리
                        row_clean = [str(cell).replace("\n", "").replace(" ", "") if cell else "" for cell in row]
                        
                        # (1) 대지위치 / 도로명주소 찾기
                        if "대지위치" in row_clean:
                            # '대지위치' 칸의 인덱스를 찾고 그 다음 칸이나 다다음 칸을 읽음
                            try:
                                idx = row_clean.index("대지위치")
                                val = row[idx+1] # 바로 옆 칸
                                if val: address = val.replace("\n", " ").strip()
                            except: pass
                        
                        # (2) 주용도 찾기
                        if "주용도" in row_clean:
                            try:
                                idx = row_clean.index("주용도")
                                val = row[idx+1]
                                if val: main_usage = val.replace("\n", " ").strip()
                            except: pass

                        # (3) 연면적 찾기
                        if "연면적" in row_clean:
                            try:
                                idx = row_clean.index("연면적")
                                val = row[idx+1]
                                # 숫자만 추출 (477 m -> 477.0)
                                nums = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)', str(val))
                                if nums: area = float(nums[0].replace(',', ''))
                            except: pass
                        
                        # (4) 소유자 (성명) 찾기
                        if "성명" in row_clean or "성명또는명칭" in row_clean:
                            # 소유자 정보는 보통 그 아래 행에 나옴. 표 구조상 복잡할 수 있어 단순화
                            pass

            # 소유자 보완 (텍스트 검색)
            # 건축물대장 소유자 현황 표에서 '성명' 아래에 있는 텍스트를 찾기는 표 구조가 가변적이라 어려움
            # 키워드 검색으로 보완
            if "소유자" in full_text:
                found = re.findall(r'소유자\s*([\w가-힣]+)', full_text)
                owners.extend(found)
            
        return RealEstateDocument("ledger", filename, full_text, address, area, owners, main_usage)

    @staticmethod
    def parse_registry(file) -> RealEstateDocument:
        """등기부등본 및 토지이용계획확인서 파서"""
        filename = file.name
        full_text = ""
        address = "인식 실패"
        area = 0.0
        owners = []
        
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text: full_text += text + "\n"
                
                # 표 추출 시도
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        row_str = [str(c).replace("\n","").replace(" ","") if c else "" for c in row]
                        
                        # 토지이용계획확인서 스타일 (소재지, 지번, 지목, 면적)
                        if "소재지" in row_str:
                            try:
                                idx = row_str.index("소재지")
                                # 소재지는 보통 그 다음 칸
                                if idx + 1 < len(row):
                                    val = row[idx+1]
                                    if val: address = val.replace("\n", " ").strip()
                            except: pass
                        
                        if "면적" in row_str or "면적(㎡)" in row_str:
                            try:
                                # 면적이 있는 행에서 숫자 찾기
                                for cell in row:
                                    if cell:
                                        nums = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)\s*$', str(cell).strip())
                                        if nums:
                                            # 너무 작은 숫자(순번 등) 제외
                                            candidate = float(nums[0].replace(',', ''))
                                            if candidate > 10: 
                                                area = candidate
                            except: pass

        # 표에서 못 찾았으면 줄글(Regex)로 재시도 (백업 로직)
        clean_full_text = RealParser.clean_text(full_text)
        
        if address == "인식 실패":
            match = re.search(r'(경기도|서울특별시|[\w]+도)\s+([\w]+시)\s+([\w]+구|[\w]+면|[\w]+읍)', clean_full_text)
            if match:
                address = match.group(0) # 대략적인 시/군/구라도 잡기

        if area == 0.0:
            match = re.search(r'면적\s*(\d+(?:,\d+)*(?:\.\d+)?)', clean_full_text)
            if match:
                area = float(match.group(1).replace(',', ''))

        # 소유자 (등기부 갑구 기준)
        # '소유자' 뒤에 오는 이름 찾기
        raw_owners = re.findall(r'소유자\s+([가-힣]{2,4}|주식회사[\w]+)', full_text)
        owners = list(set(raw_owners))
        if not owners:
            owners = ["(소유자 정보 미상 - 권리부 확인 필요)"]

        return RealEstateDocument("registry", filename, full_text, address, area, owners, "-")

# ==========================================
# 3. 비교 분석 로직
# ==========================================
class RealEstateAnalyzer:
    def __init__(self, registry: RealEstateDocument, ledger: RealEstateDocument):
        self.registry = registry
        self.ledger = ledger

    def compare(self) -> List[AnalysisResult]:
        results = []
        
        # 1. 주소 비교
        addr_reg = self.registry.address.replace(" ", "").replace("경기도", "") # 도/시 떼고 핵심만 비교
        addr_led = self.ledger.address.replace(" ", "").replace("경기도", "")
        
        # 부분 일치 확인
        is_match_addr = (addr_reg in addr_led) or (addr_led in addr_reg)
        if self.registry.address == "인식 실패" or self.ledger.address == "인식 실패":
            is_match_addr = False
            msg_addr = "⚠️ 주소 인식 실패 (파일 확인)"
        else:
            msg_addr = "일치" if is_match_addr else "불일치 확인 필요"
            
        results.append(AnalysisResult("소재지", is_match_addr, self.registry.address, self.ledger.address, msg_addr, "정상" if is_match_addr else "단순오기"))

        # 2. 면적 비교
        # 소수점 차이 무시 (tolerance)
        is_match_area = abs(self.registry.area - self.ledger.area) < 1.0
        msg_area = "일치" if is_match_area else f"오차 {abs(self.registry.area - self.ledger.area):.2f}㎡"
        
        if self.registry.area == 0 or self.ledger.area == 0:
            msg_area = "⚠️ 면적 데이터 추출 실패"
            is_match_area = False

        results.append(AnalysisResult("면적(㎡)", is_match_area, str(self.registry.area), str(self.ledger.area), msg_area, "정상" if is_match_area else "물적불일치"))

        # 3. 소유자 비교
        reg_set = set(self.registry.owners)
        led_set = set(self.ledger.owners)
        # 교집합이 하나라도 있으면 일치로 간주 (간이 로직)
        is_match_owner = not reg_set.isdisjoint(led_set)
        
        results.append(AnalysisResult("소유자", is_match_owner, str(list(reg_set)), str(list(led_set)), "일치 추정" if is_match_owner else "불일치", "정상" if is_match_owner else "권리불일치"))

        return results

# ==========================================
# 4. 웹 UI
# ==========================================
def main():
    st.set_page_config(page_title="부동산 정밀 분석기", layout="wide")
    st.title("🏘️ 부동산 공부 서류 정밀 분석기 (Table Parsing)")
    st.caption("표(Table) 인식 엔진을 탑재하여 건축물대장과 등기부등본을 정밀하게 분석합니다.")

    with st.sidebar:
        st.header("파일 업로드")
        uploaded_registry = st.file_uploader("1. 등기부등본 (또는 토지이용계획)", type=["pdf"])
        uploaded_ledger = st.file_uploader("2. 건축물대장 (필수)", type=["pdf"])
        analyze_btn = st.button("분석 실행", type="primary")

    if analyze_btn and uploaded_registry and uploaded_ledger:
        with st.spinner('표 데이터를 추출하고 있습니다...'):
            # 파싱 실행 (각 문서 타입에 맞는 파서 사용)
            doc_reg = RealParser.parse_registry(uploaded_registry)
            doc_led = RealParser.parse_ledger(uploaded_ledger)
            
            # 비교
            analyzer = RealEstateAnalyzer(doc_reg, doc_led)
            results = analyzer.compare()

            # 결과 화면
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"**📜 등기부/토지이용계획 인식결과**\n- 주소: {doc_reg.address}\n- 면적: {doc_reg.area}")
            with col2:
                st.success(f"**🏢 건축물대장 인식결과**\n- 주소: {doc_led.address}\n- 면적: {doc_led.area}\n- 용도: {doc_led.main_usage}")

            st.markdown("### 📊 교차 검증 리포트")
            
            # 결과 테이블
            data = []
            for res in results:
                data.append({
                    "항목": res.category,
                    "판정": "✅ Pass" if res.is_match else "❌ Check",
                    "등기 문서 값": res.registry_val,
                    "대장 문서 값": res.ledger_val,
                    "비고": res.message
                })
            st.table(pd.DataFrame(data))

            # 디버깅용: 실제 표 데이터 확인
            with st.expander("개발자 모드: 추출된 원본 텍스트 확인"):
                st.text_area("건축물대장 Raw Text", doc_led.raw_text[:1000])
                st.text_area("등기부 Raw Text", doc_reg.raw_text[:1000])

if __name__ == "__main__":
    main()
