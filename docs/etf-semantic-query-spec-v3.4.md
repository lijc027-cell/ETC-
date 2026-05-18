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

## Realtime Extension Planning

This section is a planned next extension only. It does not change the released v3.4 truth above, does not add realtime support to the current pipeline, and does not backfill new runtime behavior into the current release scope.

The next realtime phase must use a matrix-driven design. Realtime business truth must not be split across router rules, LLM prompt text, validator branches, formatter mappings, or adapter-specific defaults. The single authority must be a unified `realtime_registry`, and all downstream modules must read from that registry instead of carrying their own duplicate rules.

### Design Goal

The primary goal is maintainability, not prematurely freezing every realtime business detail. After PM confirmation, behavior changes must be made by editing the registry matrices first, then updating tests, without requiring scattered main-flow code edits for routine scenario, field, or display changes.

The scenario defaults and display defaults in this section are candidate starting defaults for the next realtime phase, subject to PM confirmation. They are planning inputs for the next extension, not already-approved current-release product truth.

The normative contract in this section is the registry architecture, ownership boundary, and anti-shadow governance. The candidate scenario, field, and display defaults below are seed content for that contract, not separately approved release behavior.

### Single Source Of Truth

`realtime_registry` is the only authority for:

- user phrasing to scenario classification
- all realtime field-selection business truth, including default field selection and unsupported-field handling
- field label, unit, precision, scale, and null-display policy
- registry-level scenario enablement, field exposure, scenario-field support, and role constraints
- alias coverage, scenario metadata, field metadata, composition metadata, field-execution metadata, and source-mapping metadata needed by downstream consumers

The following implementation patterns are explicitly forbidden:

- large keyword `if/else` trees in the router for realtime question classification
- hardcoded `profile -> fields` or `scenario -> fields` mappings inside realtime AST generation
- formatter-side hardcoded units, scaling, sign rules, or precision rules for realtime fields
- duplicated alias tables, field groups, or scenario definitions across prompts, validators, formatters, and adapters

### Registry Shape

The shipped `realtime_registry` must be exhaustive for every supported realtime scenario, field, alias, scenario-field support rule, composition rule, source rule, and display rule. If a required entry is missing from the registry, the behavior is unsupported and must fail validation rather than falling back to business logic hardcoded elsewhere.

The minimum top-level shape is:

