import json
import math
import os
import re
import random
import secrets
import string
import time
import threading
import base64
import html as html_module
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import boto3
from botocore.config import Config

BEDROCK_MODEL_ID    = os.environ.get("BEDROCK_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
GMAPS_FREE_LIMIT    = 9_900  # 10,000件の無料枠から100件バッファ
DAILY_LIMIT         = int(os.environ.get("DAILY_LIMIT", "3"))
SHARE_DAILY_LIMIT    = int(os.environ.get("SHARE_DAILY_LIMIT", "30"))
MAX_SHARE_COURSE_BYTES = 8192  # course JSON の上限（DynamoDBアイテム膨張・共有URL肥大化の防止）
RATE_LIMIT_TABLE    = "zer0-touring-ratelimit"
SHARE_TABLE         = "zer0-touring-share"
SITE_URL            = "https://touring.zer0-infra.com"
ADMIN_TOKEN         = os.environ.get("ADMIN_TOKEN", "")
# CloudFront が OriginCustomHeaders で付与する共有シークレット。execute-api への
# 直接アクセス（CloudFrontをバイパスしたレートリミット回避）を遮断するために使う。
EDGE_SECRET         = os.environ.get("EDGE_SECRET", "")

JST = timezone(timedelta(hours=9))  # 日本標準時（UTC+9）

ALLOWED_ORIGINS = {
    "https://touring.zer0-infra.com",
    "http://localhost:4321",
}

bedrock = boto3.client(
    "bedrock-runtime",
    region_name="ap-northeast-1",
    # Lambda Timeout=30s のため、read_timeout はそれより十分短くする
    # （旧設定の60秒だとBedrock応答が遅い場合にLambda側が先にハードタイムアウトし、
    #  エラーハンドリング・CORSヘッダーなしの500になってしまっていた）
    config=Config(read_timeout=20, connect_timeout=5),
)
dynamodb = boto3.client("dynamodb", region_name="ap-northeast-1")

# Nominatim は 1req/sec の制限があるためロックで直列化
_NOM_LOCK = threading.Lock()


def _get_cors_headers(event):
    origin = (event.get("headers") or {}).get("origin", "")
    allowed = origin if origin in ALLOWED_ORIGINS else "https://touring.zer0-infra.com"
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": allowed,
        "Access-Control-Allow-Headers": "Content-Type, X-Admin-Token",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }


def _get_client_ip(event):
    # X-Forwarded-For は「各ホップが末尾に自分が見た送信元IPを追記する」仕様のため、
    # CloudFront が付与する実クライアントIPは末尾に入る。先頭はクライアントが自由に
    # 詐称できる値なので信用しない（先頭を信用するとレートリミットが完全に回避できてしまう）。
    xff = (event.get("headers") or {}).get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip()
    return (event.get("requestContext") or {}).get("http", {}).get("sourceIp", "unknown")


def get_usage(ip):
    """今日の使用回数を読み取る（カウントを増やさない）。"""
    today = datetime.now(JST).strftime("%Y-%m-%d")
    pk    = f"{ip}#{today}"
    try:
        resp = dynamodb.get_item(
            TableName=RATE_LIMIT_TABLE,
            Key={"pk": {"S": pk}},
            ProjectionExpression="#c",
            ExpressionAttributeNames={"#c": "count"},
        )
        return int(resp.get("Item", {}).get("count", {}).get("N", 0))
    except Exception as e:
        print(f"[get-usage] ERR {e}")
        return 0


