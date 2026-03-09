import os
from sqlalchemy import create_engine, text


def main() -> None:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://trialai:trialai_password_change_me@localhost:5433/trialai",
    )
    engine = create_engine(database_url)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT document_id, original_filename, status
                     , pass1_overridden, pass2_overridden, pass4_overridden
                FROM derived.document_ingestion_metadata
                ORDER BY ingested_at DESC NULLS LAST
                LIMIT 10
                """
            )
        ).fetchall()
    print("document_ingestion_metadata (top 10):")
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