```json
{
  "intent_to_scenario_matrix": {
    "overview": {
      "enabled": true,
      "match_mode": "rule_based",
      "must_have": [],
      "any_of": ["实时行情", "现在什么情况", "今天表现如何"],
      "forbid": [],
      "priority": 100,
      "multi_match_policy": "merge",
      "allowed_cooccurrence": ["price_change", "trading", "valuation"]
    },
    "price_change": {
      "enabled": true,
      "match_mode": "rule_based",
      "must_have": [],
      "any_of": ["现在多少钱", "涨了吗", "涨跌幅多少"],
      "forbid": [],
      "priority": 90,
      "multi_match_policy": "merge",
      "allowed_cooccurrence": ["overview", "valuation"]
    }
  },
  "scenario_to_fields_matrix": {
    "overview": ["latest", "change", "changeRatio", "open", "high", "low", "amount", "volume", "iopv", "premium", "tradeTime"],
    "price_change": ["latest", "change", "changeRatio", "tradeTime"]
  },
  "field_display_matrix": {
    "latest": {"label": "最新价", "format_kind": "plain_number", "precision_mode": "max_fraction_digits", "precision_value": 4, "sign_policy": "auto", "scale_policy": "none", "unit_policy": "none", "null_policy": "display_placeholder", "zero_policy": "allow"},
    "changeRatio": {"label": "涨跌幅", "format_kind": "percent", "precision_mode": "fixed_fraction_digits", "precision_value": 2, "sign_policy": "always", "scale_policy": "ratio_to_percent", "unit_policy": "suffix_percent", "null_policy": "display_placeholder", "zero_policy": "allow"},
    "amount": {"label": "成交额", "format_kind": "scaled_number", "precision_mode": "fixed_fraction_digits", "precision_value": 2, "sign_policy": "auto", "scale_policy": "divide", "scale_value": 100000000, "unit_policy": "literal", "unit_value": "亿元", "null_policy": "display_placeholder", "zero_policy": "allow"}
  },
  "scenario_metadata": {
    "overview": {"card_group": "overview"}
  },
  "field_metadata": {
    "latest": {
      "exposed": true,
      "value_type": "price",
      "canonical_unit": "currency",
      "source_mapping_id": "latest",
      "normalization_rule_id": "default_numeric_passthrough",
      "derivation_rule_id": null,
      "freshness_policy": "accept_latest_available"
    }
  },
  "unsupported_field_policy": {
    "default_action_by_origin": {
      "default": "drop_field",
      "explicit": "reject_request",
      "derived": "reject_request"
    },
    "default_error_code": "field_not_supported"
  },
  "alias_rules": {
    "rules": [
      {
        "scope": "scenario",
        "match_kind": "exact_phrase",
        "pattern": "涨跌幅多少",
        "canonical_id": "price_change",
        "priority": 100,
        "rewrite_mode": "none",
        "emit_mode": "single",
        "collision_policy": "highest_priority_wins"
      }
    ],
    "normalized_output_contract": {
      "fields": ["normalized_text", "emitted_scenarios", "emitted_fields", "emitted_terminal_outcomes"],
      "overlap_policy": "highest_priority_wins"
    }
  },
  "role_rules": {},
  "scenario_field_support_matrix": {
    "overview": {
      "explicitly_allowed_fields": ["latest", "change", "changeRatio", "open", "high", "low", "amount", "volume", "iopv", "premium", "tradeTime"],
      "explicitly_denied_fields": [],
      "unsupported_error_code": "field_not_supported"
    }
  },
  "explicit_field_injection_rules": {
    "latest": {
      "default_scenarios": ["price_change", "overview"]
    }
  },
  "terminal_outcome_matrix": {
    "no_scenario_match": "unsupported_query",
    "explicit_field_without_supported_scenario": "field_not_supported"
  },
  "composition_rules": {
    "merge_stages": ["collect_scenarios", "expand_defaults", "apply_explicit_fields", "apply_role_filters", "apply_support_policy", "dedupe", "order"],
    "explicit_field_precedence": "explicit_over_default",
    "scenario_conflict_policy": "higher_priority_wins",
    "global_field_order": ["latest", "change", "changeRatio", "open", "high", "low", "amount", "volume", "iopv", "premium", "tradeTime"],
    "field_conflict_policy": "first_by_global_order"
  },
  "source_field_mappings": {
    "latest": {
      "sources": [
        {
          "source_id": "primary_quote",
          "source_field": "latest",
          "priority": 100,
          "capability_gate": null,
          "input_unit": "currency"
        }
      ],
      "priority_policy": "highest_priority_available",
      "freshness_policy": "accept_latest_available",
      "failure_policy": "return_null"
    }
  },
  "source_capabilities": {},
  "derivation_rules": {},
  "normalization_rules": {
    "rules": [
      {
        "rule_id": "default_numeric_passthrough",
        "null_policy": "preserve_null",
        "zero_policy": "preserve_zero",
        "normalization_steps": ["type_coerce_number"]
      }
    ]
  }
}
```

The object above is not illustrative architecture prose only. The implementation must materialize a real configuration object with this responsibility boundary, and the code path must treat it as the only business source for realtime defaults.

The registry-owned sections above are required top-level registry data, not optional prose placeholders. Empty objects are valid only when the corresponding capability is unsupported end to end and the implementation rejects any path that would require that capability.

### Intent To Scenario Matrix

`intent_to_scenario_matrix` centrally defines how user realtime questions map to scenarios. Default scenarios for the planned extension are:

- `overview`
- `price_change`
- `trading`
- `valuation`
- `order_book`
- `trade_flow`

These scenario names and their routing relationships must exist as matrix data, not as router constants. Router prompts, scenario descriptions, and few-shot style examples for realtime classification must be generated from this matrix instead of being maintained separately.

Each scenario row must be a machine-readable routing contract rather than an examples-only hint. Router code must reject scenario ids that are not defined in the registry, and must not maintain a second scenario-priority or tie-break table outside the registry.

