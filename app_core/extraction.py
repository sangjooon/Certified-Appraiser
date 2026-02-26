import re

from .text_slice import (
    extract_reference_subsequence,
    remove_reference_subsequence,
    slice_after_start_to_including_end_reverse,
    slice_between_occurrences,
    slice_from_last_start_before_end,
    slice_from_last_start_before_end_any,
    slice_from_last_start_before_end_regex,
)


#문서의 카테고리 추출
def extract_pdf_category(text: str) -> str:
    """
    PDF 문서의 카테고리를 추출합니다.
    """
    if (
        ("토지이용계획확인서" in text)
        and ("등기사항전부증명서" in text)
        and ("토지 대장" in text)
        and ("일반건축물대장" in text or "집합건축물대장" in text)
        
    ):

        return "토지이용계획확인서_토지등기_토지대장_건물"
    return "기타"


# ==========================================
# 4 - 0. [핵심] 절대 규칙(Rule)으로 데이터 뽑기위한 함수 할당하는 함수 ⚡
# ==========================================
def extract_data_by_rules(text, pdf_category):
    """
    텍스트 덩어리에서 정규표현식(Regex)을 이용해 핵심 데이터를 추출합니다.
    """
    if pdf_category == "토지이용계획확인서_토지등기_토지대장_건물":
        return extract_land_building_document_data(text)


