import json
from pathlib import Path

import mysql.connector
import pandas as pd
import requests
import streamlit as st
from streamlit_option_menu import option_menu

DB_CONFIG = dict(
    host='localhost',
    port=3306,
    database='NHL_ANALYTICS_PROJECT',
    user='root',
    password="Omsivaya@20",
)
DATA_DIR = Path(__file__).resolve().parent


st.set_page_config(page_title="NHL Analytics Hub", page_icon="🏒", layout="wide")


@st.cache_data(ttl=300)
def load_standings():
    response = requests.get("https://api-web.nhle.com/v1/standings/now", timeout=20)
    response.raise_for_status()
    payload = response.json()

    def localized(value):
        return value.get("default") if isinstance(value, dict) else value

    rows = []
    for team in payload.get("standings", []):
        rows.append({
            "logo": team.get("teamLogo"),
            "team": localized(team.get("teamName")),
            "conference": team.get("conferenceName"),
            "division": team.get("divisionName"),
            "games_played": team.get("gamesPlayed", 0),
            "wins": team.get("wins", 0),
            "losses": team.get("losses", 0),
            "ot_losses": team.get("otLosses", 0),
            "points": team.get("points", 0),
            "goals_for": team.get("goalFor", 0),
            "goals_against": team.get("goalAgainst", 0),
            "home_wins": team.get("homeWins", 0),
            "away_wins": team.get("roadWins", 0),
            "streak_type": team.get("streakCode"),
            "streak_count": team.get("streakCount"),
            "season": str(team.get("seasonId", "")),
        })

    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def load_teams():
    connection = mysql.connector.connect(**DB_CONFIG)
    try:
        query = """
            SELECT team_id, team_abbrev, team_name, conference_name, division_name, logo_url
            FROM teams
            ORDER BY team_name
        """
        return pd.read_sql_query(query, connection)
    finally:
        connection.close()


@st.cache_data(ttl=300)
def load_players():
    connection = mysql.connector.connect(**DB_CONFIG)
    try:
        query = """
            SELECT
                p.player_id,
                p.first_name,
                p.last_name,
                p.position,
                p.jersey_number,
                p.birth_date,
                p.birth_country,
                p.height_cm,
                p.weight_kg,
                p.shoots_catches,
                p.headshot_url,
                t.team_abbrev,
                t.team_name
            FROM players AS p
            JOIN teams AS t ON t.team_id = p.team_id
            ORDER BY t.team_abbrev, p.last_name
        """
        return pd.read_sql_query(query, connection)
    finally:
        connection.close()


GAME_STATE_LABELS = {
    "FUT": "Upcoming",
    "PRE": "Upcoming",
    "LIVE": "In Progress",
    "CRIT": "In Progress",
    "OFF": "Final",
    "FINAL": "Final",
}


@st.cache_data(ttl=300)
def load_games():
    connection = mysql.connector.connect(**DB_CONFIG)
    try:
        query = """
            SELECT
                g.game_id,
                g.season,
                g.game_type,
                g.game_date,
                g.home_score,
                g.away_score,
                g.game_state,
                g.venue_name,
                home.team_abbrev AS home_team_abbrev,
                home.team_name AS home_team_name,
                away.team_abbrev AS away_team_abbrev,
                away.team_name AS away_team_name
            FROM games AS g
            JOIN teams AS home ON home.team_id = g.home_team_id
            JOIN teams AS away ON away.team_id = g.away_team_id
            ORDER BY g.game_date DESC, g.game_id DESC
        """
        df = pd.read_sql_query(query, connection)
        df["status"] = df["game_state"].map(GAME_STATE_LABELS).fillna(df["game_state"])
        return df
    finally:
        connection.close()


@st.cache_data(ttl=300)
def load_skater_season_stats():
    path = DATA_DIR / "skater_season_stats.json"
    return pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))


@st.cache_data(ttl=300)
def load_goalie_season_stats():
    path = DATA_DIR / "goalie_season_stats.json"
    return pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))


