"""Shared validation for deterministic comparison and reporting definitions."""

import math
from typing import Any

from .errors import ToolkitError


def finite_number(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_native_metric(metric: dict[str, Any]) -> None:
    """Native whole-run result: explicit result ID, unit and direction; no grouping or averaging."""
    if (
        metric.get("value_field") != "value"
        or not isinstance(metric.get("unit"), str)
        or not metric["unit"].strip()
    ):
        raise ToolkitError("Native score requires value_field 'value' and an explicit unit.")
    if metric.get("semantics") != "native_score":
        raise ToolkitError("Native score metrics declare semantics 'native_score'.")
    if metric.get("direction") not in ("lower", "higher", "neutral"):
        raise ToolkitError("Declare lower, higher or neutral metric direction.")
    match = metric.get("match")
    if (
        not isinstance(match, dict)
        or not isinstance(match.get("resultId"), str)
        or set(match) - {"resultId", "result_group"}
    ):
        raise ToolkitError(
            "Native score identity is match.resultId (for example eux_score or vsi_max)."
        )
    if metric.get("group_by", []) != [] or metric.get("exclude_values"):
        raise ToolkitError("Native whole-run scores take no group_by or excluded values.")


def validate_metrics(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ToolkitError("Configure at least one explicitly defined metric.")
    names: set[str] = set()
    for metric in value:
        if not isinstance(metric, dict):
            raise ToolkitError("Each metric must be an object.")
        name = metric.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ToolkitError("Every metric requires a nonempty name.")
        key = name.strip().casefold()
        if key in names:
            raise ToolkitError(
                "Metric names must be unique, including case and surrounding spaces."
            )
        names.add(key)
        table = metric.get("table")
        if table == "native_scores":
            validate_native_metric(metric)
            continue
        if table not in ("measurements", "session_metrics"):
            raise ToolkitError(
                "Only timer, session observation and native score comparisons are supported."
            )
        expected = "duration" if table == "measurements" else "measurement"
        if (
            metric.get("value_field") != expected
            or not isinstance(metric.get("unit"), str)
            or not metric["unit"].strip()
        ):
            raise ToolkitError("Metric requires its contract value_field and an explicit unit.")
        if metric.get("semantics") == "status":
            raise ToolkitError("Status semantics are categorical; arithmetic comparison refused.")
        if metric.get("semantics") not in ("duration", "resource"):
            raise ToolkitError("Declare duration or resource semantics.")
        if metric.get("direction") not in ("lower", "higher", "neutral"):
            raise ToolkitError("Declare lower, higher or neutral metric direction.")
        match, groups = metric.get("match"), metric.get("group_by", [])
        if (
            not isinstance(match, dict)
            or not match
            or any(
                not isinstance(k, str)
                or not k
                or not (v is None or type(v) in (str, bool) or finite_number(v))
                for k, v in match.items()
            )
        ):
            raise ToolkitError("Metric match must be a nonempty object with scalar values.")
        if (
            not isinstance(groups, list)
            or any(not isinstance(k, str) or not k for k in groups)
            or len(groups) != len(set(groups))
        ):
            raise ToolkitError("group_by must be a list of unique field names.")
        excluded = metric.get("exclude_values", [])
        if not isinstance(excluded, list) or any(not finite_number(v) for v in excluded):
            raise ToolkitError("exclude_values must be a list of finite numbers.")
        identities = (
            ("applicationId", "measurementId") if table == "measurements" else ("displayName",)
        )
        for identity in identities:
            if identity not in match and identity not in groups:
                raise ToolkitError(f"Metric identity requires {identity} in match or group_by.")
        if table == "session_metrics" and not {"instance", "fieldName", "unit"}.issubset(groups):
            raise ToolkitError("Session metrics must group by instance, fieldName and unit.")
    return value