# ==========================================
# 4 - 1. 토지이용계획확인서_토지등기_토지대장_건물 문서용 데이터 추출 함수
# ==========================================
def extract_land_building_document_data(text):
    """
    토지 및 건물 관련 문서에서 데이터를 추출합니다.
    """
    data = {}

    # --- 규칙 0: 문서 범위 나누기 ---
    # 토지이용계획확인서
    land_use_plan_section = slice_between_occurrences(
        text, "문서확인번호", "등기사항전부증명서",
        include_start=True,
        include_end=False,
    )
    # 등기사항전부증명서 [토지]
    land_registry_section = slice_between_occurrences(
        text, "등기사항전부증명서", "토지 대장",
        include_start=True,
        include_end=False,
    )
    # 주요 등기사항 요약 [토지]
    land_registry_summary_section = slice_between_occurrences(
        text, "주요 등기사항 요약", "토지 대장",
        include_start=True,
        include_end=False,
    )

    # 토지 대장
    land_register_section = slice_between_occurrences(
        text, "토지 대장", "문서확인번호",
        include_start=True,
        include_end=False,
    )

    # === 표제부에서 필요한 정보 추출 ===
    # [토지] 추출
    land_address_in_registry_1 = slice_between_occurrences(
        land_registry_section, "[토지]", "표제부",
        include_start=True,
        include_end=False,
    )
    land_address_in_registry_1 = land_address_in_registry_1.replace("[토지]", "").strip()
    if land_address_in_registry_1:
        data["[토지]"] = land_address_in_registry_1
    else:
        data["[토지]"] = "찾지 못함"

    # 소재지번, 지목, 면적을 추출하기위한 범위 설정
    section_for_header_1 = slice_from_last_start_before_end_regex(
        land_registry_section, r"\n\d\s", "갑 구"
    )

    # 면적 구하기
    m2 = re.search(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*m2", section_for_header_1, re.I)
    land_area_in_registry = (m2.group(1).replace(",", "") + "m2") if m2 else ""

    # 지목 추출
    m = re.search(
        r"([가-힣]+)\s*\d+(?:,\d+)*(?:\.\d+)?\s*m2", section_for_header_1, re.I
    )
    land_category_in_registry = m.group(1) if m else ""

    # 소재 지번 추출
    true_or_false_of_match_1, land_address_in_registry_2 = (
        extract_reference_subsequence(section_for_header_1, land_address_in_registry_1)
    )
    if land_address_in_registry_2:
        data["소재지번(토지)"] = land_address_in_registry_2
    else:
        data["소재지번(토지)"] = "찾지 못함"
    # 토지 & 소재지번 매칭 여부
    if true_or_false_of_match_1 == False:
        data["토지 & 소재지번 매칭 여부"] = "X"
    else:
        data["토지 & 소재지번 매칭 여부"] = "O"

    # 지목 추출
    if land_category_in_registry:
        data["지목(토지)"] = land_category_in_registry
    else:
        data["지목(토지)"] = "찾지 못함"

    # 면적 추출
    if land_area_in_registry:
        data["면적(토지)"] = land_area_in_registry
    else:
        data["면적(토지)"] = "찾지 못함"

    # -------------------------------------
    # 갑 구 (소유권에 관한 사항)
    # -------------------------------------
    land_registry_section_gabgu = slice_between_occurrences(
        land_registry_section, "갑 구", "을 구",
        include_start=True,
        include_end=True
    )

    # 갑구에서 마지막 칸 떼어내기
    land_registry_section_gabgu_last = slice_from_last_start_before_end_regex(
        land_registry_section_gabgu, r"\n\d\s", "을 구"
    )

    # 갑구에서 등기목적 추출
    land_registry_section_gabgu_last_purpose = slice_between_occurrences(
        land_registry_section_gabgu_last, " ", " ",
        include_start=True,
        include_end=False,
    )
    
    # 9글자 넘는 예외 처리 [소유권이전청구권가등기, 공유자전원지분전부이전]
    if land_registry_section_gabgu_last_purpose == "소유권이전청구권가":
        land_registry_section_gabgu_last_purpose = "소유권이전청구권가등기"
        land_registry_section_gabgu_last = land_registry_section_gabgu_last.replace(
            "\n등기 ", "\n"
        )
    if land_registry_section_gabgu_last_purpose == "공유자전원지분전부":
        land_registry_section_gabgu_last_purpose = "공유자전원지분전부이전"
        land_registry_section_gabgu_last = land_registry_section_gabgu_last.replace(
            "\n이전 ", "\n"
        )
     
        
    if land_registry_section_gabgu_last_purpose:
        data["토지_등기_갑구_등기목적"] = land_registry_section_gabgu_last_purpose.strip()
    else:
        data["토지_등기_갑구_등기목적"] = "찾지 못함"
    

    # 갑구에서 접수일자 추출
    land_registry_section_gabgu_last_date_1 = slice_between_occurrences(
        land_registry_section_gabgu_last,
        land_registry_section_gabgu_last_purpose + " ",
        " ",
        include_start=False,
        include_end=False,
    )

    # 접수의 호 추출 하기위한 특수 범위 설정
    section_for_standard_1 = slice_between_occurrences(
        land_registry_section_gabgu_last, land_registry_section_gabgu_last_date_1, "\n",
        include_start=False,
        include_end=False,
    )

    # 접수의 호 추출
    land_registry_section_gabgu_last_date_1_ho = slice_between_occurrences(
        land_registry_section_gabgu_last,
        section_for_standard_1 + "\n",
        " ",
        include_start=False,
        include_end=False,
    )

    # 접수일자 + 호 합치기
    land_registry_section_gabgu_last_jupsu = (
        land_registry_section_gabgu_last_date_1 
        + " " + land_registry_section_gabgu_last_date_1_ho
    )

    if land_registry_section_gabgu_last_jupsu:
        data["토지_등기_갑구_접수"] = land_registry_section_gabgu_last_jupsu.strip()
    else:
        data["토지_등기_갑구_접수"] = "찾지 못함"

    # 갑구에서 등기원인 추출
    land_registry_section_gabgu_last_cause = slice_between_occurrences(
        land_registry_section_gabgu_last, land_registry_section_gabgu_last_date_1 + " ", " ", 
        include_start=False,
        include_end=False,
    )
    

    if land_registry_section_gabgu_last_cause:
        data["토지_등기_갑구_등기원인"] = (
            land_registry_section_gabgu_last_cause + " " + "매매"
        )
    else:
        data["토지_등기_갑구_등기원인"] = "찾지 못함"


    # 갑구에서 권리자 및 기타사항 추출
    land_registry_section_gabgu_last = slice_between_occurrences(
        land_registry_section_gabgu_last, " ", None,
        include_start=False,
        include_end=True,)
        
    
    
    reference = " ".join(
        s.strip() for s in [
            land_registry_section_gabgu_last_purpose,
            land_registry_section_gabgu_last_date_1,
            land_registry_section_gabgu_last_cause,
            land_registry_section_gabgu_last_date_1_ho,
            "매매",
        ]
        if s and s.strip()
    )

    ok, right_holder = remove_reference_subsequence(
        source=land_registry_section_gabgu_last,
        reference=reference,
        fail_if_not_found=False,  # 실무에선 이게 더 안전한 경우가 많음
    )

    data["토지_등기_갑구_권리자및기타사항"] = right_holder.strip() if ok else "찾지 못함"


    # 갑구에서 소유자 찾기
    land_registry_section_gabgu_owner = re.search(
        r"소유자\s*([가-힣]{2,4})\s*\d{6}-\*{7}", land_registry_section_gabgu_last
    )
    if land_registry_section_gabgu_owner:
        data["토지_등기_갑구_최종 소유자"] = land_registry_section_gabgu_owner.group(1)
    else:
        data["토지_등기_갑구_최종 소유자"] = "찾지 못함"

    # 주요 등기사항 요약에서 최종 소유자 찾기
    land_registry_summary_section_owner = slice_between_occurrences(
        land_registry_summary_section, "순위번호", " (소유자)",
        include_start=False,
        include_end=False,
    )
    if land_registry_summary_section_owner:
        data["토지_등기_요약_최종 소유자"] = land_registry_summary_section_owner.strip()
    else:
        data["토지_등기_요약_최종 소유자"] = "찾지 못함"

    # 최종 소유자 일치 여부
    gabgu_owner = (data["토지_등기_갑구_최종 소유자"] or "").strip()
    summary_owner = (land_registry_summary_section_owner or "").strip()

    if summary_owner == gabgu_owner:
        data["토지_등기_최종 소유자 일치 여부"] = "O"
    else:
        data["토지_등기_최종 소유자 일치 여부"] = "X"


    # ==========================================
    #    을 구
    # ==========================================
    if "매매 목록" in land_registry_section:
        land_registry_section_eulgu = slice_between_occurrences(
            land_registry_section, "을 구", "매매 목록",
            include_start=True,
            include_end=False
        )
    elif "주요 등기사항 요약" in land_registry_section:
        land_registry_section_eulgu = slice_between_occurrences(
            land_registry_section, "을 구", "주요 등기사항 요약",
            include_start=True,
            include_end=False
        )
    else:
        land_registry_section_eulgu = slice_between_occurrences(
            land_registry_section, "을 구", None,
            include_start=True,
            include_end=False
        )
    
    # 을 구에 "기록사항 없음" 일 경우
    if "기록사항 없음" in land_registry_section_eulgu:
        data["토지_등기_을구"] = "기록사항 없음"
    else:
        data["토지_등기_을구"] = "기록사항 있음"
        # 을구를 "\n숫자+공백" 기준으로 순차 분할
        # 예: land_registry_section_eulgu_1, land_registry_section_eulgu_2, ...
        top_ranks = [
            m.group(1) for m in re.finditer(r"(?m)^(\d+)\s+", land_registry_section_eulgu)
        ]

        for i, rank in enumerate(top_ranks, start=1):
            next_rank = top_ranks[i] if i < len(top_ranks) else None

            if i == 1:
                start_marker = f"{rank} " if f"{rank} " in land_registry_section_eulgu else f"\n{rank} "
            else:
                start_marker = f"\n{rank} "

            end_marker = f"\n{next_rank} " if next_rank else None

            block = slice_between_occurrences(
                land_registry_section_eulgu,
                start_marker,
                end_marker,
                include_start=True,
                include_end=False,
            )

            # 시작 마커를 "\n숫자 "로 잡은 경우 앞 개행 제거
            block = block.lstrip("\n")
            data[f"land_registry_section_eulgu_{i}"] = block.strip()

        data["토지_등기_을구_분할개수"] = len(top_ranks)
        
        #말소 되거나 혜지된 section을 제거
        counter_1 = 1 #"토지_등기_을구_분할개수"만큼 반복하기위한 변수
        while(counter_1 <= data["토지_등기_을구_분할개수"]):
            current_key = f"land_registry_section_eulgu_{counter_1}"
            current_text = (data.get(current_key) or "").strip()

            # "숫자1 숫자2"로 시작하고 말소/해지 문구가 있으면 숫자2 항목을 비움
            match = re.match(r"^\s*(\d+)\s+(\d+)\b", current_text)
            if match and ("말소" in current_text or "해지" in current_text):
                target_rank = int(match.group(2))
                target_key = f"land_registry_section_eulgu_{target_rank}"
                if target_key in data:
                    data[target_key] = ""

            counter_1 += 1
        
        
    









    return data


# main 함수
