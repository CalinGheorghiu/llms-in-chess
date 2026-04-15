import streamlit as st
import pandas as pd
import chess
import chess.pgn
import chess.svg
from streamlit_option_menu import option_menu
import os

st.set_page_config(layout="wide")

# =========================
# LOAD EXCEL
# =========================
@st.cache_data
def load_data(file_path):
    xls = pd.ExcelFile(file_path)

    models = []
    data = {}

    for sheet in xls.sheet_names:
        if sheet.startswith("Data "):
            model = sheet.replace("Data ", "").strip()
            models.append(model)
            data[model] = pd.read_excel(xls, f"Data {model}")

    return models, data


# =========================
# LOAD PGN
# =========================
@st.cache_data
def load_pgn_sequences(pgn_file):
    puzzles = {}

    with open(pgn_file) as f:
        i = 0
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break

            board = game.board()
            moves = list(game.mainline_moves())

            puzzles[i] = {
                "initial_fen": board.fen(),
                "moves": moves
            }

            i += 1

    return puzzles


# =========================
# FILES (UPDATED STRUCTURE)
# =========================
excel_file = "data/dataset-scored.xlsx"
pgn_file = "data/puzzles_with_moves.pgn"

if not os.path.exists(excel_file):
    st.error(f"Missing file: {excel_file}")
    st.stop()

if not os.path.exists(pgn_file):
    st.error(f"Missing file: {pgn_file}")
    st.stop()

models, data = load_data(excel_file)
pgn_data = load_pgn_sequences(pgn_file)


# =========================
# NAVIGATION
# =========================
with st.sidebar:
    selected = option_menu(
        "Navigation",
        ["Explorer", "Ranking", "Conclusions"],
        icons=["search", "bar-chart", "file-text"],
        default_index=0
    )


# =========================
# EXPLORER
# =========================
if selected == "Explorer":

    st.title("♟️ LLM Chess Explorer")

    selected_models = st.sidebar.multiselect(
        "Models",
        models,
        default=[models[0]]
    )

    if not selected_models:
        st.warning("Select at least one model")
        st.stop()

    df_main = data[selected_models[0]]

    puzzle_id = st.sidebar.selectbox(
        "Puzzle",
        sorted(df_main["puzzle_id"].unique())
    )

    puzzle = pgn_data[puzzle_id]
    initial_fen = puzzle["initial_fen"]
    moves = puzzle["moves"]

    # =========================
    # SESSION STATE
    # =========================
    if "move_index" not in st.session_state:
        st.session_state.move_index = 0

    if "current_puzzle" not in st.session_state:
        st.session_state.current_puzzle = puzzle_id

    if st.session_state.current_puzzle != puzzle_id:
        st.session_state.current_puzzle = puzzle_id
        st.session_state.move_index = 0

    # =========================
    # LAYOUT
    # =========================
    col1, col2 = st.columns([1.2, 2])

    # =========================
    # LEFT: CONTROLS + BOARD
    # =========================
    with col1:

        st.subheader("♟️ Position")

        # 🔥 CONTROLS FIRST (fix)
        colA, colB, colC, colD = st.columns(4)

        with colA:
            if st.button("⏮ Reset"):
                st.session_state.move_index = 0

        with colB:
            if st.button("⬅️ Prev"):
                if st.session_state.move_index > 0:
                    st.session_state.move_index -= 1

        with colC:
            if st.button("➡️ Next"):
                if st.session_state.move_index < len(moves):
                    st.session_state.move_index += 1

        with colD:
            if st.button("⏭ End"):
                st.session_state.move_index = len(moves)

        # 🔥 BUILD BOARD AFTER BUTTONS
        board = chess.Board(initial_fen)
        for i in range(st.session_state.move_index):
            board.push(moves[i])

        svg = chess.svg.board(board=board, size=720)
        st.image(svg)

    # =========================
    # CURRENT MOVE (FIXED)
    # =========================
    current_san = None

    if st.session_state.move_index > 0:
        temp_board = chess.Board(initial_fen)

        for i in range(st.session_state.move_index - 1):
            temp_board.push(moves[i])

        current_move = moves[st.session_state.move_index - 1]
        current_san = temp_board.san(current_move)

    # =========================
    # RIGHT: MOVES + EXPLANATIONS
    # =========================
    with col2:

        st.subheader("📜 Move Sequence")

        temp_board = chess.Board(initial_fen)

        for i, m in enumerate(moves):
            san = temp_board.san(m)
            temp_board.push(m)

            if i == st.session_state.move_index - 1:
                st.markdown(f"👉 **{i+1}. {san}**")
            else:
                st.markdown(f"{i+1}. {san}")

        st.markdown("---")
        st.subheader("🧠 Model Explanations & Corrections")

        if current_san is None:
            st.info("Click ▶️ Next to start")
        else:
            cols = st.columns(len(selected_models))

            for i, model in enumerate(selected_models):
                with cols[i]:

                    st.markdown(f"### {model}")

                    df = data[model]
                    rows = df[df["puzzle_id"] == puzzle_id]

                    move_rows = rows[
                        rows["move"].astype(str).str.contains(current_san, na=False)
                    ]

                    if move_rows.empty:
                        st.warning("No explanation")
                    else:
                        for j, r in enumerate(move_rows.itertuples(), 1):

                            st.markdown(f"**Explanation {j}**")
                            st.write(r.original_claim)

                            st.markdown("⚠️ Hallucination")
                            st.write(r.hallucination_type)

                            st.markdown("✅ Correction")
                            st.write(r.fixed_claim)

    # =========================
    # TABLE
    # =========================
    st.markdown("---")
    st.subheader("📊 Annotated Data (Full)")

    table_rows = []

    for model in selected_models:
        df = data[model]
        rows = df[df["puzzle_id"] == puzzle_id]

        for r in rows.itertuples():
            table_rows.append({
                "Model": model,
                "Move": r.move,
                "Explanation": r.original_claim,
                "Hallucination": r.hallucination_type,
                "Correction": r.fixed_claim
            })

    st.dataframe(pd.DataFrame(table_rows))


