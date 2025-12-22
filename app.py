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
    doc_type: str       # 'registry'(등기) or 'ledger'(대장)
    source_name: str    # 파일명
    raw_text: str       # 추출된 전체 텍스트 (디버깅용)
    address: str        # 주소 (지번)
    area: float         # 면적
    owners: List[str]   # 소유자 리스트

@dataclass
class AnalysisResult:
    category: str
    is_match: bool
    registry_val: str
    ledger_val: str
    message: str
    issue_type: str

# ==========================================
# 2. 진짜 텍스트 추출 및 파싱 엔진 (핵심 업그레이드)
# ==========================================
class RealParser:
    """
    [특허 구현부: OCR 처리부 + 텍스트 분석부]
    PDF에서 텍스트를 추출하고(OCR/Extraction), 정규표현식(Regex)으로 
    의미 있는 데이터(주소, 면적, 소유자)를 구조화합니다.
    """
    
    @staticmethod
    def clean_text(text):
        # 공백 정리 및 불필요한 기호 제거
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def parse_pdf(file, doc_type: str) -> RealEstateDocument:
        filename = file.name
        full_text = ""
        
        # 1. PDF 텍스트 레이어 추출 (인터넷 발급 문서는 대부분 여기서 읽힙니다)
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    full_text += extracted + "\n"
        
        # 텍스트가 안 읽히는 경우 (이미지 스캔본) -> 경고 처리
        if len(full_text) < 50:
            return RealEstateDocument(doc_type, filename, "텍스트 추출 실패", "인식 불가", 0.0, ["인식 불가"])

        # 2. 데이터 구조화 (Regex를 이용한 패턴 매칭)
        # 실제 등기부/대장 서식에 맞춰 패턴을 정교하게 다듬어야 합니다.
        
        # (1) 주소/소재지 찾기
        # 패턴: '경기도', '서울특별시' 등으로 시작하는 주소 패턴 찾기
        address_match = re.search(r'([가-힣]+[시도]\s+[가-힣]+[시군구]\s+[가-힣\d\s-]+(?:리|동|가)[\d\s-]+)', full_text)
        address = address_match.group(1).strip() if address_match else "주소 인식 실패"

        # (2) 면적 찾기
        # 패턴: 숫자 + ㎡ (등기부 '표제부'나 대장 '면적' 란 근처)
        # 단순화를 위해 텍스트에서 '면적' 뒤에 나오는 숫자 혹은 '㎡' 앞 숫자를 찾습니다.
        areas = re.findall(r'(\d+(?:,\d+)*(?:\.\d+)?)\s*㎡', full_text)
        try:
            # 여러 면적 중 가장 큰 값(보통 총면적)을 선택하거나, 첫 번째 유효값을 선택
            # 실제로는 표제부의 '면적' 컬럼 위치를 특정해야 함
            valid_areas = [float(a.replace(',', '')) for a in areas if float(a.replace(',', '')) > 0]
            area = max(valid_areas) if valid_areas else 0.0
        except:
            area = 0.0

        # (3) 소유자 찾기
        # 패턴: '소유자' 라는 단어 뒤에 오는 이름 찾기
        # 등기부: [갑구] -> (소유권에 관한 사항) -> 소유자
        owners = []
        if "소유자" in full_text:
            # '소유자' 키워드 뒤에 나오는 3~4글자 한글 이름 또는 주식회사 패턴 추출
            found_owners = re.findall(r'소유자\s+([가-힣]{2,5}|주식회사[가-힣]+)', full_text)
            owners = list(set(found_owners)) # 중복 제거
        
        if not owners:
            owners = ["소유자 인식 실패"]

        return RealEstateDocument(
            doc_type=doc_type,
            source_name=filename,
            raw_text=full_text,
            address=address,
            area=area,
            owners=owners
        )

