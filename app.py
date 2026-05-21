import os

import pandas as pd
import streamlit as st
from PIL import Image

DB_FILE = "wardrobe_db.csv"
IMAGE_DIR = "closet_images"

if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)


def load_db():
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE)
    return pd.DataFrame(
        columns=["ID", "Category", "Sub-Category", "Primary Color", "Season", "Image_Path"]
    )


def next_id(df):
    if df.empty:
        return 1
    return int(df["ID"].max()) + 1


def item_label(row):
    return f"{row['Sub-Category']} ({row['Primary Color']}) [#{int(row['ID'])}]"


def show_image(path, **kwargs):
    if path != "None" and os.path.exists(path):
        st.image(path, **kwargs)
    else:
        st.caption("No photo")


st.set_page_config(page_title="My Digital Closet", layout="wide")
df = load_db()

st.title("👗 My Custom Wardrobe App")

# --- SIDEBAR: ADD CLOTHES ---
st.sidebar.header("➕ Add New Item")
categories = ["Tops", "Bottoms", "Full Body", "Outerwear", "Footwear"]
colors = ["Black", "White", "Grey", "Beige", "Blue", "Green", "Red", "Pink", "Yellow"]
seasons = ["All", "Spring", "Summer", "Autumn", "Winter"]

with st.sidebar.form("add_item_form", clear_on_submit=True):
    category = st.selectbox("Category", categories)
    sub_cat = st.text_input("Sub-Category (e.g., Jeans, Sweater)")
    color = st.selectbox("Primary Color", colors)
    season = st.selectbox("Season", seasons)
    uploaded_file = st.file_uploader("Upload Photo", type=["jpg", "jpeg", "png"])
    submit = st.form_submit_button("Save Item")

    if submit:
        if not sub_cat.strip():
            st.sidebar.error("Please enter a sub-category.")
        else:
            new_id = next_id(df)
            img_path = "None"

            if uploaded_file is not None:
                img_path = os.path.join(IMAGE_DIR, f"item_{new_id}.png")
                Image.open(uploaded_file).save(img_path)

            new_row = pd.DataFrame(
                [
                    {
                        "ID": new_id,
                        "Category": category,
                        "Sub-Category": sub_cat.strip(),
                        "Primary Color": color,
                        "Season": season,
                        "Image_Path": img_path,
                    }
                ]
            )
            df = pd.concat([df, new_row], ignore_index=True)
            df.to_csv(DB_FILE, index=False)
            st.sidebar.success(f"Added {sub_cat.strip()} successfully!")
            st.rerun()

# --- MAIN APP TABS ---
tab1, tab2, tab3 = st.tabs(["🗄️ View Closet", "✨ Outfit Builder", "📊 Analytics"])

# TAB 1: VIEW CLOSET WITH PHOTOS
with tab1:
    st.subheader("Your Wardrobe Gallery")
    if df.empty:
        st.info("Your closet is currently empty.")
    else:
        f_cat = st.multiselect("Filter by Category", sorted(df["Category"].unique()))
        f_col = st.multiselect("Filter by Color", sorted(df["Primary Color"].unique()))

        filtered_df = df.copy()
        if f_cat:
            filtered_df = filtered_df[filtered_df["Category"].isin(f_cat)]
        if f_col:
            filtered_df = filtered_df[filtered_df["Primary Color"].isin(f_col)]

        cols = st.columns(4)
        for i, (_, row) in enumerate(filtered_df.iterrows()):
            with cols[i % 4]:
                show_image(row["Image_Path"], use_container_width=True)
                st.caption(f"**{row['Sub-Category']}** ({row['Primary Color']})")

# TAB 2: OUTFIT BUILDER
with tab2:
    st.subheader("Create an Outfit")
    if df.empty:
        st.info("Add items to build outfits.")
    else:
        tops = df[df["Category"] == "Tops"]
        bottoms = df[df["Category"] == "Bottoms"]

        if tops.empty or bottoms.empty:
            st.warning("Please add at least one 'Top' and one 'Bottom' to use the Outfit Builder.")
        else:
            build_col1, build_col2 = st.columns(2)

            with build_col1:
                st.write("### Select Top")
                top_labels = tops.apply(item_label, axis=1).tolist()
                top_by_label = dict(zip(top_labels, tops["ID"].astype(int)))
                selected_top_label = st.selectbox("Choose a Top", top_labels, key="top_select")
                top_row = tops[tops["ID"] == top_by_label[selected_top_label]].iloc[0]
                show_image(top_row["Image_Path"], width=200)

            with build_col2:
                st.write("### Select Bottom")
                bot_labels = bottoms.apply(item_label, axis=1).tolist()
                bot_by_label = dict(zip(bot_labels, bottoms["ID"].astype(int)))
                selected_bot_label = st.selectbox("Choose a Bottom", bot_labels, key="bot_select")
                bot_row = bottoms[bottoms["ID"] == bot_by_label[selected_bot_label]].iloc[0]
                show_image(bot_row["Image_Path"], width=200)

            if st.button("❤️ Save This Outfit Look"):
                st.success(
                    f"Saved: {top_row['Sub-Category']} paired with {bot_row['Sub-Category']}!"
                )

# TAB 3: ANALYTICS
with tab3:
    st.subheader("Closet Metrics")
    if df.empty:
        st.info("No data yet.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.write("By category")
            c1.bar_chart(df["Category"].value_counts())
        with c2:
            st.write("By color")
            c2.bar_chart(df["Primary Color"].value_counts())
