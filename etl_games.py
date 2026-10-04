import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import mysql.connector
import requests

SEASON = "20252026"

connection = mysql.connector.connect(
    host='localhost',
    port=3306,
    database='NHL_ANALYTICS_PROJECT',
    user='root',
    password="Omsivaya@20"
)

games_cursor = connection.cursor()
games_cursor.execute("""
CREATE TABLE IF NOT EXISTS games (
    game_id BIGINT PRIMARY KEY,
    season VARCHAR(20),
    game_type INT,
    game_date DATE,
    home_team_id INT NOT NULL,
    away_team_id INT NOT NULL,
    home_score INT,
    away_score INT,
    game_state VARCHAR(20),
    venue_name VARCHAR(150),
    CONSTRAINT fk_games_home_team
        FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    CONSTRAINT fk_games_away_team
        FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
) ENGINE=InnoDB
""")

games_cursor.execute("SELECT team_id, team_abbrev FROM teams ORDER BY team_abbrev")
teams_for_schedule = games_cursor.fetchall()
team_id_by_abbrev = {team_abbrev: team_id for team_id, team_abbrev in teams_for_schedule}


def fetch_team_schedule(team_abbrev):
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        response = requests.get(
            f"https://api-web.nhle.com/v1/club-schedule-season/{team_abbrev}/{SEASON}",
            timeout=(5, 10)
        )
        if response.status_code == 429 and attempt < max_attempts:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        break
    payload = response.json()

    team_records = []
    for game in payload.get("games", []):
        home_abbrev = game["homeTeam"]["abbrev"]
        away_abbrev = game["awayTeam"]["abbrev"]
        home_team_id = team_id_by_abbrev.get(home_abbrev)
        away_team_id = team_id_by_abbrev.get(away_abbrev)
        if home_team_id is None or away_team_id is None:
            continue

        venue = game.get("venue")
        venue_name = venue.get("default") if isinstance(venue, dict) else venue

        team_records.append((
            game["id"],
            str(game.get("season")),
            game.get("gameType"),
            game.get("gameDate"),
            home_team_id,
            away_team_id,
            game["homeTeam"].get("score"),
            game["awayTeam"].get("score"),
            game.get("gameState"),
            venue_name,
        ))

    return team_abbrev, team_records


game_records_by_id = {}
schedule_errors = []

with ThreadPoolExecutor(max_workers=2) as executor:
    futures = {}
    for team_id, team_abbrev in teams_for_schedule:
        futures[executor.submit(fetch_team_schedule, team_abbrev)] = team_abbrev
        time.sleep(0.3)

    for completed_count, future in enumerate(as_completed(futures), start=1):
        team_abbrev = futures[future]
        try:
            _, team_records = future.result()
            for record in team_records:
                # dedupe in Python too: each game appears once from each side's schedule
                game_records_by_id[record[0]] = record
            print(f"Fetched {team_abbrev}: {len(team_records)} games ({completed_count}/{len(futures)} teams)")
        except requests.RequestException as error:
            schedule_errors.append((team_abbrev, str(error)))
            print(f"Failed {team_abbrev} ({completed_count}/{len(futures)} teams): {error}")

if schedule_errors:
    raise RuntimeError(
        f"Schedule fetch failed for {len(schedule_errors)} teams; no database rows were written. "
        f"Retry after checking the network: {schedule_errors}"
    )

insert_games_query = """
INSERT IGNORE INTO games (
    game_id, season, game_type, game_date, home_team_id, away_team_id,
    home_score, away_score, game_state, venue_name
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

game_records = list(game_records_by_id.values())
games_cursor.executemany(insert_games_query, game_records)
connection.commit()

games_cursor.execute("SELECT COUNT(*) FROM games")
print(f"Fetched {len(game_records)} unique games across {len(teams_for_schedule)} teams.")
print("Database total (games):", games_cursor.fetchone())

games_cursor.close()
connection.close()
