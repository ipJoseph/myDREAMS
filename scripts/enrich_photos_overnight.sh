#!/bin/bash
# Photo enrichment - runs in chunks with rest periods to avoid detection
# Run at night when traffic looks more natural

cd /home/bigeug/myDREAMS
source .venv/bin/activate

LOG_FILE="/home/bigeug/myDREAMS/data/photo_enrichment_$(date +%Y%m%d).log"
DB_PATH="/home/bigeug/myDREAMS/data/dreams.db"

# Get starting count
START_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM listings WHERE primary_photo IS NOT NULL")

echo "============================================================" >> "$LOG_FILE"
echo "PHOTO ENRICHMENT OVERNIGHT RUN" >> "$LOG_FILE"
echo "Started: $(date)" >> "$LOG_FILE"
echo "Starting photo count: $START_COUNT" >> "$LOG_FILE"
echo "============================================================" >> "$LOG_FILE"

# Run in chunks of 200, with 10 minute breaks between chunks
CHUNK_SIZE=200
TOTAL_CHUNKS=20  # 200 x 20 = 4000 listings
DELAY_BETWEEN=600  # 10 minutes

for i in $(seq 1 $TOTAL_CHUNKS); do
    echo "" >> "$LOG_FILE"
    echo "------------------------------------------------------------" >> "$LOG_FILE"
    echo "CHUNK $i of $TOTAL_CHUNKS - Started: $(date)" >> "$LOG_FILE"
    echo "------------------------------------------------------------" >> "$LOG_FILE"

    # Count before this chunk
    BEFORE_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM listings WHERE primary_photo IS NOT NULL")

    # Run the enrichment
    python scripts/enrich_photos.py --limit $CHUNK_SIZE >> "$LOG_FILE" 2>&1

    # Count after this chunk
    AFTER_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM listings WHERE primary_photo IS NOT NULL")
    CHUNK_ADDED=$((AFTER_COUNT - BEFORE_COUNT))
    TOTAL_ADDED=$((AFTER_COUNT - START_COUNT))

    echo "" >> "$LOG_FILE"
    echo ">>> BATCH $i STATUS <<<" >> "$LOG_FILE"
    echo "    This batch added: $CHUNK_ADDED photos" >> "$LOG_FILE"
    echo "    Running total added: $TOTAL_ADDED photos" >> "$LOG_FILE"
    echo "    Total listings with photos: $AFTER_COUNT" >> "$LOG_FILE"
    echo "------------------------------------------------------------" >> "$LOG_FILE"

    # Check if we should stop (touch this file to stop gracefully)
    if [ -f "/tmp/stop_photo_enrichment" ]; then
        echo "" >> "$LOG_FILE"
        echo "*** Stop file detected, exiting gracefully ***" >> "$LOG_FILE"
        rm /tmp/stop_photo_enrichment
        break
    fi

    # Check if no more listings need enrichment
    REMAINING=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM listings l JOIN parcels p ON l.parcel_id = p.id WHERE l.primary_photo IS NULL AND l.status = 'ACTIVE' AND p.address IS NOT NULL AND p.address != ''")
    if [ "$REMAINING" -eq 0 ]; then
        echo "" >> "$LOG_FILE"
        echo "*** All eligible listings enriched! ***" >> "$LOG_FILE"
        break
    fi

    # Rest between chunks (except on last chunk)
    if [ $i -lt $TOTAL_CHUNKS ]; then
        echo "Resting for 10 minutes before next batch..." >> "$LOG_FILE"
        sleep $DELAY_BETWEEN
    fi
done

# Final summary
FINAL_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM listings WHERE primary_photo IS NOT NULL")
TOTAL_ADDED=$((FINAL_COUNT - START_COUNT))

echo "" >> "$LOG_FILE"
echo "============================================================" >> "$LOG_FILE"
echo "FINAL SUMMARY" >> "$LOG_FILE"
echo "============================================================" >> "$LOG_FILE"
echo "Completed: $(date)" >> "$LOG_FILE"
echo "Starting count: $START_COUNT" >> "$LOG_FILE"
echo "Final count: $FINAL_COUNT" >> "$LOG_FILE"
echo "Total photos added: $TOTAL_ADDED" >> "$LOG_FILE"
echo "============================================================" >> "$LOG_FILE"
