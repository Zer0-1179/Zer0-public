import json
import math
import os
import re
import random
import string
import time
import threading
import base64
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import boto3
from botocore.config import Config

BEDROCK_MODEL_ID    = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
GMAPS_USAGE_PARAM   = "/zer0-touring/gmaps-usage"
GMAPS_FREE_LIMIT    = 9_900  # 10,000件の無料枠から100件バッファ（同時アクセス時のSSM非アトミック書き込みによる誤差対策）
DAILY_LIMIT         = int(os.environ.get("DAILY_LIMIT", "3"))
RATE_LIMIT_TABLE    = "zer0-touring-ratelimit"
SHARE_TABLE         = "zer0-touring-share"
SITE_URL            = "https://touring.zer0-infra.com"
ADMIN_TOKEN         = os.environ.get("ADMIN_TOKEN", "")

ALLOWED_ORIGINS = {
    "https://touring.zer0-infra.com",
    "http://localhost:4321",
}

bedrock = boto3.client(
    "bedrock-runtime",
    region_name="ap-northeast-1",
    config=Config(read_timeout=60, connect_timeout=10),
)
ssm      = boto3.client("ssm",      region_name="ap-northeast-1")
dynamodb = boto3.client("dynamodb", region_name="ap-northeast-1")

# Nominatim は 1req/sec の制限があるためロックで直列化
_NOM_LOCK = threading.Lock()


def _get_cors_headers(event):
    origin = (event.get("headers") or {}).get("origin", "")
    allowed = origin if origin in ALLOWED_ORIGINS else "https://touring.zer0-infra.com"
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": allowed,
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
    }


def _get_client_ip(event):
    # CloudFront が X-Forwarded-For の先頭に本物のクライアントIPを付与する
    xff = (event.get("headers") or {}).get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return (event.get("requestContext") or {}).get("http", {}).get("sourceIp", "unknown")


def get_usage(ip):
    """今日の使用回数を読み取る（カウントを増やさない）。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pk    = f"{ip}#{today}"
    try:
        resp = dynamodb.get_item(
            TableName=RATE_LIMIT_TABLE,
            Key={"pk": {"S": pk}},
            ProjectionExpression="#c",
            ExpressionAttributeNames={"#c": "count"},
        )
        used = int(resp.get("Item", {}).get("count", {}).get("N", 0))
    except Exception as e:
        print(f"[get-usage] ERR {e}")
        used = 0
    return used


def check_rate_limit(ip):
    """IP別・日別カウントを DynamoDB でアトミックに管理する。
    DAILY_LIMIT 以内なら True、超過なら False を返す。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pk    = f"{ip}#{today}"
    # TTL = 翌々日0時UTC（日付またぎ直後も安全に消える）
    ttl   = int((datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)).timestamp())
    try:
        dynamodb.update_item(
            TableName=RATE_LIMIT_TABLE,
            Key={"pk": {"S": pk}},
            UpdateExpression="ADD #c :one SET #ttl = if_not_exists(#ttl, :ttl)",
            ConditionExpression="attribute_not_exists(#c) OR #c < :limit",
            ExpressionAttributeNames={"#c": "count", "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":one":   {"N": "1"},
                ":ttl":   {"N": str(ttl)},
                ":limit": {"N": str(DAILY_LIMIT)},
            },
        )
        print(f"[rate-limit] {ip} OK (limit={DAILY_LIMIT}/day)")
        return True
    except dynamodb.exceptions.ConditionalCheckFailedException:
        print(f"[rate-limit] {ip} EXCEEDED (limit={DAILY_LIMIT}/day)")
        return False
    except Exception as e:
        # DynamoDB 障害時は通す（ユーザーを巻き込まない）
        print(f"[rate-limit] ERR {e} → allow")
        return True

PROMPT_TEMPLATE = """あなたはバイクツーリングの専門家です。
以下の情報を元に、日帰りツーリングコースを3つ提案してください。

現在地: 緯度{lat:.4f}, 経度{lon:.4f}
現在の天気: {weather}、気温{temp}℃
生成ID（毎回異なるコースを選ぶために使用）: {seed}{preferences_section}

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
    "outbound_spots": [
      {{"name": "道の駅 ○○", "type": "道の駅"}}
    ],
    "return_spots": [
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

outbound_spotsのルール（最重要）:
- 行きの経由地（現在地→目的地の途中に立ち寄る場所）を1〜3箇所
- 必ず「現在地 → スポット1 → スポット2 → 目的地」の地理的順序（目的地方向に向かいながら立ち寄れる場所）
- 来た道を戻るような逆方向のスポットは絶対に含めない
- Googleマップでwaypoints順に設定した時に自然な一筆書きルートになること

return_spotsのルール（最重要）:
- 帰りの経由地（目的地→現在地の途中に立ち寄る場所）を1〜2箇所
- 必ず「目的地 → スポット3 → 現在地」の地理的順序（現在地方向に向かいながら立ち寄れる場所）
- outbound_spotsとは別ルート・別スポットを選ぶ（同じ道を往復しない）"""



