from .weather import get_weather

tools = [
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

available_functions = {
    "get_weather": get_weather,
}