# ==========================================
# 3. 비교 분석 로직 (이전과 동일)
# ==========================================
class RealEstateAnalyzer:
    def __init__(self, registry: RealEstateDocument, ledger: RealEstateDocument):
        self.registry = registry
        self.ledger = ledger

    def compare(self) -> List[AnalysisResult]:
        results = []
        
        # 주소 정규화 비교 (공백 제거)
        addr1 = self.registry.address.replace(" ", "")
        addr2 = self.ledger.address.replace(" ", "")
        
        # 주소 유사도 체크 (완전 일치가 아니더라도 포함 관계면 인정 등)
        match_addr = (addr1 in addr2) or (addr2 in addr1)
        
        results.append(AnalysisResult(
            category="소재지(주소)",
            is_match=match_addr,
            registry_val=self.registry.address,
            ledger_val=self.ledger.address,
            message="일치" if match_addr else "주소 불일치 확인",
            issue_type="정상" if match_addr else "단순오기"
        ))

        match_area = self.registry.area == self.ledger.area
        results.append(AnalysisResult(
            category="면적(㎡)",
            is_match=match_area,
            registry_val=str(self.registry.area),
            ledger_val=str(self.ledger.area),
            message="일치" if match_area else "불일치 (대장 기준)",
            issue_type="정상" if match_area else "물적현황불일치"
        ))

        reg_owners = set(self.registry.owners)
        leg_owners = set(self.ledger.owners)
        # 교집합이 있으면 일치로 간주 (공동 소유 등 복잡한 케이스 대비 단순화)
        match_owner = not reg_owners.isdisjoint(leg_owners) or (reg_owners == leg_owners)
        
        results.append(AnalysisResult(
            category="소유자",
            is_match=match_owner,
            registry_val=", ".join(reg_owners),
            ledger_val=", ".join(leg_owners),
            message="일치" if match_owner else "불일치 (등기 기준)",
            issue_type="정상" if match_owner else "권리불일치"
        ))

        return results

# ==========================================
# 4. 웹 UI
# ==========================================
def main():
    st.set_page_config(page_title="Real Estate AI Analysis", layout="wide")
    st.title("🏘️ 부동산 공부 서류 AI 분석기 (Prototyping)")
    st.caption("실제 PDF 파일을 업로드하면 텍스트를 추출하여 비교 분석합니다.")

    with st.sidebar:
        st.header("파일 업로드")
        uploaded_registry = st.file_uploader("등기부등본 (PDF)", type=["pdf"])
        uploaded_ledger = st.file_uploader("건축물/토지 대장 (PDF)", type=["pdf"])
        analyze_btn = st.button("분석 실행")

    if analyze_btn and uploaded_registry and uploaded_ledger:
        with st.spinner('AI가 문서를 읽고 있습니다... (텍스트 추출 및 구조화 중)'):
            # 파싱 실행
            doc_reg = RealParser.parse_pdf(uploaded_registry, "registry")
            doc_led = RealParser.parse_pdf(uploaded_ledger, "ledger")
            
            # 분석 실행
            analyzer = RealEstateAnalyzer(doc_reg, doc_led)
            results = analyzer.compare()

            # 결과 화면
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"📜 등기부등본 인식 결과\n\n주소: {doc_reg.address}\n면적: {doc_reg.area}㎡\n소유자: {doc_reg.owners}")
                with st.expander("등기부 원본 텍스트 보기"):
                    st.text(doc_reg.raw_text[:500] + "...")
            with col2:
                st.success(f"building 대장 인식 결과\n\n주소: {doc_led.address}\n면적: {doc_led.area}㎡\n소유자: {doc_led.owners}")
                with st.expander("대장 원본 텍스트 보기"):
                    st.text(doc_led.raw_text[:500] + "...")

            st.divider()
            st.subheader("🔍 교차 검증 결과 리포트")
            
            # 테이블 데이터 생성
            data = []
            for res in results:
                data.append({
                    "항목": res.category,
                    "판정": "✅ Pass" if res.is_match else "❌ Fail",
                    "등기 데이터": res.registry_val,
                    "대장 데이터": res.ledger_val,
                    "분석 코멘트": res.message
                })
            
            result_df = pd.DataFrame(data)
            st.table(result_df)

            # 엑셀 다운로드
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                result_df.to_excel(writer, index=False)
            
            st.download_button("엑셀 리포트 다운로드", output.getvalue(), "analysis_report.xlsx")

if __name__ == "__main__":
    main()
