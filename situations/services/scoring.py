def find_windows(scored: list[dict], min_score: int, max_windows: int = 1) -> list[dict]:
    """점수가 min_score 이상인 시간이 연속된 구간 중 좋은 순으로 max_windows개를 고른다.

    scored: [{"hour": 11, "score": 85, ...}, ...] 시간 순서대로
    """
    runs, current = [], []
    for item in scored:
        if item["score"] < min_score:
            if current:
                runs.append(current)
            current = []
            continue
        if current and item["hour"] != current[-1]["hour"] + 1:
            runs.append(current)
            current = []
        current.append(item)
    if current:
        runs.append(current)

    # 길수록, 같은 길이면 점수 합이 높을수록 좋은 구간
    runs.sort(key=lambda r: (len(r), sum(i["score"] for i in r)), reverse=True)
    picked = sorted(runs[:max_windows], key=lambda r: r[0]["hour"])
    return [
        {
            "start": f"{run[0]['hour']:02d}:00",
            "end": f"{(run[-1]['hour'] + 1) % 24:02d}:00",
        }
        for run in picked
    ]

BEST_CENTER_HOUR = 13  # 점수가 같으면 해가 가장 강한 13시 근처를 고른다


def best_block(scored: list[dict], length: int, min_score: int) -> dict | None:
    """연속된 length시간 중 점수 합이 가장 높은 구간. 모든 시간이 min_score 이상이어야 한다."""
    best_key, best_block_items = None, None
    for i in range(len(scored) - length + 1):
        block = scored[i:i + length]
        hours = [item["hour"] for item in block]
        if hours != list(range(hours[0], hours[0] + length)):
            continue  # 중간에 시간이 끊긴 구간
        if min(item["score"] for item in block) < min_score:
            continue
        center = hours[0] + length / 2
        key = (sum(item["score"] for item in block), -abs(center - BEST_CENTER_HOUR))
        if best_key is None or key > best_key:
            best_key, best_block_items = key, block

    if best_block_items is None:
        return None
    return {
        "start": f"{best_block_items[0]['hour']:02d}:00",
        "end": f"{(best_block_items[-1]['hour'] + 1) % 24:02d}:00",
    }