def check_rate_limit(ip, action="suggest", limit=None):
    """IP別・日別カウントを DynamoDB でアトミックに管理する。
    limit 以内なら True、超過なら False を返す。
    action="suggest" は既存のキー形式（{ip}#{date}）を維持し、それ以外の action は
    キーに action を含めて別枠のカウンタにする（/api/share 等の使い分け用）。"""
    if limit is None:
        limit = DAILY_LIMIT
    today = datetime.now(JST).strftime("%Y-%m-%d")
    pk    = f"{ip}#{today}" if action == "suggest" else f"{action}#{ip}#{today}"
    # TTL = 翌々日0時JST（日付またぎ直後も安全に消える）
    ttl   = int((datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)).timestamp())
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
                ":limit": {"N": str(limit)},
            },
        )
        print(f"[rate-limit] {action}:{ip} OK (limit={limit}/day)")
        return True
    except dynamodb.exceptions.ConditionalCheckFailedException:
        print(f"[rate-limit] {action}:{ip} EXCEEDED (limit={limit}/day)")
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
            dist_km = round(data["routes"][0]["distance"] / 1000)
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
    """Google Maps 残枠を DynamoDB でアトミックに確認・予約する。
    使用可能なら True、無料枠超過または未設定なら False を返す。"""
    if not GOOGLE_MAPS_API_KEY:
        return False
    current_month = datetime.now(JST).strftime("%Y-%m")
    pk  = f"gmaps#{current_month}"
    ttl = int((datetime.now(JST) + timedelta(days=60)).timestamp())  # 60日後に自動削除
    try:
        resp = dynamodb.update_item(
            TableName=RATE_LIMIT_TABLE,
            Key={"pk": {"S": pk}},
            UpdateExpression="ADD #c :n SET #ttl = if_not_exists(#ttl, :ttl)",
            ConditionExpression="attribute_not_exists(#c) OR #c < :limit",
            ExpressionAttributeNames={"#c": "count", "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":n":     {"N": str(n_courses)},
                ":ttl":   {"N": str(ttl)},
                ":limit": {"N": str(GMAPS_FREE_LIMIT - n_courses + 1)},
            },
            ReturnValues="UPDATED_NEW",
        )
        count = int(resp.get("Attributes", {}).get("count", {}).get("N", 0))
        print(f"[gmaps-usage] {current_month}: {count}/{GMAPS_FREE_LIMIT}")
        return True
    except dynamodb.exceptions.ConditionalCheckFailedException:
        print(f"[gmaps-usage] 無料枠上限 {current_month} → OSRM使用")
        return False
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


MIN_TIME_BUFFER_MS = 6000  # この値を下回ったら以降の外部API呼び出しを打ち切る（Lambdaハードタイムアウト防止）
# 注意: API Gateway HTTP APIのLambda統合タイムアウトは30秒固定でAWS側の仕様上引き上げ不可のため、
# Lambda自体のTimeoutを30秒より長くしても効果がない。エラーを確実に避けるには、この安全バッファを
# 広めに取ってLambdaの実行時間そのものを短く終わらせる方針にする。


def geocode_and_filter_spots(spots, origin_lat, origin_lon, dest_lat, dest_lon, context, reverse=False):
    """
    スポットリストをジオコードし、ルート上にないものを除外して lat/lon を付与する。
    タイムアウト防止のため最大3件に制限する。
    reverse=True のとき帰路方向（dest→origin）でフィルタリング。
    """
    result = []
    for spot in spots[:3]:  # Nominatim 直列化+スリープによるタイムアウトを防ぐため上限3件
        if context.get_remaining_time_in_millis() < MIN_TIME_BUFFER_MS:
            print(f"[waypoint] 残り時間不足のため以降のジオコーディングをスキップ（{spot['name']}以降）")
            break
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


