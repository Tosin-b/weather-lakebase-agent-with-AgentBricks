"""
Weather Alerts App
- Serves a Flask API
- Syncs weather alerts from NWS API into Lakebase
- Follows the pattern from databricks-lakebase-app-day-2
"""

import logging
import os
import sys

from flask import Flask, jsonify, render_template, request
from sentence_transformers import SentenceTransformer

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lakebase
from weather_alerts_client import WeatherAlertsClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-app")

app = Flask(__name__)

TABLE_NAME = os.environ.get("WEATHER_TABLE_NAME", "weather_information")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "dataexpert_student")
EMBEDDINGS_TABLE = os.environ.get("EMBEDDINGS_TABLE", "weather_alert_embeddings")
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Lazy-load embedding model (only when search endpoint is called)
embedding_model = None

def get_embedding_model():
    """Lazy-load the embedding model on first use."""
    global embedding_model
    if embedding_model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}...")
        embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    return embedding_model

# Default US states to fetch alerts for (all 50 states + territories)
DEFAULT_STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
                  "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
                  "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
                  "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
                  "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]


def ensure_database():
    """Create the database if it doesn't exist."""
    with lakebase.get_connection() as conn:
        conn.set_session(autocommit=True)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (DATABASE_NAME,)
            )
            if not cur.fetchone():
                logger.info(f"Creating database {DATABASE_NAME}...")
                cur.execute(f"CREATE DATABASE {DATABASE_NAME}")


def ensure_weather_table():
    """
    Create the weather_information table in Lakebase if it doesn't exist.
    Schema matches the one from sync_weather_alerts.py
    """
    lakebase.run_write(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id TEXT PRIMARY KEY,
            location TEXT NOT NULL,
            source_type TEXT NOT NULL,
            headline TEXT,
            event TEXT NOT NULL,
            narrative_text TEXT,
            issued_at TIMESTAMPTZ,
            effective_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            payload JSONB NOT NULL,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        database=DATABASE_NAME
    )
    logger.info(f"Table {TABLE_NAME} is ready")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(Exception)
def handle_exception(err):
    """Ensure all unhandled errors return JSON."""
    logger.exception("Unhandled exception while processing request")
    status_code = getattr(err, "code", 500)
    if not isinstance(status_code, int):
        status_code = 500
    return jsonify({"error": str(err)}), status_code


@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')


@app.route('/alerts', methods=['GET'])
def list_alerts():
    """Read weather alerts already synced into Lakebase."""
    ensure_weather_table()
    limit = int(request.args.get("limit", 100))
    rows = lakebase.run_query(
        f"SELECT id, location, event, headline, issued_at, expires_at, synced_at "
        f"FROM {TABLE_NAME} ORDER BY synced_at DESC LIMIT %s",
        (limit,),
        database=DATABASE_NAME
    )
    return jsonify(rows)


@app.route('/alerts/sync', methods=['POST'])
def sync_weather_alerts():
    """
    Pull active weather alerts from the National Weather Service API and
    upsert them into Lakebase.
    
    Body (optional JSON): {"states": ["CA", "TX"], "limit": null}
    Defaults to all US states when no states are supplied.
    
    Follows the /news/sync pattern from databricks-lakebase-app-day-2
    """
    ensure_database()
    ensure_weather_table()
    client = WeatherAlertsClient()

    body = request.json if request.is_json else {}
    states = body.get("states") or DEFAULT_STATES
    states = [s.strip().upper() for s in states if isinstance(s, str) and s.strip()]

    total = 0
    for state in states:
        if len(state) != 2:  # Validate 2-letter state code
            continue
        try:
            raw_data = client.get_alerts_for_state(state)
            features = raw_data.get("features", [])
            if features:
                total += _upsert_weather_batch(features)
        except Exception as e:
            logger.error(f"Error fetching alerts for {state}: {e}")
            continue

    return jsonify({"synced": total, "states": states})


