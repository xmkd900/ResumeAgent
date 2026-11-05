import json
import re
from typing import Any


def extract_json_object(raw: str) -> dict[str, Any]:
    """从模型输出中提取 JSON 对象：兼容 ```json 围栏与前后附带解释。"""
    text = (raw or "").strip()
    if not text:
        raise ValueError("模型返回为空")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise TypeError("模型未返回 JSON 对象")
    return data
