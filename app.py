import streamlit as st
import pandas as pd
import pdfplumber
import io
import re
from dataclasses import dataclass
from typing import List

# ==========================================
# 1. 도메인 스키마 정의
# ==========================================
@dataclass
class RealEstateDocument:
    doc_type: str
    source_name: str
    raw_text: str
    address: str
    area: float
    owners: List[str]

@dataclass
class AnalysisResult:
    category: str
    is_match: bool
    registry_val: str
    ledger_val: str
    message: str
    issue_type: str

# ==========================================
# 2. 강력해진 텍스트 파싱 엔진 (개선됨)
# ==========================================
class RealParser:
    @staticmethod
    def clean_text(text):
        # 1. 줄바꿈을 공백으로 변환하여 문장을 이어붙임 (핵심 개선)
        text = text.replace("\n", " ")
        # 2. 다중 공백을 하나로 줄임
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def parse_pdf(file, doc_type: str) -> RealEstateDocument:
        filename = file.name
        raw_text_pages = []
        
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    raw_text_pages.append(extracted)
        
        full_text_raw = "\n".join(raw_text_pages)      # 줄바꿈 유지 버전 (디버깅용)
        full_text_clean = RealParser.clean_text(full_text_raw) # 한 줄 처리 버전 (검색용)

        if len(full_text_clean) < 50:
            return RealEstateDocument(doc_type, filename, "텍스트 추출 실패", "인식 불가", 0.0, ["인식 불가"])

        # --- [개선된 패턴 매칭] ---
        
        # (1) 주소 찾기 (더 유연하게)
        # 전략: '시/도' 로 시작해서 '리/동/가/로/길' 로 끝나는 긴 문자열을 찾음
        # 예: "경기도 안성시 보개면 신안리 70-9"
        address = "주소 인식 실패"
        
        # 패턴 1: [소재지] 키워드 뒤에 나오는 주소
        match_addr1 = re.search(r'소\s*재\s*지\s*([가-힣\d\s\-\.,]+)', full_text_clean)
        
        # 패턴 2: 일반적인 주소 형식을 문서 앞부분(표제부)에서 강제 추출
        match_addr2 = re.search(r'([가-힣]+(시|도)\s+[가-힣]+(시|군|구)\s+[가-힣\d\s\-\.,]+(리|동|가|로|길)[\d\s\-]*)', full_text_clean)

        if match_addr1:
            address = match_addr1.group(1).strip()
        elif match_addr2:
            address = match_addr2.group(1).strip()
            # 너무 길게 잡히면 자르기 (50자 이내)
            if len(address) > 50: address = address[:50]

        # (2) 면적 찾기 (기존 유지하되, 콤마 처리 강화)
        # 면적은 보통 '면적' 글자 근처에 있거나, 숫자+㎡ 형태임
        area = 0.0
        areas = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)\s*㎡', full_text_clean)
        try:
            valid_areas = [float(a.replace(',', '')) for a in areas if float(a.replace(',', '')) > 0]
            if valid_areas:
                area = max(valid_areas) # 보통 제일 큰 숫자가 전체 면적
        except:
            pass

        # (3) 소유자 찾기 (키워드 확장)
        owners = []
        # 등기부: '권리자 및 기타사항' 칸에 '소유자'가 나옴
        # 대장: '성명' 혹은 '소유자' 칸이 있음
        
        # 패턴 A: '소유자' 뒤에 나오는 이름 (2~4글자)
        found_owners_1 = re.findall(r'소유자\s*([가-힣]{2,4})', full_text_clean)
        
        # 패턴 B: '성명' 뒤에 나오는 이름
        found_owners_2 = re.findall(r'성\s*명\s*([가-힣]{2,4})', full_text_clean)
        
        # 패턴 C: 주식회사 OO (법인 소유)
        found_owners_3 = re.findall(r'(주식회사\s*[가-힣]+)', full_text_clean)

        all_found = found_owners_1 + found_owners_2 + found_owners_3
        owners = list(set(all_found)) # 중복 제거
        
        # 필터링 (이상한 단어 제외)
        owners = [o for o in owners if o not in ["기록사항", "없음", "지분", "변경"]]

        if not owners:
            owners = ["소유자 인식 실패 (수동확인 필요)"]

        return RealEstateDocument(doc_type, filename, full_text_raw, address, area, owners)

