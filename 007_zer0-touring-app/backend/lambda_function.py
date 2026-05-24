import json
import math
import os
import re
import random
import time
import threading
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import boto3
from botocore.config import Config

BEDROCK_MODEL_ID    = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
GMAPS_USAGE_PARAM   = "/zer0-touring/gmaps-usage"
GMAPS_FREE_LIMIT    = 9_900  # 10,000件の無料枠から100件バッファ（同時アクセス時のSSM非アトミック書き込みによる誤差対策）

bedrock = boto3.client(
    "bedrock-runtime",
    region_name="ap-northeast-1",
    config=Config(read_timeout=60, connect_timeout=10),
)
ssm = boto3.client("ssm", region_name="ap-northeast-1")

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
- difficultyは以下の基準で必ず正しく選ぶこと:
  初級 = 幹線国道・一般道メイン、峠なし、距離80km以内、初心者でも安心
  中級 = 一部峠道・ワインディングあり または 距離80〜150km、ある程度の経験が必要
  上級 = 本格的な峠道・山岳路メイン または 距離150km超 または 狭路・急カーブ多数
- 3コースすべてに同じ構造のJSONを返す
- photo_spotはWikipediaに記事が存在しそうな有名な地名にする（観光地・湖・峠・温泉地など）
- duration_hoursは現在地→目的地の純粋な走行時間（一般道40km/h・高速60km/hで計算。休憩・観光時間は含めない）
- return_hoursは目的地→現在地の帰路走行時間（同様の計算基準。休憩・観光時間は含めない）
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


MAX_WAYPOINT_KM = 200  # 日帰り圏内（片道200km以内）を超える座標は誤ジオコーディングとして捨てる

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def nominatim_geocode(name, origin_lat, origin_lon):
    """地名をNominatimでジオコーディング。(lat, lon) または (None, None) を返す。"""
    # ±3° (約300km) の範囲内に限定して誤ジオコーディングを防ぐ
    box = 3
    params = {
        "q": name,
        "format": "json",
        "limit": 1,
        "countrycodes": "jp",
        "accept-language": "ja",
        "viewbox": f"{origin_lon-box},{origin_lat-box},{origin_lon+box},{origin_lat+box}",
        "bounded": 1,  # viewbox 外は返さない
    }
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "zer0-touring-app/1.0"})
    try:
        with _NOM_LOCK:
            with urllib.request.urlopen(req, timeout=4) as r:
                data = json.loads(r.read())
            time.sleep(0.25)  # 1req/sec 制限を守る
        if data:
            lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
            dist = _haversine_km(origin_lat, origin_lon, lat, lon)
            if dist > MAX_WAYPOINT_KM:
                print(f"[geocode] SKIP {name}: {dist:.0f}km (too far)")
                return None, None
            print(f"[geocode] OK   {name}: ({lat:.4f},{lon:.4f}) {dist:.0f}km")
            return lat, lon
    except Exception as e:
        print(f"[geocode] ERR  {name}: {e}")
    return None, None


def osrm_route(waypoints):
    """OSRMで実道路距離を取得。(distance_km, None) または (None, None) を返す。所要時間は呼び出し側で算出する。"""
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
            # 日帰り圏外（500km超）は誤ジオコーディング起因として捨てる
            if dist_km > 500:
                print(f"[osrm] SKIP unreasonable route: {dist_km}km")
                return None, None
            print(f"[osrm] OK {dist_km}km")
            return dist_km, None
    except Exception as e:
        print(f"[osrm] ERR {e}")
    return None, None


def check_and_reserve_gmaps(n_courses=3):
    """今月の Google Maps 残枠を確認し、n_courses 分を予約する。
    使用可能なら True、無料枠超過または未設定なら False を返す。"""
    if not GOOGLE_MAPS_API_KEY:
        return False
    current_month = datetime.now().strftime("%Y-%m")
    try:
        try:
            resp = ssm.get_parameter(Name=GMAPS_USAGE_PARAM)
            data = json.loads(resp["Parameter"]["Value"])
        except ssm.exceptions.ParameterNotFound:
            data = {"month": "", "count": 0}

        if data.get("month") != current_month:
            data = {"month": current_month, "count": 0}

        if data["count"] + n_courses > GMAPS_FREE_LIMIT:
            print(f"[gmaps-usage] 無料枠上限 {data['count']}/{GMAPS_FREE_LIMIT} → OSRM使用")
            return False

        data["count"] += n_courses
        ssm.put_parameter(Name=GMAPS_USAGE_PARAM, Value=json.dumps(data), Type="String", Overwrite=True)
        print(f"[gmaps-usage] {current_month}: {data['count']}/{GMAPS_FREE_LIMIT}")
        return True
    except Exception as e:
        print(f"[gmaps-usage] ERR {e} → OSRM使用")
        return False


