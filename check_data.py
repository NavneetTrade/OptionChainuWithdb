import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    host='localhost',
    database='optionchain',
    user='optionuser',
    password='optionpass123'
)
cursor = conn.cursor()

cursor.execute('SELECT timestamp, symbol, direction, strength FROM gamma_exposure ORDER BY timestamp DESC LIMIT 5')
results = cursor.fetchall()

print('Latest Gamma Exposure Data:')
for row in results:
    print(f'{row[0]} - {row[1]}: {row[2]} ({row[3]})')

conn.close()
