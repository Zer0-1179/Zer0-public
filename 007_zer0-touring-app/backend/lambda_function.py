import json
import os
import re
import boto3
from botocore.config import Config

BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")

bedrock = boto3.client(
    "bedrock-runtime",
    region_name="ap-northeast-1",
    config=Config(read_timeout=60, connect_timeout=10),
)

PROMPT_TEMPLATE = """あなたはバイクツーリングの専門家です。
以下の情報を元に、日帰りツーリングコースを3つ提案してください。

現在地: 緯度{lat:.4f}, 経度{lon:.4f}
現在の天気: {weather}、気温{temp}℃

必ず以下のJSON形式のみで出力してください（説明文や前置き不要）:
{{"courses": [
  {{
    "name": "コース名",
    "distance_km": 数値,
    "duration_hours": 数値,
    "highlights": ["メインの見どころ1", "メインの見どころ2", "メインの見どころ3"],
    "destination": "目的地名",
    "photo_spot": "Wikipediaで検索できる短い場所名（例: 江の島、箱根、奥多摩湖）",
    "difficulty": "初級",
    "road_types": ["国道", "県道"],
    "rest_spots": [
      {{"name": "道の駅 ○○", "type": "道の駅"}},
      {{"name": "○○温泉", "type": "温泉"}}
    ],
    "caution": "走行上の注意点（なければ空文字）",
    "best_season": "おすすめ季節（例: 5月〜10月）"
  }}
]}}

road_typesに使える値: 「峠道」「山道」「高速道路」「国道」「県道」「海岸線」「一般道」
rest_spotsのtypeに使える値: 「道の駅」「温泉」「展望台」「カフェ」「食事処」「観光地」「ガソリンスタンド」

条件:
- 3コースは距離・方向が異なること（近距離・中距離・遠距離）
- 片道200km以内の日帰り圏内
- 天気が雨・曇りの場合は屋内施設や温泉を多く含める
- destinationはGoogleマップで検索できる正確な地名
- rest_spotsは2〜4箇所の具体的なスポット名を必ず入れる
- highlightsは2〜3個の具体的な見どころ
- difficultyは「初級」「中級」「上級」のいずれか
- 3コースすべてに同じ構造のJSONを返す
- photo_spotはWikipediaに記事が存在しそうな有名な地名にする（観光地・湖・峠・温泉地など）"""

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
}


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        body = json.loads(event.get("body") or "{}")
        lat = float(body["latitude"])
        lon = float(body["longitude"])
        temp = body.get("temperature", 20)
        weather = body.get("weather_condition", "晴れ")
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Invalid request: {e}"}),
        }

    prompt = PROMPT_TEMPLATE.format(lat=lat, lon=lon, weather=weather, temp=temp)

    try:
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )
        result = json.loads(response["body"].read())
        text = result["content"][0]["text"]
        usage = result.get("usage", {})
        print(f"[Bedrock] in={usage.get('input_tokens', 0)}, out={usage.get('output_tokens', 0)}")
    except Exception as e:
        print(f"[ERROR] Bedrock: {e}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "AI service error"}),
        }

    try:
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")
        data = json.loads(json_match.group())
        courses = data["courses"]
        if len(courses) < 1:
            raise ValueError("No courses in response")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"[ERROR] Parse: {e}\nRaw: {text}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Failed to parse AI response"}),
        }

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({"courses": courses}, ensure_ascii=False),
    }
