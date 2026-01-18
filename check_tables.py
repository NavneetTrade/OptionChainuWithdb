import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='optionchain',
    user='optionuser',
    password='optionpass123'
)
cursor = conn.cursor()

cursor.execute('SELECT table_name FROM information_schema.tables WHERE table_schema = '\public'\ ORDER BY table_name')
results = cursor.fetchall()

print('Tables in database:')
for row in results:
    print(row[0])

conn.close()