PREF_PROMPTS = {
    '峠道':       '峠道・ワインディングロードを必ず含むルートにする',
    '海沿い':     '海が見える海岸線ルートを優先する',
    '温泉':       '温泉施設への立ち寄りを必ず含める（return_spotsに温泉を入れる）',
    'グルメ':     '地元名物・グルメスポットへの立ち寄りを優先する',
    '絶景':       '展望台・絶景スポットを優先して組み込む',
    '自然':       '山・森・高原・渓谷など自然豊かなスポットを優先して組み込む',
    '歴史':       '神社・寺・城・史跡など歴史文化スポットへの立ち寄りを優先する',
    'ガッツリ走る': '立ち寄りを最小限にして走行距離・ドライブ時間を重視し、より遠方の目的地を選ぶ',
    'のんびり':   'カフェ・道の駅での休憩を多めに組み込み、距離は短めでゆったりペースにする',
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


def _is_on_route(slat, slon, olat, olon, dlat, dlon, margin_deg=0.5):
    """スポットが origin→destination の経路コリドー内にあるか確認（バウンディングボックス+マージン）。"""
    min_lat = min(olat, dlat) - margin_deg
    max_lat = max(olat, dlat) + margin_deg
    min_lon = min(olon, dlon) - margin_deg
    max_lon = max(olon, dlon) + margin_deg
    return min_lat <= slat <= max_lat and min_lon <= slon <= max_lon


def geocode_and_filter_spots(spots, origin_lat, origin_lon, dest_lat, dest_lon, reverse=False):
    """
    スポットリストをジオコードし、ルート上にないものを除外して lat/lon を付与する。
    reverse=True のとき帰路方向（dest→origin）でフィルタリング。
    """
    result = []
    for spot in spots:
        lat, lon = nominatim_geocode(spot["name"], origin_lat, origin_lon)
        if lat is None:
            continue
        if reverse:
            on_route = _is_on_route(lat, lon, dest_lat, dest_lon, origin_lat, origin_lon)
        else:
            on_route = _is_on_route(lat, lon, origin_lat, origin_lon, dest_lat, dest_lon)
        if on_route:
            result.append({**spot, "lat": lat, "lon": lon})
        else:
            print(f"[waypoint] SKIP {spot['name']}: off-route ({lat:.4f},{lon:.4f})")
    return result


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

    # outbound_spots/return_spots をジオコードしてルート外を除外
    raw_out = course.get("outbound_spots") or course.get("rest_spots") or []
    raw_ret = course.get("return_spots") or []
    course["outbound_spots"] = geocode_and_filter_spots(raw_out, origin_lat, origin_lon, dest_lat, dest_lon, reverse=False)
    course["return_spots"]   = geocode_and_filter_spots(raw_ret, origin_lat, origin_lon, dest_lat, dest_lon, reverse=True)

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


def _short_id(n=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))

def _fetch_wiki_photo(spot):
    if not spot:
        return None
    try:
        url = f"https://ja.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(spot)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Zer0-Touring/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            thumb = data.get("thumbnail", {}).get("source", "")
            return re.sub(r'/\d+px-', '/800px-', thumb) if thumb else None
    except Exception:
        return None

def _handle_share_post(event, cors):
    try:
        body = json.loads(event.get("body") or "{}")
        course = body.get("course")
        if not course or not isinstance(course, dict):
            raise ValueError("course required")
    except Exception as e:
        return {"statusCode": 400, "headers": cors, "body": json.dumps({"error": str(e)})}

    photo_url  = _fetch_wiki_photo(course.get("photo_spot", ""))
    short_id   = _short_id(6)
    ttl        = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    # JS の btoa(encodeURIComponent(JSON.stringify(course))) と同等のエンコード
    course_b64 = base64.b64encode(
        urllib.parse.quote(json.dumps(course, ensure_ascii=False), safe="").encode("ascii")
    ).decode("ascii")

    dynamodb.put_item(
        TableName=SHARE_TABLE,
        Item={
            "pk":          {"S": short_id},
            "course_b64":  {"S": course_b64},
            "photo_url":   {"S": photo_url or ""},
            "name":        {"S": course.get("name", "ツーリングコース")},
            "destination": {"S": course.get("destination", "")},
            "duration":    {"S": str(course.get("duration_hours", ""))},
            "tags":        {"S": json.dumps(course.get("tags", []), ensure_ascii=False)},
            "ttl":         {"N": str(ttl)},
        },
    )
    return {"statusCode": 200, "headers": cors,
            "body": json.dumps({"url": f"{SITE_URL}/s/{short_id}"})}

