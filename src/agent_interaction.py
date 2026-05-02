from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from src.china_city_catalog import (
    MAINLAND_CHINA_CITY_ROWS,
    TOTAL_PRC_PREFECTURE_LEVEL_CITIES,
    china_city_display_name,
    china_province_display_name,
)
from src.config import EUROPE_COUNTRY_CODES


def _normalize_catalog_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return ascii_text.strip().lower().replace(" ", "").replace("-", "").replace("'", "")


@dataclass(frozen=True, slots=True)
class AgentCityOption:
    continent: str
    country: str
    province: str | None
    city: str
    country_code: str
    sort_key: str
    query: str | None = None

    @property
    def city_query(self) -> str:
        return self.query or self.city

    @property
    def path_label(self) -> str:
        return self.path_label_for_language()

    def display_province(self, language: str = "en") -> str | None:
        if self.country_code.upper() == "CN":
            return china_province_display_name(self.province, language)
        return self.province

    def display_city(self, language: str = "en") -> str:
        if self.country_code.upper() == "CN":
            return china_city_display_name(self.province, self.city, language)
        return self.city

    def path_label_for_language(self, language: str = "en") -> str:
        parts = [self.continent, self.country]
        province = self.display_province(language)
        if province:
            parts.append(province)
        parts.append(self.display_city(language))
        return " - ".join(parts)

    @property
    def supported_start_year(self) -> int:
        return 2013 if self.country_code.upper() in EUROPE_COUNTRY_CODES else 2022

    @property
    def source_summary(self) -> tuple[str, str]:
        if self.country_code.upper() in EUROPE_COUNTRY_CODES:
            return "CAMS Europe", "hourly since 2013-01-01"
        return "Open-Meteo Global", "3-hourly since 2022-08-01"


_CHINA_CITY_OPTIONS = tuple(
    AgentCityOption(
        "Asia",
        "China",
        province,
        city,
        "CN",
        _normalize_catalog_token(city),
        query=query,
    )
    for province, city, query in MAINLAND_CHINA_CITY_ROWS
)