def build_player_leaderboard(stats_df, metric, season, players_df, teams_df, min_games=0, limit=10):
    leaderboard_df = stats_df.copy()
    leaderboard_df["season"] = leaderboard_df["season"].astype("string")
    leaderboard_df = leaderboard_df[leaderboard_df["season"] == season].copy()
    leaderboard_df[metric] = pd.to_numeric(leaderboard_df[metric], errors="coerce")
    leaderboard_df["games_played"] = pd.to_numeric(leaderboard_df["games_played"], errors="coerce")
    leaderboard_df = leaderboard_df.dropna(subset=[metric])

    if min_games:
        leaderboard_df = leaderboard_df[leaderboard_df["games_played"] >= min_games]

    player_lookup = players_df[["player_id", "first_name", "last_name"]].drop_duplicates("player_id")
    team_lookup = teams_df[["team_id", "team_abbrev"]].drop_duplicates("team_id")
    leaderboard_df = leaderboard_df.merge(player_lookup, on="player_id", how="left", validate="many_to_one")
    leaderboard_df = leaderboard_df.merge(team_lookup, on="team_id", how="left", validate="many_to_one")
    leaderboard_df["first_name"] = leaderboard_df["first_name"].fillna("")
    leaderboard_df["last_name"] = leaderboard_df["last_name"].fillna("")
    leaderboard_df["team_abbrev"] = leaderboard_df["team_abbrev"].fillna("")
    leaderboard_df = leaderboard_df.sort_values(
        [metric, "last_name", "first_name"],
        ascending=[False, True, True],
        na_position="last",
    ).head(limit)
    leaderboard_df.insert(0, "rank", range(1, len(leaderboard_df) + 1))
    return leaderboard_df


with st.sidebar:
    st.markdown("## NHL Analytics Hub")
    selected = option_menu(
        "Navigation",
        ["Home", "Standings", "Team Info", "Player Search", "Game Results", "Leaderboards", "SQL Query"],
        icons=["house", "trophy", "shield", "search", "calendar-event", "bar-chart", "database"],
        menu_icon="hockey-puck",
        default_index=0,
    )


if selected == "Home":
    st.title("NHL Analytics Hub")
    try:
        standings_df = load_standings()
        hero_image, hero_copy = st.columns([1, 2])
        with hero_image:
            st.image(
                "/Users/nareshselvaraj/pandas course/NHL Analytics Hub Guvi Project/hockey.jpg",
                width=200,
            )
        with hero_copy:
            st.write("Welcome to the NHL Analytics HUB!")

        st.caption("API-driven hockey data, standings, and team performance")
        metric_row_one = st.columns(2)
        metric_row_one[0].metric(
            "Total Teams",
            len(standings_df),
            border=True,
        )
        metric_row_one[1].metric(
            "Games Played",
            int(standings_df["games_played"].sum() / 2),
            border=True,
        )

        metric_row_two = st.columns(2)
        metric_row_two[0].metric(
            "Total Goals Scored",
            int(standings_df["goals_for"].sum()),
            border=True,
        )
        leader = standings_df.sort_values(
            ["points", "wins", "goals_for"], ascending=False
        ).iloc[0]
        metric_row_two[1].metric(
            "Points Leader",
            leader["team"],
            f"{int(leader['points'])} points",
            border=True,
        )
    except requests.RequestException as error:
        st.error(f"Could not fetch NHL data for the Home page: {error}")

elif selected == "Standings":
    st.title("Standings")
    st.caption("Current NHL team standings")

    try:
        standings_df = load_standings()
        if standings_df.empty:
            st.info("The NHL API returned no standings data.")
            st.stop()

        seasons = sorted(standings_df["season"].dropna().unique(), reverse=True)
        filter_col, _ = st.columns([1, 2])
        with filter_col:
            season = st.selectbox("Season", seasons)
            conference_options = ["All", *sorted(standings_df["conference"].dropna().unique())]
            conference = st.selectbox("Conference", conference_options)

        standings_df = standings_df[standings_df["season"] == season]
        if conference != "All":
            standings_df = standings_df[standings_df["conference"] == conference]
        standings_df = standings_df.sort_values(
            ["points", "wins", "goals_for"], ascending=False
        )
        if standings_df.empty:
            st.info("No teams match the selected filters.")
        else:
            first, second, third = st.columns(3)
            first.metric("Teams", len(standings_df))
            second.metric("Games played per team", int(standings_df["games_played"].mean()))
            third.metric("Points leader", int(standings_df["points"].max()))

            st.dataframe(
                standings_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "logo": st.column_config.ImageColumn("Logo", width="small"),
                    "team": st.column_config.TextColumn("Team", width="medium"),
                    "conference": st.column_config.TextColumn("Conference"),
                    "division": st.column_config.TextColumn("Division"),
                    "games_played": st.column_config.NumberColumn("GP", format="%d"),
                    "wins": st.column_config.NumberColumn("Wins", format="%d"),
                    "losses": st.column_config.NumberColumn("Losses", format="%d"),
                    "ot_losses": st.column_config.NumberColumn("OT losses", format="%d"),
                    "points": st.column_config.NumberColumn("Points", format="%d"),
                    "goals_for": st.column_config.NumberColumn("Goals for", format="%d"),
                    "goals_against": st.column_config.NumberColumn("Goals against", format="%d"),
                    "home_wins": st.column_config.NumberColumn("Home wins", format="%d"),
                    "away_wins": st.column_config.NumberColumn("Away wins", format="%d"),
                    "streak_type": st.column_config.TextColumn("Streak"),
                    "streak_count": st.column_config.NumberColumn("Streak count", format="%d"),
                },
            )
    except requests.RequestException as error:
        st.error(f"Could not fetch standings from the NHL API: {error}")
    except (KeyError, ValueError) as error:
        st.error(f"The NHL API returned standings in an unexpected format: {error}")