def enrich_course(course, origin_lat, origin_lon, context, use_gmaps=True):
    """
    目的地（destination）をジオコーディングして距離・所要時間を取得する。
    use_gmaps=True のとき Google Maps Directions API を使用、False なら OSRM。
    失敗時は AI 推定値をそのまま維持。

    外部API（Nominatim/OSRM/Google Maps/Open-Meteo）が劣化・タイムアウトすると
    各呼び出し自体はtimeout設定により個別には失敗するが、複数呼び出しが積み重なると
    合計でLambdaのハードタイムアウトに達し、応答が一切返らず504になってしまう。
    そのため各段階の前に残り時間を確認し、不足していれば以降の呼び出しをスキップして
    それまでに得られた結果（またはAI推定値）で確実に応答を返す。
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

    if context.get_remaining_time_in_millis() < MIN_TIME_BUFFER_MS:
        print(f"[enrich] {course.get('name','')}: 残り時間不足のためスポット・距離・天気取得をスキップ")
        return

    # outbound_spots/return_spots をジオコードしてルート外を除外
    raw_out = course.get("outbound_spots") or course.get("rest_spots") or []
    raw_ret = course.get("return_spots") or []
    course["outbound_spots"] = geocode_and_filter_spots(raw_out, origin_lat, origin_lon, dest_lat, dest_lon, context, reverse=False)
    course["return_spots"]   = geocode_and_filter_spots(raw_ret, origin_lat, origin_lon, dest_lat, dest_lon, context, reverse=True)

    if context.get_remaining_time_in_millis() < MIN_TIME_BUFFER_MS:
        print(f"[enrich] {course.get('name','')}: 残り時間不足のため距離・天気取得をスキップ")
        return

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

    if context.get_remaining_time_in_millis() < MIN_TIME_BUFFER_MS:
        print(f"[dest-weather] {dest_name}: 残り時間不足のためスキップ")
        return

    dest_temp, dest_weather_code = fetch_dest_weather(dest_lat, dest_lon)
    if dest_temp is not None:
        course["dest_temp"] = dest_temp
        course["dest_weather_code"] = dest_weather_code
        print(f"[dest-weather] {dest_name}: {dest_temp}℃ code={dest_weather_code}")


def _short_id(n=6):
    """暗号論的に安全なランダムIDを生成する。"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(n))

def _fetch_wiki_photo(spot):
    if not spot:
        return None
    try:
        url = f"https://ja.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(spot)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Zer0-Touring/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            thumb = data.get("thumbnail", {}).get("source", "")
            # httpsスキーム以外は拒否（オープンリダイレクト・混在コンテンツ防止）
            if not thumb or not thumb.startswith("https://"):
                return None
            return re.sub(r'/\d+px-', '/800px-', thumb)
    except Exception:
        return None

