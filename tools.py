# tools.py

import os
import json
import requests
from dotenv import load_dotenv  # 添加这个导入

# ========== 加载 .env 文件 ==========
load_dotenv()  # 读取 .env 文件中的环境变量

# 从环境变量获取天气API Key
AMAP_API_KEY = os.getenv('AMAP_WEATHER_KEY')

# ============================================
# tools 列表
# ============================================
tools = [
    # ... 你之前的工具 ...
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询某个城市的实时天气情况",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，例如'北京'、'上海'",
                    }
                },
                "required": ["city"],
            },
        },
    },
]

# ============================================
# 天气查询函数
# ============================================
def get_weather(city):
    """
    查询指定城市的实时天气
    使用高德地图天气API
    """
    # 检查API Key是否存在
    if not AMAP_API_KEY:
        return {
            "status": "error",
            "message": "天气服务未配置，请在.env文件中设置AMAP_WEATHER_KEY"
        }
    
    # 第一步：用城市名获取adcode（城市编码）
    geo_url = "https://restapi.amap.com/v3/geocode/geo"
    geo_params = {
        "address": city,
        "key": AMAP_API_KEY
    }
    
    try:
        geo_response = requests.get(geo_url, params=geo_params, timeout=10)
        geo_data = geo_response.json()
        
        if geo_data.get("status") != "1" or not geo_data.get("geocodes"):
            return {
                "status": "error",
                "message": f"未找到城市 '{city}'，请检查名称是否正确"
            }
        
        adcode = geo_data["geocodes"][0]["adcode"]
        
        # 第二步：用adcode查询天气
        weather_url = "https://restapi.amap.com/v3/weather/weatherInfo"
        weather_params = {
            "city": adcode,
            "key": AMAP_API_KEY,
            "extensions": "base"
        }
        
        weather_response = requests.get(weather_url, params=weather_params, timeout=10)
        weather_data = weather_response.json()
        
        if weather_data.get("status") != "1":
            return {
                "status": "error",
                "message": weather_data.get("info", "获取天气信息失败")
            }
        
        lives = weather_data.get("lives", [])
        if not lives:
            return {
                "status": "error",
                "message": "未获取到天气数据"
            }
        
        live = lives[0]
        return {
            "status": "success",
            "city": live.get("city", city),
            "weather": live.get("weather", "未知"),
            "temperature": live.get("temperature", "未知"),
            "wind_direction": live.get("winddirection", "未知"),
            "wind_power": live.get("windpower", "未知"),
            "humidity": live.get("humidity", "未知"),
            "report_time": live.get("reporttime", "未知")
        }
        
    except requests.exceptions.Timeout:
        return {"status": "error", "message": "请求超时，请稍后重试"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"网络请求失败: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"获取天气失败: {str(e)}"}

# ============================================
# 函数映射表
# ============================================
available_functions = {
    "get_weather": get_weather,
}