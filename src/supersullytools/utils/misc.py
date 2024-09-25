import re
from datetime import datetime
from random import choices
from string import ascii_lowercase
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pandas import DataFrame
    from pydantic import ValidationError


def camel_to_snake(camel_case):
    snake_case = re.sub(r"(?<!^)(?=[A-Z])", "_", camel_case).lower()
    return snake_case


def date_id(now=None):
    now = now or datetime.utcnow()
    return now.strftime("%Y%m%d%H%M%S") + "".join(choices(ascii_lowercase, k=6))


def load_data_from_file(file, replace_nan=True) -> "DataFrame":
    import numpy as np
    import pandas as pd

    if file.type == "text/csv":
        data = pd.read_csv(file, dtype=str, low_memory=False)
    elif file.type == "text/tab-separated-values":
        data = pd.read_csv(file, dtype=str, low_memory=False, sep="\t")
    elif (
        file.type == "application/vnd.ms-excel"
        or file.type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ):
        data = pd.read_excel(file, dtype=str)
    elif file.type == "application/json":
        data = pd.read_json(file, dtype=str)
    elif file.type == "application/octet-stream":  # Assuming this is a Parquet file for now
        data = pd.read_parquet(file, dtype=str)
    else:
        raise RuntimeError(f"Unknown / unsupported file type {file.type}")

    if replace_nan:
        return data.replace({np.nan: None})
    else:
        return data


def format_validation_error(error: "ValidationError") -> str:
    """Parse Pydantic ValidationError and return a formatted markdown error message."""

    messages = ["## Validation Errors\n"]

    for error_item in error.errors():
        loc = " -> ".join(map(str, error_item["loc"]))  # Join the location to create a readable path
        msg = error_item["msg"]
        param = error_item["type"]
        messages.append(f"- **Location:** `{loc}`\n  **Message:** {msg}\n  **Type:** `{param}`\n")

    return "\n".join(messages)
