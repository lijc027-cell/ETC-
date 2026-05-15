# ETF Semantic Query Spec v3.4

v3.4 only adds time-series display capability for three narrow cases:

- `nav_trend`: unit NAV trend queries.
- `scale_share_trend`: fund scale and fund share trend queries.
- `trading_metric`: existing trading metric intent gains amount-series support only for `ths_amt_fund`.

v3.4 does not add purchase status, does not add a separate `trading_amount` intent, does not require a new `timeseries_point` type, does not change the existing `trading_metric` `output_style`, does not compute local derived metrics, and does not expose fields from the newer dictionary unless those fields are already imported and registered.

## Capability Scope

### Intent Registration

`nav_trend` and `scale_share_trend` are v3.3-pipeline intents. They must be registered in exactly these three places:

- `SUPPORTED_INTENTS`, so embedding or lexical intent matching does not discard them.
- `_INTENT_DESCRIPTIONS`, so semantic matching has descriptions for them.
- `capability_registry`, so LLM AST generation, validation, and compilation have field constraints.

They do not need to be added to `ALLOWED_QUERY_INTENTS`, which belongs to the older `validate_v3_ast` path and is not the v3.3 strict path for new capabilities.

### Capability Definitions

`nav_trend`:

- `query_mode`: `single`
- `output_style`: `timeseries_series`
- fields: `ths_unit_nv_fund`

`scale_share_trend`:

- `query_mode`: `single`
- `output_style`: `timeseries_series`
- fields: `ths_fund_scale_fund`, `ths_fund_shares_fund`

`trading_metric`:

- keep `output_style = "trading_metric"`
- keep existing latest support for `ths_amt_fund`, `ths_netcashflow_fund`, `ths_margin_trading_balance_fund`, and `ths_short_selling_amtb_fund`
- allow `series` mode only for `ths_amt_fund`
- do not automatically open trend queries for any other trading metric field

## AST Contract

Trend queries use `timeseries_semantics.by_field` with `mode = "series"`.

Default one-year series:

```json
{
  "mode": "series",
  "period": "1y"
}
```

Business-day count window:

```json
{
  "mode": "series",
  "period": "business_days",
  "count": 5
}
```

When generation context detects a trend query, it must write the expected field semantics into `expected_timeseries_modes`:

```json
{
  "expected_timeseries_modes": {
    "ths_unit_nv_fund": {
      "mode": "series",
      "period": "1y"
    }
  }
}
```

Validator requirements:

- add `series` to allowed `timeseries_semantics` modes
- if `expected_timeseries_modes` requires a field to use `series`, the LLM draft cannot omit that field from `timeseries_semantics.by_field`
- valid calendar-window periods: `1m`, `3m`, `6m`, `1y`, `3y`, `5y`, `std`
- valid business-day window: `period = "business_days"` with positive integer `count`
- `period_window_too_large` is valid only when `period = "business_days"` and `count > 250`
- existing modes remain unchanged: `latest`, `latest_two`, `specified`

Timeseries row processing requirements:

- `_apply_timeseries_semantics_to_row` must add a `series` branch that preserves the full array, truncates by `period` / `count`, sorts by `btime` ascending, and does not reduce to a single point

## Field Selection

`nav_trend` always selects and answers only:

- `ths_unit_nv_fund`

`scale_share_trend` selects only the user-requested metric:

- ask for scale: select / answer / project `ths_fund_scale_fund`
- ask for shares: select / answer / project `ths_fund_shares_fund`
- explicitly ask for both scale and shares: select / answer / project both fields

`trading_metric` series selects only:

- `ths_amt_fund`

Other `trading_metric` fields remain latest-only in v3.4.

## Output Contract

Trend output is a structured series block:

```json
{
  "series": [
    {
      "field": "ths_unit_nv_fund",
      "label": "单位净值",
      "format": "plain",
      "period": "1y",
      "points": [
        {"btime": "2026-05-11", "value": 8.9215}
      ]
    }
  ]
}
```

Formatter requirements:

- add a `timeseries_series` branch for `nav_trend` and `scale_share_trend`
- add a `trading_metric` branch to the formatter; inside it, detect `timeseries_semantics.mode = "series"` and output the same `series[]` shape; for latest, keep existing single-point formatting
- sort `series.points` by `btime` ascending
- display null values as `暂无数据`

## Time and Missing Data

Default period is `1y`.

Period phrase mapping:

- `成立以来`, `全部历史`, `成立至今`: `period = "std"`
- `近 N 日`, `近 N 个交易日`, `近 N 个业务日` plus a trend phrase: `period = "business_days"`, `count = N`
- `1m`, `3m`, `6m`, `1y`, `3y`, `5y`: truncate by `btime` date window

Window limits:

- return `UnsupportedQuery(period_window_too_large)` only when `period = "business_days"` and `count > 250`
- do not apply the 250-point limit to `1m`, `3m`, `6m`, `1y`, `3y`, `5y`, or `std`; these windows remain valid even if the returned series has more than 250 points
- example: `近99999个交易日净值走势` returns `UnsupportedQuery(period_window_too_large)`
- example: `成立以来净值走势` is allowed as `nav_trend` with `period = "std"`

