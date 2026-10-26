import json

import pytest

from app import ticks


def assignment(name, value):
    return name + "=" + json.dumps(value)


def test_latest_pages_and_amount_units(monkeypatch):
    ticks._cache.clear()
    calls = []

    def fetch(query):
        calls.append(query)
        if query["action"] == "detail":
            return assignment("v_detail_time_sz000001", [20261023, "a|b|c|d"])
        p = query["p"]
        count = 1 if p == 3 else 70
        records = [f"{p * 70 + i}/14:59:00/11.26/0.00/100/112600/B" for i in range(count)]
        return assignment("v_detail_data_sz000001", [p, "|".join(records)])

    monkeypatch.setattr(ticks, "_fetch", fetch)
    data = ticks.get_ticks("000001")
    assert len(data["rows"]) == 100
    assert {q["p"] for q in calls if "p" in q} == {1, 2, 3}
    assert data["trade_date"] == "2026-10-23"
    assert data["rows"][0]["amount"] == 112600
    assert data["rows"][0]["volume"] == 100
    assert data["rows"][0]["dir"] == "bull"
    assert "seq" not in data["rows"][0]
    before = len(calls)
    assert ticks.get_ticks("000001") == data
    assert len(calls) == before
    ticks._cache.clear()


def test_page_direction_and_invalid_numbers():
    records = "1/14:00:00/10/0/20/20000/S|2/14:00:03/10/0/3/3000/M|3/14:00:06/nan/0/3/3000/B"
    rows = ticks._parse_page(assignment("v_detail_data_sh600000", [2, records]), "sh600000", 2)
    assert [r["dir"] for r in rows] == ["bear", "neutral"]
    with pytest.raises(ValueError, match="mismatch"):
        ticks._parse_page(assignment("v_detail_data_sh600000", [0, records]), "sh600000", 2)


def test_no_execution_of_upstream_script():
    with pytest.raises(ValueError):
        ticks._assignment('v_detail_time_sz000001=[20261023,"a"];alert(1)', "v_detail_time_sz000001")


def test_empty_and_unsupported_are_explicit(monkeypatch):
    ticks._cache.clear()
    monkeypatch.setattr(ticks, "_fetch", lambda query: "")
    assert ticks.get_ticks("600000")["rows"] == []
    assert "暂无" in ticks.get_ticks("600000")["note"]
    assert "北交所" in ticks.get_ticks("920002")["note"]
    with pytest.raises(ValueError):
        ticks.get_ticks("not-a-code")