def _handle_share_post(event, cors):
    try:
        body = json.loads(event.get("body") or "{}")
        course = body.get("course")
        if not course or not isinstance(course, dict):
            raise ValueError("course required")
        course_json_bytes = len(json.dumps(course, ensure_ascii=False).encode("utf-8"))
        if course_json_bytes > MAX_SHARE_COURSE_BYTES:
            raise ValueError("course too large")
    except Exception as e:
        return {"statusCode": 400, "headers": cors, "body": json.dumps({"error": str(e)})}

    # 無認証で誰でも呼べるエンドポイントのため IP 別・日別レートリミットで書き込み量を制限する
    client_ip = _get_client_ip(event)
    if not check_rate_limit(client_ip, action="share", limit=SHARE_DAILY_LIMIT):
        return {
            "statusCode": 429, "headers": cors,
            "body": json.dumps({"error": "共有機能の利用上限に達しました。時間をおいて再度お試しください。"}, ensure_ascii=False),
        }

    photo_url  = _fetch_wiki_photo(course.get("photo_spot", ""))
    short_id   = _short_id(6)
    ttl        = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    # JS の btoa(encodeURIComponent(JSON.stringify(course))) と同等のエンコード
    course_b64 = base64.b64encode(
        urllib.parse.quote(json.dumps(course, ensure_ascii=False), safe="").encode("ascii")
    ).decode("ascii")

    item = {
        "pk":          {"S": short_id},
        "course_b64":  {"S": course_b64},
        "photo_url":   {"S": photo_url or ""},
        "name":        {"S": course.get("name", "ツーリングコース")},
        "destination": {"S": course.get("destination", "")},
        "duration":    {"S": str(course.get("duration_hours", ""))},
        "tags":        {"S": json.dumps(course.get("tags", []), ensure_ascii=False)},
        "ttl":         {"N": str(ttl)},
    }

    try:
        dynamodb.put_item(
            TableName=SHARE_TABLE,
            Item=item,
            ConditionExpression="attribute_not_exists(pk)",  # ID衝突防止
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:
        # ID衝突（極めて稀）: 新IDで1回リトライ（こちらも衝突防止条件を維持）
        short_id = _short_id(6)
        item["pk"] = {"S": short_id}
        dynamodb.put_item(TableName=SHARE_TABLE, Item=item,
                          ConditionExpression="attribute_not_exists(pk)")

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

    og_title = html_module.escape(f"{name} | Zer0 Touring")
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
    og_desc = html_module.escape(" · ".join(parts) if parts else "AIが提案する日帰りバイクツーリングコース")

    redirect = f"{SITE_URL}/?course={course_b64}"
    # og:image の Wikimedia URL はクローラーがそのまま取得できるため CSP 不要
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:image" content="{html_module.escape(photo_url)}">
<meta property="og:url" content="{SITE_URL}/s/{short_id}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{og_title}">
<meta name="twitter:description" content="{og_desc}">
<meta name="twitter:image" content="{html_module.escape(photo_url)}">
<meta http-equiv="refresh" content="0; url={html_module.escape(redirect)}">
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

    # CloudFront経由以外（execute-api URLへの直接アクセス）を遮断する。
    # execute-apiを直接叩かれるとCloudFrontが付与するX-Forwarded-For末尾を
    # 信頼する対策が意味を失い、レートリミットが回避できてしまうため。
    if EDGE_SECRET:
        req_secret = (event.get("headers") or {}).get("x-origin-verify", "")
        if not secrets.compare_digest(req_secret, EDGE_SECRET):
            return {"statusCode": 403, "headers": cors, "body": json.dumps({"error": "Forbidden"})}

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
        is_admin  = bool(ADMIN_TOKEN and secrets.compare_digest(req_token, ADMIN_TOKEN))
        if is_admin:
            payload = {"used": 0, "limit": DAILY_LIMIT, "remaining": DAILY_LIMIT, "admin": True}
        else:
            used = get_usage(client_ip)
            payload = {"used": used, "limit": DAILY_LIMIT, "remaining": max(0, DAILY_LIMIT - used)}
        return {"statusCode": 200, "headers": cors, "body": json.dumps(payload)}

    # POST /api/suggest のみ許可（未知パスは 404 を返す）
    if not (method == "POST" and path == "/api/suggest"):
        return {"statusCode": 404, "headers": cors, "body": json.dumps({"error": "Not found"})}

    # 入力検証を先に行い、不正なリクエストでレートリミットのクォータを消費しないようにする
    # （検証を後にすると、壊れたリクエストを送るだけで1日の利用回数が無駄に減ってしまう）。
    try:
        body = json.loads(event.get("body") or "{}")
        lat = float(body["latitude"])
        lon = float(body["longitude"])
        temp = body.get("temperature", 20)
        weather = body.get("weather_condition", "晴れ")
        raw_prefs = body.get("preferences", [])
        preferences = [p for p in raw_prefs if isinstance(p, str) and p in PREF_PROMPTS]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
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

    # temperature/weather_condition はそのまま Bedrock プロンプトに埋め込まれるため、
    # 型・長さを制限してプロンプト肥大化・異常値の混入を防ぐ
    try:
        temp = max(-50.0, min(60.0, float(temp)))
    except (TypeError, ValueError):
        temp = 20
    if not isinstance(weather, str) or not weather or len(weather) > 20:
        weather = "晴れ"

    # レートリミット（IP別・日別）— 管理者トークンがあればスキップ
    client_ip = _get_client_ip(event)
    req_token = (event.get("headers") or {}).get("x-admin-token", "")
    is_admin  = bool(ADMIN_TOKEN and secrets.compare_digest(req_token, ADMIN_TOKEN))
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

    # 今月の Google Maps 残枠を確認（n_courses 分を DynamoDB でアトミックに予約）
    use_gmaps = check_and_reserve_gmaps(n_courses=len(courses))

    # 距離・所要時間を実データに上書き（タイムアウト余裕がある場合のみ）
    if context.get_remaining_time_in_millis() > 12000:
        def _enrich(course):
            try:
                enrich_course(course, lat, lon, context, use_gmaps=use_gmaps)
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
