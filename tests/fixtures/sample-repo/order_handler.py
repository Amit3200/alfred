"""Handle duplicate order detection before checkout completes."""


def is_duplicate_order(order_id: str, seen: set[str]) -> bool:
    if order_id in seen:
        return True
    seen.add(order_id)
    return False


def validate_order(order_id: str, seen: set[str]) -> bool:
    return not is_duplicate_order(order_id, seen)
