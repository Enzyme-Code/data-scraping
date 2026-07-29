from typing import Any

import pandas as pd


def to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(records)


def to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return df.to_dict(orient="records")