@app.route('/api/weather', methods=['GET'])
def get_weather():
    """API endpoint to get weather alerts for a specific state."""
    state = request.args.get('state', '').strip().upper()
    
    if not state:
        return jsonify({'error': 'State parameter is required'}), 400
    
    if len(state) != 2:
        return jsonify({'error': 'State must be a 2-letter code (e.g., CA, TX)'}), 400
    
    try:
        client = WeatherAlertsClient()
        weather_data = client.get_alerts_for_state(state)
        return jsonify(weather_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/weather/search', methods=['POST'])
def search_weather():
    """
    Semantic search over weather alert embeddings using pgvector.
    
    Body (JSON): {"query": "risk of flooding near rivers", "top_k": 5}
    
    Returns top_k most similar weather alerts with:
    - location: where the alert applies
    - event: type of weather event
    - chunk_text: the alert narrative
    - similarity: cosine similarity score (0-1, higher is better)
    """
    # Validate request body
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 400
    
    body = request.json or {}
    query = body.get('query', '').strip()
    
    # Validate query
    if not query:
        return jsonify({'error': 'query parameter is required'}), 400
    
    if len(query) > 1000:
        return jsonify({'error': 'query must be less than 1000 characters'}), 400
    
    # Validate and clamp top_k
    try:
        top_k = int(body.get('top_k', 5))
    except (ValueError, TypeError):
        return jsonify({'error': 'top_k must be an integer'}), 400
    
    # Clamp top_k to reasonable bounds
    top_k = max(1, min(top_k, 20))
    
    try:
        # 1. Check if embeddings table has data
        count_query = f"SELECT COUNT(*) as count FROM {EMBEDDINGS_TABLE}"
        count_result = lakebase.run_query(count_query, database=DATABASE_NAME)
        total_embeddings = count_result[0]['count'] if count_result else 0
        
        if total_embeddings == 0:
            return jsonify({
                'query': query,
                'top_k': top_k,
                'results': [],
                'message': 'No weather embeddings available. Please sync weather alerts first via /alerts/sync'
            }), 200
        
        # 2. Embed the query using the same model used for ingestion
        logger.info(f"Embedding query: '{query}'")
        model = get_embedding_model()
        query_embedding = model.encode(query).tolist()
        
        # 3. Convert embedding to pgvector format (JSON array string)
        import json as _json
        embedding_str = _json.dumps(query_embedding)
        
        # 4. Run cosine similarity search using pgvector's <=> operator
        #    Lower distance = more similar (0 = identical, 2 = opposite)
        search_query = f"""
            SELECT 
                location,
                event,
                chunk_text,
                1 - (embedding <=> %s::vector) AS similarity
            FROM {EMBEDDINGS_TABLE}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        
        results = lakebase.run_query(
            search_query,
            (embedding_str, embedding_str, top_k),
            database=DATABASE_NAME
        )
        
        logger.info(f"Found {len(results)} results for query: '{query}' (total embeddings: {total_embeddings})")
        
        return jsonify({
            'query': query,
            'top_k': top_k,
            'total_available': total_embeddings,
            'results': results
        })
        
    except Exception as e:
        logger.exception("Error during semantic search")
        error_msg = str(e)
        
        # Check for common pgvector errors
        if 'type "vector" does not exist' in error_msg.lower():
            return jsonify({
                'error': 'pgvector extension not enabled',
                'details': f'Run "CREATE EXTENSION vector;" on database {DATABASE_NAME}'
            }), 500
        
        if 'relation' in error_msg.lower() and EMBEDDINGS_TABLE in error_msg:
            return jsonify({
                'error': f'Table {EMBEDDINGS_TABLE} does not exist',
                'details': 'Run the ingestion notebook to create embeddings first'
            }), 500
        
        return jsonify({'error': error_msg}), 500


def _upsert_weather_batch(features: list[dict]) -> int:
    """
    Upsert weather alert features into the weather_information table.
    Normalizes the raw API response into our schema.
    
    Follows the _upsert_news_batch pattern from databricks-lakebase-app-day-2
    """
    import json as _json

    count = 0
    with lakebase.get_connection(database=DATABASE_NAME) as conn:
        with conn.cursor() as cur:
            for feature in features:
                try:
                    props = feature.get("properties", {})
                    area_desc = props.get("areaDesc", "")
                    
                    cur.execute(
                        f"""
                        INSERT INTO {TABLE_NAME} (
                            id, location, source_type, headline, event,
                            narrative_text, issued_at, effective_at, expires_at,
                            payload, synced_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT (id) DO UPDATE
                            SET location = EXCLUDED.location,
                                source_type = EXCLUDED.source_type,
                                headline = EXCLUDED.headline,
                                event = EXCLUDED.event,
                                narrative_text = EXCLUDED.narrative_text,
                                issued_at = EXCLUDED.issued_at,
                                effective_at = EXCLUDED.effective_at,
                                expires_at = EXCLUDED.expires_at,
                                payload = EXCLUDED.payload,
                                synced_at = EXCLUDED.synced_at
                        """,
                        (
                            str(props.get("id", feature.get("id"))),
                            area_desc,
                            "nws_api",
                            props.get("headline"),
                            props.get("event"),
                            props.get("description"),
                            props.get("sent"),
                            props.get("effective"),
                            props.get("expires"),
                            _json.dumps(feature),
                        ),
                    )
                    count += 1
                except Exception as e:
                    logger.error(f"Error upserting alert: {e}")
                    continue
            conn.commit()
    return count


if __name__ == '__main__':
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', 8080))
    app.run(debug=True, host=host, port=port)
    print(f"Flask app running on http://{host}:{port}")