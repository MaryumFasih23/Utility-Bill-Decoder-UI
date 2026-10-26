"""
eval/review_app.py — Streamlit Verification & Review Interface
Enables human (or AI-assisted) verification of Level 1 extracted bill details against original bill scans.
"""
import csv
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
from PIL import Image
import streamlit as st

st.set_page_config(
    page_title="Level 1 Bill Verification Tool",
    page_icon="🔍",
    layout="wide"
)

ROOT = Path(__file__).resolve().parents[1]
SHEET_PATH = ROOT / "eval/review_sheet.csv"

def load_sheet():
    if not SHEET_PATH.exists():
        st.error(f"Review sheet not found at `{SHEET_PATH}`. Please run `python scripts/build_review_sheet.py` first.")
        st.stop()
    return pd.read_csv(SHEET_PATH, dtype=str).fillna("")

def save_sheet(df):
    df.to_csv(SHEET_PATH, index=False, encoding="utf-8")

df_sheet = load_sheet()

st.title("🔍 Level 1 Ground-Truth Verification Tool")
st.caption("Inspect original bill scans side-by-side with extracted values to verify accuracy or record ground truth.")

# Summary metrics across the entire dataset
total_rows = len(df_sheet)
correct_count = (df_sheet["correct"].str.lower() == "correct").sum()
incorrect_count = (df_sheet["correct"].str.lower() == "incorrect").sum()
unsure_count = (df_sheet["correct"].str.lower() == "unsure").sum()
unlabeled_count = total_rows - (correct_count + incorrect_count + unsure_count)

col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
col_m1.metric("Total Fields", total_rows)
col_m2.metric("✅ Correct", correct_count)
col_m3.metric("❌ Incorrect", incorrect_count)
col_m4.metric("❓ Unsure", unsure_count)
col_m5.metric("⏳ Unlabeled", unlabeled_count)

st.markdown("---")

# Sidebar navigation
with st.sidebar:
    st.header("📋 Bills")
    bill_ids = sorted(df_sheet["bill_id"].unique())
    selected_bill = st.selectbox("Select Bill to Inspect", bill_ids, index=0)
    
    st.markdown("---")
    st.subheader("🔎 Zoom Controls")
    zoom_width = st.slider("Image Display Width (px)", min_value=400, max_value=2400, value=900, step=50)

    st.markdown("---")
    st.subheader("⚡ Quick Batch Actions")
    if st.button("Mark all unlabeled on this bill as Correct", use_container_width=True):
        mask = (df_sheet["bill_id"] == selected_bill) & (df_sheet["correct"] == "")
        df_sheet.loc[mask, "correct"] = "correct"
        save_sheet(df_sheet)
        st.success("Updated unlabeled rows to correct!")
        st.rerun()

    if st.button("Reset this bill's review labels", use_container_width=True):
        mask = df_sheet["bill_id"] == selected_bill
        df_sheet.loc[mask, "correct"] = ""
        df_sheet.loc[mask, "true_value"] = ""
        df_sheet.loc[mask, "notes"] = ""
        save_sheet(df_sheet)
        st.info("Reset review labels for this bill.")
        st.rerun()

    st.markdown("---")
    st.caption("When done labeling, run `python eval/score.py` to generate the evaluation report.")

# Filter rows for selected bill
bill_rows = df_sheet[df_sheet["bill_id"] == selected_bill].copy()
img_rel_path = bill_rows["bill_image_path"].iloc[0] if not bill_rows.empty else ""
img_full_path = ROOT / img_rel_path

col_img, col_form = st.columns([0.48, 0.52], gap="large")

with col_img:
    st.subheader(f"📄 Scan: {selected_bill}")
    if img_full_path.exists():
        try:
            image = Image.open(img_full_path)
            st.image(image, width=zoom_width, caption=f"{img_rel_path} ({image.width}x{image.height} px)")
        except Exception as e:
            st.error(f"Cannot open image: {e}")
    else:
        st.warning(f"Image not found at path: `{img_full_path}`")

with col_form:
    st.subheader(f"📝 Verification Form — {selected_bill}")
    st.caption("Review extracted values against the image on the left. Click 'Save Changes' when done.")

    with st.form(key=f"form_{selected_bill}"):
        updated_records = []
        for idx, row in bill_rows.iterrows():
            fld = row["field"]
            ext_val = row["extracted_value"]
            curr_status = row["correct"].lower()
            curr_true = row["true_value"]
            curr_notes = row["notes"]

            st.markdown(f"**Field:** `{fld}` | **Extracted:** `{ext_val if ext_val != '' else '(null/empty)'}`")
            
            c1, c2, c3 = st.columns([0.3, 0.35, 0.35])
            
            status_opts = ["", "correct", "incorrect", "unsure"]
            status_idx = status_opts.index(curr_status) if curr_status in status_opts else 0
            
            new_status = c1.selectbox(
                "Status",
                options=status_opts,
                index=status_idx,
                key=f"status_{idx}",
                format_func=lambda x: "⏳ Unlabeled" if x == "" else ("✅ Correct" if x == "correct" else ("❌ Incorrect" if x == "incorrect" else "❓ Unsure"))
            )
            
            new_true = c2.text_input(
                "True Value (if incorrect)",
                value=curr_true,
                key=f"true_{idx}",
                placeholder="True printed value"
            )
            
            new_notes = c3.text_input(
                "Notes",
                value=curr_notes,
                key=f"notes_{idx}",
                placeholder="Observation or comments"
            )
            
            st.markdown("<hr style='margin: 0.4rem 0;'>", unsafe_allow_html=True)
            
            updated_records.append((idx, new_status, new_true, new_notes))

        submitted = st.form_submit_button(f"💾 Save Changes for {selected_bill}", use_container_width=True)
        if submitted:
            for idx, n_stat, n_true, n_not in updated_records:
                df_sheet.at[idx, "correct"] = n_stat
                df_sheet.at[idx, "true_value"] = n_true
                df_sheet.at[idx, "notes"] = n_not
            save_sheet(df_sheet)
            st.success(f"Successfully saved verification changes for {selected_bill}!")
            st.rerun()
