from app import funds


def test_summary_preserves_missing_and_does_not_double_count_passives():
    item = {"t": "2026-10-23 00:00:00", "zmbtdcje": 200000, "zmbddcje": 100000,
            "zmstdcje": 40000, "zmsddcje": 20000, "bdmbtdcje": 40000, "bdmstdcje": 200000}
    day = funds.normalize_day(item)
    assert day["buy"] == 300000
    assert day["sell"] == 60000
    assert day["net"] == 240000
    assert day["tiers"][2]["net"] is None
    assert day["tiers"][0]["passive_buy"] == 40000
    item["zmbddcje"] = None
    assert funds.normalize_day(item)["buy"] is None
    assert funds.normalize_day(item)["net"] is None


def test_detail_session_filters_units_and_invalid_prices():
    rows = [{"d": "2026-10-23", "t": t, "p": 12, "v": 1000, "ts": 1}
            for t in ["09:15:00", "09:25:00", "09:29:00", "09:30:00", "11:30:00", "12:00:00", "13:00:00", "15:00:00", "15:13:00"]]
    rows += [{"d": "2026-10-22", "t": "14:00:00", "p": 12, "v": 1000},
             {"d": "2026-10-23", "t": "14:00:00", "p": "nan", "v": 1000}]
    valid, excluded = funds.normalize_trades(rows, "2026-10-23")
    assert len(valid) == 5
    assert excluded == 6
    assert valid[0]["time"] == "15:00:00"
    assert valid[0]["amount"] == 12000
    assert valid[0]["volume"] == 10


def test_filter_covers_all_returned_records_before_pagination():
    rows = [{"id": i, "amount": i * 1000000, "side": "buy" if i % 2 else "sell"} for i in range(250)]
    dataset = {"trades": rows, "source": "test"}
    result = funds.select_trades(dataset, minimum=200000000, side="buy", page=2, page_size=10)
    assert result["total"] == 25
    assert result["available_count"] == 250
    assert len(result["rows"]) == 10
    assert all(r["amount"] >= 200000000 and r["side"] == "buy" for r in result["rows"])
    assert result["matched_buy"] == sum(r["amount"] for r in rows if r["amount"] >= 200000000 and r["side"] == "buy")
    assert "trades" not in result
    all_result = funds.select_trades(dataset, minimum=200000000, side="buy", page_size=10, all_rows=True)
    assert len(all_result["rows"]) == all_result["total"] == 25


def test_partial_provider_failure_retains_valid_summary(monkeypatch):
    funds._cache.clear()
    def request(path, licence, params=None):
        if "transaction" in path:
            return [{"t": "2026-10-23", "zmbtdcje": 0, "zmbddcje": 0, "zmstdcje": 0, "zmsddcje": 0}]
        raise RuntimeError("secret credential in upstream error")
    monkeypatch.setattr(funds, "_request", request)
    result = funds.get_dataset("600293", {"user_id": 1, "id": 1, "licence": "UNITTEST-NOT-A-KEY"})
    assert result["summary"]["net"] == 0
    assert result["trades"] == []
    assert result["capabilities"]["l2_order_details"] is False
    assert "secret" not in str(result)
    assert result["warnings"]
    funds._cache.clear()


def test_cache_isolated_by_user_source_and_credential(monkeypatch):
    funds._cache.clear()
    calls = []
    def request(path, licence, params=None):
        calls.append(licence)
        if "transaction" in path:
            return [{"t": "2026-10-23", "zmbtdcje": 1000, "zmbddcje": 0, "zmstdcje": 0, "zmsddcje": 0}]
        return [{"d": "2026-10-23", "t": "15:00:00", "p": 10, "v": 100, "ts": 1}]
    monkeypatch.setattr(funds, "_request", request)
    source = {"user_id": 91, "id": 91, "licence": "TEST-CERT-A"}
    funds.get_dataset("600293", source)
    funds.get_dataset("600293", source)
    assert len(calls) == 2
    funds.get_dataset("600293", {**source, "user_id": 92, "id": 92})
    assert len(calls) == 4
    funds.get_dataset("600293", {**source, "licence": "TEST-CERT-B"})
    assert len(calls) == 6
    funds._cache.clear()