# =========================
# RANKING
# =========================
elif selected == "Ranking":

    import plotly.express as px

    st.title("📊 Model Ranking & Analysis")

    category_weights = {
        "move_legality": 8,
        "piece_placement": 6,
        "material": 5,
        "piece_relations": 4,
        "geometry": 3,
        "reasoning": 2,
        "other": 1
    }

    severity_weights = {
        "major": 3,
        "medium": 2,
        "minor": 1,
        "small": 1
    }

    delta = 0.7

    def extract_category(text):
        text = str(text).lower()

        if "illegal" in text:
            return "move_legality"
        if "square" in text:
            return "piece_placement"
        if "material" in text:
            return "material"
        if "pin" in text or "fork" in text:
            return "piece_relations"
        if "diagonal" in text:
            return "geometry"
        if "reason" in text:
            return "reasoning"

        return "other"

    def extract_severity(text):
        text = str(text).lower()
        if "major" in text:
            return "major"
        if "medium" in text:
            return "medium"
        return "minor"

    all_rows = []

    for model in models:
        df = data[model].dropna(subset=["hallucination_type"])

        for _, row in df.iterrows():
            cat = extract_category(row["hallucination_type"])
            sev = extract_severity(row["hallucination_type"])

            all_rows.append({
                "Model": model,
                "Puzzle": row["puzzle_id"],
                "Category": cat,
                "Severity": sev,
                "Penalty": category_weights[cat] * severity_weights[sev]
            })

    df_all = pd.DataFrame(all_rows)

    model_scores = []

    for model in models:
        df_model = df_all[df_all["Model"] == model]

        total = 0
        grouped = df_model.groupby(["Puzzle", "Category"])

        for _, group in grouped:
            penalties = sorted(group["Penalty"], reverse=True)
            for i, p in enumerate(penalties):
                total += p * (delta ** i)

        model_scores.append({"Model": model, "Penalty": total})

    scores_df = pd.DataFrame(model_scores)
    max_penalty = scores_df["Penalty"].max()
    scores_df["Score"] = 100 * (1 - scores_df["Penalty"] / max_penalty)

    st.dataframe(scores_df.sort_values("Score", ascending=False))

    pivot = df_all.groupby(["Model", "Category"])["Penalty"].sum().unstack().fillna(0)

    fig = px.imshow(pivot, text_auto=True)
    st.plotly_chart(fig, use_container_width=True)


# =========================
# CONCLUSIONS
# =========================
elif selected == "Conclusions":

    st.title("🧾 Conclusions")

    st.markdown("""
LLMs show strong potential for chess education, but current models suffer from:

- Structural hallucinations (board misunderstanding)
- Reasoning hallucinations (incorrect logic)
- Overconfidence in incorrect outputs

👉 They cannot yet function as reliable standalone instructors.

Future systems should combine LLMs with deterministic chess engines.
""")
# =========================
# CONCLUSIONS
# =========================
elif selected == "Conclusions":

    st.title("🧾 Conclusions")

    # =========================
    # INTRO
    # =========================
    st.markdown("""
The integration of **Large Language Models (LLMs)** into chess e-learning environments presents a compelling opportunity for delivering personalized, natural-language instruction.  
However, our evaluation shows that this potential **cannot be reliably realized in their ungrounded, baseline form**.
""")

    st.markdown("---")

    # =========================
    # FAILURE MODES
    # =========================
    st.subheader("⚠️ Divergent Failure Modes")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Structural Failures")
        st.markdown("""
- Models like **DeepSeek** and **Kimi**
- Struggle with **board representation**
- Exhibit **geometric blindness**
- Produce **high rates of hallucinations**
        """)

    with col2:
        st.markdown("### Illusion of Reasoning")
        st.markdown("""
- Models like **Gemini** and **GPT**
- Handle geometry correctly
- Fail at **tactical reasoning**
- Replace calculation with **pattern matching**
        """)

    st.markdown("---")

    # =========================
    # PEDAGOGICAL RISK
    # =========================
    st.subheader("🎓 Pedagogical Risk")

    st.markdown("""
A critical finding is the **educational vulnerability** of these models:

- Most models present outputs with **high confidence**
- Errors are **not signaled clearly**
- Users (students) assume correctness

👉 This creates **negative instructional value**, where:
- Illegal moves may be accepted as valid  
- Incorrect strategies may be learned  
- Conceptual understanding is degraded  
""")

    st.info("""
Only Llama showed partial awareness of its limitations by expressing uncertainty more often.
""")

    st.markdown("---")

    # =========================
    # FINAL TAKEAWAY
    # =========================
    st.subheader("🚫 Key Conclusion")

    st.error("""
Foundation LLMs cannot function as reliable standalone chess instructors.
""")

    # =========================
    # FUTURE WORK
    # =========================
    st.subheader("🚀 Future Direction")

    st.markdown("""
To safely leverage LLMs in educational systems:

- Combine LLMs with **deterministic chess engines**
- Ground explanations in **verified board states**
- Use LLMs for **language**, not **validation**

👉 Hybrid systems can provide:
- ✔ Accurate calculations  
- ✔ Clear explanations  
- ✔ Reliable learning experience  
""")
