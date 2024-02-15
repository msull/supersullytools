import streamlit as st

from supersullytools.streamlit.misc import check_or_x
from supersullytools.streamlit.paginator import item_paginator

sample_data = [
    {"name": "Item1", "category": "Electronics", "price": 299.99, "rating": 4.5, "in_stock": True},
    {"name": "Item2", "category": "Books", "price": 15.99, "rating": 4.8, "in_stock": False},
    {"name": "Item3", "category": "Clothing", "price": 49.99, "rating": 3.9, "in_stock": True},
    {"name": "Item4", "category": "Groceries", "price": 3.49, "rating": 4.2, "in_stock": True},
]


def display_sample_item(item_idx):
    item = sample_data[item_idx]
    st.subheader(item["name"])
    st.caption(f"category={item['category']}")
    metric_cols = iter(st.columns(3))
    with next(metric_cols):
        st.metric("Price", item["price"])
    with next(metric_cols):
        st.metric("Rating", item["rating"])
    with next(metric_cols):
        st.metric("In-Stock", check_or_x(item["in_stock"]))


def main():
    st.write("Use left/right arrows to navigate between items.")
    item_names = [x["name"] for x in sample_data]
    item_paginator(
        title="Available Items",
        items=item_names,
        display_item_names=True,
        item_handler_fn=display_sample_item,
        enable_keypress_nav=True,
    )


if __name__ == "__main__":
    main()
