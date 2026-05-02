# China City Zh Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show Chinese province and city names for mainland China when the app language is `zh-CN`, while preserving English catalog values for API queries and state.

**Architecture:** Keep the catalog's English values as the source of truth, then add a small display-name layer for mainland China in the catalog module. Surface that through `AgentCityOption` display helpers and Streamlit `format_func` hooks so selection state stays stable while rendered text changes by language.

**Tech Stack:** Python, Streamlit, pytest

---

### Task 1: Add regression tests for Chinese display names

**Files:**
- Modify: `D:\C\python\new_python\tests\test_agent_interaction.py`
- Test: `D:\C\python\new_python\tests\test_agent_interaction.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_china_city_option_exposes_chinese_display_labels() -> None:
    option = city_option_from_path("Asia", "China", "Beijing Municipality", "Beijing")

    assert option.display_province("zh-CN") == "北京市"
    assert option.display_city("zh-CN") == "北京"
    assert option.path_label_for_language("zh-CN") == "Asia - China - 北京市 - 北京"
    assert option.city_query == "Beijing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_interaction.py::test_china_city_option_exposes_chinese_display_labels -v`
Expected: `AttributeError` or assertion failure because the display helpers do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@property
def path_label(self) -> str:
    return self.path_label_for_language()

def display_province(self, language: str = "en") -> str | None:
    ...

def display_city(self, language: str = "en") -> str:
    ...

def path_label_for_language(self, language: str = "en") -> str:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_interaction.py::test_china_city_option_exposes_chinese_display_labels -v`
Expected: `PASS`

### Task 2: Render Chinese names in the Streamlit selectors

**Files:**
- Modify: `D:\C\python\new_python\src\china_city_catalog.py`
- Modify: `D:\C\python\new_python\src\agent_interaction.py`
- Modify: `D:\C\python\new_python\pages\4_Historical_Data_Agent.py`
- Test: `D:\C\python\new_python\tests\test_agent_interaction.py`

- [ ] **Step 1: Add mainland China display-name helpers**

```python
def china_province_display_name(province: str | None, language: str = "en") -> str | None:
    ...

def china_city_display_name(province: str | None, city: str, language: str = "en") -> str:
    ...
```

- [ ] **Step 2: Thread the helpers through `AgentCityOption` and selector formatting**

```python
def format_city_option_label(city_label: str, *, continent: str, country: str, province: str | None, language: str) -> str:
    option = city_option_from_path(continent, country, province, city_label)
    return option.display_city(language)
```

- [ ] **Step 3: Run targeted regression tests**

Run: `pytest tests/test_agent_interaction.py -v`
Expected: all tests in the module pass.

### Task 3: Verify no regression in translation helpers

**Files:**
- Test: `D:\C\python\new_python\tests\test_i18n.py`

- [ ] **Step 1: Run the i18n tests**

Run: `pytest tests/test_i18n.py -v`
Expected: `PASS`

- [ ] **Step 2: Run both focused test modules together**

Run: `pytest tests/test_agent_interaction.py tests/test_i18n.py -v`
Expected: `PASS`