_CATALOG = (
    AgentCityOption("Africa", "Kenya", "Nairobi County", "Nairobi", "KE", "nairobi"),
    AgentCityOption("Africa", "South Africa", "Gauteng", "Johannesburg", "ZA", "johannesburg"),
    AgentCityOption("Africa", "South Africa", "Western Cape", "Cape Town", "ZA", "cape-town"),
    *_CHINA_CITY_OPTIONS,
    AgentCityOption("Asia", "India", "Karnataka", "Bengaluru", "IN", "bengaluru"),
    AgentCityOption("Asia", "India", "Delhi", "Delhi", "IN", "delhi"),
    AgentCityOption("Asia", "India", "Maharashtra", "Mumbai", "IN", "mumbai"),
    AgentCityOption("Asia", "Japan", "Fukuoka", "Fukuoka", "JP", "fukuoka"),
    AgentCityOption("Asia", "Japan", "Hokkaido", "Sapporo", "JP", "sapporo"),
    AgentCityOption("Asia", "Japan", "Kyoto", "Kyoto", "JP", "kyoto"),
    AgentCityOption("Asia", "Japan", "Osaka", "Osaka", "JP", "osaka"),
    AgentCityOption("Asia", "Japan", "Tokyo", "Tokyo", "JP", "tokyo"),
    AgentCityOption("Asia", "Singapore", None, "Singapore", "SG", "singapore"),
    AgentCityOption("Asia", "South Korea", "Busan", "Busan", "KR", "busan"),
    AgentCityOption("Asia", "South Korea", "Incheon", "Incheon", "KR", "incheon"),
    AgentCityOption("Asia", "South Korea", "Seoul", "Seoul", "KR", "seoul"),
    AgentCityOption("Asia", "United Arab Emirates", "Abu Dhabi", "Abu Dhabi", "AE", "abu-dhabi"),
    AgentCityOption("Asia", "United Arab Emirates", "Dubai", "Dubai", "AE", "dubai"),
    AgentCityOption("Europe", "France", "Auvergne-Rhone-Alpes", "Lyon", "FR", "lyon"),
    AgentCityOption("Europe", "France", "Ile-de-France", "Paris", "FR", "paris"),
    AgentCityOption("Europe", "France", "Provence-Alpes-Cote d'Azur", "Marseille", "FR", "marseille"),
    AgentCityOption("Europe", "Germany", "Berlin", "Berlin", "DE", "berlin"),
    AgentCityOption("Europe", "Germany", "Hesse", "Frankfurt", "DE", "frankfurt"),
    AgentCityOption("Europe", "Germany", "Hamburg", "Hamburg", "DE", "hamburg"),
    AgentCityOption("Europe", "Germany", "Bavaria", "Munich", "DE", "munich"),
    AgentCityOption("Europe", "Italy", "Lazio", "Rome", "IT", "rome"),
    AgentCityOption("Europe", "Italy", "Lombardy", "Milan", "IT", "milan"),
    AgentCityOption("Europe", "Netherlands", "North Holland", "Amsterdam", "NL", "amsterdam"),
    AgentCityOption("Europe", "Netherlands", "South Holland", "Rotterdam", "NL", "rotterdam"),
    AgentCityOption("Europe", "Poland", "Lesser Poland", "Krakow", "PL", "krakow"),
    AgentCityOption("Europe", "Poland", "Masovian", "Warsaw", "PL", "warsaw"),
    AgentCityOption("Europe", "Spain", "Catalonia", "Barcelona", "ES", "barcelona"),
    AgentCityOption("Europe", "Spain", "Community of Madrid", "Madrid", "ES", "madrid"),
    AgentCityOption("Europe", "Spain", "Valencian Community", "Valencia", "ES", "valencia"),
    AgentCityOption("Europe", "United Kingdom", "England", "London", "GB", "london"),
    AgentCityOption("Europe", "United Kingdom", "Scotland", "Edinburgh", "GB", "edinburgh"),
    AgentCityOption("Europe", "United Kingdom", "England", "Manchester", "GB", "manchester"),
    AgentCityOption("North America", "Canada", "Quebec", "Montreal", "CA", "montreal"),
    AgentCityOption("North America", "Canada", "Ontario", "Toronto", "CA", "toronto"),
    AgentCityOption("North America", "Canada", "British Columbia", "Vancouver", "CA", "vancouver"),
    AgentCityOption("North America", "Mexico", "Mexico City", "Mexico City", "MX", "mexico-city"),
    AgentCityOption("North America", "United States", "Illinois", "Chicago", "US", "chicago"),
    AgentCityOption("North America", "United States", "California", "Los Angeles", "US", "los-angeles"),
    AgentCityOption("North America", "United States", "New York", "New York", "US", "new-york"),
    AgentCityOption("North America", "United States", "California", "San Francisco", "US", "san-francisco"),
    AgentCityOption("North America", "United States", "Washington", "Seattle", "US", "seattle"),
    AgentCityOption("Oceania", "Australia", "Queensland", "Brisbane", "AU", "brisbane"),
    AgentCityOption("Oceania", "Australia", "Victoria", "Melbourne", "AU", "melbourne"),
    AgentCityOption("Oceania", "Australia", "Western Australia", "Perth", "AU", "perth"),
    AgentCityOption("Oceania", "Australia", "New South Wales", "Sydney", "AU", "sydney"),
    AgentCityOption("Oceania", "New Zealand", "Auckland", "Auckland", "NZ", "auckland"),
    AgentCityOption("Oceania", "New Zealand", "Wellington", "Wellington", "NZ", "wellington"),
    AgentCityOption("South America", "Argentina", "Buenos Aires", "Buenos Aires", "AR", "buenos-aires"),
    AgentCityOption("South America", "Brazil", "Rio de Janeiro", "Rio de Janeiro", "BR", "rio-de-janeiro"),
    AgentCityOption("South America", "Brazil", "Sao Paulo", "Sao Paulo", "BR", "sao-paulo"),
    AgentCityOption("South America", "Chile", "Santiago Metropolitan", "Santiago", "CL", "santiago"),
)

DEFAULT_CITY_PATH = ("Asia", "China", "Beijing Municipality", "Beijing")


def continent_labels() -> list[str]:
    return _unique_preserving_order(option.continent for option in _CATALOG)


def country_labels(continent: str) -> list[str]:
    return sorted(
        {option.country for option in _CATALOG if option.continent == continent},
        key=_normalize_sort_key,
    )


def province_labels(continent: str, country: str) -> list[str]:
    return sorted(
        {option.province for option in _CATALOG if option.continent == continent and option.country == country and option.province},
        key=_normalize_sort_key,
    )


def city_labels(continent: str, country: str, province: str | None = None) -> list[str]:
    return [option.city for option in city_options(continent, country, province)]


def city_options(continent: str, country: str, province: str | None = None) -> list[AgentCityOption]:
    filtered = [
        option
        for option in _CATALOG
        if option.continent == continent
        and option.country == country
        and ((province or None) == option.province if province else True)
    ]
    return sorted(filtered, key=lambda option: option.sort_key)


