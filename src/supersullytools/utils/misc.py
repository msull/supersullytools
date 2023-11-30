from datetime import datetime
from random import choices
from string import ascii_lowercase

import numpy as np
import pandas as pd


def date_id(now=None):
    now = now or datetime.utcnow()
    return now.strftime("%Y%m%d%H%M%S") + "".join(choices(ascii_lowercase, k=6))


def load_data_from_file(file, replace_nan=True) -> pd.DataFrame:
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
        return data.replace({np.NAN: None})
    else:
        return data