elif selected == "Team Info":
    st.title("Team Info")

    try:
        teams_df = load_teams()
        players_df = load_players()
        if teams_df.empty:
            st.info("No team data found.")
            st.stop()

        team_name = st.selectbox("Select Team", teams_df["team_name"])
        team_row = teams_df[teams_df["team_name"] == team_name].iloc[0]

        logo_col, info_col = st.columns([1, 3])
        with logo_col:
            st.image(team_row["logo_url"], width=150)
        with info_col:
            st.write(f"**Conference:** {team_row['conference_name']}")
            st.write(f"**Division:** {team_row['division_name']}")

        st.subheader("Team Roster")
        roster_df = players_df[players_df["team_abbrev"] == team_row["team_abbrev"]]
        if roster_df.empty:
            st.info("No roster data found for this team.")
        else:
            st.dataframe(
                roster_df,
                use_container_width=True,
                hide_index=True,
                column_order=["first_name", "last_name", "position", "jersey_number"],
                column_config={
                    "first_name": st.column_config.TextColumn("First name"),
                    "last_name": st.column_config.TextColumn("Last name"),
                    "position": st.column_config.TextColumn("Position"),
                    "jersey_number": st.column_config.NumberColumn("Jersey #", format="%d"),
                },
            )
    except mysql.connector.Error as error:
        st.error(f"Could not load team data from the database: {error}")

