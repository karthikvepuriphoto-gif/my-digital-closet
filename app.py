"""My Digital Closet — a small wardrobe tracker.

Run it with: streamlit run app.py
"""

from __future__ import annotations

import html
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

import wardrobe as w

PAGES = ["Closet", "Add", "Outfits", "Insights"]
SORTS = ["Recently added", "Name", "Color"]
SLOT_FIELDS = [
    ("Outerwear_ID", "Layer"),
    ("Top_ID", "Top"),
    ("FullBody_ID", "One piece"),
    ("Bottom_ID", "Bottom"),
    ("Footwear_ID", "Shoes"),
]

st.set_page_config(
    page_title="My Digital Closet",
    page_icon="🧥",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def apply_pending_state() -> None:
    if st.session_state.pop("reset_add", False):
        st.session_state["add_name"] = ""
        st.session_state["add_cat"] = w.CATEGORIES[0]
        st.session_state["add_color"] = w.COLORS[0]
        st.session_state["add_season"] = w.SEASONS[0]
        st.session_state["add_nonce"] = int(st.session_state.get("add_nonce", 0)) + 1
    if "nav_request" in st.session_state:
        st.session_state["nav"] = st.session_state.pop("nav_request")
    elif "nav" not in st.session_state:
        st.session_state["nav"] = "Closet"
    if st.session_state.pop("reset_outfit_name", False):
        st.session_state["outfit_name"] = ""
    st.session_state.setdefault("closet_query", "")
    st.session_state.setdefault("outfit_mode", "Separates")
    st.session_state.setdefault("outfit_name", "")


def inject_css() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,520;9..144,640&family=Outfit:wght@400;500;600&display=swap');

          html, body, [class*="css"] {
            font-family: "Outfit", "Avenir Next", "Segoe UI", sans-serif;
          }
          .stApp {
            background:
              radial-gradient(1200px 400px at 10% -10%, rgba(156, 123, 74, 0.16), transparent 50%),
              #efe8df;
            color: #221c18;
          }
          .block-container {
            max-width: 1120px;
            padding-top: 1.4rem;
            padding-bottom: 4rem;
          }
          header[data-testid="stHeader"] {
            background: transparent;
          }
          [data-testid="stToolbar"] { display: none; }
          footer { display: none; }
          [data-testid="stHeadingAction"] { display: none; }

          .closet-top .eyebrow {
            margin: 0;
            color: #8a6740;
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.16em;
            text-transform: uppercase;
          }
          .closet-top .wordmark {
            margin: 0.15rem 0 0.2rem;
            font-family: "Fraunces", Georgia, serif;
            font-size: 2.6rem;
            font-weight: 560;
            letter-spacing: -0.04em;
            line-height: 1;
            color: #221c18;
          }
          .closet-top .counts {
            margin: 0;
            color: #6e655c;
            font-size: 0.98rem;
          }
          .page-intro { margin: 0.4rem 0 0.8rem; }
          .page-intro h2 {
            margin: 0;
            font-family: "Fraunces", Georgia, serif;
            font-weight: 560;
            font-size: 1.7rem;
            letter-spacing: -0.03em;
            color: #221c18;
          }
          .page-intro p {
            margin: 0.3rem 0 0;
            color: #6e655c;
            font-size: 1rem;
          }
          .piece-name, .look-name {
            margin: 0.75rem 0 0.15rem;
            font-family: "Fraunces", Georgia, serif;
            font-size: 1.28rem;
            line-height: 1.15;
            letter-spacing: -0.03em;
            color: #221c18;
            overflow-wrap: anywhere;
          }
          .piece-meta, .look-meta {
            margin: 0 0 0.65rem;
            color: #6e655c;
            font-size: 0.88rem;
          }
          .slot-label {
            margin: 0;
            color: #8a6740;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
          }
          .slot-name {
            margin: 0.1rem 0 0.45rem;
            color: #221c18;
            font-size: 0.95rem;
          }
          .swatch {
            height: 220px;
            border-radius: 14px;
            display: flex;
            align-items: flex-end;
            padding: 12px;
            background: #d9d0c4;
          }
          .swatch.preview { height: 150px; }
          .swatch.compact { height: 72px; border-radius: 10px; padding: 8px; }
          .swatch span {
            background: rgba(255, 252, 248, 0.88);
            color: #221c18;
            border-radius: 999px;
            padding: 0.2rem 0.6rem;
            font-size: 0.82rem;
          }
          .empty {
            background: #fffcf8;
            border: 1px solid #e4d9cc;
            border-radius: 18px;
            padding: 1.4rem 1.3rem;
            margin: 0.4rem 0 0.8rem;
          }
          .empty h2 {
            margin: 0;
            font-family: "Fraunces", Georgia, serif;
            font-size: 1.5rem;
            font-weight: 560;
            letter-spacing: -0.03em;
          }
          .empty p { margin: 0.4rem 0 0; color: #6e655c; }
          .banner {
            border-radius: 14px;
            padding: 0.75rem 1rem;
            margin: 0.2rem 0 0.8rem;
          }
          .banner.ok { background: #e4efe6; color: #1d3b2a; }
          .banner.err { background: #f8e6e2; color: #6f2d24; }
          .st-key-closet_grid [data-testid="stImage"] img {
            width: 100%;
            height: 220px;
            object-fit: cover;
            border-radius: 14px;
            background: #efeae3;
          }
          .st-key-look_preview [data-testid="stImage"] img {
            width: 100%;
            height: 150px;
            object-fit: cover;
            border-radius: 12px;
            background: #efeae3;
          }
          .st-key-saved_grid [data-testid="stImage"] img {
            width: 100%;
            height: 72px;
            object-fit: cover;
            border-radius: 10px;
            background: #efeae3;
          }
          [data-testid="stVerticalBlockBorderWrapper"] {
            background: #fffcf8;
            border-color: #e4d9cc !important;
            border-radius: 18px !important;
            box-shadow: 0 12px 30px rgba(60, 42, 28, 0.05);
          }
          @media (max-width: 700px) {
            .closet-top .wordmark { font-size: 2.1rem; }
            .block-container { padding-left: 1rem; padding-right: 1rem; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    apply_pending_state()
    inject_css()
    try:
        items = w.load_items(w.ITEMS_PATH)
        outfits = w.load_outfits(w.OUTFITS_PATH)
    except w.WardrobeError as exc:
        st.error(str(exc))
        st.stop()

    page = render_nav()
    render_header(items, outfits, page)
    render_flash()
    if page == "Add":
        page_add(items, outfits)
    elif page == "Outfits":
        page_outfits(items, outfits)
    elif page == "Insights":
        page_insights(items, outfits)
    else:
        page_closet(items)


def render_nav() -> str:
    page = st.segmented_control(
        "Section",
        PAGES,
        key="nav",
        label_visibility="collapsed",
        width="stretch",
    )
    if page not in PAGES:
        page = "Closet"
    return page


def render_header(items: pd.DataFrame, outfits: pd.DataFrame, page: str) -> None:
    pieces = len(items)
    looks = len(outfits)
    piece_word = "piece" if pieces == 1 else "pieces"
    look_word = "look" if looks == 1 else "looks"
    title, action = st.columns([4, 1], vertical_alignment="center")
    with title:
        st.markdown(
            f"""
            <header class="closet-top">
              <p class="eyebrow">Closet tracker</p>
              <p class="wordmark">My Digital Closet</p>
              <p class="counts">{pieces} {piece_word} · {looks} {look_word}</p>
            </header>
            """,
            unsafe_allow_html=True,
        )
    with action:
        if page != "Add" and st.button(
            "Add a piece",
            type="primary",
            width="stretch",
            key="header_add",
        ):
            st.session_state["nav_request"] = "Add"
            st.rerun()


def render_flash() -> None:
    message = st.session_state.pop("flash", None)
    if not message:
        return
    kind, text = message
    st.markdown(
        f'<div class="banner {html.escape(kind)}">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def page_title(title: str, lede: str) -> None:
    st.markdown(
        f"""
        <div class="page-intro">
          <h2>{html.escape(title)}</h2>
          <p>{html.escape(lede)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_block(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="empty">
          <h2>{html.escape(title)}</h2>
          <p>{html.escape(body)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_closet(items: pd.DataFrame) -> None:
    page_title("Closet", "Browse what you own, then narrow it by category, color, or season.")
    if items.empty:
        empty_block(
            "Your closet is empty",
            "Add the pieces you actually wear. A photo helps, but a name and color are enough.",
        )
        return

    categories = ["All"] + w.CATEGORIES + _extras(items, "Category", w.CATEGORIES)
    colors = ["All"] + _known_values(items, "Primary Color", w.COLORS)
    seasons = list(w.SEASONS) + _extras(items, "Season", w.SEASONS)
    _ensure_choice("closet_category", categories, "All")
    _ensure_choice("closet_color", colors, "All")
    _ensure_choice("closet_season", seasons, "All")
    _ensure_choice("closet_sort", SORTS, "Recently added")

    st.text_input(
        "Search",
        placeholder="Search name, color, or category",
        key="closet_query",
    )
    st.pills("Category", categories, key="closet_category", required=True)
    color_col, season_col, sort_col = st.columns(3)
    with color_col:
        st.selectbox("Color", colors, key="closet_color")
    with season_col:
        st.selectbox("Season", seasons, key="closet_season")
    with sort_col:
        st.selectbox("Sort", SORTS, key="closet_sort")

    category = st.session_state["closet_category"]
    color = st.session_state["closet_color"]
    season = st.session_state["closet_season"]
    query = st.session_state["closet_query"]
    filtered = w.sort_items(
        w.filter_items(
            items,
            query=query,
            category=category,
            color=color,
            season=season,
        ),
        st.session_state["closet_sort"],
    )
    active = bool(str(query).strip()) or category != "All" or color != "All" or season != "All"
    if season not in ("", "All"):
        st.caption("Includes pieces marked for all seasons.")
    if filtered.empty:
        empty_block("Nothing matches", "Try a different name, color, or season.")
        st.button("Clear filters", on_click=_clear_filters)
        return
    note, clear = st.columns([4, 1], vertical_alignment="center")
    with note:
        if active:
            st.caption(f"Showing {len(filtered)} of {len(items)}")
    with clear:
        if active:
            st.button("Clear filters", on_click=_clear_filters, key="clear_filters_top")
    render_closet_grid(filtered)


def render_closet_grid(items: pd.DataFrame) -> None:
    with st.container(
        horizontal=True,
        wrap=True,
        gap="medium",
        vertical_alignment="distribute",
        key="closet_grid",
    ):
        for _, row in items.iterrows():
            piece_card(row)


def piece_card(row: pd.Series) -> None:
    item_id = int(row["ID"])
    name = str(row["Sub-Category"])
    with st.container(border=True, width=240):
        if not show_photo(row["Image_Path"]):
            swatch(name, str(row["Primary Color"]))
        st.markdown(
            f"""
            <p class="piece-name">{html.escape(name)}</p>
            <p class="piece-meta">{html.escape(meta_line(row))}</p>
            """,
            unsafe_allow_html=True,
        )
        with st.container(horizontal=True, gap="xsmall"):
            edit = st.button("Edit", key=f"edit_{item_id}", width="stretch")
            remove = st.button("Remove", key=f"remove_{item_id}", width="stretch")
    if edit:
        prime_edit(row)
        edit_dialog(item_id)
    if remove:
        remove_dialog(item_id)


def page_add(items: pd.DataFrame, outfits: pd.DataFrame) -> None:
    page_title("Add a piece", "A name is enough to start. A photo makes the closet easier to browse.")
    fields, preview = st.columns(2, gap="large")
    with fields:
        name = st.text_input(
            "Name",
            placeholder="Jeans, sweater, loafers",
            max_chars=80,
            key="add_name",
        )
        category = st.selectbox("Category", w.CATEGORIES, key="add_cat")
        color = st.selectbox("Color", w.COLORS, key="add_color")
        season = st.selectbox(
            "Season",
            w.SEASONS,
            key="add_season",
            help="Choose All if you wear it year-round.",
        )
    with preview:
        nonce = int(st.session_state.get("add_nonce", 0))
        photo = st.file_uploader(
            "Photo",
            type=["png", "jpg", "jpeg"],
            key=f"add_photo_{nonce}",
            help="JPG or PNG. Large photos are resized.",
        )
        if photo is not None:
            st.image(photo, width="stretch")
        else:
            swatch(name.strip() or "New piece", color)
    if st.button("Save piece", type="primary", key="save_piece"):
        save_new_piece(name, category, color, season, photo, items, outfits)


def save_new_piece(name, category, color, season, photo, items, outfits) -> None:
    cleaned = name.strip()
    if not cleaned:
        st.error("Enter a name for this piece.")
        return
    image_path = ""
    if photo is not None:
        try:
            image_path = w.store_photo(
                photo.getvalue(),
                w.next_item_id(items, outfits),
                w.APP_DIR,
            )
        except w.WardrobeError as exc:
            st.error(str(exc))
            return
    try:
        updated = w.add_item(
            items,
            outfits,
            category=category,
            sub_category=cleaned,
            color=color,
            season=season,
            image_path=image_path,
        )
        w.save_items(updated, w.ITEMS_PATH)
    except w.WardrobeError as exc:
        st.error(str(exc))
        return
    st.session_state["flash"] = ("ok", f"Added {cleaned}.")
    st.session_state["nav_request"] = "Closet"
    st.session_state["reset_add"] = True
    st.rerun()


def page_outfits(items: pd.DataFrame, outfits: pd.DataFrame) -> None:
    page_title(
        "Outfits",
        "Start with separates or a one-piece, then add a layer and shoes if you want.",
    )
    if items.empty:
        empty_block(
            "Nothing to style yet",
            "Add a few pieces and you can put looks together here.",
        )
        return

    _ensure_choice("outfit_mode", ["Separates", "One piece"], "Separates")
    mode = st.pills(
        "Base",
        ["Separates", "One piece"],
        key="outfit_mode",
        required=True,
    )
    builder, preview = st.columns([1.05, 0.95], gap="large")
    with builder:
        if mode == "One piece":
            full_id = piece_select("One piece", items, "Full Body", "outfit_full")
            top_id = None
            bottom_id = None
        else:
            top_id = piece_select("Top", items, "Tops", "outfit_top")
            bottom_id = piece_select("Bottom", items, "Bottoms", "outfit_bottom")
            full_id = None
        outer_id = piece_select(
            "Layer",
            items,
            "Outerwear",
            "outfit_outer",
            empty_ok=True,
            empty_label="No layer",
        )
        shoe_id = piece_select(
            "Shoes",
            items,
            "Footwear",
            "outfit_shoes",
            empty_ok=True,
            empty_label="No shoes",
        )
        suggestion = suggest_name(items, [outer_id, top_id or full_id, bottom_id, shoe_id])
        st.text_input(
            "Look name",
            placeholder=suggestion,
            max_chars=80,
            key="outfit_name",
        )
        ready, reason = outfit_ready(mode, top_id, bottom_id, full_id)
        if not ready:
            st.caption(reason)
        if st.button("Save look", type="primary", disabled=not ready, key="save_look"):
            label = st.session_state.get("outfit_name", "").strip() or suggestion
            save_look(
                outfits,
                label,
                top_id,
                bottom_id,
                full_id,
                outer_id,
                shoe_id,
            )
    with preview:
        with st.container(border=True, key="look_preview"):
            st.markdown(
                """
                <p class="piece-name">This look</p>
                <p class="piece-meta">The pieces you picked, from coat to shoes.</p>
                """,
                unsafe_allow_html=True,
            )
            chosen = [
                ("Layer", outer_id),
                ("Top", top_id),
                ("One piece", full_id),
                ("Bottom", bottom_id),
                ("Shoes", shoe_id),
            ]
            shown = False
            for label, item_id in chosen:
                row = find_row(items, item_id)
                if row is None:
                    continue
                shown = True
                show_piece_row(label, row, size="preview")
            if not shown:
                st.caption("Choose pieces and they will show up here.")

    st.markdown(
        """
        <div class="page-intro">
          <h2>Saved looks</h2>
          <p>These stay on this computer with the rest of your closet.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if outfits.empty:
        empty_block("No looks yet", "Build one above and it will stay here after you refresh.")
        return
    ordered = outfits.sort_values("ID", ascending=False, kind="mergesort")
    with st.container(horizontal=True, wrap=True, gap="medium", key="saved_grid"):
        for _, outfit in ordered.iterrows():
            saved_look_card(items, outfit)


def page_insights(items: pd.DataFrame, outfits: pd.DataFrame) -> None:
    page_title("Insights", "A quick read on what is taking up space in the closet.")
    if items.empty:
        empty_block("No numbers yet", "Add a few pieces and the mix of colors and seasons will show up here.")
        return
    st.markdown(
        f'<div class="banner ok">{html.escape(w.closet_summary(items))}</div>',
        unsafe_allow_html=True,
    )
    pieces, looks, colors, seasons = st.columns(4)
    pieces.metric("Pieces", len(items))
    looks.metric("Looks", len(outfits))
    colors.metric("Colors", items["Primary Color"].replace("", pd.NA).nunique())
    seasons.metric("Seasons tagged", items["Season"].replace("", pd.NA).nunique())
    left, right = st.columns(2)
    with left:
        st.markdown("##### By category")
        chart(items, "Category", "Pieces")
    with right:
        st.markdown("##### By color")
        chart(items, "Primary Color", "Pieces")
    st.markdown("##### By season")
    chart(items, "Season", "Pieces")


def chart(items: pd.DataFrame, column: str, value_name: str) -> None:
    counts = (
        items[column]
        .replace("", "Unknown")
        .value_counts()
        .rename_axis(column)
        .reset_index(name=value_name)
    )
    top = max(int(counts[value_name].max()), 1)
    spec = (
        alt.Chart(counts)
        .mark_bar(color="#24382d", cornerRadiusEnd=3)
        .encode(
            y=alt.Y(
                f"{column}:N",
                sort=alt.EncodingSortField(field=value_name, order="descending"),
                title=None,
                axis=alt.Axis(labelLimit=160),
            ),
            x=alt.X(
                f"{value_name}:Q",
                title=None,
                scale=alt.Scale(domain=[0, top + 1], nice=False),
                axis=alt.Axis(tickMinStep=1, values=list(range(0, top + 1))),
            ),
            tooltip=[alt.Tooltip(column, title=column), alt.Tooltip(value_name, title=value_name)],
        )
        .properties(height=max(36 * len(counts) + 24, 120))
    )
    st.altair_chart(spec, width="stretch")


def piece_select(
    label: str,
    items: pd.DataFrame,
    category: str,
    key: str,
    *,
    empty_ok: bool = False,
    empty_label: str = "None",
) -> int | None:
    frame = items[items["Category"] == category].sort_values(
        "Sub-Category",
        key=lambda names: names.astype(str).str.lower(),
        kind="mergesort",
    )
    options: list[int | None] = []
    if empty_ok:
        options.append(None)
    options.extend(int(item_id) for item_id in frame["ID"].tolist())
    if not options:
        st.caption(f"No {label.lower()} in the closet yet.")
        return None
    if key not in st.session_state or st.session_state[key] not in options:
        st.session_state[key] = options[0]
    return st.selectbox(
        label,
        options,
        format_func=lambda item_id: empty_label if item_id is None else option_label(frame, item_id),
        key=key,
    )


def saved_look_card(items: pd.DataFrame, outfit: pd.Series) -> None:
    outfit_id = int(outfit["ID"])
    pieces = [(label, find_row(items, outfit[field])) for field, label in SLOT_FIELDS]
    pieces = [(label, row) for label, row in pieces if row is not None]
    with st.container(border=True, width=320):
        st.markdown(
            f"""
            <p class="look-name">{html.escape(str(outfit["Name"]))}</p>
            <p class="look-meta">{html.escape(look_meta(outfit, pieces))}</p>
            """,
            unsafe_allow_html=True,
        )
        if not pieces:
            st.caption("The pieces in this look are no longer in the closet.")
        for label, row in pieces:
            show_piece_row(label, row, size="mini")
        if st.button("Remove look", key=f"remove_look_{outfit_id}", width="stretch"):
            remove_look_dialog(outfit_id, str(outfit["Name"]))


def show_piece_row(label: str, row: pd.Series, *, size: str) -> None:
    photo, text = st.columns([1, 2], vertical_alignment="center")
    with photo:
        if not show_photo(row["Image_Path"]):
            swatch(str(row["Sub-Category"]), str(row["Primary Color"]), size=size)
    with text:
        st.markdown(
            f"""
            <p class="slot-label">{html.escape(label)}</p>
            <p class="slot-name">{html.escape(str(row["Sub-Category"]))}</p>
            """,
            unsafe_allow_html=True,
        )


def show_photo(path: object) -> bool:
    resolved = w.resolve_image(path, w.APP_DIR)
    if resolved is None:
        return False
    st.image(str(resolved), width="stretch")
    return True


def swatch(name: str, color: str, *, size: str = "card") -> None:
    klass = "swatch" if size == "card" else f"swatch {size}"
    st.markdown(
        f"""
        <div class="{klass}" style="background:{html.escape(swatch_color(color), quote=True)}">
          <span>{html.escape(name)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def save_look(outfits, name, top_id, bottom_id, full_id, outer_id, shoe_id) -> None:
    try:
        updated = w.add_outfit(
            outfits,
            name=name,
            top_id=top_id,
            bottom_id=bottom_id,
            full_body_id=full_id,
            outerwear_id=outer_id,
            footwear_id=shoe_id,
        )
        w.save_outfits(updated, w.OUTFITS_PATH)
    except w.WardrobeError as exc:
        st.error(str(exc))
        return
    st.session_state["flash"] = ("ok", f"Saved {name}.")
    st.session_state["reset_outfit_name"] = True
    st.rerun()


@st.dialog("Edit piece", width="medium")
def edit_dialog(item_id: int) -> None:
    items = w.load_items(w.ITEMS_PATH)
    row = find_row(items, item_id)
    if row is None:
        st.info("That piece is no longer in the closet.")
        return
    name = st.text_input("Name", max_chars=80, key="edit_name")
    category = st.selectbox(
        "Category",
        _with_current(w.CATEGORIES, st.session_state.get("edit_cat", "")),
        key="edit_cat",
    )
    color = st.selectbox(
        "Color",
        _with_current(w.COLORS, st.session_state.get("edit_color", "")),
        key="edit_color",
    )
    season = st.selectbox(
        "Season",
        _with_current(w.SEASONS, st.session_state.get("edit_season", "")),
        key="edit_season",
        help="Choose All if you wear it year-round.",
    )
    nonce = int(st.session_state.get("edit_nonce", 0))
    uploaded = st.file_uploader(
        "Replace photo",
        type=["png", "jpg", "jpeg"],
        key=f"edit_photo_{nonce}",
    )
    if uploaded is not None:
        st.image(uploaded, width="stretch")
    elif not show_photo(row["Image_Path"]):
        swatch(str(row["Sub-Category"]), str(row["Primary Color"]), size="mini")
    with st.container(horizontal=True, gap="small"):
        save = st.button("Save changes", type="primary", key="edit_save")
        cancel = st.button("Cancel", key="edit_cancel")
    if cancel:
        st.rerun()
    if save:
        apply_edit(items, row, name, category, color, season, uploaded)


def apply_edit(items, row, name, category, color, season, uploaded) -> None:
    cleaned = name.strip()
    if not cleaned:
        st.error("Enter a name for this piece.")
        return
    fields = {
        "Sub-Category": cleaned,
        "Category": category,
        "Primary Color": color,
        "Season": season,
    }
    old_photo = row["Image_Path"]
    if uploaded is not None:
        try:
            fields["Image_Path"] = w.store_photo(uploaded.getvalue(), int(row["ID"]), w.APP_DIR)
        except w.WardrobeError as exc:
            st.error(str(exc))
            return
    try:
        updated = w.update_item(items, int(row["ID"]), **fields)
        w.save_items(updated, w.ITEMS_PATH)
        if uploaded is not None:
            w.remove_stored_photo(old_photo, w.APP_DIR, updated)
    except w.WardrobeError as exc:
        st.error(str(exc))
        return
    st.session_state["flash"] = ("ok", f"Updated {cleaned}.")
    st.rerun()


@st.dialog("Remove this piece?")
def remove_dialog(item_id: int) -> None:
    items = w.load_items(w.ITEMS_PATH)
    row = find_row(items, item_id)
    if row is None:
        st.info("That piece is already gone.")
        return
    name = str(row["Sub-Category"])
    st.markdown(
        f"<p>Remove <strong>{html.escape(name)}</strong> from the closet? "
        "Saved looks keep their other pieces.</p>",
        unsafe_allow_html=True,
    )
    if st.button("Remove piece", type="primary", key="confirm_remove"):
        outfits = w.load_outfits(w.OUTFITS_PATH)
        kept_items, kept_outfits = w.delete_item(items, outfits, item_id, w.APP_DIR)
        w.save_items(kept_items, w.ITEMS_PATH)
        w.save_outfits(kept_outfits, w.OUTFITS_PATH)
        st.session_state["flash"] = ("ok", f"Removed {name}.")
        st.rerun()
    if st.button("Keep it", key="cancel_remove"):
        st.rerun()


@st.dialog("Remove this look?")
def remove_look_dialog(outfit_id: int, name: str) -> None:
    st.markdown(
        f"<p>Remove <strong>{html.escape(name)}</strong>? The clothes stay in your closet.</p>",
        unsafe_allow_html=True,
    )
    if st.button("Remove look", type="primary", key="confirm_remove_look"):
        outfits = w.delete_outfit(w.load_outfits(w.OUTFITS_PATH), outfit_id)
        w.save_outfits(outfits, w.OUTFITS_PATH)
        st.session_state["flash"] = ("ok", f"Removed {name}.")
        st.rerun()
    if st.button("Keep it", key="cancel_remove_look"):
        st.rerun()


def prime_edit(row: pd.Series) -> None:
    st.session_state["edit_name"] = str(row["Sub-Category"])
    st.session_state["edit_cat"] = str(row["Category"])
    st.session_state["edit_color"] = str(row["Primary Color"])
    st.session_state["edit_season"] = str(row["Season"])
    st.session_state["edit_nonce"] = int(st.session_state.get("edit_nonce", 0)) + 1


def outfit_ready(mode, top_id, bottom_id, full_id) -> tuple[bool, str]:
    if mode == "One piece":
        if full_id is None:
            return False, "Add a one-piece, like a dress or jumpsuit, before saving this look."
        return True, ""
    if top_id is None or bottom_id is None:
        return False, "Add a top and a bottom before saving a separates look."
    return True, ""


def suggest_name(items: pd.DataFrame, ids: list[object]) -> str:
    names = []
    for item_id in ids:
        row = find_row(items, item_id)
        if row is not None:
            names.append(str(row["Sub-Category"]))
    return " + ".join(names) if names else "Untitled look"


def find_row(items: pd.DataFrame, item_id: object) -> pd.Series | None:
    parsed = w.parse_optional_id(item_id)
    if parsed is None or items.empty:
        return None
    match = items[items["ID"] == parsed]
    if match.empty:
        return None
    return match.iloc[0]


def option_label(frame: pd.DataFrame, item_id: int) -> str:
    row = find_row(frame, item_id)
    if row is None:
        return "Missing piece"
    return f"{row['Sub-Category']} · {row['Primary Color']}"


def meta_line(row: pd.Series) -> str:
    season = str(row["Season"])
    season_text = "All seasons" if season == "All" else season
    return f"{row['Category']} · {row['Primary Color']} · {season_text}"


def look_meta(outfit: pd.Series, pieces: list[tuple[str, pd.Series]]) -> str:
    created = format_created(str(outfit["Created"]))
    names = ", ".join(str(row["Sub-Category"]) for _, row in pieces) or "No pieces left"
    if created:
        return f"{names} · {created}"
    return names


def format_created(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return text
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def swatch_color(color: str) -> str:
    palette = {
        "Black": "#2a2a2a",
        "White": "#f4f1ea",
        "Grey": "#c4beb6",
        "Beige": "#e0d0b8",
        "Brown": "#8a6244",
        "Blue": "#3e618f",
        "Navy": "#24344f",
        "Green": "#3f5c49",
        "Red": "#8d3d3d",
        "Pink": "#e7b3bf",
        "Yellow": "#e4c56a",
        "Orange": "#d4843c",
        "Purple": "#65547a",
    }
    return palette.get(color, "#d9d0c4")


def _known_values(items: pd.DataFrame, column: str, preferred: list[str]) -> list[str]:
    present = {str(value) for value in items[column].tolist() if str(value).strip()}
    ordered = [value for value in preferred if value in present]
    return ordered + _extras(items, column, preferred)


def _extras(items: pd.DataFrame, column: str, known: list[str]) -> list[str]:
    present = {str(value) for value in items[column].tolist() if str(value).strip()}
    return sorted(value for value in present if value not in known)


def _with_current(options: list[str], current: str) -> list[str]:
    if current and current not in options:
        return options + [current]
    return options


def _ensure_choice(key: str, options: list[str], fallback: str) -> None:
    if key not in st.session_state or st.session_state[key] not in options:
        st.session_state[key] = fallback if fallback in options else options[0]


def _clear_filters() -> None:
    st.session_state["closet_query"] = ""
    st.session_state["closet_category"] = "All"
    st.session_state["closet_color"] = "All"
    st.session_state["closet_season"] = "All"


if __name__ == "__main__":
    main()
