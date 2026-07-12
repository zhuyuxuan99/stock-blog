import json
import requests
import time
import threading
import gzip
import os
from queue import Queue
from datetime import datetime, timedelta

# Tushare API token
TUSHARE_TOKEN = "f6833eb29d6eb93772f06a29d64b3b1f40e2325fde0ea955bc5758ac"

# 数据基础目录：本机项目位于 E:\claudecode；可用环境变量 STRATEGY_BASE 覆盖（如原机 D:\claudecode）
BASE_DIR = os.environ.get("STRATEGY_BASE", r"E:\claudecode")

def load_strategy_json(path):
    """加载策略 JSON。文件缺失或解析失败时返回空字典 {}，使该策略被安全跳过而非崩溃。"""
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"警告: 读取数据失败，跳过该策略: {path} ({e})")
            return {}
    print(f"警告: 找不到数据文件，跳过该策略: {path}")
    return {}

# 读取三个策略的数据（缺失的策略返回空字典，后续逻辑自动跳过）
hunter_data = load_strategy_json(os.path.join(BASE_DIR, "dog", "state", "signal_history", "top10_history.json"))
mosquito_data = load_strategy_json(os.path.join(BASE_DIR, "mosquito", "top10_history.json"))
elephant_data = load_strategy_json(os.path.join(BASE_DIR, "elephants", "output", "top10_history.json"))

if not any([hunter_data, mosquito_data, elephant_data]):
    print("错误: 三个策略的源数据文件均缺失，无法继续。请确认 STRATEGY_BASE 指向含 dog/mosquito/elephants 的目录。")
    raise SystemExit(1)

CACHE_FILE = os.path.join(BASE_DIR, "top10_html", "stock_prices_cache.json.gz")

HUNTER_HISTORY_DIR = os.path.join(BASE_DIR, "dog", "state", "signal_history")

def normalize_date(date_str):
    """标准化日期字符串，提取YYYY-MM-DD格式的日期部分"""
    if not date_str:
        return date_str
    if ' ' in date_str:
        return date_str.split(' ')[0]
    return date_str

def get_hunter_timestamps():
    """获取猎狗组每个日期的文件修改时间作为时间戳"""
    timestamps = {}
    if os.path.exists(HUNTER_HISTORY_DIR):
        for filename in os.listdir(HUNTER_HISTORY_DIR):
            if filename.endswith('.json') and filename != 'top10_history.json':
                date_str = filename.replace('.json', '')
                filepath = os.path.join(HUNTER_HISTORY_DIR, filename)
                try:
                    mtime = os.path.getmtime(filepath)
                    dt = datetime.fromtimestamp(mtime)
                    timestamps[date_str] = dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
    return timestamps

def normalize_elephant_dates(data):
    """规范化大象组数据中的日期，处理带时间戳的日期格式"""
    normalized = {}
    timestamps = {}
    for date, stocks in data.items():
        normalized_date = normalize_date(date)
        if normalized_date not in normalized:
            normalized[normalized_date] = []
        if normalized_date not in timestamps:
            timestamps[normalized_date] = date
        for stock in stocks:
            stock_copy = stock.copy()
            stock_copy['_original_date'] = date
            normalized[normalized_date].append(stock_copy)
    return normalized, timestamps

