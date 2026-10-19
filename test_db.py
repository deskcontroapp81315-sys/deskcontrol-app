import psycopg2

# رابط الاتصال الخاص بك من موقع Neon
DATABASE_URL = "postgresql://neondb_owner:npg_Xvi61BfaenmC@ep-purple-thunder-b5gn0ot3-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

try:
    print("جاري الاتصال بقاعدة البيانات السحابية...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # اختبار الاتصال
    cursor.execute("SELECT version();")
    db_version = cursor.fetchone()
    
    print("✅ تم الاتصال بنجاح بقاعدة البيانات السحابية!")
    print("إصدار قاعدة البيانات:", db_version[0])

    cursor.close()
    conn.close()

except Exception as error:
    print("❌ حدث خطأ أثناء الاتصال:", error)