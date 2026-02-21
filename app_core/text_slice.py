import re
from typing import List, Optional, Tuple

def slice_between_occurrences(
    text: str,
    start: str,
    end: Optional[str],
    *,
    start_occurrence: int = 1,
    end_occurrence: int = 1,
    include_start: bool = True,
    include_end: bool = False,
    not_found: str = "",
    ) -> str:
    """
    text에서 start ~ end 구간을 잘라 반환 (occurrence 지원).

    - start_occurrence: start가 여러 번 나오면 몇 번째 start를 기준으로 할지 (1=첫 번째)
    - end_occurrence: start "이후"에 나오는 end 중 몇 번째 end를 기준으로 할지 (1=첫 번째)
    - include_start/include_end: 경계 문자열 포함 여부
    - end가 None이면 start 기준으로 끝까지
    - start를 못 찾으면 not_found 반환
    - end를 못 찾으면 start부터 끝까지 반환(기존 동작 유지)
    """

    if start_occurrence < 1 or end_occurrence < 1:
        raise ValueError("start_occurrence와 end_occurrence는 1 이상의 정수여야 합니다.")

    # 1) start 찾기 (n번째 occurrence)
    s = -1
    pos = 0
    for _ in range(start_occurrence):
        s = text.find(start, pos)
        if s == -1:
            return not_found
        pos = s + len(start)  # 다음 start 탐색은 이 뒤부터

    # start 포함/미포함 적용
    start_idx = s if include_start else s + len(start)

    # 2) end가 None이면 start 기준으로 끝까지
    if end is None:
        return text[start_idx:]

    # 3) end 찾기 (start 뒤에서 n번째 occurrence)
    e = -1
    search_pos = pos  # start 다음 위치부터 탐색
    for _ in range(end_occurrence):
        e = text.find(end, search_pos)
        if e == -1:
            # end가 없으면 start부터 끝까지
            return text[start_idx:]
        search_pos = e + len(end)

    # end 포함/미포함 적용
    end_idx = e + len(end) if include_end else e

    return text[start_idx:end_idx]


# 역주행을 하며 마지막 문자열 미포함, 첫 문자열 포함
def slice_from_last_start_before_end(
    text: str,
    start_marker: str,
    end_marker: str,
    *,
    include_start: bool = True,
    include_end: bool = False,
    use_last_end: bool = True,  # end_marker가 여러 개면 마지막 것을 기준
    not_found: str = "",
    ) -> str:
    """
    end_marker 위치에서 왼쪽으로 역주행하며 가장 가까운 start_marker를 찾아,
    start_marker ~ end_marker 사이를 잘라 반환.

    기본 동작:
    - start_marker 포함 (include_start=True)
    - end_marker 미포함, 직전까지 (include_end=False)
    - end_marker는 마지막 등장(use_last_end=True)을 기준
    """
    # 1) end_marker 위치 찾기
    end_pos = text.rfind(end_marker) if use_last_end else text.find(end_marker)
    if end_pos == -1:
        return not_found

    # 2) end_marker "앞부분"에서 start_marker를 뒤에서 찾기(=역주행 효과)
    start_pos = text.rfind(start_marker, 0, end_pos)
    if start_pos == -1:
        return not_found

    # 3) 포함/미포함 옵션 반영
    s = start_pos if include_start else start_pos + len(start_marker)
    e = end_pos + len(end_marker) if include_end else end_pos

    return text[s:e]


# 역주행을 하며 마지막 문자열 미포함, 첫 문자열 포함 인데, 첫 문자열은 리스트 / 튜플
def slice_from_last_start_before_end_any(
    text: str,
    start_markers: List[str],  # 리스트/튜플 OK
    end_marker: str,
    *,
    include_start: bool = True,
    include_end: bool = False,
    use_last_end: bool = True,
    not_found: str = "",
    ) -> str:
    # 1) end_marker 위치
    end_pos = text.rfind(end_marker) if use_last_end else text.find(end_marker)
    if end_pos == -1:
        return not_found

    # 2) end_marker 앞에서 start 후보들 중 "가장 뒤에 있는 것" 선택
    best_start_pos = -1
    best_start_len = 0

    for sm in start_markers:
        pos = text.rfind(sm, 0, end_pos)
        if pos > best_start_pos:
            best_start_pos = pos
            best_start_len = len(sm)

    if best_start_pos == -1:
        return not_found

    # 3) 포함/미포함 적용
    s = best_start_pos if include_start else best_start_pos + best_start_len
    e = end_pos + len(end_marker) if include_end else end_pos
    return text[s:e]


# 역주행을 하며 마지막 문자열 미포함, 첫 문자열 포함 인데 정규표현식 사용
def slice_from_last_start_before_end_regex(
    text: str,
    start_pat: str,  # regex
    end_lit: str,  # literal
    *,
    include_start: bool = True,
    include_end: bool = False,
    use_last_end: bool = True,
    flags: int = re.S,
    not_found: str = "",
    ) -> str:
    end_pos = text.rfind(end_lit) if use_last_end else text.find(end_lit)
    if end_pos == -1:
        return not_found

    # end_pos 앞쪽에서 start_pat의 "마지막 매치" 찾기
    prefix = text[:end_pos]
    last = None
    for m in re.finditer(start_pat, prefix, flags):
        last = m

    if last is None:
        return not_found

    s = last.start() if include_start else last.end()
    e = end_pos + len(end_lit) if include_end else end_pos
    return text[s:e]