The routing interpreter must also be registry-driven. For the planned default model, each scenario row must define executable matcher primitives such as `match_mode`, `must_have`, `any_of`, `forbid`, deterministic `priority`, `multi_match_policy`, and `allowed_cooccurrence`. A match occurs only when the row satisfies the declared interpreter semantics for those primitives. Alias normalization must happen from registry-owned alias rules before scenario classification. Co-occurrence must be enforced only from registry-declared allowed combinations. Router output must be limited to registry-declared scenario ids plus explicit unsupported or denied outcomes declared in registry-owned terminal outcome rules.

If a future implementation uses an LLM-assisted classifier instead of deterministic matcher primitives, all realtime-specific routing rubric must still come from registry-generated content, and the classifier contract must emit schema-validated evidence that maps back to registry-declared scenarios and tie-resolution rules. No implementer-controlled realtime routing rubric may live outside registry-owned content.

### Scenario To Fields Matrix

`scenario_to_fields_matrix` centrally defines scenario-default field expansion. The planned default mapping is:

- `overview`: `latest`, `change`, `changeRatio`, `open`, `high`, `low`, `amount`, `volume`, `iopv`, `premium`, `tradeTime`
- `price_change`: `latest`, `change`, `changeRatio`, `tradeTime`
- `trading`: `amount`, `volume`, `latestVolume`, `tradeTime`
- `valuation`: `latest`, `iopv`, `premium`, `tradeTime`
- `order_book`: `bid1`, `ask1`, `bidSize1`, `askSize1`, `tradeTime`
- `trade_flow`: `sellVolume`, `buyVolume`, `latestVolume`, `tradeTime`

Multi-scenario composition must also be matrix-driven. The flow should first resolve all matched scenarios, then merge field lists from this matrix, deduplicate them, and apply one stable registry-defined field order. No second copy of this mapping may be hardcoded in the AST expander, prompt templates, or output layer.

Any merge order, precedence, conflict resolution, pruning order, or presentation grouping required for multi-scenario composition must be declared in registry-owned composition metadata. The merge algorithm must remain generic and parameterized by registry data only.

`composition_rules` must define the executable stages for multi-scenario assembly, including how explicit user-requested fields interact with scenario defaults, how scenario conflicts are resolved, when role filtering runs, how scenario-field support is enforced, how deduplication is performed, and how final ordering is applied. Mixed `multi_match_policy` values, asymmetric co-occurrence, and explicit-field scenario injection rules must resolve deterministically from registry data only.

### Field Display Matrix

`field_display_matrix` centrally defines display semantics for realtime fields. For the planned default contract, every exposed field must have an explicit per-field display row. The candidate starting defaults are:

- price-like fields `preClose`, `open`, `high`, `low`, `latest`, `bid1`, `ask1`, `iopv`: display with up to 4 decimal places
- `change`: display with up to 4 decimal places and keep explicit positive or negative sign
- `changeRatio`, `swing`: display as percent with 2 decimal places
- `amount`: scale from yuan to `亿元` by default
- `volume`: scale from hands to `万手` by default
- `latestVolume`, `sellVolume`, `buyVolume`, `bidSize1`, `askSize1`: display raw values by default
- `premium`: display as price spread by default
- `tradeDate`, `tradeTime`: display as-is
- `null`: display `暂无数据`
- `0`: treat as valid data, not missing data

Formatter behavior must be derived from this matrix. Field units, precision, percent formatting, sign retention, scaling, trailing-zero trimming, and missing-data rendering must not be re-implemented as ad hoc business logic elsewhere.

Each exposable realtime field must resolve to a complete display contract, including `label` or `label_key`, format kind, unit semantics, precision semantics, sign policy when applicable, null handling, and zero handling. If a field does not resolve to a complete display contract from registry data, it is unsupported.

The display schema must use closed enum-like policies rather than freeform prose. The implementation must define machine-readable semantics for `format_kind`, `precision_mode`, `sign_policy`, `scale_policy`, `unit_policy`, `null_policy`, and `zero_policy`, so formatter code can execute generic formatting without field-specific business branches. The example registry rows above must be read as normative examples of that same contract, not as a looser alternative schema.

### Module Boundaries

Each realtime module may read the registry, but may not define a second business truth:

