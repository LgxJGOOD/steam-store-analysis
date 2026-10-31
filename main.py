import requests
from bs4 import BeautifulSoup
import csv
import re
import time
import os
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

def clean_text(text):
    if not text:
        return ''
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_game_info(app_id, max_retries=3, retry_delay=10):
    url = f'https://store.steampowered.com/app/{app_id}'

    for attempt in range(max_retries):
        try:
            session = requests.Session()
            session.cookies.set('wants_mature_content', '1', domain='store.steampowered.com')

            res = session.get(url, headers=headers, timeout=10)
            res.encoding = 'utf-8'

            if 'agecheck' in res.url.lower():
                return None, 'agecheck'

            if res.status_code != 200:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return None, 'error'

            soup = BeautifulSoup(res.text, 'html.parser')

            # ❗ 未推出检测
            coming = soup.find('div', {"class": "game_area_comingsoon"})
            if coming:
                txt = coming.get_text(strip=True)
                if '尚未在 Steam 上推出' in txt or 'not yet available' in txt.lower():
                    return None, 'not_released'

            # 游戏名称
            name_elem = soup.find('div', {"id": "appHubAppName"})
            if not name_elem:
                return None, 'not_found'

            name = clean_text(name_elem.get_text(strip=True))
            if not name:
                return None, 'not_found'

            # 价格
            price_elem = soup.find('div', {"class": "discount_original_price"}) \
                or soup.find('div', {"class": "game_purchase_price"}) \
                or soup.find('div', {"class": "discount_final_price"})

            price = clean_text(price_elem.get_text(strip=True)) if price_elem else ''

            # 单人检测
            is_single = False
            for label in soup.find_all('div', {"class": "label"}):
                t = label.get_text(strip=True)
                if '单人' in t or 'Single-player' in t:
                    is_single = True
                    break

            if not is_single:
                return None, 'not_single_player'

            # 第三方检测
            is_third = False
            need_account = False

            for drm in soup.find_all('div', {'class': 'DRM_notice'}):
                t = drm.get_text(strip=True).lower()
                if 'third party drm' in t or '第三方 drm' in t:
                    is_third = True
                if 'requires third party account' in t or '需要第三方账户' in t:
                    need_account = True

            data = {
                'id': app_id,
                'name': name,
                'price': price,
                'url': url,
                'is_single_player': '是',
                'is_third_party': '是' if is_third else '否',
                'requires_third_party_account': '是' if need_account else '否'
            }

            return data, 'success'

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return None, 'timeout'
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return None, 'error'


def main():
    # === 文件 ===
    input_file = 'ids.txt'
    output_file = 'steam_games_result.csv'
    progress_file = 'progress.txt'
    stats_file = 'stats.json'

    # === 状态映射 ===
    status_map = {
        'success': '成功',
        'agecheck': '年龄验证',
        'not_single_player': '非单人',
        'not_released': '未推出',
        'not_found': '不存在',
        'error': '错误',
        'timeout': '超时'
    }

    # === 读取ID ===
    with open(input_file, 'r', encoding='utf-8') as f:
        ids = [x.strip() for x in f if x.strip()]

    total = len(ids)
    print(f"总共 {total} 个 ID")

    # === 读取进度 ===
    processed = set()
    if os.path.exists(progress_file):
        with open(progress_file, 'r', encoding='utf-8') as f:
            processed = set(x.strip() for x in f)

    # === 读取统计 ===
    if os.path.exists(stats_file):
        with open(stats_file, 'r', encoding='utf-8') as f:
            stats = json.load(f)
    else:
        stats = {k: 0 for k in status_map}

    # === CSV初始化 ===
    fieldnames = [
        'ID', '链接', '游戏名称', '价格',
        '是否单人', '是否为第三方', '是否需要第三方账户', '状态'
    ]

    if not os.path.exists(output_file):
        with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

    # === 主循环 ===
    for idx, app_id in enumerate(ids, 1):
        if app_id in processed:
            continue

        info, status = get_game_info(app_id)

        # 构造行（所有情况都写）
        row = {
            'ID': app_id,
            '链接': f'https://store.steampowered.com/app/{app_id}',
            '游戏名称': '',
            '价格': '',
            '是否单人': '',
            '是否为第三方': '',
            '是否需要第三方账户': '',
            '状态': status_map.get(status, status)
        }

        if info:
            row.update({
                '游戏名称': info['name'],
                '价格': info['price'],
                '是否单人': info['is_single_player'],
                '是否为第三方': info['is_third_party'],
                '是否需要第三方账户': info['requires_third_party_account']
            })

        # 写CSV
        with open(output_file, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(row)

        # 更新状态
        if status in stats:
            stats[status] += 1

        processed.add(app_id)

        # 保存进度
        with open(progress_file, 'w', encoding='utf-8') as f:
            for p in processed:
                f.write(p + '\n')

        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False)

        # 打印进度
        done = len(processed)
        print(f"\r进度 {done}/{total} | 成功:{stats['success']} | 未推出:{stats['not_released']} | 非单人:{stats['not_single_player']} | 错误:{stats['error']}", end='')

        time.sleep(1)

    print("\n\n完成！")


if __name__ == "__main__":
    main()