import json
import os
import re
import random
import time
import threading
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.config import Config

BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")

bedrock = boto3.client(
    "bedrock-runtime",
    region_name="ap-northeast-1",
    config=Config(read_timeout=60, connect_timeout=10),
)

# Nominatim は 1req/sec の制限があるためロックで直列化
_NOM_LOCK = threading.Lock()

PROMPT_TEMPLATE = """あなたはバイクツーリングの専門家です。
以下の情報を元に、日帰りツーリングコースを3つ提案してください。

現在地: 緯度{lat:.4f}, 経度{lon:.4f}
現在の天気: {weather}、気温{temp}℃
生成ID（毎回異なるコースを選ぶために使用）: {seed}

必ず以下のJSON形式のみで出力してください（説明文や前置き不要）:
{{"courses": [
  {{
    "name": "コース名",
    "distance_km": 数値,
    "duration_hours": 数値,
    "return_hours": 数値,
    "return_note": "帰路の方法（例: 高速で帰還、来た道を折り返す、国道○号経由）",
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
    "best_season": "おすすめ季節（例: 5月〜10月）",
    "tags": ["🌊 海沿い", "⛰ 峠あり"]
  }}
]}}

road_typesに使える値: 「峠道」「山道」「高速道路」「国道」「県道」「海岸線」「一般道」
rest_spotsのtypeに使える値: 「道の駅」「温泉」「展望台」「カフェ」「食事処」「観光地」「ガソリンスタンド」

条件:
- 3コースは距離・方向が異なること（近距離・中距離・遠距離）
- 片道200km以内の日帰り圏内
- 天気が雨・曇りの場合は屋内施設や温泉を多く含める
- destinationはGoogleマップで検索できる正確な地名
- highlightsは2〜3個の具体的な見どころ
- difficultyは「初級」「中級」「上級」のいずれか
- 3コースすべてに同じ構造のJSONを返す
- photo_spotはWikipediaに記事が存在しそうな有名な地名にする（観光地・湖・峠・温泉地など）
- duration_hoursは現在地→目的地の片道所要時間（一般道40km/h・高速60km/hで計算し、休憩・観光1〜2時間を加算した現実的な値にすること）
- return_hoursは目的地→現在地の帰路所要時間（同様の計算基準）
- return_noteは帰路の具体的な方法を10〜20文字程度で記述
- 生成IDが変わるたびに必ず別の地域・コースを選ぶこと（同じ現在地でも毎回違う提案をする）
- tagsは「🌊 海沿い」「⛰ 峠あり」「🌸 景色良し」「🏯 歴史スポット」「🌿 自然豊か」「🛣 高速メイン」「🐟 グルメ」「♨️ 温泉あり」の中から該当するものを1〜3個選んで配列で返すこと

rest_spotsのルール（最重要）:
- 2〜4箇所の具体的なスポット名を必ず入れる
- 必ず「現在地 → スポット1 → スポット2 → 目的地」の地理的順序で並べる
- 途中で来た道を戻るような折り返しルートにしない（一筆書きのスムーズな動線）
- 各スポットは実際にそのルート上または近傍にある場所を選ぶ
- Googleマップでwaypoints順に設定した時に自然なルートになること"""

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
}


def nominatim_geocode(name, origin_lat, origin_lon):
    """地名をNominatimでジオコーディング。(lat, lon) または (None, None) を返す。"""
    params = {
        "q": name,
        "format": "json",
        "limit": 1,
        "countrycodes": "jp",
        "accept-language": "ja",
        # 現在地周辺を優先（日本全国から外れた結果を抑制）
        "viewbox": f"{origin_lon-4},{origin_lat-4},{origin_lon+4},{origin_lat+4}",
        "bounded": 0,
    }
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "zer0-touring-app/1.0"})
    try:
        with _NOM_LOCK:
            with urllib.request.urlopen(req, timeout=4) as r:
                data = json.loads(r.read())
            time.sleep(0.25)  # 1req/sec 制限を守る
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"[geocode] {name}: {e}")
    return None, None


def osrm_route(waypoints):
    """OSRMで実道路距離・所要時間を取得。(distance_km, duration_hours) または (None, None) を返す。"""
    # 座標は lon,lat の順（OSRM仕様）
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    url = f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=false"
    req = urllib.request.Request(url, headers={"User-Agent": "zer0-touring-app/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            dist_km = round(route["distance"] / 1000)
            # 走行時間 + 観光・休憩 1.5h
            duration_hours = round(route["duration"] / 3600 + 1.5, 1)
            return dist_km, duration_hours
    except Exception as e:
        print(f"[osrm] {e}")
    return None, None


def enrich_course(course, origin_lat, origin_lon):
    """
    コースの全ウェイポイント（現在地→立ち寄りスポット→目的地）を
    ジオコーディングしてOSRMで実距離・所要時間を上書きする。
    失敗時はAI推定値をそのまま維持。
    """
    waypoints = [(origin_lat, origin_lon)]

    # rest_spots（順番通り） + destination を順にジオコーディング
    spot_names = [s["name"] for s in course.get("rest_spots", []) if s.get("name")]
    spot_names.append(course.get("destination", ""))

    geocoded_count = 0
    for name in spot_names:
        if not name:
            continue
        lat, lon = nominatim_geocode(name, origin_lat, origin_lon)
        if lat is not None:
            waypoints.append((lat, lon))
            geocoded_count += 1

    print(f"[enrich] {course.get('name','')} waypoints={len(waypoints)} (geocoded={geocoded_count}/{len(spot_names)})")

    if len(waypoints) < 2:
        return

    dist_km, duration_hours = osrm_route(waypoints)
    if dist_km is not None:
        course["distance_km"] = dist_km
        course["duration_hours"] = duration_hours
        # 帰路は立ち寄りなし分だけ短め
        course["return_hours"] = round(duration_hours - 0.5, 1)
        print(f"[enrich] {course.get('name','')} -> {dist_km}km {duration_hours}h")


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

    seed = random.randint(100000, 999999)
    prompt = PROMPT_TEMPLATE.format(lat=lat, lon=lon, weather=weather, temp=temp, seed=seed)

    try:
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2048,
                "temperature": 1.0,
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

    # OSRM で実距離・所要時間に上書き（タイムアウト余裕がある場合のみ）
    if context.get_remaining_time_in_millis() > 12000:
        def _enrich(course):
            try:
                enrich_course(course, lat, lon)
            except Exception as e:
                print(f"[ERROR] enrich: {e}")
            return course

        with ThreadPoolExecutor(max_workers=3) as executor:
            courses = list(executor.map(_enrich, courses))
    else:
        print("[WARN] Skipped OSRM enrichment: insufficient time remaining")

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({"courses": courses}, ensure_ascii=False),
    }
