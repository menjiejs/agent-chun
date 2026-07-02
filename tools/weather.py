import os

import requests
from dotenv import load_dotenv

load_dotenv()

AMAP_API_KEY = os.getenv("AMAP_WEATHER_KEY")


def get_weather(city):
    """
    查询指定城市的实时天气
    使用高德地图天气API
    """
    if not AMAP_API_KEY:
        return {
            "status": "error",
            "message": "天气服务未配置，请在.env文件中设置AMAP_WEATHER_KEY",
        }

    geo_url = "https://restapi.amap.com/v3/geocode/geo"
    geo_params = {
        "address": city,
        "key": AMAP_API_KEY,
    }

    try:
        geo_response = requests.get(geo_url, params=geo_params, timeout=10)
        geo_data = geo_response.json()

        if geo_data.get("status") != "1" or not geo_data.get("geocodes"):
            return {
                "status": "error",
                "message": f"未找到城市 '{city}'，请检查名称是否正确",
            }

        adcode = geo_data["geocodes"][0]["adcode"]

        weather_url = "https://restapi.amap.com/v3/weather/weatherInfo"
        weather_params = {
            "city": adcode,
            "key": AMAP_API_KEY,
            "extensions": "base",
        }

        weather_response = requests.get(weather_url, params=weather_params, timeout=10)
        weather_data = weather_response.json()

        if weather_data.get("status") != "1":
            return {
                "status": "error",
                "message": weather_data.get("info", "获取天气信息失败"),
            }

        lives = weather_data.get("lives", [])
        if not lives:
            return {
                "status": "error",
                "message": "未获取到天气数据",
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
            "report_time": live.get("reporttime", "未知"),
        }

    except requests.exceptions.Timeout:
        return {"status": "error", "message": "请求超时，请稍后重试"}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"网络请求失败: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"获取天气失败: {str(e)}"}
