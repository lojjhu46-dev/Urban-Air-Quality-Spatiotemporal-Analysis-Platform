# Catalog And Navigation I18n Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Localize the built-in location catalog display layer and the sidebar page navigation without changing English state values or query behavior.

**Architecture:** Keep the catalog's English values as canonical state and query inputs, then add a thin display-name layer for built-in continents, countries, regions, and cities. Hide Streamlit's default sidebar navigation and render a translated custom navigation list from a single helper used by `app.py` and all page scripts.

**Tech Stack:** Python, Streamlit, pytest

---

### Task 1: Add failing tests for localized catalog labels

**Files:**
- Modify: `D:\C\python\new_python\tests\test_agent_interaction.py`
- Test: `D:\C\python\new_python\tests\test_agent_interaction.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_non_china_city_option_exposes_localized_display_labels() -> None:
    option = city_option_from_path("North America", "United States", "California", "San Francisco")

    assert option.display_continent("zh-CN") == "北美洲"
    assert option.display_country("zh-CN") == "美国"
    assert option.display_province("zh-CN") == "加利福尼亚州"
    assert option.display_city("zh-CN") == "旧金山"
    assert option.path_label_for_language("zh-CN") == "北美洲 - 美国 - 加利福尼亚州 - 旧金山"
    assert option.city_query == "San Francisco"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_agent_interaction.py::test_non_china_city_option_exposes_localized_display_labels -v`
Expected: fail with `AttributeError` or assertion failure because the non-China display helpers do not localize those labels yet.

- [ ] **Step 3: Write minimal implementation**

```python
def display_continent(self, language: str = "en") -> str:
    ...

def display_country(self, language: str = "en") -> str:
    ...

def display_province(self, language: str = "en") -> str | None:
    ...

def display_city(self, language: str = "en") -> str:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_agent_interaction.py::test_non_china_city_option_exposes_localized_display_labels -v`
Expected: `PASS`

### Task 2: Add failing tests for translated sidebar navigation labels

**Files:**
- Create: `D:\C\python\new_python\tests\test_navigation.py`
- Test: `D:\C\python\new_python\tests\test_navigation.py`

- [ ] **Step 1: Write the failing test**

```python
def test_sidebar_navigation_items_are_localized() -> None:
    zh_items = sidebar_navigation_items("zh-CN")
    en_items = sidebar_navigation_items("en")

    assert zh_items[0].label == "首页"
    assert zh_items[1].label == "总览"
    assert zh_items[-1].label == "历史数据 Agent"
    assert en_items[0].label == "Home"
    assert en_items[2].label == "Spatiotemporal Playback"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_navigation.py -v`
Expected: fail because the navigation helper does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class SidebarNavItem:
    path: str
    label: str

def sidebar_navigation_items(language: str) -> list[SidebarNavItem]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_navigation.py -v`
Expected: `PASS`

### Task 3: Wire localized catalog labels into the Agent page

**Files:**
- Modify: `D:\C\python\new_python\src\agent_interaction.py`
- Modify: `D:\C\python\new_python\pages\4_Historical_Data_Agent.py`
- Modify: `D:\C\python\new_python\tests\test_agent_interaction.py`

- [ ] **Step 1: Add catalog display-name lookup helpers**

```python
def continent_display_name(continent: str, language: str = "en") -> str:
    ...

def country_display_name(continent: str, country: str, language: str = "en") -> str:
    ...

def province_display_name(continent: str, country: str, province: str | None, language: str = "en") -> str | None:
    ...

def city_display_name(continent: str, country: str, province: str | None, city: str, language: str = "en") -> str:
    ...
```

- [ ] **Step 2: Apply `format_func` to continent, country, province, and city selectboxes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_agent_interaction.py -v`
Expected: all agent interaction tests pass with localized display labels.

### Task 4: Render translated custom sidebar navigation and hide the default one

**Files:**
- Modify: `D:\C\python\new_python\.streamlit\config.toml`
- Create: `D:\C\python\new_python\src\navigation.py`
- Modify: `D:\C\python\new_python\src\i18n.py`
- Modify: `D:\C\python\new_python\app.py`
- Modify: `D:\C\python\new_python\pages\1_Overview.py`
- Modify: `D:\C\python\new_python\pages\2_Spatiotemporal_Playback.py`
- Modify: `D:\C\python\new_python\pages\3_Correlation_Analysis.py`
- Modify: `D:\C\python\new_python\pages\4_Historical_Data_Agent.py`
- Test: `D:\C\python\new_python\tests\test_navigation.py`

- [ ] **Step 1: Add navigation translation keys and helper module**

```python
NAV_ITEMS = (
    ("app.py", "nav.home"),
    ("pages/1_Overview.py", "nav.overview"),
    ("pages/2_Spatiotemporal_Playback.py", "nav.playback"),
    ("pages/3_Correlation_Analysis.py", "nav.correlation"),
    ("pages/4_Historical_Data_Agent.py", "nav.agent"),
)
```

- [ ] **Step 2: Disable Streamlit's default sidebar navigation**

```toml
[client]
showSidebarNavigation = false
```

- [ ] **Step 3: Call the shared navigation renderer from the app and every page**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_navigation.py tests/test_agent_interaction.py -v`
Expected: `PASS`

### Task 5: Run focused regression verification

**Files:**
- Test: `D:\C\python\new_python\tests\test_agent_interaction.py`
- Test: `D:\C\python\new_python\tests\test_navigation.py`
- Test: `D:\C\python\new_python\tests\test_i18n.py`

- [ ] **Step 1: Run the full focused regression set**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_agent_interaction.py tests/test_navigation.py tests/test_i18n.py -v`
Expected: all tests pass.