def google_maps_route(origin_lat, origin_lon, dest_lat, dest_lon):
    """Google Maps Directions API で高速道路込みの実走行時間・距離を取得。
    (distance_km, duration_hours) または (None, None) を返す。"""
    if not GOOGLE_MAPS_API_KEY:
        return None, None
    params = {
        "origin":      f"{origin_lat:.6f},{origin_lon:.6f}",
        "destination": f"{dest_lat:.6f},{dest_lon:.6f}",
        "mode":        "driving",
        "key":         GOOGLE_MAPS_API_KEY,
    }
    url = "https://maps.googleapis.com/maps/api/directions/json?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "zer0-touring-app/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        if data.get("status") != "OK" or not data.get("routes"):
            print(f"[gmaps] status={data.get('status')}")
            return None, None
        leg = data["routes"][0]["legs"][0]
        dist_km = round(leg["distance"]["value"] / 1000)
        duration_h = round(leg["duration"]["value"] / 3600, 1)
        if dist_km > 500:
            print(f"[gmaps] SKIP unreasonable: {dist_km}km")
            return None, None
        print(f"[gmaps] OK {dist_km}km {duration_h}h")
        return dist_km, duration_h
    except Exception as e:
        print(f"[gmaps] ERR {e}")
    return None, None


def fetch_dest_weather(lat, lon):
    """Open-Meteo で目的地の現在天気を取得。(temp, weather_code) または (None, None) を返す。"""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&current=temperature_2m,weathercode&timezone=auto"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "zer0-touring-app/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        current = data.get("current", {})
        return round(current["temperature_2m"]), int(current["weathercode"])
    except Exception as e:
        print(f"[dest-weather] ERR {e}")
    return None, None


def enrich_course(course, origin_lat, origin_lon, use_gmaps=True):
    """
    目的地（destination）をジオコーディングして距離・所要時間を取得する。
    use_gmaps=True のとき Google Maps Directions API を使用、False なら OSRM。
    失敗時は AI 推定値をそのまま維持。
    """
    dest_name = course.get("destination", "")
    if not dest_name:
        return

    dest_lat, dest_lon = nominatim_geocode(dest_name, origin_lat, origin_lon)
    if dest_lat is None:
        print(f"[enrich] {course.get('name','')} destination geocode failed, keeping AI estimate")
        return

    course["dest_lat"] = dest_lat
    course["dest_lon"] = dest_lon

    dist_km, duration_h = None, None

    if use_gmaps:
        dist_km, duration_h = google_maps_route(origin_lat, origin_lon, dest_lat, dest_lon)

    if dist_km is None:
        # OSRM フォールバック
        waypoints = [(origin_lat, origin_lon), (dest_lat, dest_lon)]
        dist_km, _ = osrm_route(waypoints)
        if dist_km is not None:
            if dist_km >= 80:
                avg_kmh = 70
            elif dist_km >= 40:
                avg_kmh = 55
            else:
                avg_kmh = 40
            duration_h = round(dist_km / avg_kmh, 1)
            print(f"[enrich/osrm] {course.get('name','')} -> {dist_km}km avg={avg_kmh}km/h {duration_h}h")

    if dist_km is not None:
        course["distance_km"] = dist_km
        course["duration_hours"] = duration_h
        course["return_hours"] = duration_h
        print(f"[enrich] {course.get('name','')} -> {dist_km}km {duration_h}h")

    dest_temp, dest_weather_code = fetch_dest_weather(dest_lat, dest_lon)
    if dest_temp is not None:
        course["dest_temp"] = dest_temp
        course["dest_weather_code"] = dest_weather_code
        print(f"[dest-weather] {dest_name}: {dest_temp}℃ code={dest_weather_code}")


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

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Coordinates out of range"}),
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

    # 今月の Google Maps 残枠を確認（3コース分予約）
    use_gmaps = check_and_reserve_gmaps(n_courses=len(courses))

    # 距離・所要時間を実データに上書き（タイムアウト余裕がある場合のみ）
    if context.get_remaining_time_in_millis() > 12000:
        def _enrich(course):
            try:
                enrich_course(course, lat, lon, use_gmaps=use_gmaps)
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
