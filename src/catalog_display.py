from __future__ import annotations

from src.china_city_catalog import china_city_display_name, china_province_display_name

CONTINENT_DISPLAY_NAMES = {
    "Africa": "非洲",
    "Asia": "亚洲",
    "Europe": "欧洲",
    "North America": "北美洲",
    "Oceania": "大洋洲",
    "South America": "南美洲",
}

COUNTRY_DISPLAY_NAMES = {
    ("Africa", "Kenya"): "肯尼亚",
    ("Africa", "South Africa"): "南非",
    ("Asia", "China"): "中国",
    ("Asia", "India"): "印度",
    ("Asia", "Japan"): "日本",
    ("Asia", "Singapore"): "新加坡",
    ("Asia", "South Korea"): "韩国",
    ("Asia", "United Arab Emirates"): "阿联酋",
    ("Europe", "France"): "法国",
    ("Europe", "Germany"): "德国",
    ("Europe", "Italy"): "意大利",
    ("Europe", "Netherlands"): "荷兰",
    ("Europe", "Poland"): "波兰",
    ("Europe", "Spain"): "西班牙",
    ("Europe", "United Kingdom"): "英国",
    ("North America", "Canada"): "加拿大",
    ("North America", "Mexico"): "墨西哥",
    ("North America", "United States"): "美国",
    ("Oceania", "Australia"): "澳大利亚",
    ("Oceania", "New Zealand"): "新西兰",
    ("South America", "Argentina"): "阿根廷",
    ("South America", "Brazil"): "巴西",
    ("South America", "Chile"): "智利",
}

PROVINCE_DISPLAY_NAMES = {
    ("Africa", "Kenya", "Nairobi County"): "内罗毕郡",
    ("Africa", "South Africa", "Gauteng"): "豪登省",
    ("Africa", "South Africa", "Western Cape"): "西开普省",
    ("Asia", "India", "Karnataka"): "卡纳塔克邦",
    ("Asia", "India", "Delhi"): "德里",
    ("Asia", "India", "Maharashtra"): "马哈拉施特拉邦",
    ("Asia", "Japan", "Fukuoka"): "福冈县",
    ("Asia", "Japan", "Hokkaido"): "北海道",
    ("Asia", "Japan", "Kyoto"): "京都府",
    ("Asia", "Japan", "Osaka"): "大阪府",
    ("Asia", "Japan", "Tokyo"): "东京都",
    ("Asia", "South Korea", "Busan"): "釜山广域市",
    ("Asia", "South Korea", "Incheon"): "仁川广域市",
    ("Asia", "South Korea", "Seoul"): "首尔特别市",
    ("Asia", "United Arab Emirates", "Abu Dhabi"): "阿布扎比",
    ("Asia", "United Arab Emirates", "Dubai"): "迪拜",
    ("Europe", "France", "Auvergne-Rhone-Alpes"): "奥弗涅-罗讷-阿尔卑斯大区",
    ("Europe", "France", "Ile-de-France"): "法兰西岛大区",
    ("Europe", "France", "Provence-Alpes-Cote d'Azur"): "普罗旺斯-阿尔卑斯-蓝色海岸大区",
    ("Europe", "Germany", "Berlin"): "柏林州",
    ("Europe", "Germany", "Hesse"): "黑森州",
    ("Europe", "Germany", "Hamburg"): "汉堡州",
    ("Europe", "Germany", "Bavaria"): "巴伐利亚州",
    ("Europe", "Italy", "Lazio"): "拉齐奥大区",
    ("Europe", "Italy", "Lombardy"): "伦巴第大区",
    ("Europe", "Netherlands", "North Holland"): "北荷兰省",
    ("Europe", "Netherlands", "South Holland"): "南荷兰省",
    ("Europe", "Poland", "Lesser Poland"): "小波兰省",
    ("Europe", "Poland", "Masovian"): "马佐夫舍省",
    ("Europe", "Spain", "Catalonia"): "加泰罗尼亚自治区",
    ("Europe", "Spain", "Community of Madrid"): "马德里自治区",
    ("Europe", "Spain", "Valencian Community"): "瓦伦西亚自治区",
    ("Europe", "United Kingdom", "England"): "英格兰",
    ("Europe", "United Kingdom", "Scotland"): "苏格兰",
    ("North America", "Canada", "Quebec"): "魁北克省",
    ("North America", "Canada", "Ontario"): "安大略省",
    ("North America", "Canada", "British Columbia"): "不列颠哥伦比亚省",
    ("North America", "Mexico", "Mexico City"): "墨西哥城",
    ("North America", "United States", "Illinois"): "伊利诺伊州",
    ("North America", "United States", "California"): "加利福尼亚州",
    ("North America", "United States", "New York"): "纽约州",
    ("North America", "United States", "Washington"): "华盛顿州",
    ("Oceania", "Australia", "Queensland"): "昆士兰州",
    ("Oceania", "Australia", "Victoria"): "维多利亚州",
    ("Oceania", "Australia", "Western Australia"): "西澳大利亚州",
    ("Oceania", "Australia", "New South Wales"): "新南威尔士州",
    ("Oceania", "New Zealand", "Auckland"): "奥克兰",
    ("Oceania", "New Zealand", "Wellington"): "惠灵顿",
    ("South America", "Argentina", "Buenos Aires"): "布宜诺斯艾利斯",
    ("South America", "Brazil", "Rio de Janeiro"): "里约热内卢州",
    ("South America", "Brazil", "Sao Paulo"): "圣保罗州",
    ("South America", "Chile", "Santiago Metropolitan"): "圣地亚哥首都大区",
}