# ==========================================
# 3. 비교 분석 로직
# ==========================================
class RealEstateAnalyzer:
    def __init__(self, registry: RealEstateDocument, ledger: RealEstateDocument):
        self.registry = registry
        self.ledger = ledger

    def compare(self) -> List[AnalysisResult]:
        results = []
        
        # 주소 비교 (간단 포함 여부)
        addr_reg = self.registry.address.replace(" ", "")
        addr_led = self.ledger.address.replace(" ", "")
        
        # 둘 중 하나라도 인식이 안됐으면 '판독불가'
        if "실패" in self.registry.address or "실패" in self.ledger.address:
            match_addr = False
            msg_addr = "⚠️ 주소 텍스트 추출 실패 (원본 확인 필요)"
        else:
            match_addr = (addr_reg in addr_led) or (addr_led in addr_reg)
            msg_addr = "일치" if match_addr else "불일치 확인 필요"

        results.append(AnalysisResult("소재지(주소)", match_addr, self.registry.address, self.ledger.address, msg_addr, "정상" if match_addr else "확인필요"))

        # 면적 비교
        match_area = self.registry.area == self.ledger.area
        msg_area = "일치" if match_area else f"차이: {abs(self.registry.area - self.ledger.area)}㎡"
        results.append(AnalysisResult("면적(㎡)", match_area, str(self.registry.area), str(self.ledger.area), msg_area, "정상" if match_area else "물적불일치"))

        # 소유자 비교
        reg_owners = set(self.registry.owners)
        leg_owners = set(self.ledger.owners)
        
        if "실패" in str(reg_owners) or "실패" in str(leg_owners):
            match_owner = False
            msg_owner = "⚠️ 소유자 명칭 추출 실패"
        else:
            match_owner = not reg_owners.isdisjoint(leg_owners) # 교집합이 있으면 OK
            msg_owner = "일치 (추정)" if match_owner else "불일치"

        results.append(AnalysisResult("소유자", match_owner, str(list(reg_owners)), str(list(leg_owners)), msg_owner, "정상" if match_owner else "권리불일치"))

        return results

# ==========================================
# 4. 웹 UI
# ==========================================
def main():
    st.set_page_config(page_title="부동산 공부 분석기", layout="wide")
    st.title("🏘️ 부동산 공부 서류 AI 분석기 (v2.0)")
    st.markdown("---")

    with st.sidebar:
        st.header("📂 서류 업로드")
        uploaded_registry = st.file_uploader("1. 등기부등본 (PDF)", type=["pdf"])
        uploaded_ledger = st.file_uploader("2. 건축물/토지 대장 (PDF)", type=["pdf"])
        analyze_btn = st.button("분석 실행", type="primary")

    if analyze_btn and uploaded_registry and uploaded_ledger:
        with st.spinner('AI가 문서를 해독하고 있습니다...'):
            doc_reg = RealParser.parse_pdf(uploaded_registry, "registry")
            doc_led = RealParser.parse_pdf(uploaded_ledger, "ledger")
            
            analyzer = RealEstateAnalyzer(doc_reg, doc_led)
            results = analyzer.compare()

            # ---------------------------------------------------------
            # [디버깅 영역] 컴퓨터가 읽은 진짜 텍스트를 보여줌 (매우 중요!)
            # ---------------------------------------------------------
            with st.expander("🔍 [개발자 모드] AI가 읽어낸 원본 텍스트 확인하기 (클릭)", expanded=False):
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.markdown("**📜 등기부등본 Raw Text**")
                    st.text_area("등기부 내용", doc_reg.raw_text, height=300)
                with col_d2:
                    st.markdown("**📜 대장 Raw Text**")
                    st.text_area("대장 내용", doc_led.raw_text, height=300)
            
            # 결과 리포트
            st.subheader("📊 교차 검증 결과 리포트")
            
            # 요약 카드
            c1, c2, c3 = st.columns(3)
            c1.metric("주소 일치 여부", "Pass" if results[0].is_match else "Check")
            c2.metric("면적 일치 여부", "Pass" if results[1].is_match else "Check")
            c3.metric("소유자 일치 여부", "Pass" if results[2].is_match else "Check")

            # 상세 테이블
            data = []
            for res in results:
                data.append({
                    "항목": res.category,
                    "상태": "✅" if res.is_match else "❌",
                    "등기부 (권리)": res.registry_val,
                    "대장 (현황)": res.ledger_val,
                    "분석 결과": res.message
                })
            st.table(pd.DataFrame(data))

if __name__ == "__main__":
    main()
