"""Помощники оформления: связка заказов, созданных одним действием."""

from collections import defaultdict


def attach_checkout_groups(orders):
    """Проставляет каждому заказу номера соседей по общему checkout_id."""
    orders = list(orders)
    groups = defaultdict(list)
    for order in orders:
        if order.checkout_id:
            groups[order.checkout_id].append(order)

    for order in orders:
        siblings = groups.get(order.checkout_id, [])
        order.checkout_group_ids = [
            sibling.pk for sibling in siblings if sibling.pk != order.pk
        ]
    return orders