CITY_DISPLAY_NAMES = {
    ("Africa", "Kenya", "Nairobi County", "Nairobi"): "内罗毕",
    ("Africa", "South Africa", "Gauteng", "Johannesburg"): "约翰内斯堡",
    ("Africa", "South Africa", "Western Cape", "Cape Town"): "开普敦",
    ("Asia", "India", "Karnataka", "Bengaluru"): "班加罗尔",
    ("Asia", "India", "Delhi", "Delhi"): "德里",
    ("Asia", "India", "Maharashtra", "Mumbai"): "孟买",
    ("Asia", "Japan", "Fukuoka", "Fukuoka"): "福冈",
    ("Asia", "Japan", "Hokkaido", "Sapporo"): "札幌",
    ("Asia", "Japan", "Kyoto", "Kyoto"): "京都",
    ("Asia", "Japan", "Osaka", "Osaka"): "大阪",
    ("Asia", "Japan", "Tokyo", "Tokyo"): "东京",
    ("Asia", "Singapore", None, "Singapore"): "新加坡",
    ("Asia", "South Korea", "Busan", "Busan"): "釜山",
    ("Asia", "South Korea", "Incheon", "Incheon"): "仁川",
    ("Asia", "South Korea", "Seoul", "Seoul"): "首尔",
    ("Asia", "United Arab Emirates", "Abu Dhabi", "Abu Dhabi"): "阿布扎比",
    ("Asia", "United Arab Emirates", "Dubai", "Dubai"): "迪拜",
    ("Europe", "France", "Auvergne-Rhone-Alpes", "Lyon"): "里昂",
    ("Europe", "France", "Ile-de-France", "Paris"): "巴黎",
    ("Europe", "France", "Provence-Alpes-Cote d'Azur", "Marseille"): "马赛",
    ("Europe", "Germany", "Berlin", "Berlin"): "柏林",
    ("Europe", "Germany", "Hesse", "Frankfurt"): "法兰克福",
    ("Europe", "Germany", "Hamburg", "Hamburg"): "汉堡",
    ("Europe", "Germany", "Bavaria", "Munich"): "慕尼黑",
    ("Europe", "Italy", "Lazio", "Rome"): "罗马",
    ("Europe", "Italy", "Lombardy", "Milan"): "米兰",
    ("Europe", "Netherlands", "North Holland", "Amsterdam"): "阿姆斯特丹",
    ("Europe", "Netherlands", "South Holland", "Rotterdam"): "鹿特丹",
    ("Europe", "Poland", "Lesser Poland", "Krakow"): "克拉科夫",
    ("Europe", "Poland", "Masovian", "Warsaw"): "华沙",
    ("Europe", "Spain", "Catalonia", "Barcelona"): "巴塞罗那",
    ("Europe", "Spain", "Community of Madrid", "Madrid"): "马德里",
    ("Europe", "Spain", "Valencian Community", "Valencia"): "瓦伦西亚",
    ("Europe", "United Kingdom", "England", "London"): "伦敦",
    ("Europe", "United Kingdom", "Scotland", "Edinburgh"): "爱丁堡",
    ("Europe", "United Kingdom", "England", "Manchester"): "曼彻斯特",
    ("North America", "Canada", "Quebec", "Montreal"): "蒙特利尔",
    ("North America", "Canada", "Ontario", "Toronto"): "多伦多",
    ("North America", "Canada", "British Columbia", "Vancouver"): "温哥华",
    ("North America", "Mexico", "Mexico City", "Mexico City"): "墨西哥城",
    ("North America", "United States", "Illinois", "Chicago"): "芝加哥",
    ("North America", "United States", "California", "Los Angeles"): "洛杉矶",
    ("North America", "United States", "New York", "New York"): "纽约",
    ("North America", "United States", "California", "San Francisco"): "旧金山",
    ("North America", "United States", "Washington", "Seattle"): "西雅图",
    ("Oceania", "Australia", "Queensland", "Brisbane"): "布里斯班",
    ("Oceania", "Australia", "Victoria", "Melbourne"): "墨尔本",
    ("Oceania", "Australia", "Western Australia", "Perth"): "珀斯",
    ("Oceania", "Australia", "New South Wales", "Sydney"): "悉尼",
    ("Oceania", "New Zealand", "Auckland", "Auckland"): "奥克兰",
    ("Oceania", "New Zealand", "Wellington", "Wellington"): "惠灵顿",
    ("South America", "Argentina", "Buenos Aires", "Buenos Aires"): "布宜诺斯艾利斯",
    ("South America", "Brazil", "Rio de Janeiro", "Rio de Janeiro"): "里约热内卢",
    ("South America", "Brazil", "Sao Paulo", "Sao Paulo"): "圣保罗",
    ("South America", "Chile", "Santiago Metropolitan", "Santiago"): "圣地亚哥",
}


def continent_display_name(continent: str, language: str = "en") -> str:
    if language != "zh-CN":
        return continent
    return CONTINENT_DISPLAY_NAMES.get(continent, continent)


def country_display_name(continent: str, country: str, language: str = "en") -> str:
    if language != "zh-CN":
        return country
    return COUNTRY_DISPLAY_NAMES.get((continent, country), country)


def province_display_name(continent: str, country: str, province: str | None, language: str = "en") -> str | None:
    if province is None:
        return None
    if country == "China":
        return china_province_display_name(province, language)
    if language != "zh-CN":
        return province
    return PROVINCE_DISPLAY_NAMES.get((continent, country, province), province)


def city_display_name(
    continent: str,
    country: str,
    province: str | None,
    city: str,
    language: str = "en",
) -> str:
    if country == "China":
        return china_city_display_name(province, city, language)
    if language != "zh-CN":
        return city
    return CITY_DISPLAY_NAMES.get((continent, country, province, city), city)
