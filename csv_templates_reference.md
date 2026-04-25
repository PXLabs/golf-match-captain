# CSV Upload Templates

This guide provides the exact column headers expected by the **Raw Table Management** CSV upload on the Admin page.

> [!TIP]
> The easiest way to get an exact template for a specific table is to select it in the dropdown and click **Download CSV**. Even if it's empty, it will give you the perfect headers!

When uploading new data, ensure your CSV headers exactly match the comma-separated strings below.

***

### `player`
Core roster entity. Survives across events.
```csv
player_id,name,cpga_id,current_index,tee_preference,notes,created_at,updated_at
```
- **`player_id`**: Leave blank for new rows (auto-generates).
- **`current_index`**: Decimal (e.g., `12.5`). Defaults to `0.0` if empty.

### `course`
Golf courses reused across events.
```csv
course_id,name,location,created_at
```
- **`course_id`**: Leave blank for new rows.

### `tee_deck`
One row per tee deck per course.
```csv
tee_id,course_id,name,rating,slope,par,total_yards,stroke_index,notes
```
- **`course_id`**: Must match an existing ID from the `course` table.
- **`stroke_index`**: Must be a JSON array bracket format (e.g., `[5, 11, 1, 15, 9, 13, 3, 17, 7, 6, 12, 2, 16, 10, 14, 4, 18, 8]`).
- **`total_yards`**: Optional integer.
- **`notes`**: Optional supplementary description.

### `event`
Tournament tracking entity.
```csv
event_id,name,start_date,team_a_name,team_b_name,handicap_mode,allowance_pct,status,created_at
```
- **`handicap_mode`**: Usually `FULL_INDEX`, `PERCENTAGE`, or `PLAY_OFF_LOW`.
- **`status`**: `ACTIVE`, `COMPLETED`, or `ARCHIVED`.

### `event_player`
Assigns players to a team ('A' or 'B') for an event.
```csv
event_id,player_id,team,role
```
- **`team`**: Exactly `A` or `B`.
- **`role`**: `Player`, `Captain`, or `Alternate Captain`.

### `round`
Events consist of daily rounds.
```csv
round_id,event_id,course_id,tee_id_a,tee_id_b,date,holes,format_code,round_number
```
- **`holes`**: 9 or 18.
- **`format_code`**: `SINGLES_MP`, `FOURBALL_MP`, `FOURSOMES_MP`, `SINGLES_STROKE`, `SCRAMBLE`.

### `match`
Individual pairings/games within a round.
```csv
match_id,round_id,team_a_player1_id,team_a_player2_id,team_b_player1_id,team_b_player2_id,result,result_detail,notes,match_order,hole_scores
```
- **`result`**: `A`, `B`, or `HALVED`.
- **`hole_scores`**: Advanced JSON blob field used by the scorecard AI. Leave blank if manually entering later.

### `score_record`
Historical rounds logged to track handicaps and intelligence signals.
```csv
record_id,player_id,date,course,tee_deck,posted_score,differential,created_at
```

### `player_tag`
Contextual tags consumed by the AI Advisor.
```csv
tag_id,player_id,tag_type,tag_value,created_date
```
- **`tag_type`**: E.g., `PLAYING_STYLE`, `TEMPERAMENT`, `COURSE_AFFINITY`.