The system must not generate a trading calendar and must not fill missing dates.

Missing data rules:

- for `latest`, if no point has `value != null`, return `data_not_available`
- for `series`, return a series if at least one point has parseable `btime`, even if every value is null
- for `series`, return `data_not_available` only when no point has parseable `btime`

## Routing Rules

Hard routing rules run before embedding fallback.

### Pre-routing rejection

Before `fund_scale`, `nav_trend`, and embedding fallback, reject NAV-derived requests:

- if the question contains `净值` and also contains any of `变了多少`, `变化了多少`, `涨了多少`, `跌了多少`, `涨跌多少`, return `UnsupportedQuery(derived_not_supported)`
- this rule takes precedence over the existing single-point `fund_scale` shortcut for `净值`
- this rule also takes precedence over `nav_trend`
- purpose: prevent questions such as `510500净值变了多少` from being downgraded to the single-point `510500净值` query

### `nav_trend`

Route to `nav_trend`:

- `净值走势`
- `净值曲线`
- `净值趋势`
- `净值变化趋势`
- `净值变化曲线`

Do not route to `nav_trend`:

- `净值`, `最新净值`, `单位净值是多少`: keep existing `fund_scale` single-point behavior
- `净值变化了多少`, `净值变了多少`, `净值涨了多少`, `净值跌了多少`, `净值涨跌多少`: return `UnsupportedQuery(derived_not_supported)` via the pre-routing rejection rule
- `近一年收益率`, `最大回撤`: do not use NAV series as derived performance

### `scale_share_trend`

Route to `scale_share_trend`:

- `规模走势`, `规模趋势`, `规模变化`: return only scale series
- `份额走势`, `份额趋势`, `份额变化`: return only share series
- `规模和份额走势`, `规模、份额变化`: return two series blocks

Do not route to `scale_share_trend`:

- `近 N 日 + 变动`
- `近 N 日 + 变动率`
- `近 N 日 + 变化了多少`
- `净流入天数`

Those are derived requests and must return `UnsupportedQuery(derived_not_supported)`.

### `trading_metric`

Route examples:

- `成交额是多少`, `最近成交额`: `trading_metric` latest
- `成交额走势`, `成交额趋势`: `trading_metric` with `ths_amt_fund` series

Boundary examples:

- `净现金流走势`, `融资余额走势`, `融券金额走势`: `UnsupportedQuery(series_not_enabled)`
- `实时成交额`, `盘中成交额`: `DeniedQuery(realtime_not_supported)`
- `成交量`, `换手率`: `UnsupportedQuery(field_not_available)`
- `日均成交额`, `日均换手率`: `UnsupportedQuery(field_not_imported)`

`series_not_enabled` is reserved only for fields that already have v3.3 latest-query capability but whose v3.4 series display is not opened. Typical examples are `净现金流走势`, `融资余额走势`, and `融券金额走势`.

Do not use `series_not_enabled` when the requested field does not exist, is not imported, or has not passed probe registration. Those cases must keep their distinct errors: `field_not_available` or `field_not_imported`.

## Compatibility

v3.4 must not regress v3.3 behavior:

- `performance` remains derived-performance behavior where applicable
- specified-date NAV remains `specified`
- `report` and `manager_detail` are unaffected
- existing `trading_metric` latest fields are not removed
- `series` must not be reused by `performance` to compute returns

## Acceptance Cases

| Question | Expected behavior |
| --- | --- |
| `510500近一年净值走势` | `nav_trend`, `series`, `period=1y` |
| `159919成立以来净值曲线` | `nav_trend`, `period=std` |
| `510500近5日净值走势` | `nav_trend`, `period=business_days`, `count=5` |
| `510500净值` | existing `fund_scale` single point |
| `510500净值变了多少` | `UnsupportedQuery(derived_not_supported)` |
| `510500净值变化了多少` | `UnsupportedQuery(derived_not_supported)` |
| `510500净值涨了多少` | `UnsupportedQuery(derived_not_supported)` |
| `510500净值跌了多少` | `UnsupportedQuery(derived_not_supported)` |
| `510500近一年收益率` | `performance` |
| `510500近一年规模变化` | `scale_share_trend`, only scale |
| `159919份额变化趋势` | `scale_share_trend`, only shares |
| `510500规模和份额走势` | two series blocks |
| `510500近5日份额变动` | `UnsupportedQuery(derived_not_supported)` |
| `510500成交额是多少` | `trading_metric` latest |
| `510500成交额走势` | `trading_metric`, `ths_amt_fund`, `series` |
| `510500净现金流走势` | `UnsupportedQuery(series_not_enabled)` |
| `510500融资余额走势` | `UnsupportedQuery(series_not_enabled)` |
| `510500融券金额走势` | `UnsupportedQuery(series_not_enabled)` |
| `510500盘中成交额` | `DeniedQuery(realtime_not_supported)` |
| `510500成交量是多少` | `UnsupportedQuery(field_not_available)` |
| `510500日均成交额是多少` | `UnsupportedQuery(field_not_imported)` |
| `510500近99999个交易日净值走势` | `UnsupportedQuery(period_window_too_large)` |
| `510500成立以来净值走势` | `nav_trend`, `period=std`; not limited by 250 points |