elif selected == "Player Search":
    st.title("Player Search")
    st.caption("Search current NHL rosters")

    try:
        players_df = load_players()
        if players_df.empty:
            st.info("No player data found. Run the players ETL step to load rosters into the database.")
            st.stop()

        filter_name, filter_team, filter_position = st.columns([2, 1, 1])
        with filter_name:
            search_term = st.text_input("Search by name", "")
        with filter_team:
            team_options = ["All", *sorted(players_df["team_abbrev"].dropna().unique())]
            team = st.selectbox("Team", team_options)
        with filter_position:
            position_options = ["All", *sorted(players_df["position"].dropna().unique())]
            position = st.selectbox("Position", position_options)

        filtered_df = players_df.copy()
        search_words = search_term.split()
        if search_words:
            full_name = (
                filtered_df["first_name"].fillna("").astype(str)
                + " "
                + filtered_df["last_name"].fillna("").astype(str)
            )
            name_mask = pd.Series(True, index=filtered_df.index)
            for word in search_words:
                name_mask &= full_name.str.contains(word, case=False, regex=False, na=False)
            filtered_df = filtered_df[name_mask]
        if team != "All":
            filtered_df = filtered_df[filtered_df["team_abbrev"] == team]
        if position != "All":
            filtered_df = filtered_df[filtered_df["position"] == position]

        if filtered_df.empty:
            st.info("No players match the selected filters.")
        else:
            metric_row = st.columns(3)
            metric_row[0].metric("Players", len(filtered_df))
            metric_row[1].metric("Teams represented", filtered_df["team_abbrev"].nunique())
            metric_row[2].metric("Avg height (cm)", round(filtered_df["height_cm"].mean(), 1))

            PAGE_SIZE = 20
            table_df = filtered_df.reset_index(drop=True)
            total_players = len(table_df)
            total_pages = max(1, -(-total_players // PAGE_SIZE))  # ceil division

            filter_signature = (search_term, team, position)
            if st.session_state.get("player_search_filter_signature") != filter_signature:
                st.session_state["player_search_filter_signature"] = filter_signature
                st.session_state["player_search_page"] = 1

            page = max(1, min(st.session_state.get("player_search_page", 1), total_pages))
            st.session_state["player_search_page"] = page

            prev_col, info_col, next_col = st.columns([1, 2, 1])
            with prev_col:
                if st.button("⬅️ Previous", disabled=(page <= 1), use_container_width=True):
                    st.session_state["player_search_page"] = page - 1
                    st.rerun()
            with info_col:
                st.markdown(
                    f"<p style='text-align:center; margin-top:0.5rem;'>"
                    f"Page {page} of {total_pages} ({total_players} players)</p>",
                    unsafe_allow_html=True,
                )
            with next_col:
                if st.button("Next ➡️", disabled=(page >= total_pages), use_container_width=True):
                    st.session_state["player_search_page"] = page + 1
                    st.rerun()

            start = (page - 1) * PAGE_SIZE
            page_df = table_df.iloc[start:start + PAGE_SIZE]

            for _, player in page_df.iterrows():
                jersey = int(player["jersey_number"]) if pd.notna(player["jersey_number"]) else "—"
                header = (
                    f"{player['first_name']} {player['last_name']} "
                    f"— {player['team_abbrev']} · {player['position']} · #{jersey}"
                )
                with st.expander(header):
                    age_text = ""
                    if pd.notna(player["birth_date"]):
                        birth_date = pd.to_datetime(player["birth_date"])
                        today = pd.Timestamp.today()
                        age = today.year - birth_date.year - (
                            (today.month, today.day) < (birth_date.month, birth_date.day)
                        )
                        age_text = f" (Age {age})"

                    photo_col, detail_col = st.columns([1, 3])
                    with photo_col:
                        if pd.notna(player["headshot_url"]):
                            st.image(player["headshot_url"], width=150)
                    with detail_col:
                        st.write(f"**Team:** {player['team_name']} ({player['team_abbrev']})")
                        st.write(f"**Position:** {player['position']}  |  **Jersey #:** {jersey}")
                        birth_date_text = (
                            pd.to_datetime(player["birth_date"]).strftime("%Y-%m-%d")
                            if pd.notna(player["birth_date"]) else "—"
                        )
                        st.write(f"**Birth date:** {birth_date_text}{age_text}")
                        st.write(f"**Birth country:** {player['birth_country'] if pd.notna(player['birth_country']) else '—'}")
                        height = f"{player['height_cm']:.0f} cm" if pd.notna(player["height_cm"]) else "—"
                        weight = f"{player['weight_kg']:.0f} kg" if pd.notna(player["weight_kg"]) else "—"
                        st.write(f"**Height:** {height}  |  **Weight:** {weight}")
                        st.write(f"**Shoots/Catches:** {player['shoots_catches'] if pd.notna(player['shoots_catches']) else '—'}")
    except mysql.connector.Error as error:
        st.error(f"Could not load player data from the database: {error}")

elif selected == "Leaderboards":
    st.title("📊 Leaderboards")
    st.caption("Season leaders from the collected NHL stats")

    try:
        skater_stats = load_skater_season_stats()
        goalie_stats = load_goalie_season_stats()
        players_df = load_players()
        teams_df = load_teams()
    except mysql.connector.Error as error:
        st.error(f"Could not load player and team names from the database: {error}")
        st.stop()
    except (OSError, ValueError) as error:
        st.error(f"Could not read the leaderboard JSON data: {error}")
        st.stop()

    season_values = (
        set(skater_stats["season"].dropna().astype(str))
        | set(goalie_stats["season"].dropna().astype(str))
    )
    available_seasons = sorted(
        (value for value in season_values if value.lower() not in {"", "none", "nan", "<na>"}),
        reverse=True,
    )
    if not available_seasons:
        st.info("No season stats are available in the leaderboard JSON files.")
        st.stop()

    season = st.selectbox(
        "Season",
        available_seasons,
        format_func=lambda value: f"{value[:4]}-{value[6:]}" if len(value) == 8 else value,
    )
    goals_tab, assists_tab, penalty_tab, save_pct_tab, team_wins_tab = st.tabs(
        ["🥅 Goals", "🅰️ Assists", "⏱️ Penalty Minutes", "🥅 Save %", "🏆 Team Wins"]
    )

    def show_player_leaderboard(stats_df, metric, label, min_games=0, as_percentage=False):
        ranked_df = build_player_leaderboard(
            stats_df,
            metric,
            season,
            players_df,
            teams_df,
            min_games=min_games,
        )
        if ranked_df.empty:
            st.info("No players meet the selected season and qualification criteria.")
            return

        display_df = ranked_df[["rank", "first_name", "last_name", "team_abbrev", metric]].copy()
        if as_percentage:
            display_df[metric] = display_df[metric] * 100
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "rank": st.column_config.NumberColumn("Rank", format="%d"),
                "first_name": st.column_config.TextColumn("First name"),
                "last_name": st.column_config.TextColumn("Last name"),
                "team_abbrev": st.column_config.TextColumn("Team"),
                metric: st.column_config.NumberColumn(
                    label,
                    format="%.1f%%" if as_percentage else "%d",
                ),
            },
        )

    with goals_tab:
        show_player_leaderboard(skater_stats, "goals", "Goals")

    with assists_tab:
        show_player_leaderboard(skater_stats, "assists", "Assists")

    with penalty_tab:
        show_player_leaderboard(skater_stats, "penalty_min", "Penalty minutes")

    with save_pct_tab:
        minimum_games = st.number_input(
            "Minimum games played",
            min_value=1,
            max_value=82,
            value=20,
            step=1,
        )
        show_player_leaderboard(
            goalie_stats,
            "save_pct",
            "Save %",
            min_games=minimum_games,
            as_percentage=True,
        )

    with team_wins_tab:
        st.caption("Current season standings")
        try:
            standings_df = load_standings()
            team_leaders = standings_df.dropna(subset=["wins"]).copy()
            team_leaders["wins"] = pd.to_numeric(team_leaders["wins"], errors="coerce")
            team_leaders = team_leaders.dropna(subset=["wins"]).sort_values(
                ["wins", "points", "goals_for"],
                ascending=False,
            ).head(10)
            if team_leaders.empty:
                st.info("No team standings are available right now.")
            else:
                team_leaders.insert(0, "rank", range(1, len(team_leaders) + 1))
                st.dataframe(
                    team_leaders[["rank", "team", "wins", "points", "conference", "division"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "rank": st.column_config.NumberColumn("Rank", format="%d"),
                        "team": st.column_config.TextColumn("Team"),
                        "wins": st.column_config.NumberColumn("Wins", format="%d"),
                        "points": st.column_config.NumberColumn("Points", format="%d"),
                        "conference": st.column_config.TextColumn("Conference"),
                        "division": st.column_config.TextColumn("Division"),
                    },
                )
        except requests.RequestException as error:
            st.error(f"Could not fetch current team standings: {error}")

elif selected == "Game Results":
    st.title("Game Results")
    st.caption("NHL game results and schedule")

    try:
        games_df = load_games()
        if games_df.empty:
            st.info("No game data found. Run the games ETL step to load the schedule into the database.")
            st.stop()

        filter_team, filter_status, filter_type = st.columns(3)
        with filter_team:
            team_options = ["All", *sorted(set(games_df["home_team_abbrev"]) | set(games_df["away_team_abbrev"]))]
            team = st.selectbox("Team", team_options)
        with filter_status:
            status_options = ["All", *sorted(games_df["status"].dropna().unique())]
            status = st.selectbox("Status", status_options)
        with filter_type:
            type_labels = {1: "Preseason", 2: "Regular", 3: "Playoffs"}
            games_df["game_type_label"] = games_df["game_type"].map(type_labels).fillna(games_df["game_type"])
            type_options = ["All", *sorted(games_df["game_type_label"].dropna().unique())]
            game_type = st.selectbox("Game type", type_options)

        filtered_df = games_df.copy()
        if team != "All":
            filtered_df = filtered_df[
                (filtered_df["home_team_abbrev"] == team) | (filtered_df["away_team_abbrev"] == team)
            ]
        if status != "All":
            filtered_df = filtered_df[filtered_df["status"] == status]
        if game_type != "All":
            filtered_df = filtered_df[filtered_df["game_type_label"] == game_type]

        if filtered_df.empty:
            st.info("No games match the selected filters.")
        else:
            metric_row = st.columns(3)
            metric_row[0].metric("Games", len(filtered_df))
            metric_row[1].metric("Final", int((filtered_df["status"] == "Final").sum()))
            metric_row[2].metric("Upcoming", int((filtered_df["status"] == "Upcoming").sum()))

            display_df = filtered_df.copy()
            display_df["matchup"] = (
                display_df["away_team_abbrev"] + " @ " + display_df["home_team_abbrev"]
            )
            display_df["score"] = display_df.apply(
                lambda row: f"{row['away_score']} - {row['home_score']}"
                if pd.notna(row["away_score"]) and pd.notna(row["home_score"])
                else "-",
                axis=1,
            )

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_order=[
                    "game_date", "matchup", "score", "status",
                    "game_type_label", "venue_name",
                ],
                column_config={
                    "game_date": st.column_config.DateColumn("Date"),
                    "matchup": st.column_config.TextColumn("Matchup"),
                    "score": st.column_config.TextColumn("Score (away - home)"),
                    "status": st.column_config.TextColumn("Status"),
                    "game_type_label": st.column_config.TextColumn("Type"),
                    "venue_name": st.column_config.TextColumn("Venue", width="medium"),
                },
            )
    except mysql.connector.Error as error:
        st.error(f"Could not load game data from the database: {error}")

