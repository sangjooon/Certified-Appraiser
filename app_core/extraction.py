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