# 역주행을 하며 마지막 문자열 포함, 첫 문자열 미포함
def slice_after_start_to_including_end_reverse(
    text: str,
    start_marker: str,
    end_marker: str,
    *,
    use_last_end: bool = True,
    not_found: str = "",
    ) -> str:
    """
    end_marker(기준)를 잡고, 그 앞에서 가장 가까운 start_marker를 '역주행'으로 찾아,
    start_marker는 제외(미포함)하고 end_marker는 포함하여 반환한다.

    반환 구간:
      (start_marker의 끝)  ~  (end_marker의 끝)

    - use_last_end=True이면 end_marker가 여러 번 나와도 '마지막 end_marker'를 기준으로 함
      False면 첫 번째 end_marker를 기준으로 함
    """
    # 1) end_marker 위치 잡기
    end_pos = text.rfind(end_marker) if use_last_end else text.find(end_marker)
    if end_pos == -1:
        return not_found

    end_end = end_pos + len(end_marker)  # end_marker 포함이므로 끝 위치는 여기

    # 2) end_marker 앞쪽에서 start_marker를 뒤에서부터(가장 가까운 것) 찾기
    start_pos = text.rfind(start_marker, 0, end_pos)
    if start_pos == -1:
        return not_found

    start_end = start_pos + len(start_marker)  # start_marker 미포함이므로 여기서 시작

    # 3) 구간 반환
    return text[start_end:end_end]


# 기준 문자열과 같은 단어들만 추출
def _normalize_token(tok: str) -> str:
    """
    OCR 흔들림을 조금 견디게 토큰 정규화.
    - 양끝 특수문자 제거
    - 공백류 제거는 token 단계에선 필요 없음
    - 하이픈은 유지(496-10 같은 지번에 중요)
    """
    tok = tok.strip()
    # 토큰 양끝의 불필요한 문장부호 제거 (하이픈은 유지해야 하므로 제외)
    tok = re.sub(r"^[\s,.:;(){}\[\]<>\"'`]+|[\s,.:;(){}\[\]<>\"'`]+$", "", tok)
    return tok


def extract_reference_subsequence(
    source: str, reference: str, *, require_exact: bool = True
    ) -> Tuple[bool, str]:
    """
    source에서 reference 토큰들을 '순서대로' 찾아서 뽑아냄.
    - 성공: (True, reference를 정규화해 조합한 문자열)
    - 실패: (False, 실패 이유)
    """
    # 줄바꿈/탭 등 공백 정리
    source_clean = re.sub(r"\s+", " ", source).strip()
    ref_clean = re.sub(r"\s+", " ", reference).strip()

    source_tokens = [
        _normalize_token(t) for t in source_clean.split(" ") if _normalize_token(t)
    ]
    ref_tokens = [
        _normalize_token(t) for t in ref_clean.split(" ") if _normalize_token(t)
    ]

    if not ref_tokens:
        return False, "reference가 비어있음"

    # 투 포인터로 subsequence 매칭
    j = 0
    for tok in source_tokens:
        if tok == ref_tokens[j]:
            j += 1
            if j == len(ref_tokens):
                break

    if j != len(ref_tokens):
        return False, f"reference 토큰을 전부 찾지 못함 (진행 {j}/{len(ref_tokens)})"

    # 성공 시: reference와 '똑같이' 만들고 싶다면 reference 기반으로 반환
    result = " ".join(ref_tokens)

    if require_exact:
        # 완전 동일(정규화 기준) 확인
        if result != " ".join(ref_tokens):
            return False, "정규화 후에도 동일 문자열 구성 실패"
        return True, result

    return True, result


# 기준 문자열과 다른 단어들만 추출
def remove_reference_subsequence(
    source: str, reference: str, *, fail_if_not_found: bool = True
    ) -> Tuple[bool, str]:
    """
    source에서 reference 토큰들을 '순서대로' 매칭해 제거하고,
    남은 토큰들을 공백으로 합쳐 반환.

    - fail_if_not_found=True이면 reference 토큰을 전부 못 찾으면 실패 처리
    - False이면 찾은 것만 제거하고 남은 것 반환
    """
    source_clean = re.sub(r"\s+", " ", source).strip()
    ref_clean = re.sub(r"\s+", " ", reference).strip()

    source_tokens: List[str] = [
        _normalize_token(t) for t in source_clean.split(" ") if _normalize_token(t)
    ]
    ref_tokens: List[str] = [
        _normalize_token(t) for t in ref_clean.split(" ") if _normalize_token(t)
    ]

    if not ref_tokens:
        return False, "reference가 비어있음"

    kept = []
    j = 0  # ref_tokens 포인터

    for tok in source_tokens:
        if j < len(ref_tokens) and tok == ref_tokens[j]:
            # 매칭된 reference 토큰은 제거(keep 안 함)
            j += 1
        else:
            kept.append(tok)

    if fail_if_not_found and j != len(ref_tokens):
        return False, f"reference 토큰을 전부 찾지 못함 (진행 {j}/{len(ref_tokens)})"

    return True, " ".join(kept)


# ==========================================
# 0 - 1. [유틸] PDF 쪼개기 함수
# ==========================================
