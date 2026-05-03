from __future__ import annotations

import streamlit as st

LANGUAGE_STATE_KEY = "app_language"
DEFAULT_LANGUAGE = "en"

LANGUAGE_OPTIONS = {
    "zh-CN": "\u7b80\u4f53\u4e2d\u6587",
    "en": "English",
}

TRANSLATIONS = {
    "language.label": {"zh-CN": "\u8bed\u8a00", "en": "Language"},
    "nav.home": {"zh-CN": "\u9996\u9875", "en": "Home"},
    "app.page_title": {"zh-CN": "\u7a7a\u6c14\u8d28\u91cf\u5206\u6790\u5e73\u53f0", "en": "Air Quality Dashboard"},
    "app.title": {"zh-CN": "\u57ce\u5e02\u7a7a\u6c14\u8d28\u91cf\u65f6\u7a7a\u5206\u6790\u5e73\u53f0", "en": "City Air Quality Spatiotemporal Dashboard"},
    "app.caption": {"zh-CN": "Python 3.14 | Streamlit + Plotly | \u5386\u53f2\u6570\u636e\u91c7\u96c6 Agent", "en": "Python 3.14 | Streamlit + Plotly | Historical Collection Agent"},
    "app.body": {
        "zh-CN": "\u672c\u9879\u76ee\u63d0\u4f9b\uff1a\n- \u591a\u9875\u9762\u8054\u52a8\u7b5b\u9009\u5206\u6790\n- \u7ad9\u70b9\u7ea7\u6c61\u67d3\u65f6\u7a7a\u56de\u653e\n- \u6c61\u67d3\u7269\u4e0e\u6c14\u8c61\u76f8\u5173\u6027\u5206\u6790\n- \u57fa\u4e8e DeepSeek \u7684\u6307\u5b9a\u57ce\u5e02\u5386\u53f2\u7a7a\u6c14\u8d28\u91cf\u91c7\u96c6 Agent\n\n\u5982\u679c\u7f3a\u5c11\u5904\u7406\u540e\u7684\u6570\u636e\uff0c\u53ef\u8fd0\u884c\u4ee5\u4e0b\u547d\u4ee4\uff1a\n- `python scripts/generate_demo_data.py --out data/processed/beijing_aq.parquet`\n- `python scripts/build_dataset.py --raw data/raw --out data/processed/beijing_aq.parquet`",
        "en": "This project delivers:\n- Multi-filter linked analysis across pages\n- Spatiotemporal map playback at station level\n- Pollutant-weather correlation views\n- A DeepSeek-assisted agent for collecting historical AQ data for a selected city\n\nIf processed data is missing, run one of these commands:\n- `python scripts/generate_demo_data.py --out data/processed/beijing_aq.parquet`\n- `python scripts/build_dataset.py --raw data/raw --out data/processed/beijing_aq.parquet`",
    },
    "app.active_dataset": {"zh-CN": "\u5f53\u524d\u6570\u636e\u96c6\u8def\u5f84\uff1a`{path}`", "en": "Active dataset path: `{path}`"},
    "app.agent_hint": {"zh-CN": "\u53ef\u524d\u5f80 Historical Data Agent \u9875\u9762\u91c7\u96c6\u65b0\u57ce\u5e02\u6570\u636e\uff0c\u5e76\u5207\u6362\u5230\u65b0\u751f\u6210\u7684\u6570\u636e\u96c6\u6587\u4ef6\u3002", "en": "Open the Historical Data Agent page to collect another city's archive and switch this app to the new dataset file."},
    "common.city": {"zh-CN": "\u57ce\u5e02", "en": "City"},
    "common.actual_start": {"zh-CN": "\u5b9e\u9645\u8d77\u59cb", "en": "Actual start"},
    "common.actual_end": {"zh-CN": "\u5b9e\u9645\u7ed3\u675f", "en": "Actual end"},
    "common.chunks": {"zh-CN": "\u5206\u6bb5\u6570", "en": "Chunks"},
    "common.failed_to_load_dataset": {"zh-CN": "\u6570\u636e\u96c6\u52a0\u8f7d\u5931\u8d25\uff1a{error}", "en": "Failed to load dataset: {error}"},
    "common.no_data_after_filters": {"zh-CN": "\u7b5b\u9009\u540e\u65e0\u53ef\u7528\u6570\u636e\uff0c\u8bf7\u8c03\u6574\u4fa7\u8fb9\u680f\u7b5b\u9009\u6761\u4ef6\u3002", "en": "No data after filters. Adjust the sidebar filters."},
    "common.summary_mode": {"zh-CN": "\u6458\u8981\u6a21\u5f0f\uff1a{mode}", "en": "Summary mode: {mode}"},
    "common.download_parquet": {"zh-CN": "\u4e0b\u8f7d parquet", "en": "Download parquet"},
    "common.download_csv": {"zh-CN": "\u4e0b\u8f7d CSV", "en": "Download CSV"},
    "ui.dataset": {"zh-CN": "\u6570\u636e\u96c6", "en": "Dataset"},
    "ui.dataset_hint": {"zh-CN": "\u63d0\u793a\uff1aAgent \u751f\u6210\u7684\u6570\u636e\u96c6\u6587\u4ef6\u4f1a\u81ea\u52a8\u51fa\u73b0\u5728\u8fd9\u91cc\u3002", "en": "Tip: agent-generated dataset files appear here automatically."},
    "ui.filters": {"zh-CN": "\u5168\u5c40\u7b5b\u9009", "en": "Global filters"},
    "ui.date_range": {"zh-CN": "\u65e5\u671f\u8303\u56f4", "en": "Date range"},
    "ui.stations": {"zh-CN": "\u7ad9\u70b9", "en": "Stations"},
    "ui.primary_pollutant": {"zh-CN": "\u4e3b\u6c61\u67d3\u7269", "en": "Primary pollutant"},
    "ui.performance_hint": {"zh-CN": "\u6027\u80fd\u63d0\u793a\uff1a\u5efa\u8bae\u5c06\u65e5\u671f\u8303\u56f4\u63a7\u5236\u5728 30-180 \u5929\u5185\uff0c\u4ee5\u83b7\u5f97\u66f4\u6d41\u7545\u7684\u4ea4\u4e92\u4f53\u9a8c\u3002", "en": "Performance tip: keep date range focused (e.g., 30-180 days) for smoother interaction."},
    "weather.temp": {"zh-CN": "\u6e29\u5ea6", "en": "Temperature"},
    "weather.humidity": {"zh-CN": "\u6e7f\u5ea6", "en": "Humidity"},
    "weather.wind_speed": {"zh-CN": "\u98ce\u901f", "en": "Wind speed"},
    "overview.page_title": {"zh-CN": "\u603b\u89c8", "en": "Overview"},
    "overview.title": {"zh-CN": "\u603b\u89c8", "en": "Overview"},
    "overview.latest_mean": {"zh-CN": "\u6700\u65b0\u5747\u503c", "en": "Latest mean"},
    "overview.last_24h_mean": {"zh-CN": "\u8fd124\u5c0f\u65f6\u5747\u503c", "en": "Last 24h mean"},
    "overview.exceed_hours": {"zh-CN": "\u8d85\u6807\u65f6\u957f", "en": "Exceed hours"},
    "overview.station_spread": {"zh-CN": "\u7ad9\u70b9\u5dee\u5f02", "en": "Station spread"},
    "overview.compute_events": {"zh-CN": "\u8ba1\u7b97\u4e8b\u4ef6\u6807\u6ce8\uff08\u8f83\u6162\uff09", "en": "Compute event annotations (slower)"},
    "overview.detected_events": {"zh-CN": "\u68c0\u6d4b\u5230\u7684\u4e8b\u4ef6\u6807\u6ce8", "en": "Detected event annotations"},
    "overview.no_events": {"zh-CN": "\u5f53\u524d\u7b5b\u9009\u8303\u56f4\u5185\u672a\u68c0\u6d4b\u5230\u4e8b\u4ef6\u3002", "en": "No events detected for current filter range."},
    "playback.page_title": {"zh-CN": "\u65f6\u7a7a\u56de\u653e", "en": "Spatiotemporal Playback"},
    "playback.title": {"zh-CN": "\u65f6\u7a7a\u56de\u653e", "en": "Spatiotemporal Playback"},
    "playback.no_timestamp": {"zh-CN": "\u7b5b\u9009\u540e\u6ca1\u6709\u53ef\u7528\u7684\u65f6\u95f4\u6233\u3002", "en": "No timestamp values after filtering."},
    "playback.select_day": {"zh-CN": "\u9009\u62e9\u65e5\u671f", "en": "Select day"},
    "playback.select_hour": {"zh-CN": "\u9009\u62e9\u5c0f\u65f6", "en": "Select hour"},
    "playback.span": {"zh-CN": "\u56de\u653e\u65f6\u957f\uff08\u5c0f\u65f6\uff09", "en": "Playback span (hours)"},
    "playback.play_button": {"zh-CN": "\u64ad\u653e\u5c0f\u65f6\u52a8\u753b", "en": "Play hourly animation"},
    "playback.frame_title": {"zh-CN": "{pollutant} @ {timestamp}", "en": "{pollutant} @ {timestamp}"},
    "playback.hotspot_spread": {"zh-CN": "\u6240\u9009\u65f6\u95f4\u70ed\u70b9\u5dee\u5f02\uff1a{value:.1f}", "en": "Hotspot spread at selected hour: {value:.1f}"},
    "correlation.page_title": {"zh-CN": "\u76f8\u5173\u6027\u5206\u6790", "en": "Correlation Analysis"},
    "correlation.title": {"zh-CN": "\u76f8\u5173\u6027\u5206\u6790", "en": "Correlation Analysis"},
    "correlation.weather_variable": {"zh-CN": "\u6c14\u8c61\u53d8\u91cf", "en": "Weather variable"},
    "correlation.station_daily_comparison": {"zh-CN": "\u7ad9\u70b9\u65e5\u5747\u503c\u5bf9\u6bd4", "en": "Station daily comparison"},
    "chart.daily_trend": {"zh-CN": "\u65e5\u5747\u8d8b\u52bf\uff1a{pollutant}", "en": "Daily trend: {pollutant}"},
    "chart.station": {"zh-CN": "\u7ad9\u70b9", "en": "Station"},
    "chart.station_ranking": {"zh-CN": "\u7ad9\u70b9\u6392\u540d\uff08{pollutant}\uff09", "en": "Station ranking ({pollutant})"},
    "chart.station_distribution": {"zh-CN": "\u7ad9\u70b9\u5206\u5e03\uff1a{pollutant}", "en": "Station distribution: {pollutant}"},
    "chart.longitude": {"zh-CN": "\u7ecf\u5ea6", "en": "Longitude"},
    "chart.latitude": {"zh-CN": "\u7eac\u5ea6", "en": "Latitude"},
    "chart.correlation_matrix": {"zh-CN": "\u76f8\u5173\u6027\u77e9\u9635", "en": "Correlation matrix"},
    "chart.samples": {"zh-CN": "\u6837\u672c\u70b9", "en": "Samples"},
    "chart.linear_fit": {"zh-CN": "\u7ebf\u6027\u62df\u5408", "en": "Linear fit"},
    "chart.vs": {"zh-CN": "{y} \u4e0e {x}", "en": "{y} vs {x}"},
    "events.heavy_pollution": {"zh-CN": "{pollutant} \u9ad8\u503c\u65e5\uff08{value:.1f}\uff09", "en": "{pollutant} high day ({value:.1f})"},
    "events.sharp_shift": {"zh-CN": "\u65e5\u53d8\u5316\u5267\u70c8\uff08{delta:.1f}\uff09", "en": "Rapid day-over-day shift ({delta:.1f})"},
    "agent.page_title": {"zh-CN": "\u5386\u53f2\u6570\u636e Agent", "en": "Historical Data Agent"},
    "agent.title": {"zh-CN": "\u5386\u53f2\u7a7a\u6c14\u8d28\u91cf\u6570\u636e\u91c7\u96c6 Agent", "en": "Historical Air Quality Collection Agent"},
    "agent.caption": {"zh-CN": "\u901a\u8fc7\u7ed3\u6784\u5316\u7684\u57ce\u5e02\u76ee\u5f55\u3001\u6807\u7b7e\u9009\u62e9\u548c\u53ef\u9009 DeepSeek \u589e\u5f3a\uff0c\u89c4\u5212\u5e76\u91c7\u96c6\u6307\u5b9a\u57ce\u5e02\u7684\u5386\u53f2\u7a7a\u6c14\u8d28\u91cf\u6570\u636e\u96c6\u3002", "en": "Use the structured city catalog, tag-based selectors, and optional DeepSeek enhancement to plan and collect a city dataset."},
    "agent.default_instruction": {"zh-CN": "\u91c7\u96c6 {start_year} \u5e74\u5230 {end_year} \u5e74\u7684\u5317\u4eac PM2.5\u3001PM10\u3001NO2\u3001SO2\u3001CO \u548c O3 \u6570\u636e\uff0c\u5305\u542b\u6c14\u8c61\u5217\uff0c\u5e76\u4fdd\u5b58\u6570\u636e\u96c6\u3002", "en": "Collect Beijing PM2.5, PM10, NO2, SO2, CO, and O3 from {start_year} to {end_year}, include weather columns, and save the dataset."},
    "agent.plan_section": {"zh-CN": "Agent \u8ba1\u5212", "en": "Agent Plan"},
    "agent.plan_caption": {"zh-CN": "\u6570\u636e\u6e90\uff1a{source} | \u57df\uff1a{domain} | \u91c7\u6837\u9891\u7387\uff1a{sampling} | \u89c4\u5212\u6a21\u5f0f\uff1a{mode}", "en": "Source: {source} | Domain: {domain} | Sampling: {sampling} | Planner mode: {mode}"},
    "agent.planned_pollutants": {"zh-CN": "\u8ba1\u5212\u6c61\u67d3\u7269", "en": "Planned pollutants"},
    "agent.quality_checks": {"zh-CN": "\u8d28\u91cf\u68c0\u67e5", "en": "Quality checks"},
    "agent.risk_flags": {"zh-CN": "\u98ce\u9669\u63d0\u793a", "en": "Risk flags"},
    "agent.chunk_preview": {"zh-CN": "\u5206\u6bb5\u65f6\u95f4\u9884\u89c8", "en": "Chunk window preview"},
    "agent.deepseek_settings": {"zh-CN": "DeepSeek \u8bbe\u7f6e", "en": "DeepSeek Settings"},
    "agent.use_deepseek": {"zh-CN": "\u5f53 API key \u53ef\u7528\u65f6\uff0c\u4f7f\u7528 DeepSeek \u589e\u5f3a\u8ba1\u5212\u8bf4\u660e\u3001\u8fd0\u884c\u6458\u8981\uff0c\u5e76\u5728\u4e2d\u56fd\u57ce\u5e02\u8986\u76d6\u8f83\u5f31\u65f6\u5c1d\u8bd5\u540c\u7701\u4ee3\u7406\u8865\u4f4d", "en": "Use DeepSeek to enhance plan notes, run summaries, and same-province China proxy recovery when the API key is configured"},
    "agent.model": {"zh-CN": "\u6a21\u578b", "en": "Model"},
    "agent.base_url": {"zh-CN": "Base URL", "en": "Base URL"},
    "agent.api_key_found": {"zh-CN": "\u5df2\u5728 Streamlit secrets \u4e2d\u53d1\u73b0 `deepseek_api_key`\u3002", "en": "Found `deepseek_api_key` in Streamlit secrets."},
    "agent.api_key_optional": {"zh-CN": "\u672a\u914d\u7f6e `deepseek_api_key`\u3002\u4ecd\u53ef\u4f7f\u7528\u7ed3\u6784\u5316\u91c7\u96c6\u6d41\u7a0b\uff0c\u53ea\u662f\u4e0d\u4f7f\u7528 DeepSeek \u589e\u5f3a\u3002", "en": "No `deepseek_api_key` found. The structured collection flow still works; it just skips DeepSeek enhancement."},
    "agent.api_key_missing": {"zh-CN": "\u672a\u5728 Streamlit secrets \u4e2d\u627e\u5230 `deepseek_api_key`\u3002\u672a\u914d\u7f6e key \u65f6\uff0c\u81ea\u7136\u8bed\u8a00 agent \u4e0d\u53ef\u7528\u3002", "en": "No `deepseek_api_key` found. The natural-language agent is unavailable until the key is configured."},
    "agent.request_section": {"zh-CN": "\u7ed3\u6784\u5316\u91c7\u96c6\u8bf7\u6c42", "en": "Structured Collection Request"},
    "agent.request_caption": {"zh-CN": "\u4f7f\u7528\u4e0b\u62c9 chevron \u9009\u62e9\u5927\u6d32\u3001\u56fd\u5bb6/\u5730\u533a\u3001\u7701/\u5dde\uff08\u5982\u6709\uff09\u548c\u57ce\u5e02\uff0c\u53ea\u663e\u793a\u8fd1\u671f\u8986\u76d6\u8f83\u7a33\u5b9a\u7684\u7cbe\u9009\u5730\u70b9\u3002", "en": "Use the dropdown chevrons to choose continent, country/region, province/state when available, and city. Only curated locations with more stable recent coverage are shown."},
    "agent.continent_select": {"zh-CN": "\u5927\u6d32", "en": "Continent"},
    "agent.country_select": {"zh-CN": "\u56fd\u5bb6 / \u5730\u533a", "en": "Country / region"},
    "agent.province_select": {"zh-CN": "\u7701 / \u5dde / \u884c\u653f\u533a", "en": "Province / state / region"},
    "agent.province_skip": {"zh-CN": "\u5f53\u524d\u56fd\u5bb6/\u5730\u533a\u65e0\u9700\u8be5\u6b65", "en": "No province/state step for this country/region"},
    "agent.city_select": {"zh-CN": "\u57ce\u5e02", "en": "City"},
    "agent.custom_city_option": {"zh-CN": "\u81ea\u5b9a\u4e49\u67e5\u8be2", "en": "Custom search"},
    "agent.custom_city_caption": {"zh-CN": "\u8f93\u5165\u56fd\u5bb6/\u5730\u533a\u548c\u57ce\u5e02\u540d\u79f0\uff0cDeepSeek \u4f1a\u5148\u5224\u65ad\u62fc\u5199\u3001\u91cd\u540d\u57ce\u5e02\u548c\u56fd\u5bb6/\u5730\u533a\u662f\u5426\u5339\u914d\u3002", "en": "Enter a country/region and city name. DeepSeek validates spelling, same-name cities, and country/region fit before collection."},
    "agent.custom_city_country": {"zh-CN": "\u56fd\u5bb6 / \u5730\u533a", "en": "Country / region"},
    "agent.custom_city_name": {"zh-CN": "\u57ce\u5e02\u540d\u79f0", "en": "City name"},
    "agent.custom_city_inputs_required": {"zh-CN": "\u8bf7\u5148\u8f93\u5165\u56fd\u5bb6/\u5730\u533a\u548c\u57ce\u5e02\u540d\u79f0\u3002", "en": "Enter both country/region and city name first."},
    "agent.custom_city_requires_key": {"zh-CN": "\u81ea\u5b9a\u4e49\u5168\u7403\u57ce\u5e02\u67e5\u8be2\u9700\u8981\u5728 Streamlit secrets \u4e2d\u914d\u7f6e `deepseek_api_key`\u3002", "en": "Custom global city search requires `deepseek_api_key` in Streamlit secrets."},
    "agent.validating_custom_city": {"zh-CN": "\u6b63\u5728\u8bf7 DeepSeek \u6821\u9a8c\u81ea\u5b9a\u4e49\u57ce\u5e02", "en": "Asking DeepSeek to validate the custom city"},
    "agent.custom_city_validated_starting_agent": {"zh-CN": "\u4f4d\u7f6e\u5df2\u786e\u8ba4\uff0c\u6b63\u5728\u542f\u52a8 Agent \u89c4\u5212\u4e0e\u91c7\u96c6\u6d41\u7a0b\u3002", "en": "Location confirmed. Starting the agent planning and collection workflow."},
    "agent.custom_city_validation_unavailable": {"zh-CN": "DeepSeek \u672a\u8fd4\u56de\u53ef\u7528\u7684\u57ce\u5e02\u6821\u9a8c\u7ed3\u679c\uff0c\u8bf7\u91cd\u65b0\u8f93\u5165\u3002", "en": "DeepSeek did not return a usable city validation result. Re-enter the location."},
    "agent.custom_city_validated": {"zh-CN": "\u5df2\u6821\u9a8c\uff1a{city}, {country}", "en": "Validated: {city}, {country}"},
    "agent.custom_city_confirmation": {"zh-CN": "DeepSeek \u5efa\u8bae\u4f7f\u7528 `{city}`, `{country}`\u3002\u662f\u5426\u7ee7\u7eed\u6267\u884c\u91c7\u96c6\u6d41\u7a0b\uff1f", "en": "DeepSeek suggests `{city}`, `{country}`. Continue the collection flow?"},
    "agent.custom_city_matching_countries": {"zh-CN": "\u540c\u540d\u57ce\u5e02\u53ef\u80fd\u4f4d\u4e8e\uff1a{countries}", "en": "Same-name city matches may exist in: {countries}"},
    "agent.custom_city_confirm_yes": {"zh-CN": "\u662f\uff0c\u7ee7\u7eed", "en": "Yes, continue"},
    "agent.custom_city_confirm_no": {"zh-CN": "\u5426\uff0c\u91cd\u65b0\u8f93\u5165\u56fd\u5bb6/\u5730\u533a", "en": "No, re-enter country/region"},
    "agent.custom_city_low_confidence": {"zh-CN": "DeepSeek \u5bf9\u8be5\u56fd\u5bb6/\u5730\u533a\u548c\u57ce\u5e02\u5339\u914d\u7f6e\u4fe1\u5ea6\u8f83\u4f4e\uff0c\u8bf7\u91cd\u65b0\u8f93\u5165\u3002", "en": "DeepSeek has low confidence in this country/region and city match. Re-enter the location."},
    "agent.custom_city_confirmed": {"zh-CN": "\u5df2\u786e\u8ba4\u81ea\u5b9a\u4e49\u57ce\u5e02\uff1a{city}, {country}", "en": "Confirmed custom city: {city}, {country}"},
    "agent.custom_city_country_code_missing": {"zh-CN": "DeepSeek \u672a\u8fd4\u56de\u53ef\u7528\u7684\u56fd\u5bb6/\u5730\u533a\u4ee3\u7801\uff0c\u8bf7\u91cd\u65b0\u8f93\u5165\u56fd\u5bb6/\u5730\u533a\u3002", "en": "DeepSeek did not return a usable country/region code. Re-enter the country/region."},
    "agent.custom_support_window": {"zh-CN": "\u81ea\u5b9a\u4e49\u57ce\u5e02\u5c06\u5728 DeepSeek \u6821\u9a8c\u540e\u4f7f\u7528 Open-Meteo \u5168\u7403\u57ce\u5e02\u89e3\u6790\uff1b\u6b27\u6d32\u57ce\u5e02\u901a\u5e38\u53ef\u56de\u6eaf\u5230 2013 \u5e74\uff0c\u5176\u4ed6\u57ce\u5e02\u901a\u5e38\u53ef\u56de\u6eaf\u5230 2022 \u5e74\u3002", "en": "Custom cities use Open-Meteo global geocoding after DeepSeek validation. European cities usually go back to 2013; other cities usually go back to 2022."},
    "agent.custom_instruction": {"zh-CN": "\u76ee\u6807\u57ce\u5e02\u4e3a {country} \u7684 {city}\u3002\u8bf7\u91c7\u96c6 {start_year} \u5e74\u5230 {end_year} \u5e74\u7684 {pollutants} \u5386\u53f2\u7a7a\u6c14\u8d28\u91cf\u6570\u636e\uff0c{weather_clause}\uff0c\u5e76\u4fdd\u5b58\u4e3a\u5f53\u524d dashboard \u53ef\u76f4\u63a5\u52a0\u8f7d\u7684\u6570\u636e\u96c6\u3002", "en": "Target city is {city}, {country}. Collect historical air-quality data for {pollutants} from {start_year} to {end_year}, {weather_clause}, and save a dataset that the current dashboard can load directly."},
    "agent.city_catalog_hint": {"zh-CN": "\u57ce\u5e02\u5217\u8868\u5df2\u6309\u62fc\u97f3/\u9996\u5b57\u6bcd\u6392\u5e8f\u3002\u4e2d\u56fd\u76ee\u524d\u5df2\u6269\u5c55\u5230\u5168\u90e8 31 \u4e2a\u7701\u7ea7\u884c\u653f\u533a\uff0c\u5e76\u8986\u76d6\u8d85\u8fc7 50% \u7684\u5730\u7ea7\u5e02/\u76f4\u8f96\u5e02\uff0c\u4f18\u5148\u4e00\u4e8c\u7ebf\u57ce\u5e02\uff0c\u4e0d\u5305\u542b\u53bf\u7ea7\u5e02\u3002", "en": "City lists are sorted by pinyin/initial letter. China coverage now spans all 31 mainland province-level regions and more than 50% of prefecture-level cities / municipalities, prioritizing tier-1 and tier-2 cities and excluding county-level cities."},
    "agent.support_window": {"zh-CN": "\u5f53\u524d\u9009\u62e9\uff1a`{path}` | \u6570\u636e\u6e90\uff1a{source} | \u53ef\u7528\u65f6\u95f4\u7a97\uff1a{window}", "en": "Current selection: `{path}` | Source: {source} | Availability window: {window}"},
    "agent.deepseek_proxy_hint": {"zh-CN": "\u82e5\u542f\u7528 DeepSeek\uff0c\u5f53\u9009\u4e2d\u7684\u4e2d\u56fd\u57ce\u5e02\u5728\u5f53\u524d\u6570\u636e\u6e90\u4e0b\u65e0\u53ef\u7528\u6c61\u67d3\u7269\u503c\u65f6\uff0c\u91c7\u96c6\u5668\u4f1a\u5c1d\u8bd5\u7528\u540c\u7701\u57ce\u5e02\u4f5c\u4e3a\u53ef\u89c6\u5316\u4ee3\u7406\u6570\u636e\u3002", "en": "When DeepSeek is enabled and a selected China city has no usable pollutant values in the current source, the collector can retry with same-province proxy cities for visualization."},
    "agent.year_range": {"zh-CN": "\u67e5\u8be2\u5e74\u4efd\u8303\u56f4", "en": "Year range"},
    "agent.pollutants_select": {"zh-CN": "\u7a7a\u6c14\u8d28\u91cf\u6807\u7b7e", "en": "Air-quality tags"},
    "agent.weather_select": {"zh-CN": "\u6c14\u8c61\u6807\u7b7e\uff08\u53ef\u9009\uff09", "en": "Weather tags (optional)"},
    "agent.request_preview": {"zh-CN": "\u8bf7\u6c42\u9884\u89c8", "en": "Request Preview"},
    "agent.request_preview_caption": {"zh-CN": "\u4e0b\u65b9\u662f\u5f53\u524d\u7ed3\u6784\u5316\u9009\u62e9\u751f\u6210\u7684\u5185\u90e8\u91c7\u96c6\u6307\u4ee4\u3002", "en": "This is the internal collection instruction generated from the current structured selections."},
    "agent.resolving_city": {"zh-CN": "\u6b63\u5728\u89e3\u6790\u6240\u9009\u57ce\u5e02\u5750\u6807\u4e0e\u65f6\u533a", "en": "Resolving the selected city coordinates and timezone"},
    "agent.building_plan": {"zh-CN": "\u6b63\u5728\u6784\u5efa\u91c7\u96c6\u8ba1\u5212", "en": "Building the collection plan"},
    "agent.city_not_found": {"zh-CN": "\u65e0\u6cd5\u4e3a `{city}` \u89e3\u6790\u5230\u7a33\u5b9a\u57ce\u5e02\u5019\u9009\u9879\u3002", "en": "Could not resolve a stable city candidate for `{city}`."},
    "agent.weather_fields_label": {"zh-CN": "\u8ba1\u5212\u6c14\u8c61\u5b57\u6bb5", "en": "Planned weather fields"},
    "agent.no_weather_fields": {"zh-CN": "\u672a\u9009\u62e9\u6c14\u8c61\u5b57\u6bb5", "en": "No weather fields selected"},
    "agent.natural_section": {"zh-CN": "\u81ea\u7136\u8bed\u8a00 Agent", "en": "Natural Language Agent"},
    "agent.natural_caption": {"zh-CN": "\u793a\u4f8b\uff1a\u91c7\u96c6 2022 \u5e74\u5230 2025 \u5e74\u7684\u6210\u90fd PM2.5 \u548c O3 \u6570\u636e\uff0c\u5305\u542b\u6c14\u8c61\u5217\uff0c\u5e76\u4fdd\u5b58\u6570\u636e\u96c6\u3002", "en": "Example: collect Chengdu PM2.5 and O3 from 2022 to 2025 with weather columns, then save the dataset."},
    "agent.instruction": {"zh-CN": "Agent \u6307\u4ee4", "en": "Agent instruction"},
    "agent.draft_plan": {"zh-CN": "Agent\uff1a\u751f\u6210\u8ba1\u5212", "en": "Agent: Draft Plan"},
    "agent.plan_and_collect": {"zh-CN": "Agent\uff1a\u89c4\u5212\u5e76\u91c7\u96c6", "en": "Agent: Plan and Collect"},
    "agent.tool_requires_key": {"zh-CN": "tool-calling agent \u6a21\u5f0f\u9700\u8981\u5728 Streamlit secrets \u4e2d\u914d\u7f6e `deepseek_api_key`\u3002", "en": "Tool-calling agent mode requires `deepseek_api_key` in Streamlit secrets."},
    "agent.tool_failed": {"zh-CN": "tool-calling agent \u6267\u884c\u5931\u8d25\uff1a{error}", "en": "Tool-calling agent failed: {error}"},
    "agent.tool_no_progress_after_validation": {"zh-CN": "DeepSeek \u5df2\u786e\u8ba4\u4f4d\u7f6e\uff0c\u4f46\u6ca1\u6709\u7ee7\u7eed\u8c03\u7528\u89c4\u5212\u6216\u91c7\u96c6\u5de5\u5177\u3002\u8bf7\u91cd\u8bd5\uff0c\u6216\u8c03\u6574\u8f93\u5165\u540e\u518d\u8fd0\u884c\u3002", "en": "DeepSeek confirmed the location but did not continue with planning or collection tools. Try again, or adjust the input and run it again."},
    "agent.tool_completed": {"zh-CN": "tool-calling agent \u6267\u884c\u5b8c\u6210\u3002", "en": "Tool-calling agent completed."},
    "agent.dataset_active": {"zh-CN": "\u65b0\u91c7\u96c6\u7684\u6570\u636e\u96c6\u5df2\u6210\u4e3a\u5f53\u524d\u6d3b\u8dc3\u6570\u636e\u96c6\u3002", "en": "The collected dataset is now the active dataset choice for the rest of the app."},
    "agent.tool_trace": {"zh-CN": "Tool \u8c03\u7528\u8f68\u8ff9", "en": "Tool Trace"},
    "agent.last_run": {"zh-CN": "\u4e0a\u6b21\u8fd0\u884c", "en": "Last Run"},
    "agent.last_run_saved": {"zh-CN": "\u5df2\u4fdd\u5b58 {row_count:,} \u884c\u6570\u636e\u5230 `{path}`\uff0c\u65f6\u95f4\u8303\u56f4 {started_at} \u81f3 {ended_at}\u3002", "en": "Saved {row_count:,} rows to `{path}` from {started_at} to {ended_at}."},
    "agent.open_overview": {"zh-CN": "\u4f7f\u7528\u8be5\u6570\u636e\u96c6\u6253\u5f00\u603b\u89c8", "en": "Open Overview with this dataset"},
    "agent.open_playback": {"zh-CN": "\u4f7f\u7528\u8be5\u6570\u636e\u96c6\u6253\u5f00\u56de\u653e", "en": "Open Playback with this dataset"},
    "collection.clipped_start": {"zh-CN": "\u7533\u8bf7\u7684\u8d77\u59cb\u5e74\u4efd\u5df2\u88ab\u622a\u65ad\u4e3a {date}\uff0c\u56e0\u4e3a\u8be5\u57ce\u5e02\u7684\u6570\u636e\u6e90\u6700\u65e9\u53ef\u7528\u65e5\u671f\u4ece\u8be5\u65f6\u95f4\u5f00\u59cb\u3002", "en": "Requested start year was clipped to {date} because this city's source window starts there."},
    "collection.clipped_end": {"zh-CN": "\u7533\u8bf7\u7684\u7ed3\u675f\u65e5\u671f\u5df2\u88ab\u622a\u65ad\u4e3a {date}\uff0c\u56e0\u4e3a\u672a\u6765\u5386\u53f2\u6570\u636e\u4e0d\u53ef\u7528\u3002", "en": "Requested end date was clipped to {date} because future history is unavailable."},
    "collection.default_planner_notes": {"zh-CN": "\u4e3a {city} \u5728 {chunks} \u4e2a\u5206\u6bb5\u4e2d\u91c7\u96c6 {pollutants} \u6570\u636e{weather_clause}\uff0c\u7136\u540e\u4fdd\u5b58\u4e3a\u53ef\u4ee5\u88ab\u73b0\u6709 dashboard \u9875\u9762\u76f4\u63a5\u52a0\u8f7d\u7684\u6570\u636e\u96c6\u6587\u4ef6\u3002", "en": "Collect {pollutants} for {city} in {chunks} chunk(s) {weather_clause}, then save a dataset file that can be loaded by the existing dashboard pages."},
    "collection.weather_with": {"zh-CN": "\uff0c\u5305\u542b\u6c14\u8c61\u589e\u5f3a", "en": "with weather enrichment"},
    "collection.weather_with_fields": {"zh-CN": "\uff0c\u9644\u52a0\u6c14\u8c61\u5b57\u6bb5 {fields}", "en": "with weather fields {fields}"},
    "collection.weather_without": {"zh-CN": "\uff0c\u4e0d\u5305\u542b\u6c14\u8c61\u589e\u5f3a", "en": "without weather enrichment"},
    "collection.default_summary": {"zh-CN": "\u5df2\u4e3a {city} \u91c7\u96c6 {rows:,} \u884c\u6570\u636e\uff0c\u65f6\u95f4\u8303\u56f4 {start} \u81f3 {end}\u3002\u91c7\u6837\u9891\u7387\u4e3a {sampling}\uff0c\u6240\u9009\u6c61\u67d3\u7269\u8986\u76d6\u60c5\u51b5\u4e3a {coverage}\u3002\u5df2\u4fdd\u5b58\u81f3 {path}\u3002{warnings}", "en": "Collected {rows:,} rows for {city} from {start} to {end}. Sampling is {sampling}; selected pollutant coverage is {coverage}. Saved to {path}.{warnings}"},
    "collection.summary_warnings": {"zh-CN": " \u8b66\u544a\uff1a{warnings}", "en": " Warnings: {warnings}"},
    "collection.agent_prepared": {"zh-CN": "Agent \u5df2\u4e3a {city} \u51c6\u5907\u597d\u91c7\u96c6\u6d41\u7a0b\u3002", "en": "The agent prepared a collection workflow for {city}."},
    "collection.agent_planned": {"zh-CN": "Agent \u5df2\u4e3a {city} \u751f\u6210\u91c7\u96c6\u8ba1\u5212\u3002", "en": "The agent planned a collection workflow for {city}."},
    "collection.agent_no_message": {"zh-CN": "Agent \u5df2\u5b8c\u6210\uff0c\u4f46\u672a\u8fd4\u56de\u6700\u7ec8\u6587\u5b57\u8bf4\u660e\u3002", "en": "The agent completed without returning a final narrative message."},
    "collection.quality_window": {"zh-CN": "\u786e\u8ba4\u9996\u4e2a\u548c\u6700\u540e\u4e00\u4e2a\u65f6\u95f4\u6233\u4e0e\u8ba1\u5212\u7684\u91c7\u96c6\u65f6\u95f4\u7a97\u4e00\u81f4\u3002", "en": "Confirm the first and last timestamps match the planned collection window."},
    "collection.quality_non_null": {"zh-CN": "\u5728\u5408\u5e76\u6240\u6709\u5206\u6bb5\u540e\uff0c\u68c0\u67e5\u6240\u9009\u6c61\u67d3\u7269\u7684\u975e\u7a7a\u6bd4\u4f8b\u3002", "en": "Inspect non-null ratios for the selected pollutants after all chunks are merged."},
    "collection.quality_parquet": {"zh-CN": "\u5c06\u6570\u636e\u96c6\u4fdd\u6301\u4e3a\u53ef\u88ab dashboard \u76f4\u63a5\u52a0\u8f7d\u7684\u8868\u683c\u6587\u4ef6\u683c\u5f0f\u3002", "en": "Keep the dataset in a dashboard-loadable tabular file format."},
    "collection.risk_coverage": {"zh-CN": "\u5386\u53f2\u8986\u76d6\u8303\u56f4\u53d6\u51b3\u4e8e\u6240\u9009\u57ce\u5e02\u4ee5\u53ca Open-Meteo \u57df\u7684\u53ef\u7528\u6027\u3002", "en": "Historical coverage depends on the selected city and Open-Meteo domain availability."},
    "collection.risk_sampling": {"zh-CN": "\u5168\u7403 CAMS \u6570\u636e\u4e3a 3 \u5c0f\u65f6\u91c7\u6837\uff0c\u800c\u4e0d\u662f\u6309\u5c0f\u65f6\u91c7\u6837\uff0c\u56e0\u6b64\u4e0d\u540c\u5730\u533a\u7684\u65f6\u95f4\u5bc6\u5ea6\u53ef\u80fd\u4e0d\u540c\u3002", "en": "Global CAMS data is 3-hourly rather than hourly, so time density can differ by region."},
    "collection.progress_air_quality": {"zh-CN": "\u6b63\u5728\u83b7\u53d6\u7a7a\u6c14\u8d28\u91cf {start} -> {end}", "en": "Fetching air quality {start} -> {end}"},
    "collection.progress_weather": {"zh-CN": "\u6b63\u5728\u83b7\u53d6\u6c14\u8c61\u6570\u636e {start} -> {end}", "en": "Fetching weather {start} -> {end}"},
    "collection.progress_merge": {"zh-CN": "\u6b63\u5728\u5408\u5e76\u5404\u5206\u6bb5\u7ed3\u679c\u5e76\u6784\u5efa dashboard \u53ef\u7528\u6570\u636e\u96c6", "en": "Merging chunk outputs and building dashboard-ready dataset"},
    "collection.progress_saved": {"zh-CN": "\u6570\u636e\u96c6\u5df2\u4fdd\u5b58\u5230 {path}", "en": "Saved dataset to {path}"},
    "collection.weather_skipped": {"zh-CN": "{start} \u81f3 {end} \u7684\u6c14\u8c61\u8865\u5145\u5df2\u8df3\u8fc7\uff1a{error}", "en": "Weather supplement skipped for {start} to {end}: {error}"},
    "collection.no_rows": {"zh-CN": "\u91c7\u96c6\u5df2\u6267\u884c\u5b8c\u6210\uff0c\u4f46\u8ba1\u5212\u65f6\u95f4\u8303\u56f4\u5185\u672a\u8fd4\u56de\u4efb\u4f55\u7a7a\u6c14\u8d28\u91cf\u6570\u636e\u3002", "en": "The collection run completed, but no air-quality rows were returned for the planned range."},
    "collection.no_usable_rows": {"zh-CN": "\u91c7\u96c6\u5df2\u8fd4\u56de\u65f6\u95f4\u6233\uff0c\u4f46\u6240\u9009\u6c61\u67d3\u7269\u5728\u8be5\u65f6\u95f4\u7a97\u5185\u5747\u65e0\u53ef\u7528\u6570\u503c\u3002", "en": "The collection returned timestamps, but none of the selected pollutants had usable values in the planned window."},
    "collection.deepseek_proxy_attempt": {"zh-CN": "\u8bf7\u6c42\u57ce\u5e02 {requested} \u5728\u5f53\u524d\u6570\u636e\u6e90\u4e0b\u65e0\u53ef\u7528\u6c61\u67d3\u7269\u503c\uff0c\u6b63\u5728\u8bf7 DeepSeek \u63a8\u8350 {province} \u5185\u7684\u4ee3\u7406\u67e5\u8be2\u3002", "en": "Requested city {requested} had no usable pollutant coverage in the current source; asking DeepSeek for proxy queries inside {province}."},
    "collection.deepseek_proxy_used": {"zh-CN": "\u8bf7\u6c42\u57ce\u5e02 {requested} \u8986\u76d6\u8f83\u5f31\uff0c\u56e0\u6b64\u4f7f\u7528 {actual} \u4f5c\u4e3a\u540c\u7701\u7684\u53ef\u89c6\u5316\u4ee3\u7406\u6570\u636e\u3002", "en": "Requested city {requested} had weak coverage, so {actual} was used as a same-province proxy dataset for visualization."},
    "collection.deepseek_proxy_failed": {"zh-CN": "DeepSeek \u5df2\u63d0\u4f9b\u540c\u7701\u4ee3\u7406\u63d0\u793a\uff0c\u4f46\u672a\u627e\u5230\u4efb\u4f55\u6709\u6548\u7684\u7a7a\u6c14\u8d28\u91cf\u6570\u636e\u3002", "en": "DeepSeek suggested same-province proxy hints, but none produced usable air-quality data."},
}