def _handle_share_get(short_id):
    html_headers = {"Content-Type": "text/html; charset=utf-8"}
    try:
        item = dynamodb.get_item(
            TableName=SHARE_TABLE, Key={"pk": {"S": short_id}}
        ).get("Item")
    except Exception:
        item = None

    if not item:
        return {"statusCode": 404, "headers": html_headers,
                "body": "<html><body>このリンクは無効か期限切れです。</body></html>"}

    name       = item.get("name", {}).get("S", "ツーリングコース")
    dest       = item.get("destination", {}).get("S", "")
    duration   = item.get("duration", {}).get("S", "")
    photo_url  = item.get("photo_url", {}).get("S", "") or f"{SITE_URL}/icons/icon-512.png"
    course_b64 = item.get("course_b64", {}).get("S", "")
    try:
        tags = json.loads(item.get("tags", {}).get("S", "[]"))
    except Exception:
        tags = []

    og_title = f"{name} | Zer0 Touring"
    parts = []
    if dest:
        parts.append(f"目的地: {dest}")
    if duration:
        try:
            h = float(duration)
            parts.append(f"約{int(h)}時間{int((h % 1) * 60):02d}分")
        except Exception:
            pass
    if tags:
        parts.append(" ".join(tags[:3]))
    og_desc = " · ".join(parts) if parts else "AIが提案する日帰りバイクツーリングコース"

    redirect = f"{SITE_URL}/?course={course_b64}"
    # og:image の Wikimedia URL はクローラーがそのまま取得できるため CSP 不要
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:image" content="{photo_url}">
<meta property="og:url" content="{SITE_URL}/s/{short_id}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{og_title}">
<meta name="twitter:description" content="{og_desc}">
<meta name="twitter:image" content="{photo_url}">
<meta http-equiv="refresh" content="0; url={redirect}">
<script>location.replace({json.dumps(redirect)})</script>
</head>
<body>リダイレクト中...</body>
</html>"""
    return {"statusCode": 200, "headers": html_headers, "body": html}


def lambda_handler(event, context):
    cors   = _get_cors_headers(event)
    http   = (event.get("requestContext") or {}).get("http", {})
    method = http.get("method", "")
    path   = http.get("path", "")

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": cors, "body": ""}

    # GET /s/{id} — OGP HTML + リダイレクト（レートリミット対象外）
    if method == "GET" and path.startswith("/s/"):
        return _handle_share_get(path[3:])

    # POST /api/share — URL短縮・OGP用保存（レートリミット対象外）
    if method == "POST" and path == "/api/share":
        return _handle_share_post(event, cors)

    # GET /api/status — 残り回数を返す（カウント増加なし）
    if method == "GET" and path == "/api/status":
        client_ip = _get_client_ip(event)
        req_token = (event.get("headers") or {}).get("x-admin-token", "")
        is_admin  = bool(ADMIN_TOKEN and req_token == ADMIN_TOKEN)
        if is_admin:
            payload = {"used": 0, "limit": DAILY_LIMIT, "remaining": DAILY_LIMIT, "admin": True}
        else:
            used = get_usage(client_ip)
            payload = {"used": used, "limit": DAILY_LIMIT, "remaining": max(0, DAILY_LIMIT - used)}
        return {"statusCode": 200, "headers": cors, "body": json.dumps(payload)}

    # レートリミット（IP別・日別）— 管理者トークンがあればスキップ
    client_ip = _get_client_ip(event)
    req_token = (event.get("headers") or {}).get("x-admin-token", "")
    is_admin  = bool(ADMIN_TOKEN and req_token == ADMIN_TOKEN)
    if not is_admin and not check_rate_limit(client_ip):
        return {
            "statusCode": 429,
            "headers": cors,
            "body": json.dumps(
                {"error": f"1日{DAILY_LIMIT}回まで利用できます。明日またお試しください。"},
                ensure_ascii=False,
            ),
        }
    if is_admin:
        print(f"[rate-limit] admin bypass ({client_ip})")

    try:
        body = json.loads(event.get("body") or "{}")
        lat = float(body["latitude"])
        lon = float(body["longitude"])
        temp = body.get("temperature", 20)
        weather = body.get("weather_condition", "晴れ")
        raw_prefs = body.get("preferences", [])
        preferences = [p for p in raw_prefs if isinstance(p, str) and p in PREF_PROMPTS]
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        return {
            "statusCode": 400,
            "headers": cors,
            "body": json.dumps({"error": f"Invalid request: {e}"}),
        }

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return {
            "statusCode": 400,
            "headers": cors,
            "body": json.dumps({"error": "Coordinates out of range"}),
        }

    seed = random.randint(100000, 999999)
    if preferences:
        pref_lines = '\n'.join(f'- {PREF_PROMPTS[p]}' for p in preferences)
        preferences_section = f"\n\nユーザーの希望スタイル（全3コースで優先すること）:\n{pref_lines}"
    else:
        preferences_section = ""
    prompt = PROMPT_TEMPLATE.format(lat=lat, lon=lon, weather=weather, temp=temp, seed=seed, preferences_section=preferences_section)

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
            "headers": cors,
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
            "headers": cors,
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
        "headers": cors,
        "body": json.dumps({"courses": courses}, ensure_ascii=False),
    }