def city_option_from_path(continent: str, country: str, province: str | None, city: str) -> AgentCityOption:
    for option in _CATALOG:
        if option.continent == continent and option.country == country and option.province == (province or None) and option.city == city:
            return option
    raise ValueError(f"Unknown city selection: {continent=} {country=} {province=} {city=}")


def build_agent_instruction(
    city_option: AgentCityOption,
    start_year: int,
    end_year: int,
    pollutants: list[str],
    weather_fields: list[str],
    *,
    language: str = "en",
) -> str:
    pollutant_text = ", ".join(_unique_lower(pollutants)) or "pm25"
    weather_text = ", ".join(_unique_lower(weather_fields))

    if language == "zh-CN":
        weather_clause = f"附加气象字段 {weather_text}" if weather_text else "不附加气象字段"
        return (
            f"目标城市限定为 {city_option.path_label_for_language(language)}。"
            f"请采集 {start_year} 年到 {end_year} 年的 {pollutant_text} 历史空气质量数据，"
            f"{weather_clause}，并保存为当前 dashboard 可直接加载的数据集。"
        )

    weather_clause = f"include weather fields {weather_text}" if weather_text else "skip weather fields"
    return (
        f"Limit the target city to {city_option.path_label_for_language(language)}. "
        f"Collect historical air-quality data for {pollutant_text} from {start_year} to {end_year}, "
        f"{weather_clause}, and save a dataset that the current dashboard can load directly."
    )


def build_city_search_queries(city_option: AgentCityOption) -> list[str]:
    province = city_option.province or ""
    return _unique_strings(
        [
            city_option.city_query,
            f"{city_option.city} {province}".strip(),
            f"{city_option.city} {city_option.country}".strip(),
            f"{city_option.city_query} {city_option.country_code}".strip(),
        ]
    )


def candidate_matches_city_option(
    city_option: AgentCityOption,
    *,
    candidate_name: str,
    candidate_admin1: str | None,
    candidate_country_code: str | None,
) -> bool:
    if city_option.country_code and str(candidate_country_code or "").upper() != city_option.country_code.upper():
        return False

    city_name = _normalize_location_name(city_option.city)
    normalized_name = _normalize_location_name(candidate_name)
    if city_name and normalized_name != city_name:
        return False

    province_name = _normalize_location_name(city_option.province or "")
    normalized_admin1 = _normalize_location_name(candidate_admin1 or "")
    if province_name and normalized_admin1:
        return province_name == normalized_admin1 or province_name in normalized_admin1 or normalized_admin1 in province_name
    return True


def option_has_province_step(continent: str, country: str) -> bool:
    return any(option.province for option in _CATALOG if option.continent == continent and option.country == country)


def default_city_option() -> AgentCityOption:
    return city_option_from_path(*DEFAULT_CITY_PATH)


def china_city_count() -> int:
    return len(_CHINA_CITY_OPTIONS)


def china_city_coverage_ratio() -> float:
    return china_city_count() / TOTAL_PRC_PREFECTURE_LEVEL_CITIES


def china_province_labels() -> list[str]:
    return sorted({option.province for option in _CHINA_CITY_OPTIONS if option.province}, key=_normalize_sort_key)


def resolve_china_catalog_province(value: str | None) -> str | None:
    normalized = _normalize_location_name(value or "")
    for province in china_province_labels():
        province_key = _normalize_location_name(province)
        if normalized == province_key or normalized in province_key or province_key in normalized:
            return province
    return None


def china_province_city_names(province: str | None) -> list[str]:
    matched_province = resolve_china_catalog_province(province)
    if not matched_province:
        return []
    return [option.city for option in city_options("Asia", "China", matched_province)]


def _normalize_location_name(value: str) -> str:
    compact = _normalize_catalog_token(value)
    for suffix in (
        "municipality",
        "province",
        "state",
        "region",
        "county",
        "prefecture",
        "district",
        "autonomousregion",
        "specialadministrativeregion",
        "city",
    ):
        compact = compact.replace(suffix, "")
    return compact


def _normalize_sort_key(value: str | None) -> str:
    return _normalize_location_name(value or "")


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        output.append(text)
        seen.add(text)
    return output


def _unique_lower(values: list[str]) -> list[str]:
    return [item.lower() for item in _unique_strings(values)]


def _unique_preserving_order(values) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        output.append(value)
        seen.add(value)
    return output