elif selected == "SQL Query":
    st.title("SQL Query")
    st.caption("Run read-only SQL queries against the NHL Analytics database")

    READY_MADE_QUERIES = {
        "Players per team": (
            "SELECT t.team_name, t.team_abbrev, COUNT(*) AS player_count\n"
            "FROM players p\n"
            "JOIN teams t ON t.team_id = p.team_id\n"
            "GROUP BY t.team_name, t.team_abbrev\n"
            "ORDER BY player_count DESC;"
        ),
        "Top 10 point scorers (season)": (
            "SELECT p.first_name, p.last_name, t.team_abbrev, s.season, s.goals, s.assists, s.points\n"
            "FROM skater_season_stats s\n"
            "JOIN players p ON p.player_id = s.player_id\n"
            "JOIN teams t ON t.team_id = s.team_id\n"
            "ORDER BY s.points DESC\n"
            "LIMIT 10;"
        ),
        "Current standings": (
            "SELECT t.team_name, st.wins, st.losses, st.ot_losses, st.points, st.goals_for, st.goals_against\n"
            "FROM standings st\n"
            "JOIN teams t ON t.team_id = st.team_id\n"
            "ORDER BY st.points DESC;"
        ),
        "Next 10 upcoming games": (
            "SELECT g.game_date, away.team_abbrev AS away_team, home.team_abbrev AS home_team, g.venue_name\n"
            "FROM games g\n"
            "JOIN teams home ON home.team_id = g.home_team_id\n"
            "JOIN teams away ON away.team_id = g.away_team_id\n"
            "WHERE g.game_state IN ('FUT', 'PRE')\n"
            "ORDER BY g.game_date ASC\n"
            "LIMIT 10;"
        ),
        "Biggest game result margins": (
            "SELECT g.game_date, home.team_abbrev AS home_team, g.home_score,\n"
            "       away.team_abbrev AS away_team, g.away_score,\n"
            "       ABS(g.home_score - g.away_score) AS margin\n"
            "FROM games g\n"
            "JOIN teams home ON home.team_id = g.home_team_id\n"
            "JOIN teams away ON away.team_id = g.away_team_id\n"
            "WHERE g.home_score IS NOT NULL AND g.away_score IS NOT NULL\n"
            "ORDER BY margin DESC\n"
            "LIMIT 10;"
        ),
        "Players by birth country": (
            "SELECT birth_country, COUNT(*) AS player_count\n"
            "FROM players\n"
            "WHERE birth_country IS NOT NULL\n"
            "GROUP BY birth_country\n"
            "ORDER BY player_count DESC;"
        ),
        "Tallest players": (
            "SELECT first_name, last_name, position, height_cm, weight_kg\n"
            "FROM players\n"
            "ORDER BY height_cm DESC\n"
            "LIMIT 10;"
        ),
        "Average size by position": (
            "SELECT position,\n"
            "       ROUND(AVG(height_cm), 1) AS avg_height_cm,\n"
            "       ROUND(AVG(weight_kg), 1) AS avg_weight_kg,\n"
            "       COUNT(*) AS players\n"
            "FROM players\n"
            "WHERE position IS NOT NULL\n"
            "GROUP BY position\n"
            "ORDER BY avg_height_cm DESC;"
        ),
        "Best single-game performances": (
            "SELECT gs.game_id, p.first_name, p.last_name, gs.goals, gs.assists, gs.points, gs.shots_on_goal\n"
            "FROM game_stats gs\n"
            "JOIN players p ON p.player_id = gs.player_id\n"
            "ORDER BY gs.points DESC\n"
            "LIMIT 10;"
        ),
        "Team goal differential": (
            "SELECT t.team_name, st.goals_for, st.goals_against,\n"
            "       (st.goals_for - st.goals_against) AS goal_diff\n"
            "FROM standings st\n"
            "JOIN teams t ON t.team_id = st.team_id\n"
            "ORDER BY goal_diff DESC;"
        ),
        "Most penalty minutes": (
            "SELECT p.first_name, p.last_name, t.team_abbrev, s.penalty_min\n"
            "FROM skater_season_stats s\n"
            "JOIN players p ON p.player_id = s.player_id\n"
            "JOIN teams t ON t.team_id = s.team_id\n"
            "ORDER BY s.penalty_min DESC\n"
            "LIMIT 10;"
        ),
        "Busiest venues": (
            "SELECT venue_name, COUNT(*) AS games_hosted\n"
            "FROM games\n"
            "WHERE venue_name IS NOT NULL\n"
            "GROUP BY venue_name\n"
            "ORDER BY games_hosted DESC\n"
            "LIMIT 15;"
        ),
        "Win % by conference": (
            "SELECT t.conference_name,\n"
            "       SUM(st.wins) AS total_wins,\n"
            "       SUM(st.games_played) AS total_games,\n"
            "       ROUND(SUM(st.wins) / SUM(st.games_played) * 100, 1) AS win_pct\n"
            "FROM standings st\n"
            "JOIN teams t ON t.team_id = st.team_id\n"
            "GROUP BY t.conference_name;"
        ),
        "Players missing bio data": (
            "SELECT player_id, first_name, last_name, team_id\n"
            "FROM players\n"
            "WHERE birth_country IS NULL OR birth_date IS NULL;"
        ),
        "Custom query": "SELECT * FROM teams LIMIT 10;",
    }

    query_label = st.selectbox("Ready-made query", list(READY_MADE_QUERIES.keys()))

    if st.session_state.get("sql_query_label") != query_label:
        st.session_state["sql_query_label"] = query_label
        st.session_state["sql_query_text"] = READY_MADE_QUERIES[query_label]

    st.text_area("SQL query (SELECT only)", key="sql_query_text", height=180)

    run_clicked = st.button("▶️ Run Query", type="primary")

    if run_clicked:
        query_text = st.session_state["sql_query_text"]
        stripped = query_text.strip().rstrip(";")
        lowered = stripped.lower()
        blocked_keywords = (
            "insert", "update", "delete", "drop", "alter",
            "truncate", "create", "grant", "revoke", "replace",
        )

        if not lowered.startswith("select"):
            st.session_state["sql_query_error"] = (
                "Only SELECT queries are allowed on this page. "
                "Use MySQL Workbench for INSERT/UPDATE/DELETE/DDL statements."
            )
            st.session_state["sql_query_result"] = None
        elif ";" in stripped or any(f" {kw} " in f" {lowered} " for kw in blocked_keywords):
            st.session_state["sql_query_error"] = (
                "Query contains a disallowed keyword or multiple statements. "
                "Only a single SELECT statement is permitted here."
            )
            st.session_state["sql_query_result"] = None
        else:
            try:
                connection = mysql.connector.connect(**DB_CONFIG)
                try:
                    st.session_state["sql_query_result"] = pd.read_sql_query(stripped, connection)
                    st.session_state["sql_query_error"] = None
                finally:
                    connection.close()
            except mysql.connector.Error as error:
                st.session_state["sql_query_error"] = f"Query failed: {error}"
                st.session_state["sql_query_result"] = None

    if st.session_state.get("sql_query_error"):
        st.error(st.session_state["sql_query_error"])
    elif st.session_state.get("sql_query_result") is not None:
        result_df = st.session_state["sql_query_result"]
        st.success(f"{len(result_df)} row(s) returned.")
        st.dataframe(result_df, use_container_width=True, hide_index=True)
    else:
        st.info("Pick a ready-made query or write your own, then click Run Query.")

else:
    st.title(selected)
    st.info(f"The {selected} view is not implemented yet.")






