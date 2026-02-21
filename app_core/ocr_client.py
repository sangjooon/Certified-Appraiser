import json
import time
import uuid

import requests

def call_naver_ocr(file_bytes, file_ext, api_url, secret_key):
    """네이버 OCR을 호출해서 JSON 결과를 받아옵니다."""
    request_json = {
        "images": [{"format": file_ext, "name": "demo"}],
        "requestId": str(uuid.uuid4()),
        "version": "V2",
        "timestamp": int(round(time.time() * 1000)),
    }

    payload = {"message": json.dumps(request_json)}
    headers = {"X-OCR-SECRET": secret_key}

    content_type = "application/pdf" if file_ext == "pdf" else "image/jpeg"
    files = {"file": (f"upload.{file_ext}", file_bytes, content_type)}

    try:
        r = requests.post(
            api_url, headers=headers, data=payload, files=files, timeout=60
        )

        return {
            "ok": (r.status_code == 200),
            "status_code": r.status_code,
            "text": r.text[:2000],
            "json": (
                r.json()
                if "application/json" in r.headers.get("Content-Type", "")
                else None
            ),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ==========================================
# 2. [전처리] JSON -> 줄글 텍스트 변환
# ==========================================
def json_to_text_lines(ocr_json, line_y_threshold=15):
    """
    OCR 결과(JSON)의 모든 페이지(images)를 순서대로 텍스트로 합칩니다.
    각 페이지는 '위->아래, 좌->우' 정렬 후 줄 단위로 재구성합니다.
    """
    if not ocr_json or "images" not in ocr_json:
        return ""

    pages_text = []

    for page_idx, img in enumerate(ocr_json["images"], start=1):
        fields = img.get("fields", [])
        extracted_data = []

        for field in fields:
            text = field.get("inferText", "")
            verts = field.get("boundingPoly", {}).get("vertices", [])
            if not verts:
                continue
            x = verts[0].get("x", 0)
            y = verts[0].get("y", 0)
            extracted_data.append({"text": text, "x": x, "y": y})

        extracted_data.sort(key=lambda k: k["y"])

        full_text = ""
        if extracted_data:
            current_line = []
            last_y = extracted_data[0]["y"]

            for item in extracted_data:
                if abs(item["y"] - last_y) > line_y_threshold:
                    current_line.sort(key=lambda k: k["x"])
                    full_text += (
                        " ".join([d["text"] for d in current_line]).strip() + "\n"
                    )
                    current_line = []

                current_line.append(item)
                last_y = item["y"]

            if current_line:
                current_line.sort(key=lambda k: k["x"])
                full_text += " ".join([d["text"] for d in current_line]).strip()

        pages_text.append(f"\n===== PAGE {page_idx} =====\n{full_text}".strip())

    return "\n".join(pages_text).strip()


# ==========================================
# 3. [전처리] pdf의 카테고리 추출 함수
# ==========================================
