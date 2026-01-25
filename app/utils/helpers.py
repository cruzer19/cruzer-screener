def get_tick(price: float) -> int:
    if price < 200:
        return 1
    elif price < 500:
        return 2
    elif price < 2000:
        return 5
    elif price < 5000:
        return 10
    else:
        return 25


def round_down(price: float) -> int:
    tick = get_tick(price)
    return int(price // tick * tick)


def round_up(price: float) -> int:
    tick = get_tick(price)
    return int((price + tick - 1) // tick * tick)