- Alias normalization reads registry-owned `alias_rules` only.
- Router reads `intent_to_scenario_matrix` only for realtime scenario classification after alias normalization.
- Pre-expansion validation reads registry-owned scenario enablement, field exposure metadata, role rules, and request-shape constraints only.
- Realtime AST expansion reads `scenario_to_fields_matrix`, `scenario_field_support_matrix`, `explicit_field_injection_rules`, and registry-owned composition metadata only for field expansion and multi-scenario merge.
- Post-expansion validation reads registry-owned scenario-field support, unsupported-field policy, and role rules only.
- Formatter reads `field_display_matrix` only for labels and display semantics.
- Adapters may only execute registry-declared field execution metadata, source mappings, capability metadata, derivation rules, and normalization rules. Adapters may not define scenarios, default field sets, aliases, role rules, unsupported-field policy, display semantics, fallback source precedence, freshness behavior, derivation dependencies, or source-specific business defaults in code.

The processing order must remain explicit and stable: alias normalization -> scenario classification -> pre-expansion validation -> field expansion -> post-expansion validation -> data execution -> formatting. Realtime cards must derive their scenario, field, and display business truth from `realtime_registry`. Router prompt scenario descriptions must be generated from `intent_to_scenario_matrix`. Realtime AST default fields and merge behavior must be generated from `scenario_to_fields_matrix` plus registry-owned composition metadata. Data execution must resolve every exposed field through `field_metadata`, source mappings, derivation rules, and normalization rules. Formatter output rules must be generated from `field_display_matrix`.

### Registry Ownership Rules

Any later business change to realtime wording, scenario membership, field-selection behavior, alias behavior, unsupported-field behavior, labels, units, scale, precision, display policy, source precedence, derivation behavior, normalization behavior, or multi-scenario composition must be implemented by updating `realtime_registry` first. After that, tests should be updated to match.

Direct execution-code edits that bypass the registry are not allowed. The only exception is purely mechanical plumbing that preserves observable business behavior end to end. Mechanical plumbing does not include changes to routing outcomes, field expansion, alias resolution, unsupported-field handling, validation decisions, card content, formatter output, source-field precedence, derivation behavior, or normalization behavior.

If a PR changes intended realtime product truth, it must include a registry diff. If a PR fixes an implementation bug so runtime behavior conforms to already-declared registry truth, it may omit a registry diff only if it proves the previous behavior contradicted the registry and adds regression tests for the conformance fix.

### Planning-Time Test Requirements

The next-phase implementation must include a single-source-of-truth check with at least these guarantees:

- canonical scenario ids are owned by `intent_to_scenario_matrix` rows and derived elsewhere
- canonical field ids are owned by `field_metadata` and derived elsewhere
- each default field combination is defined only in `scenario_to_fields_matrix`
- each field unit, scale, and precision rule is defined only in `field_display_matrix`
- each alias rule, scenario-field support rule, explicit-field injection rule, composition rule, field execution rule, and source rule is defined only in registry-owned metadata
- prompts, formatters, validators, and adapters do not maintain shadow copies of the same business mapping

Planned implementation tests must verify matrix-driven behavior directly:

- changing one `scenario_to_fields_matrix` entry changes AST expansion and formatter output
- changing one `field_display_matrix` rule changes output formatting without formatter code changes
- changing one `intent_to_scenario_matrix` classification rule changes router results without router logic edits
- changing registry-owned alias or scenario-field support rules changes validator and routing behavior without validator or router logic edits
- changing registry-owned explicit-field injection rules changes scenario selection and field expansion without expander logic edits
- changing registry-owned source mapping, field execution, or normalization rules changes adapter behavior without adapter business-logic edits
- config-only registry mutation tests prove router prompt generation, AST expansion, validator decisions, card generation, and formatter behavior all follow the updated registry
- locked end-to-end golden fixtures prove the runtime follows registry-owned routing, validation, field expansion, and formatting behavior
- registry schema validation must fail on malformed registry structure or unknown enum values
- cross-reference integrity checks must fail when registry references point to unknown scenarios, fields, source rules, derivation rules, normalization rules, or terminal outcomes
- repository-level CI checks must use explicit allowlist / denylist scope to prevent non-test modules from re-declaring routing rules, default field lists, alias mappings, validator business rules, source mapping rules, derivation rules, normalization rules, or field display business rules outside the registry module