def load_cache():
    """加载缓存数据（支持gzip压缩）"""
    if os.path.exists(CACHE_FILE):
        try:
            with gzip.open(CACHE_FILE, 'rt', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载缓存失败: {e}")
            return {}
    return {}

def save_cache(data):
    """保存缓存数据（使用gzip压缩）"""
    try:
        with gzip.open(CACHE_FILE, 'wt', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        original_size = len(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        compressed_size = os.path.getsize(CACHE_FILE)
        print(f"缓存已保存，原始 {original_size/1024:.1f}KB -> 压缩后 {compressed_size/1024:.1f}KB")
    except Exception as e:
        print(f"保存缓存失败: {e}")

def get_cached_stock_prices(code, cache):
    """获取缓存的股票价格数据"""
    if code in cache:
        return cache[code]
    return None

def update_cache(cache, code, prices):
    """更新缓存数据"""
    cache[code] = prices
    return cache

def convert_code_sina(code):
    """将股票代码转换为新浪财经格式"""
    if code.endswith('.SH'):
        return 'sh' + code.replace('.SH', '')
    elif code.endswith('.SZ'):
        return 'sz' + code.replace('.SZ', '')
    return code.lower()

def get_stock_history_sina(code, start_date, end_date):
    """使用新浪财经接口获取股票历史数据"""
    sina_code = convert_code_sina(code)

    # 计算需要获取的天数
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days + 30  # 多取一些数据以确保覆盖

    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {
        "symbol": sina_code,
        "scale": 240,  # 日K线
        "ma": "no",
        "datalen": days
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return data
    except Exception as e:
        print(f"  新浪接口错误 {code}: {e}")

    # 如果新浪失败，尝试东方财富接口
    return get_stock_history_eastmoney(code, start_date, end_date)

def convert_code_eastmoney(code):
    """将股票代码转换为东方财富格式"""
    if code.endswith('.SH'):
        market = '1'
        stock_code = code.replace('.SH', '').lstrip('0')
        return f"{market}.{stock_code}"
    elif code.endswith('.SZ'):
        market = '0'
        stock_code = code.replace('.SZ', '').lstrip('0')
        return f"{market}.{stock_code}"
    return code

def get_stock_history_eastmoney(code, start_date, end_date):
    """使用东方财富接口获取股票历史数据"""
    eastmoney_code = convert_code_eastmoney(code)

    start_str = start_date.replace("-", "")
    end_str = end_date.replace("-", "")

    url = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": eastmoney_code,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": 101,  # 日K线
        "fqt": 1,    # 前复权
        "beg": start_str,
        "end": end_str
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and data["data"].get("klines"):
                klines = data["data"]["klines"]
                result = []
                for line in klines:
                    parts = line.split(",")
                    if len(parts) >= 6:
                        result.append({
                            "day": parts[0],
                            "open": parts[1],
                            "close": parts[2],
                            "high": parts[3],
                            "low": parts[4],
                            "volume": parts[5],
                            "pct_chg": parts[8] if len(parts) > 8 else "0"
                        })
                return result
    except Exception as e:
        print(f"  东方财富接口错误 {code}: {e}")

    return []

def get_stock_realtime_price(code):
    """获取股票实时价格（腾讯财经实时行情接口）"""
    sina_code = convert_code_sina(code)
    
    url = f"http://qt.gtimg.cn/q={sina_code}"
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.text
            if data:
                parts = data.split('="')
                if len(parts) >= 2:
                    price_info = parts[1].split('";')[0].split('~')
                    if len(price_info) >= 6:
                        current_price = float(price_info[3])
                        prev_close = float(price_info[4])
                        return {
                            "price": current_price,
                            "open": float(price_info[5]),
                            "high": float(price_info[25]),
                            "low": float(price_info[26]),
                            "prev_close": prev_close,
                            "pct_chg": round((current_price - prev_close) / prev_close * 100, 2)
                        }
    except Exception as e:
        print(f"  获取实时价格失败 {code}: {e}")
    
    return None

def get_multiple_realtime_prices(codes):
    """批量获取多只股票实时价格（腾讯财经接口）"""
    results = {}
    sina_codes = ','.join([convert_code_sina(code) for code in codes])
    
    url = f"http://qt.gtimg.cn/q={sina_codes}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            lines = response.text.strip().split('\n')
            for line in lines:
                parts = line.split('="')
                if len(parts) >= 2:
                    code_part = parts[0].split('_')[-1]
                    if code_part.startswith('v_'):
                        code_part = code_part[2:]
                    price_info = parts[1].split('";')[0].split('~')
                    if len(price_info) >= 6:
                        current_price = float(price_info[3])
                        prev_close = float(price_info[4])
                        results[code_part] = {
                            "price": current_price,
                            "open": float(price_info[5]),
                            "high": float(price_info[25]) if len(price_info) > 25 else current_price,
                            "low": float(price_info[26]) if len(price_info) > 26 else current_price,
                            "prev_close": prev_close,
                            "pct_chg": round((current_price - prev_close) / prev_close * 100, 2)
                        }
    except Exception as e:
        print(f"  批量获取实时价格失败: {e}")
    
    return results

def get_stock_history_163(code, start_date, end_date):
    """使用网易财经接口获取股票历史数据（备用）"""
    # 转换代码格式
    if code.endswith('.SH'):
        symbol = '0' + code.replace('.SH', '')
    else:
        symbol = '1' + code.replace('.SZ', '')

    start_str = start_date.replace("-", "")
    end_str = end_date.replace("-", "")

    url = f"http://quotes.money.163.com/service/chddata.html"
    params = {
        "code": symbol,
        "start": start_str,
        "end": end_str,
        "fields": "TCLOSE;HIGH;LOW;TOPEN;LCLOSE;CHG;PCHG;TURNOVER;VOTURNOVER;VATURNOVER"
    }

    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            # 解析CSV数据
            lines = response.text.strip().split('\n')
            if len(lines) > 1:
                result = []
                for line in lines[1:]:  # 跳过标题行
                    parts = line.split(',')
                    if len(parts) >= 10:
                        result.append({
                            "day": parts[0].replace('-', ''),
                            "close": parts[3],
                            "pct_chg": parts[7]
                        })
                return result
    except Exception as e:
        print(f"  网易接口错误 {code}: {e}")

    return []

def get_stock_history_tushare(codes, start_date, end_date):
    """使用Tushare接口批量获取股票历史收盘价数据"""
    # 将日期转换为YYYYMMDD格式
    start_str = start_date.replace("-", "")
    end_str = end_date.replace("-", "")
    
    url = "https://api.tushare.pro"
    
    # 由于tushare pro的日线数据接口有限制，我们尝试获取每只股票
    result = {}
    
    for code in codes[:50]:  # 限制每次最多50只股票
        payload = {
            "api_name": "daily",
            "token": TUSHARE_TOKEN,
            "params": {
                "ts_code": code,
                "start_date": start_str,
                "end_date": end_str
            },
            "fields": "ts_code,trade_date,close,pct_chg"
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            data = response.json()
            
            if data.get("code") == 0 and data.get("data"):
                items = data["data"].get("items", [])
                fields = data["data"].get("fields", [])
                
                for item in items:
                    if isinstance(item, list) and len(item) > 0:
                        row = dict(zip(fields, item))
                        ts_code = row.get("ts_code")
                        if ts_code:
                            if ts_code not in result:
                                result[ts_code] = []
                            result[ts_code].append({
                                "day": row.get("trade_date", ""),
                                "close": float(row.get("close", 0) or 0),
                                "pct_chg": float(row.get("pct_chg", 0) or 0)
                            })
        except Exception as e:
            print(f"  Tushare接口错误 {code}: {e}")
        
        time.sleep(0.2)  # 避免API限流
    
    return result

# 获取今天的日期
today = datetime.now().strftime("%Y-%m-%d")

# 获取所有需要查询的股票代码和推荐日期
all_stocks = {}

# 处理猎狗组数据 - 获取今天之前的30个日历日(约21个交易日)
hunter_dates = sorted([d for d in hunter_data.keys() if d <= today], reverse=True)[:29]
for date in hunter_dates:
    raw = hunter_data[date]
    # 兼容新旧数据格式：新格式 {"stocks": [...], "last_updated": "..."}，旧格式 [...]
    if isinstance(raw, dict) and "stocks" in raw:
        stocks = raw["stocks"]
    else:
        stocks = raw
    for stock in stocks:
        code = stock["code"]
        if code not in all_stocks:
            all_stocks[code] = {"dates": [], "name": stock["name"], "strategies": []}
        if date not in all_stocks[code]["dates"]:
            all_stocks[code]["dates"].append(date)
        all_stocks[code]["name"] = stock["name"]
        if "猎狗组" not in all_stocks[code]["strategies"]:
            all_stocks[code]["strategies"].append("猎狗组")

# 处理蚊子组数据 - 获取今天之前的30个日历日(约21个交易日)，先规范化日期格式
mosquito_data_normalized = {}
mosquito_timestamps = {}
for date, stocks in mosquito_data.items():
    normalized_date = normalize_date(date)
    if normalized_date not in mosquito_data_normalized:
        mosquito_data_normalized[normalized_date] = []
    if normalized_date not in mosquito_timestamps:
        mosquito_timestamps[normalized_date] = date
    for stock in stocks:
        stock_copy = stock.copy()
        stock_copy['_original_date'] = date
        mosquito_data_normalized[normalized_date].append(stock_copy)

mosquito_dates = sorted([d for d in mosquito_data_normalized.keys() if d <= today], reverse=True)[:29]
for date in mosquito_dates:
    stocks = mosquito_data_normalized[date]
    for stock in stocks:
        code = stock["code"]
        if code not in all_stocks:
            all_stocks[code] = {"dates": [], "name": stock["name"], "strategies": []}
        if date not in all_stocks[code]["dates"]:
            all_stocks[code]["dates"].append(date)
        all_stocks[code]["name"] = stock["name"]
        if "蚊子组" not in all_stocks[code]["strategies"]:
            all_stocks[code]["strategies"].append("蚊子组")

# 处理大象组数据 - 先规范化日期格式
elephant_data_normalized, elephant_timestamps = normalize_elephant_dates(elephant_data)
elephant_dates = sorted([d for d in elephant_data_normalized.keys() if d <= today], reverse=True)[:29]
for date in elephant_dates:
    stocks = elephant_data_normalized[date]
    for stock in stocks:
        code = stock["code"]
        if code not in all_stocks:
            all_stocks[code] = {"dates": [], "name": stock["name"], "strategies": [], "timestamps": {}}
        if date not in all_stocks[code]["dates"]:
            all_stocks[code]["dates"].append(date)
        if '_original_date' in stock:
            if 'timestamps' not in all_stocks[code]:
                all_stocks[code]["timestamps"] = {}
            all_stocks[code]["timestamps"][date] = stock['_original_date']
        all_stocks[code]["name"] = stock["name"]
        if "大象组" not in all_stocks[code]["strategies"]:
            all_stocks[code]["strategies"].append("大象组")

print(f"共有 {len(all_stocks)} 只股票需要查询价格")

# 获取所有涉及的日期范围
all_dates = set()
for code, info in all_stocks.items():
    all_dates.update(info["dates"])

# 生成连续的日期范围（从最早日期到今天，包含周末和节假日）
if all_dates:
    earliest_date = min(all_dates)
else:
    earliest_date = today

def get_date_range(start_date, end_date):
    dates = []
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates

# 生成连续日期列表（包含所有日期，包括周末）
continuous_dates = get_date_range(earliest_date, today)
print(f"需要获取 {earliest_date} 到 {today} 的历史数据，共 {len(continuous_dates)} 天")

# 加载缓存
cache = load_cache()
print(f"缓存中已有 {len(cache)} 只股票的价格数据")

# 获取每只股票的历史价格（使用多线程并行获取 + 缓存机制）
stock_prices = {}
stock_prices_lock = threading.Lock()
request_counter = 0
counter_lock = threading.Lock()
start_time = time.time()

def fetch_stock_worker(queue, earliest_date, today):
    """工作线程：从队列中获取股票代码并获取价格数据"""
    global request_counter
    
    while not queue.empty():
        try:
            idx, code, info = queue.get(timeout=2)
            
            # 先检查缓存
            cached_prices = get_cached_stock_prices(code, cache)
            
            if cached_prices:
                # 检查缓存数据是否覆盖了所需日期范围（必须覆盖到今天）
                cached_dates = sorted([p["date"] for p in cached_prices])
                if cached_dates:
                    latest_cached_date = cached_dates[-1]
                    today_str = today.replace("-", "")
                    
                    # 如果缓存的最新日期 >= 今天，说明缓存足够
                    if latest_cached_date >= today_str:
                        with stock_prices_lock:
                            stock_prices[code] = cached_prices
                        print(f"[{idx+1}/{len(all_stocks)}] {code} {info['name']} 使用缓存数据")
                        queue.task_done()
                        continue
            
            # 需要获取新数据
            # 限流：每秒钟最多5次请求
            with counter_lock:
                request_counter += 1
                current_count = request_counter
            if current_count % 5 == 0:
                time.sleep(1)
            
            prices = []
            
            # 1. 优先使用Tushare（使用收盘价）
            tushare_results = get_stock_history_tushare([code], earliest_date, today)
            if code in tushare_results:
                prices = tushare_results[code]
            
            # 2. 如果Tushare失败，尝试新浪财经
            if not prices:
                prices = get_stock_history_sina(code, earliest_date, today)
            
            # 3. 如果新浪失败，尝试东方财富
            if not prices:
                prices = get_stock_history_eastmoney(code, earliest_date, today)
            
            # 4. 如果东方财富也失败，尝试网易财经
            if not prices:
                prices = get_stock_history_163(code, earliest_date, today)
            
            if prices:
                formatted_prices = []
                for p in prices:
                    date_str = p.get("day", "")
                    if "-" in date_str:
                        date_str = date_str.replace("-", "")
                    close = float(p.get("close", 0) or 0)
                    pct_chg = float(p.get("pct_chg", 0) or 0)
                    formatted_prices.append({
                        "date": date_str,
                        "close": close,
                        "pct_chg": pct_chg
                    })
                
                with stock_prices_lock:
                    stock_prices[code] = formatted_prices
                    update_cache(cache, code, formatted_prices)
                
                elapsed = time.time() - start_time
                print(f"[{idx+1}/{len(all_stocks)}] {code} {info['name']} 成功获取 {len(formatted_prices)} 条数据 (耗时 {elapsed:.1f}s)")
            else:
                print(f"[{idx+1}/{len(all_stocks)}] {code} {info['name']} 所有接口均失败")
            
            queue.task_done()
            
        except Exception as e:
            print(f"获取数据出错: {e}")
            queue.task_done()

# 创建队列并添加所有股票
stock_queue = Queue()
for i, (code, info) in enumerate(all_stocks.items()):
    stock_queue.put((i, code, info))

# 创建工作线程（8个线程并行）
num_threads = 8
threads = []
for _ in range(num_threads):
    t = threading.Thread(target=fetch_stock_worker, args=(stock_queue, earliest_date, today))
    t.daemon = True
    threads.append(t)
    t.start()

# 等待所有任务完成
stock_queue.join()

# 保存缓存
save_cache(cache)

elapsed_time = time.time() - start_time
print(f"\n共成功获取 {len(stock_prices)} 只股票的价格数据，耗时 {elapsed_time:.2f} 秒")

# 计算每只股票在推荐日之后的收益
returns_data = {}

def calculate_return(prices, recommend_date, realtime_price=None):
    """计算推荐日之后每天的价格和累计收益率（支持实时价格）"""
    recommend_date_str = recommend_date.replace("-", "")

    # 按日期排序
    prices_sorted = sorted(prices, key=lambda x: x.get("date", ""))

    # 找到推荐日当天或之前最近一个交易日的价格作为基准（支持周末/节假日）
    base_price = None
    base_date = None
    latest_price = None
    latest_date = None

    for price in prices_sorted:
        trade_date = price.get("date", "")
        close_price = price.get("close", 0)

        # 记录最新价格
        if latest_date is None or trade_date > latest_date:
            latest_date = trade_date
            latest_price = close_price

    # 找推荐日之前最近一个交易日的收盘价作为推荐价格（使用前一日收盘价）
    for price in reversed(prices_sorted):
        trade_date = price.get("date", "")
        close_price = price.get("close", 0)
        if trade_date < recommend_date_str:
            base_date = trade_date
            base_price = close_price
            break

    # 如果有基准价格，计算每日数据
    if base_price and base_price > 0:
        # 创建每日数据列表
        daily_data = []
        
        # 获取推荐日和最新日的日期对象
        from datetime import datetime, timedelta
        base_date_obj = datetime.strptime(base_date, "%Y%m%d")
        
        # 如果有实时价格，最新日期设置为今天
        if realtime_price:
            latest_date_obj = datetime.now()
        else:
            latest_date_obj = datetime.strptime(latest_date, "%Y%m%d")
        
        # 创建价格字典方便查询
        price_dict = {p["date"]: p for p in prices_sorted}
        
        # 获取今天的日期字符串
        today_str = datetime.now().strftime("%Y%m%d")
        
        # 遍历从推荐日到最新日的每一天
        current_date = base_date_obj
        while current_date <= latest_date_obj:
            date_str = current_date.strftime("%Y%m%d")
            date_display = current_date.strftime("%Y-%m-%d")
            day_of_week = current_date.weekday()  # 0=周一, 6=周日
            is_weekend = day_of_week >= 5  # 周六或周日
            
            # 检查是否是今天且有实时价格
            is_today = date_str == today_str
            
            if is_weekend:
                # 周末，没有交易数据，显示"周末"
                daily_data.append({
                    "date": date_str,
                    "date_display": date_display,
                    "close": None,
                    "return_rate": None,
                    "is_weekend": True
                })
            elif date_str in price_dict:
                close_price = price_dict[date_str]["close"]
                pct_chg = price_dict[date_str].get("pct_chg", None)
                return_rate = (close_price - base_price) / base_price * 100
                daily_data.append({
                    "date": date_str,
                    "date_display": date_display,
                    "close": close_price,
                    "pct_chg": round(pct_chg, 2) if pct_chg is not None else None,
                    "return_rate": round(return_rate, 2),
                    "is_weekend": False
                })
            elif is_today and realtime_price:
                # 使用实时价格
                close_price = realtime_price["price"]
                pct_chg = realtime_price.get("pct_chg", None)
                return_rate = (close_price - base_price) / base_price * 100
                daily_data.append({
                    "date": date_str,
                    "date_display": date_display,
                    "close": close_price,
                    "pct_chg": round(pct_chg, 2) if pct_chg is not None else None,
                    "return_rate": round(return_rate, 2),
                    "is_weekend": False,
                    "is_realtime": True
                })
            else:
                # 节假日，没有交易数据
                daily_data.append({
                    "date": date_str,
                    "date_display": date_display,
                    "close": None,
                    "return_rate": None,
                    "is_weekend": False
                })
            
            current_date += timedelta(days=1)
        
        # 确定最新价格（优先使用实时价格）
        final_latest_price = realtime_price["price"] if realtime_price else latest_price
        final_latest_date = today_str if realtime_price else latest_date
        
        # 计算交易日数量（从推荐日到今日，不包括推荐日当天）
        trading_days_count = 0
        for day in daily_data:
            if not day["is_weekend"] and day["close"] is not None:
                trading_days_count += 1
        # 减去推荐日当天
        trading_days_count -= 1
        if trading_days_count < 0:
            trading_days_count = 0
        
        # 检查推荐日是否是周末或节假日（没有收盘价）
        recommend_date_obj = datetime.strptime(recommend_date_str, "%Y%m%d")
        recommend_day_of_week = recommend_date_obj.weekday()
        is_recommend_weekend = recommend_day_of_week >= 5
        
        # 如果推荐日是周末或节假日，没有收益数据
        if is_recommend_weekend or base_price == 0:
            result_return_rate = None
        else:
            result_return_rate = round((final_latest_price - base_price) / base_price * 100, 2)
        
        result = {
            "recommend_price": base_price,
            "recommend_date": base_date,
            "daily_data": daily_data,
            "latest_price": final_latest_price,
            "latest_date": final_latest_date,
            "return_rate": result_return_rate,
            "has_realtime": realtime_price is not None,
            "trading_days": trading_days_count
        }
        
        return result

    return None

# 获取所有股票的实时价格（用于计算今日盈亏）
print("\n获取实时价格...")
realtime_prices = get_multiple_realtime_prices(list(all_stocks.keys()))
print(f"成功获取 {len(realtime_prices)} 只股票的实时价格")

for code, info in all_stocks.items():
    prices = stock_prices.get(code, [])
    
    # 获取该股票的实时价格
    realtime_price = realtime_prices.get(convert_code_sina(code), None)

    returns_data[code] = {
        "name": info["name"],
        "strategies": info["strategies"],
        "returns": {},
        "price_data": prices,
        "realtime_price": realtime_price
    }

    # 计算收益（传入实时价格）
    for recommend_date in info["dates"]:
        return_info = calculate_return(prices, recommend_date, realtime_price)
        if return_info:
            returns_data[code]["returns"][recommend_date] = return_info

# 保存收益数据
returns_data["_metadata"] = {
    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "timezone": "Asia/Shanghai"
}

with open(os.path.join(BASE_DIR, "top10_html", "stock_returns.json"), "w", encoding="utf-8") as f:
    json.dump(returns_data, f, ensure_ascii=False, indent=2)

print("\n收益数据已保存到 stock_returns.json")

# 获取猎狗组时间戳（从文件修改时间）
hunter_timestamps = get_hunter_timestamps()

# 保存推荐数据（用于HTML页面）
recommendations_data = {
    "hunter": {},
    "mosquito": {},
    "elephant": {},
    "hunter_timestamps": hunter_timestamps,
    "mosquito_timestamps": mosquito_timestamps,
    "elephant_timestamps": elephant_timestamps,
    "all_dates": continuous_dates
}

for date in hunter_dates:
    raw = hunter_data[date]
    if isinstance(raw, dict) and "stocks" in raw:
        recommendations_data["hunter"][date] = raw["stocks"]
    else:
        recommendations_data["hunter"][date] = raw

for date in mosquito_dates:
    recommendations_data["mosquito"][date] = mosquito_data_normalized[date]

for date in elephant_dates:
    recommendations_data["elephant"][date] = elephant_data_normalized[date]

with open(os.path.join(BASE_DIR, "top10_html", "recommendations.json"), "w", encoding="utf-8") as f:
    json.dump(recommendations_data, f, ensure_ascii=False, indent=2)

print("推荐数据已保存到 recommendations.json")

# 统计各策略收益
def get_strategy_returns(data, strategy):
    returns = []
    for code, info in data.items():
        if code.startswith('_'):
            continue
        if strategy in info["strategies"]:
            for date, ret in info["returns"].items():
                returns.append(ret["return_rate"])
    return returns

hunter_returns = get_strategy_returns(returns_data, "猎狗组")
mosquito_returns = get_strategy_returns(returns_data, "蚊子组")
elephant_returns = get_strategy_returns(returns_data, "大象组")

print("\n各策略收益统计:")
if hunter_returns:
    hunter_valid = [r for r in hunter_returns if r is not None]
    print(f"  猎狗组: 平均 {sum(hunter_valid)/len(hunter_valid):.2f}% (共{len(hunter_valid)}条有效)")
if mosquito_returns:
    mosquito_valid = [r for r in mosquito_returns if r is not None]
    print(f"  蚊子组: 平均 {sum(mosquito_valid)/len(mosquito_valid):.2f}% (共{len(mosquito_valid)}条有效)")
if elephant_returns:
    elephant_valid = [r for r in elephant_returns if r is not None]
    print(f"  大象组: 平均 {sum(elephant_valid)/len(elephant_valid):.2f}% (共{len(elephant_valid)}条有效)")

# 显示部分收益数据示例
print("\n示例收益数据:")
count = 0
for code, info in returns_data.items():
    if code.startswith('_'):
        continue
    if info["returns"] and count < 10:
        for date, ret in info["returns"].items():
            print(f"  {code} - {info['name']} ({info['strategies'][0]}):")
            print(f"    推荐日 {date}: {ret['recommend_price']} -> 最新 {ret['latest_price']}, 收益 {ret['return_rate']}%")
            count += 1
