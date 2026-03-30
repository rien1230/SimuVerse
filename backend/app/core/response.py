"""
Consistent success/error response helpers.
All API endpoints should return through these so the frontend always
gets a predictable shape.
"""
from typing import Any, Optional


def success(data: Any, message: str = "") -> dict:
    response = {"success": True, "data": data}
    if message:
        response["message"] = message
    return response


def error(reason: str, status: Optional[str] = None) -> dict:
    response = {"success": False, "error": reason}
    if status:
        response["status"] = status
    return response