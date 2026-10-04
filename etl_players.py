import time

import mysql.connector
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

connection = mysql.connector.connect(
    host='localhost',
    port=3306,
    database='NHL_ANALYTICS_PROJECT',
    user='root',
    password="Omsivaya@20"
)

players_cursor = connection.cursor()
players_cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    player_id BIGINT PRIMARY KEY,
    team_id INT NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    position VARCHAR(10),
    jersey_number INT,
    birth_date DATE,
    birth_country VARCHAR(10),
    height_cm REAL,
    weight_kg REAL,
    shoots_catches VARCHAR(5),
    headshot_url TEXT,
    CONSTRAINT fk_players_team
        FOREIGN KEY (team_id) REFERENCES teams(team_id)
) ENGINE=InnoDB
""")

players_cursor.execute("SELECT team_id, team_abbrev FROM teams ORDER BY team_abbrev")
teams_for_rosters = players_cursor.fetchall()


def fetch_team_roster(team_id, team_abbrev):
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        response = requests.get(
            f"https://api-web.nhle.com/v1/roster/{team_abbrev}/current",
            timeout=(5, 10)
        )
        if response.status_code == 429 and attempt < max_attempts:
            wait_seconds = 2 ** attempt
            time.sleep(wait_seconds)
            continue
        response.raise_for_status()
        break
    roster = response.json()
    position_map = {"L": "LW", "R": "RW"}
    team_records = []

    for group_name in ("forwards", "defensemen", "goalies"):
        for player in roster.get(group_name, []):
            first_name = player.get("firstName")
            last_name = player.get("lastName")
            position_code = player.get("positionCode")

            team_records.append((
                player["id"],
                team_id,
                first_name.get("default") if isinstance(first_name, dict) else first_name,
                last_name.get("default") if isinstance(last_name, dict) else last_name,
                position_map.get(position_code, position_code),
                player.get("sweaterNumber"),
                player.get("birthDate"),
                player.get("birthCountry"),
                player.get("heightInCentimeters"),
                player.get("weightInKilograms"),
                player.get("shootsCatches"),
                player.get("headshot")
            ))

    return team_abbrev, team_records


player_records = []
roster_errors = []

with ThreadPoolExecutor(max_workers=2) as executor:
    futures = {}
    for team_id, team_abbrev in teams_for_rosters:
        futures[executor.submit(fetch_team_roster, team_id, team_abbrev)] = team_abbrev
        time.sleep(0.3)

    for completed_count, future in enumerate(as_completed(futures), start=1):
        team_abbrev = futures[future]
        try:
            _, team_records = future.result()
            player_records.extend(team_records)
            print(f"Fetched {team_abbrev}: {len(team_records)} players ({completed_count}/{len(futures)} teams)")
        except requests.RequestException as error:
            roster_errors.append((team_abbrev, str(error)))
            print(f"Failed {team_abbrev} ({completed_count}/{len(futures)} teams): {error}")

if roster_errors:
    raise RuntimeError(
        f"Roster fetch failed for {len(roster_errors)} teams; no database rows were written. "
        f"Retry the cell after checking the network: {roster_errors}"
    )

upsert_players_query = """
INSERT INTO players (
    player_id, team_id, first_name, last_name, position, jersey_number,
    birth_date, birth_country, height_cm, weight_kg, shoots_catches, headshot_url
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    team_id = VALUES(team_id),
    first_name = VALUES(first_name),
    last_name = VALUES(last_name),
    position = VALUES(position),
    jersey_number = VALUES(jersey_number),
    birth_date = VALUES(birth_date),
    birth_country = VALUES(birth_country),
    height_cm = VALUES(height_cm),
    weight_kg = VALUES(weight_kg),
    shoots_catches = VALUES(shoots_catches),
    headshot_url = VALUES(headshot_url)
"""

players_cursor.executemany(upsert_players_query, player_records)
connection.commit()

players_cursor.execute("""
SELECT COUNT(*) AS player_count, COUNT(DISTINCT team_id) AS team_count
FROM players
""")
print(f"Fetched and saved {len(player_records)} player records.")
print("Database totals (players, teams):", players_cursor.fetchone())

players_cursor.close()
connection.close()