def normalize_language(language: str | None) -> str:
    if language in LANGUAGE_OPTIONS:
        return str(language)
    return DEFAULT_LANGUAGE


def get_language() -> str:
    return normalize_language(st.session_state.get(LANGUAGE_STATE_KEY, DEFAULT_LANGUAGE))


def set_language(language: str) -> str:
    normalized = normalize_language(language)
    st.session_state[LANGUAGE_STATE_KEY] = normalized
    return normalized


def language_label(language: str) -> str:
    return LANGUAGE_OPTIONS[normalize_language(language)]


def t(key: str, language: str | None = None, **kwargs: object) -> str:
    normalized = normalize_language(language or get_language())
    entry = TRANSLATIONS.get(key, {})
    template = entry.get(normalized) or entry.get(DEFAULT_LANGUAGE) or key
    return template.format(**kwargs)


def render_language_selector(*, label: str | None = None, key: str = "language_selector") -> str:
    current = get_language()
    options = list(LANGUAGE_OPTIONS.keys())
    selected = st.selectbox(
        label or t("language.label", current),
        options=options,
        index=options.index(current),
        format_func=language_label,
        key=key,
    )
    return set_language(selected)


def weather_label(weather_key: str, language: str | None = None) -> str:
    return t(f"weather.{weather_key}", language)


def api_language(language: str | None = None) -> str:
    normalized = normalize_language(language or get_language())
    return "zh" if normalized == "zh-CN" else "en"


